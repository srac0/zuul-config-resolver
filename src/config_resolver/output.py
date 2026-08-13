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


def write_diff_vars(diff_result, output_path):
    """Write per-job diff result to a YAML file."""
    with open(output_path, "w") as f:
        yaml.dump(
            diff_result,
            f,
            default_flow_style=False,
            sort_keys=True,
            allow_unicode=True,
        )


def format_diff(diff_result):
    """Return human-readable lines summarizing a per-job diff."""
    if not diff_result:
        return ["No variable changes detected."]

    lines = []
    added = {k: v for k, v in diff_result.items() if v["status"] == "added"}
    removed = {
        k: v for k, v in diff_result.items() if v["status"] == "removed"
    }
    changed = {
        k: v for k, v in diff_result.items() if v["status"] == "changed"
    }

    if added:
        lines.append(f"Added jobs ({len(added)}):")
        for name in sorted(added):
            var_count = len(added[name].get("vars", {}))
            lines.append(f"  + {name}  ({var_count} vars)")
        lines.append("")

    if removed:
        lines.append(f"Removed jobs ({len(removed)}):")
        for name in sorted(removed):
            var_count = len(removed[name].get("vars", {}))
            lines.append(f"  - {name}  ({var_count} vars)")
        lines.append("")

    if changed:
        lines.append(f"Changed jobs ({len(changed)}):")
        for name in sorted(changed):
            lines.append(f"  ~ {name}")
            diff = changed[name]["diff"]
            _format_diff_detail(diff, lines)
        lines.append("")

    return lines


def _format_diff_detail(diff, lines):
    """Append human-readable details for a single job's diff."""
    if "values_changed" in diff:
        for path, change in sorted(diff["values_changed"].items()):
            key = _simplify_path(path)
            old = change.get("old_value", "?")
            new = change.get("new_value", "?")
            lines.append(f"      {key}:")
            lines.append(f"        was: {old}")
            lines.append(f"        now: {new}")

    if "dictionary_item_added" in diff:
        for path in sorted(diff["dictionary_item_added"]):
            key = _simplify_path(path)
            lines.append(f"      + {key}")

    if "dictionary_item_removed" in diff:
        for path in sorted(diff["dictionary_item_removed"]):
            key = _simplify_path(path)
            lines.append(f"      - {key}")

    if "type_changes" in diff:
        for path, change in sorted(diff["type_changes"].items()):
            key = _simplify_path(path)
            old = change.get("old_value", "?")
            new = change.get("new_value", "?")
            lines.append(f"      {key} (type changed):")
            lines.append(f"        was: {old}")
            lines.append(f"        now: {new}")


def _simplify_path(path):
    """Turn DeepDiff paths like root['key']['sub'] into key.sub."""
    path = path.removeprefix("root").replace("['", ".").replace("']", "")
    return path.lstrip(".")


def show_diff(diff_result):
    """Print a human-readable diff summary to stdout."""
    for line in format_diff(diff_result):
        print(line)


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
