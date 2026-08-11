"""Walk the Zuul job parent chain and deep-merge variables."""

import os
import warnings

from config_resolver.merge import deep_update
from config_resolver.yaml_loader import load_yaml


def walk_parents(job_name, registry):
    """Build the parent chain from root to leaf.

    Follows parent links from leaf to root, then reverses so the root
    job is first. Warns if a parent is not found in the registry; it
    may live in a different repo (use --repo-dir to include it).
    Raises ValueError on circular parent references.
    """
    parent_chain = []
    current = job_name
    visited = set()

    while current:
        if current in visited:
            raise ValueError(f"Circular parent reference: {current}")
        visited.add(current)

        job = registry.get(current)
        if job is None:
            warnings.warn(
                f"Parent job '{current}' not found in registry, "
                "it may live in a different repo",
                stacklevel=2,
            )
            break

        parent_chain.append(job)
        current = job.parent

    parent_chain.reverse()
    return parent_chain


def _load_include_vars(repo_dir, include_path):
    """Load include-vars file and return a dict."""
    include_vars = {}
    full_path = os.path.join(repo_dir, include_path)
    if not os.path.isfile(full_path):
        warnings.warn(
            f"Include-vars file not found: {full_path}",
            stacklevel=2,
        )
        return {}
    docs = load_yaml(full_path)
    for doc in docs:
        if isinstance(doc, dict):
            include_vars.update(doc)
    return include_vars


def _merge_vars_layer(
    accumulated,
    sources,
    entries,
    override_control,
    source_file,
    job_name,
    repo_dir,
):
    """Merge one layer of variables into the accumulator with tracking."""
    for key, value in entries.items():
        if override_control.get(key) is True:
            accumulated[key] = value
        elif isinstance(accumulated.get(key), dict) and isinstance(
            value, dict
        ):
            accumulated[key] = deep_update(accumulated[key], value)
        else:
            accumulated[key] = value

        selected_entry = {
            "file": source_file,
            "job_name": job_name,
            "repo_dir": repo_dir,
            "value": accumulated[key],
        }
        historical_entry = {
            "file": source_file,
            "job_name": job_name,
            "repo_dir": repo_dir,
            "value": value,
        }
        if key not in sources:
            sources[key] = {
                "selected": selected_entry,
                "history": [historical_entry],
            }
        else:
            sources[key]["selected"] = selected_entry
            sources[key]["history"].append(historical_entry)


def merge_parent_chain(parent_chain):
    """Deep-merge vars and extra-vars through the parent chain.

    Extra-vars are merged separately, then applied on top of vars
    with dict.update(), matching Zuul's squash_variables.
    """
    merged_vars = {}
    vars_sources = {}

    for job in parent_chain:
        for include_path in job.include_vars:
            include_vars = _load_include_vars(job.repo_dir, include_path)
            _merge_vars_layer(
                merged_vars,
                vars_sources,
                include_vars,
                {},
                include_path,
                job.name,
                job.repo_dir,
            )

        _merge_vars_layer(
            merged_vars,
            vars_sources,
            job.vars,
            job.vars_override_control,
            job.source_file,
            job.name,
            job.repo_dir,
        )

    merged_extra = {}
    extra_sources = {}

    for job in parent_chain:
        _merge_vars_layer(
            merged_extra,
            extra_sources,
            job.extra_vars,
            job.extra_vars_override_control,
            job.source_file,
            job.name,
            job.repo_dir,
        )

    for key, value in merged_extra.items():
        merged_vars[key] = value
        entry = extra_sources[key]
        if key in vars_sources:
            vars_sources[key]["selected"] = entry["selected"]
            vars_sources[key]["history"].extend(entry["history"])
        else:
            vars_sources[key] = entry

    return merged_vars, vars_sources


def resolve_parents(job_name, registry):
    """Walk the parent chain and return merged vars.

    Returns (merged_vars, vars_sources, parent_chain) where vars_sources
    maps each variable key to its source tracking dict and parent_chain
    is the list of JobDefinition objects from root to leaf.
    """
    parent_chain = walk_parents(job_name, registry)
    merged_vars, vars_sources = merge_parent_chain(parent_chain)
    return merged_vars, vars_sources, parent_chain
