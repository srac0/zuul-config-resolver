import os

from config_resolver.job_registry import (
    _unwrap_vars,
    build_registry,
    discover_zuul_files,
)
from config_resolver.yaml_loader import OverrideValue


class TestDiscoverZuulFiles:
    def test_finds_zuul_yaml(self, tmp_path):
        (tmp_path / "zuul.yaml").write_text("[]")
        paths = discover_zuul_files(str(tmp_path))
        assert len(paths) == 1
        assert paths[0].endswith("zuul.yaml")

    def test_finds_dot_zuul_yaml(self, tmp_path):
        (tmp_path / ".zuul.yaml").write_text("[]")
        paths = discover_zuul_files(str(tmp_path))
        assert len(paths) == 1
        assert paths[0].endswith(".zuul.yaml")

    def test_finds_zuul_d_files(self, tmp_path):
        d = tmp_path / "zuul.d"
        d.mkdir()
        (d / "jobs.yaml").write_text("[]")
        (d / "nodesets.yaml").write_text("[]")
        paths = discover_zuul_files(str(tmp_path))
        assert len(paths) == 2
        assert paths[0].endswith("jobs.yaml")
        assert paths[1].endswith("nodesets.yaml")

    def test_skips_zuul_ignore(self, tmp_path):
        d = tmp_path / "zuul.d"
        d.mkdir()
        (d / "jobs.yaml").write_text("[]")
        (d / ".zuul.ignore").write_text("")
        paths = discover_zuul_files(str(tmp_path))
        assert paths == []

    def test_skips_non_yaml_files(self, tmp_path):
        d = tmp_path / "zuul.d"
        d.mkdir()
        (d / "jobs.yaml").write_text("[]")
        (d / "README.md").write_text("docs")
        (d / "script.py").write_text("pass")
        paths = discover_zuul_files(str(tmp_path))
        assert len(paths) == 1

    def test_finds_yml_extension(self, tmp_path):
        d = tmp_path / "zuul.d"
        d.mkdir()
        (d / "jobs.yml").write_text("[]")
        paths = discover_zuul_files(str(tmp_path))
        assert len(paths) == 1

    def test_empty_repo(self, tmp_path):
        paths = discover_zuul_files(str(tmp_path))
        assert paths == []


class TestUnwrapVars:
    def test_plain_vars_unchanged(self):
        raw = {"a": 1, "b": "hello"}
        clean, overrides = _unwrap_vars(raw)
        assert clean == {"a": 1, "b": "hello"}
        assert overrides == {}

    def test_override_value_unwrapped(self):
        raw = {"config": OverrideValue({"x": 1}, override=True)}
        clean, overrides = _unwrap_vars(raw)
        assert clean == {"config": {"x": 1}}
        assert overrides == {"config": True}

    def test_inherit_value_unwrapped(self):
        raw = {"config": OverrideValue({"x": 1}, override=False)}
        clean, overrides = _unwrap_vars(raw)
        assert clean == {"config": {"x": 1}}
        assert overrides == {"config": False}

    def test_mixed_vars(self):
        raw = {
            "plain": "value",
            "tagged": OverrideValue([1, 2], override=True),
        }
        clean, overrides = _unwrap_vars(raw)
        assert clean == {"plain": "value", "tagged": [1, 2]}
        assert overrides == {"tagged": True}


