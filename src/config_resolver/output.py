"""Write resolved variables and source tracking to YAML files."""

import json
import os

import yaml


def list_jobs(resolver):
    """Print all registered job names, sorted alphabetically."""
    jobs = sorted(resolver.registry.keys())
    print(f"Found {len(jobs)} jobs")
    for job in jobs:
        print(f"  {job}")


def write_resolved_vars(merged_vars, output_path):
    """Write merged variables to a YAML file, usable with -e @file."""
    with open(output_path, "w") as f:
        yaml.dump(
            merged_vars,
            f,
            default_flow_style=False,
            sort_keys=False,
            allow_unicode=True,
        )


def write_sources(sources, output_path):
    """Write source tracking dict to a YAML file."""
    with open(output_path, "w") as f:
        yaml.dump(
            sources,
            f,
            default_flow_style=False,
            sort_keys=True,
            allow_unicode=True,
        )


def format_overrides(vars_sources):
    """Return a list of human-readable override summary lines."""
    lines = []
    for key, entry in vars_sources.items():
        history = entry["history"]
        if len(history) < 2:
            continue
        labels = [
            f"{h['job_name']} ({os.path.basename(h['file'])})"
            for h in reversed(history)
        ]
        count = len(history) - 1
        suffix = "s" if count > 1 else ""
        lines.append(
            f"{key} ({count} override{suffix}): {' <- '.join(labels)}"
        )
    return lines


def show_overrides(vars_sources):
    """Print overridden variables to stdout."""
    for line in format_overrides(vars_sources):
        print(line)


def _unique_values(values):
    elements = set()
    for element in values:
        if isinstance(element, (dict, list)):
            elements.add(json.dumps(element, sort_keys=True))
        else:
            elements.add(element)
    return elements


def format_conflicts(vars_sources):
    """Return override summary lines for variables with differing values."""
    lines = []
    for key, entry in vars_sources.items():
        history = list(reversed(entry["history"]))
        if len(history) < 2:
            continue
        values = [h["value"] for h in history]
        if len(_unique_values(values)) == 1:
            continue
        labels = [f" [{h['value']}] ({h['job_name']})" for h in history]
        count = len(history) - 1
        suffix = "s" if count > 1 else ""
        lines.append(
            f"{key} ({count} override{suffix}): {' <- '.join(labels)}"
        )
    return lines


def show_conflicts(vars_sources):
    """Print overridden variables with conflicts to stdout."""
    lines = format_conflicts(vars_sources)
    if lines:
        print("<variable> (x override):  [<value>] (<job_name>)")
    for line in lines:
        print(line)


def format_parents(parent_chain):
    """Return lines showing each parent with source file and var count."""
    lines = []
    for i, job in enumerate(parent_chain):
        indent = "  " * i
        var_count = len(job.vars)
        extra_count = len(job.extra_vars)
        include_count = len(job.include_vars)

        parts = []
        if var_count:
            parts.append(f"{var_count} vars")
        if extra_count:
            parts.append(f"{extra_count} extra-vars")
        if include_count:
            parts.append(f"{include_count} include-vars")

        detail = ", ".join(parts) if parts else "no vars"
        lines.append(f"{indent}{job.name} ({job.source_file}, {detail})")
    return lines


def show_parents(parent_chain):
    """Print the parent chain with per-job detail to stdout."""
    for line in format_parents(parent_chain):
        print(line)
