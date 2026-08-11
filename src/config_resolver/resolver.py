"""Orchestrate variable resolution for a Zuul job."""

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
