"""Parse Zuul config files and build a registry of job definitions."""

import os
from dataclasses import dataclass, field

from config_resolver.yaml_loader import OverrideValue, load_yaml


@dataclass
class JobDefinition:
    name: str
    parent: str | None = None
    vars: dict = field(default_factory=dict)
    vars_override_control: dict = field(default_factory=dict)
    extra_vars: dict = field(default_factory=dict)
    extra_vars_override_control: dict = field(default_factory=dict)
    host_vars: dict = field(default_factory=dict)
    group_vars: dict = field(default_factory=dict)
    include_vars: list = field(default_factory=list)
    source_file: str = ""
    repo_dir: str = ""
    abstract: bool = False
    final: bool = False


def _unwrap_vars(raw_vars):
    """Separate OverrideValue wrappers from a vars dict.

    Returns (clean_vars, overrides) where clean_vars has raw values
    and overrides maps keys with explicit tags to their override
    boolean.
    """
    clean = {}
    overrides = {}
    for key, value in raw_vars.items():
        if isinstance(value, OverrideValue):
            clean[key] = value.value
            overrides[key] = value.override
        else:
            clean[key] = value
    return clean, overrides


def _parse_job(job_data, repo_dir, source_file):
    """Convert a raw job dict into a JobDefinition."""
    clean_vars, vars_override_control = _unwrap_vars(job_data.get("vars", {}))
    clean_extra_vars, extra_vars_override_control = _unwrap_vars(
        job_data.get("extra-vars", {})
    )

    include_vars = []
    for entry in job_data.get("include-vars", []):
        if isinstance(entry, str):
            include_vars.append(entry)
        elif isinstance(entry, dict) and "name" in entry:
            include_vars.append(entry["name"])

    return JobDefinition(
        name=job_data["name"],
        parent=job_data.get("parent"),
        vars=clean_vars,
        extra_vars=clean_extra_vars,
        extra_vars_override_control=extra_vars_override_control,
        host_vars=job_data.get("host-vars", {}),
        group_vars=job_data.get("group-vars", {}),
        include_vars=include_vars,
        vars_override_control=vars_override_control,
        repo_dir=repo_dir,
        source_file=source_file,
        abstract=job_data.get("abstract", False),
        final=job_data.get("final", False),
    )


def discover_zuul_files(repo_dir):
    """Find all Zuul config files in a repo directory.

    Checks zuul.yaml, .zuul.yaml, zuul.d/, and .zuul.d/.
    Skips directories containing a .zuul.ignore sentinel file.
    """
    paths = []

    for filename in ("zuul.yaml", ".zuul.yaml"):
        filepath = os.path.join(repo_dir, filename)
        if os.path.isfile(filepath):
            paths.append(filepath)

    for dirname in ("zuul.d", ".zuul.d"):
        dirpath = os.path.join(repo_dir, dirname)
        if not os.path.isdir(dirpath):
            continue
        for root, _, files in os.walk(dirpath):
            if ".zuul.ignore" in files:
                continue
            for f in sorted(files):
                if f.endswith((".yaml", ".yml")):
                    paths.append(os.path.join(root, f))

    return paths


def build_registry(repo_dirs):
    """Parse all Zuul config files and return a dict of job definitions.

    Returns dict[str, JobDefinition] keyed by job name.
    Non-job entries (nodesets, project-templates, etc.) are skipped.
    """
    registry = {}

    for repo_dir in repo_dirs:
        for filepath in discover_zuul_files(repo_dir):
            rel_path = os.path.relpath(filepath, repo_dir)
            docs = load_yaml(filepath)
            for doc in docs:
                if not isinstance(doc, list):
                    continue
                for item in doc:
                    if not isinstance(item, dict):
                        continue
                    if "job" not in item:
                        continue
                    job_data = item["job"]
                    if (
                        not isinstance(job_data, dict)
                        or "name" not in job_data
                    ):
                        continue
                    job = _parse_job(job_data, repo_dir, rel_path)
                    registry[job.name] = job

    return registry
