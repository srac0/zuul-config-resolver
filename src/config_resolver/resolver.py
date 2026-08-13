"""Orchestrate variable resolution for a Zuul job."""

import contextlib
import os
import subprocess
import tempfile

from deepdiff import DeepDiff

from config_resolver.job_registry import build_registry
from config_resolver.parent_walker import resolve_parents


class Resolver:
    """Resolve Zuul job variables across one or more repo directories."""

    def __init__(self, repo_dirs) -> None:
        if not isinstance(repo_dirs, list):
            raise TypeError(
                f"repo_dirs must be a list, got {type(repo_dirs).__name__}"
            )
        self.registry = build_registry(repo_dirs)

    def resolve_job(self, job_name):
        """Return (merged_vars, vars_sources, parent_chain) for a job."""
        return resolve_parents(job_name, self.registry)


def _run_git(*args, cwd=None, timeout=30):
    """Run a git command, stripping inherited GIT_* env vars."""
    env = {
        k: v
        for k, v in os.environ.items()
        if not k.startswith("GIT_")
        or k
        in {
            "GIT_SSH",
            "GIT_SSH_COMMAND",
            "GIT_EXEC_PATH",
            "GIT_SSL_CAINFO",
        }
    }
    return subprocess.run(
        ("git", *args),
        capture_output=True,
        text=True,
        check=True,
        cwd=cwd,
        timeout=timeout,
        env=env,
    )


def _diff_registries(current_resolver, ref_resolver):
    """Compute per-job variable diffs between two resolvers."""
    all_jobs = sorted(
        set(current_resolver.registry) | set(ref_resolver.registry)
    )
    result = {}

    for job_name in all_jobs:
        in_current = job_name in current_resolver.registry
        in_ref = job_name in ref_resolver.registry

        if not in_current:
            ref_vars, _, _ = ref_resolver.resolve_job(job_name)
            result[job_name] = {"status": "removed", "vars": ref_vars}
            continue

        if not in_ref:
            cur_vars, _, _ = current_resolver.resolve_job(job_name)
            result[job_name] = {"status": "added", "vars": cur_vars}
            continue

        cur_vars, _, _ = current_resolver.resolve_job(job_name)
        ref_vars, _, _ = ref_resolver.resolve_job(job_name)
        diff = DeepDiff(ref_vars, cur_vars, ignore_order=True)
        if diff:
            result[job_name] = {
                "status": "changed",
                "diff": diff.to_dict(),
            }

    return result


def compute_diff(repo_dir, ref):
    """Compare resolved variables between the working tree and a ref.

    Creates a temporary git worktree at the given ref, resolves every
    job on both sides, and returns a per-job diff of the results.
    """
    current_resolver = Resolver([repo_dir])

    with tempfile.TemporaryDirectory() as tmp_dir:
        worktree_path = os.path.join(tmp_dir, "worktree")
        _run_git(
            "worktree",
            "add",
            "--detach",
            worktree_path,
            ref,
            cwd=repo_dir,
        )
        try:
            ref_resolver = Resolver([worktree_path])
            result = _diff_registries(current_resolver, ref_resolver)
        finally:
            with contextlib.suppress(subprocess.CalledProcessError):
                _run_git(
                    "worktree",
                    "remove",
                    "--force",
                    worktree_path,
                    cwd=repo_dir,
                )

    return result