class TestBuildRegistry:
    def test_parses_minimal_job(self, tmp_path):
        d = tmp_path / "zuul.d"
        d.mkdir()
        (d / "jobs.yaml").write_text(
            "- job:\n    name: my-job\n    vars:\n      foo: bar\n"
        )
        registry = build_registry([str(tmp_path)])
        assert "my-job" in registry
        job = registry["my-job"]
        assert job.name == "my-job"
        assert job.vars == {"foo": "bar"}
        assert job.parent is None

    def test_extracts_parent(self, tmp_path):
        d = tmp_path / "zuul.d"
        d.mkdir()
        (d / "jobs.yaml").write_text(
            "- job:\n    name: child-job\n    parent: parent-job\n"
        )
        registry = build_registry([str(tmp_path)])
        assert registry["child-job"].parent == "parent-job"

    def test_extracts_include_vars(self, tmp_path):
        d = tmp_path / "zuul.d"
        d.mkdir()
        (d / "jobs.yaml").write_text(
            "- job:\n"
            "    name: my-job\n"
            "    include-vars:\n"
            "      - name: vars/extra.yaml\n"
            "      - name: vars/more.yaml\n"
        )
        registry = build_registry([str(tmp_path)])
        assert registry["my-job"].include_vars == [
            "vars/extra.yaml",
            "vars/more.yaml",
        ]

    def test_handles_job_with_no_vars(self, tmp_path):
        d = tmp_path / "zuul.d"
        d.mkdir()
        (d / "jobs.yaml").write_text("- job:\n    name: bare-job\n")
        registry = build_registry([str(tmp_path)])
        assert registry["bare-job"].vars == {}

    def test_skips_non_job_entries(self, tmp_path):
        d = tmp_path / "zuul.d"
        d.mkdir()
        (d / "mixed.yaml").write_text(
            "- nodeset:\n"
            "    name: my-nodeset\n"
            "    nodes: []\n"
            "- project-template:\n"
            "    name: my-template\n"
            "- job:\n"
            "    name: real-job\n"
        )
        registry = build_registry([str(tmp_path)])
        assert len(registry) == 1
        assert "real-job" in registry

    def test_records_source_file(self, tmp_path):
        d = tmp_path / "zuul.d"
        d.mkdir()
        (d / "deploy-jobs.yaml").write_text("- job:\n    name: my-job\n")
        registry = build_registry([str(tmp_path)])
        expected = os.path.join("zuul.d", "deploy-jobs.yaml")
        assert registry["my-job"].source_file == expected

    def test_handles_abstract_and_final(self, tmp_path):
        d = tmp_path / "zuul.d"
        d.mkdir()
        (d / "jobs.yaml").write_text(
            "- job:\n"
            "    name: base-job\n"
            "    abstract: true\n"
            "- job:\n"
            "    name: leaf-job\n"
            "    final: true\n"
        )
        registry = build_registry([str(tmp_path)])
        assert registry["base-job"].abstract is True
        assert registry["base-job"].final is False
        assert registry["leaf-job"].final is True
        assert registry["leaf-job"].abstract is False

    def test_unwraps_override_in_vars(self, tmp_path):
        d = tmp_path / "zuul.d"
        d.mkdir()
        (d / "jobs.yaml").write_text(
            "- job:\n"
            "    name: override-job\n"
            "    vars:\n"
            "      config: !override\n"
            "        a: 1\n"
        )
        registry = build_registry([str(tmp_path)])
        job = registry["override-job"]
        assert job.vars == {"config": {"a": 1}}
        assert job.vars_override_control == {"config": True}

    def test_multiple_files(self, tmp_path):
        d = tmp_path / "zuul.d"
        d.mkdir()
        (d / "a.yaml").write_text("- job:\n    name: job-a\n")
        (d / "b.yaml").write_text("- job:\n    name: job-b\n")
        registry = build_registry([str(tmp_path)])
        assert "job-a" in registry
        assert "job-b" in registry


class TestBuildRegistryMultiRepo:
    """Test build_registry with multiple repo directories."""

    def test_combines_jobs_from_two_repos(self, tmp_path):
        repo_a = tmp_path / "repo_a"
        repo_b = tmp_path / "repo_b"
        for r in (repo_a, repo_b):
            (r / "zuul.d").mkdir(parents=True)
        (repo_a / "zuul.d" / "jobs.yaml").write_text(
            "- job:\n    name: job-a\n    vars:\n      key: from_a\n"
        )
        (repo_b / "zuul.d" / "jobs.yaml").write_text(
            "- job:\n    name: job-b\n    vars:\n      key: from_b\n"
        )
        registry = build_registry([str(repo_a), str(repo_b)])
        assert "job-a" in registry
        assert "job-b" in registry
        assert registry["job-a"].repo_dir == str(repo_a)
        assert registry["job-b"].repo_dir == str(repo_b)

    def test_last_repo_wins_on_duplicate(self, tmp_path):
        repo_a = tmp_path / "repo_a"
        repo_b = tmp_path / "repo_b"
        for r in (repo_a, repo_b):
            (r / "zuul.d").mkdir(parents=True)
        (repo_a / "zuul.d" / "jobs.yaml").write_text(
            "- job:\n    name: dupe\n    vars:\n      v: from_a\n"
        )
        (repo_b / "zuul.d" / "jobs.yaml").write_text(
            "- job:\n    name: dupe\n    vars:\n      v: from_b\n"
        )
        registry = build_registry([str(repo_a), str(repo_b)])
        assert registry["dupe"].vars["v"] == "from_b"
        assert registry["dupe"].repo_dir == str(repo_b)

    def test_repo_dir_stored_on_job(self, tmp_path):
        d = tmp_path / "zuul.d"
        d.mkdir()
        (d / "jobs.yaml").write_text("- job:\n    name: my-job\n")
        registry = build_registry([str(tmp_path)])
        assert registry["my-job"].repo_dir == str(tmp_path)

    def test_empty_repo_skipped(self, tmp_path):
        repo_a = tmp_path / "repo_a"
        repo_b = tmp_path / "repo_b"
        repo_a.mkdir()
        (repo_b / "zuul.d").mkdir(parents=True)
        (repo_b / "zuul.d" / "jobs.yaml").write_text(
            "- job:\n    name: only-job\n"
        )
        registry = build_registry([str(repo_a), str(repo_b)])
        assert len(registry) == 1
        assert "only-job" in registry
