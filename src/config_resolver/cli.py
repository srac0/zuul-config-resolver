"""Command-line interface for config-resolver."""

import argparse
import os
import sys

import yaml

from config_resolver import __version__
from config_resolver.output import (
    list_jobs,
    show_conflicts,
    show_overrides,
    show_parents,
    write_resolved_vars,
    write_sources,
)
from config_resolver.resolver import Resolver


def _run(args):
    if args.config:
        with open(args.config) as f:
            repo_dirs = yaml.safe_load(f)["repos"]
    else:
        repo_dirs = list(args.repo_dir) if args.repo_dir else []

        cwd = os.path.realpath(os.getcwd())
        if cwd not in [os.path.realpath(d) for d in repo_dirs]:
            repo_dirs.insert(0, cwd)

    resolver = Resolver(repo_dirs)

    if args.list_jobs:
        list_jobs(resolver)
        return 0

    if not args.job_name:
        print("error: job_name is required", file=sys.stderr)
        return 2

    merged_vars, vars_sources, parent_chain = resolver.resolve_job(
        args.job_name
    )

    if not parent_chain:
        print(f"Job '{args.job_name}' not found in registry.", file=sys.stderr)
        return 1

    if args.show_parents:
        show_parents(parent_chain)

    if args.verbose:
        print(f"Resolved {len(merged_vars)} variables")
        print(f"Chain: {' -> '.join(j.name for j in parent_chain)}")

    os.makedirs(args.output_dir, exist_ok=True)

    vars_path = os.path.join(args.output_dir, "resolved-vars.yaml")
    write_resolved_vars(merged_vars, vars_path)
    print(f"Wrote {vars_path}")

    sources_path = os.path.join(args.output_dir, "resolved-vars-sources.yaml")
    write_sources(vars_sources, sources_path)
    print(f"Wrote {sources_path}")

    if args.show_overrides:
        show_overrides(vars_sources)

    if args.show_conflicts:
        show_conflicts(vars_sources)

    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="config-resolver",
        description="Resolve Zuul job variables through the parent chain.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    parser.add_argument("job_name", nargs="?", help="Zuul job name to resolve")
    parser.add_argument(
        "--config",
        help="Path to config file listing repo directories.",
    )
    parser.add_argument(
        "--repo-dir",
        action="append",
        help=(
            "Path to an additional Zuul repo to scan. "
            "cwd is always included automatically. "
            "Pass multiple times for cross-repo resolution "
            "(e.g. --repo-dir ./zuul-jobs "
            "--repo-dir ./project-config)."
        ),
    )
    parser.add_argument(
        "--output-dir",
        default=".",
        help="Directory for output files (default: cwd)",
    )
    parser.add_argument(
        "--list-jobs",
        action="store_true",
        help="List all jobs found in the given repo(s) and exit",
    )
    parser.add_argument(
        "--show-parents",
        action="store_true",
        help="Print each parent with source file and var counts",
    )
    parser.add_argument(
        "--show-overrides",
        action="store_true",
        help="Show the list of overridden variables",
    )
    parser.add_argument(
        "--show-conflicts",
        action="store_true",
        help="Show the list of overridden variables with conflicts",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print extra info during resolution",
    )

    args = parser.parse_args(argv)
    return _run(args)
