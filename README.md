# Zuul Config Resolver

Diagnostic tool for static Zuul variable resolution. Takes a job name, walks the parent inheritance chain across multiple repos, collects variables from `job.vars`, `job.extra-vars`, and `include-vars` files, deep-merges them (honoring `!override`/`!inherit` YAML tags), and outputs resolved variables with full provenance tracking. It also detects variable conflicts that Zuul resolves silently.

## Installation

Install as a standalone CLI tool with [uv](https://docs.astral.sh/uv/):

```bash
uv tool install git+https://github.com/srac0/zuul-config-resolver
```

Or install from a local clone:

```bash
git clone https://github.com/srac0/zuul-config-resolver.git
cd zuul-config-resolver
uv tool install .
```

After installation, `config-resolver` is available on your `PATH`.

For development:

```bash
git clone https://github.com/srac0/zuul-config-resolver.git
cd zuul-config-resolver
uv sync
pre-commit install
```

## Usage

### Resolve a job

Clone the Zuul job repos side by side, then point `config-resolver` at them. When run from inside a Zuul repo, it uses the current directory by default.

```bash
config-resolver my-deploy-job
```

For multi-repo resolution, pass `--repo-dir` flags or use a config file:

```bash
config-resolver \
  --repo-dir ../zuul-jobs \
  --repo-dir ../project-config \
  my-deploy-job
```

Or with a config file:

```yaml
# repos.yaml
repos:
  - ../zuul-jobs
  - ../project-config
```

```bash
config-resolver --config repos.yaml my-deploy-job
```

This writes two files to the current directory (override with `--output-dir`):

- `resolved-vars.yaml` - all merged variables, ready for `ansible-playbook -e @resolved-vars.yaml`
- `resolved-vars-sources.yaml` - maps each variable to its source file, job name, and merge history

### Show conflicts

Find variables where a child job silently overrides a parent's value:

```bash
config-resolver --config repos.yaml --show-conflicts my-deploy-job
```

```
log_level (1 override):
  [debug] (my-deploy-job) <- [info] (base-deploy-job)
retry_count (1 override):
  [5] (my-deploy-job) <- [3] (base-deploy-job)
```

### Show overrides

List all variables that are set at more than one level in the chain, even when the value stays the same:

```bash
config-resolver --config repos.yaml --show-overrides my-deploy-job
```

### Inspect the parent chain

See each parent job with its source file and variable counts:

```bash
config-resolver --config repos.yaml --show-parents my-deploy-job
```

### List all jobs

```bash
config-resolver --config repos.yaml --list-jobs
```

### Help

```bash
config-resolver --help
```

## Development

Without installing, use `uv run` to run the tool from a local checkout:

```bash
uv run config-resolver --list-jobs
```

### Tests

```bash
uv run pytest
```

### Lint and format

```bash
pre-commit run --all-files
```
