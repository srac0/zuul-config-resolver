import subprocess

import pytest

from config_resolver.resolver import Resolver, compute_diff


class TestResolverSynthetic:
    """Test the Resolver with synthetic job definitions."""

    def test_simple_two_job_chain(self, tmp_path):
        d = tmp_path / "zuul.d"
        d.mkdir()
        (d / "jobs.yaml").write_text(
            "- job:\n"
            "    name: parent\n"
            "    vars:\n"
            "      a: 1\n"
            "      config:\n"
            "        x: 10\n"
            "- job:\n"
            "    name: child\n"
            "    parent: parent\n"
            "    vars:\n"
            "      b: 2\n"
            "      config:\n"
            "        y: 20\n"
        )
        resolver = Resolver([str(tmp_path)])
        merged_vars, _, parent_chain = resolver.resolve_job("child")
        assert merged_vars["a"] == 1
        assert merged_vars["b"] == 2
        assert merged_vars["config"] == {"x": 10, "y": 20}
        assert [j.name for j in parent_chain] == ["parent", "child"]

    def test_override_replaces_entire_dict(self, tmp_path):
        d = tmp_path / "zuul.d"
        d.mkdir()
        (d / "jobs.yaml").write_text(
            "- job:\n"
            "    name: parent\n"
            "    vars:\n"
            "      config:\n"
            "        a: 1\n"
            "        b: 2\n"
            "- job:\n"
            "    name: child\n"
            "    parent: parent\n"
            "    vars:\n"
            "      config: !override\n"
            "        b: 3\n"
        )
        resolver = Resolver([str(tmp_path)])
        merged_vars, _, _ = resolver.resolve_job("child")
        assert merged_vars["config"] == {"b": 3}
        assert "a" not in merged_vars["config"]

    def test_include_vars_loaded(self, tmp_path):
        d = tmp_path / "zuul.d"
        d.mkdir()
        v = tmp_path / "vars"
        v.mkdir()
        (v / "extra.yaml").write_text("extra_key: extra_value\n")
        (d / "jobs.yaml").write_text(
            "- job:\n"
            "    name: my-job\n"
            "    include-vars:\n"
            "      - name: vars/extra.yaml\n"
            "    vars:\n"
            "      own_key: own_value\n"
        )
        resolver = Resolver([str(tmp_path)])
        merged_vars, _, _ = resolver.resolve_job("my-job")
        assert merged_vars["extra_key"] == "extra_value"
        assert merged_vars["own_key"] == "own_value"

    def test_job_vars_override_include_vars(self, tmp_path):
        d = tmp_path / "zuul.d"
        d.mkdir()
        v = tmp_path / "vars"
        v.mkdir()
        (v / "defaults.yaml").write_text("shared: from_include\n")
        (d / "jobs.yaml").write_text(
            "- job:\n"
            "    name: my-job\n"
            "    include-vars:\n"
            "      - name: vars/defaults.yaml\n"
            "    vars:\n"
            "      shared: from_job\n"
        )
        resolver = Resolver([str(tmp_path)])
        merged_vars, _, _ = resolver.resolve_job("my-job")
        assert merged_vars["shared"] == "from_job"

    def test_sources_through_resolver(self, tmp_path):
        d = tmp_path / "zuul.d"
        d.mkdir()
        (d / "jobs.yaml").write_text(
            "- job:\n"
            "    name: parent\n"
            "    vars:\n"
            "      shared: from_parent\n"
            "      parent_only: 1\n"
            "- job:\n"
            "    name: child\n"
            "    parent: parent\n"
            "    vars:\n"
            "      shared: from_child\n"
            "      child_only: 2\n"
        )
        resolver = Resolver([str(tmp_path)])
        _, sources, _ = resolver.resolve_job("child")
        assert sources["shared"]["selected"]["value"] == "from_child"
        assert sources["shared"]["selected"]["job_name"] == "child"
        assert len(sources["shared"]["history"]) == 2
        assert sources["parent_only"]["selected"]["job_name"] == "parent"
        assert sources["child_only"]["selected"]["job_name"] == "child"

    def test_jinja_templates_preserved(self, tmp_path):
        d = tmp_path / "zuul.d"
        d.mkdir()
        (d / "jobs.yaml").write_text(
            "- job:\n"
            "    name: my-job\n"
            "    vars:\n"
            '      basedir: "{{ ansible_user_dir }}/data"\n'
        )
        resolver = Resolver([str(tmp_path)])
        merged_vars, _, _ = resolver.resolve_job("my-job")
        assert "{{ ansible_user_dir }}" in merged_vars["basedir"]

    def test_extra_vars_through_resolver(self, tmp_path):
        d = tmp_path / "zuul.d"
        d.mkdir()
        (d / "jobs.yaml").write_text(
            "- job:\n"
            "    name: parent\n"
            "    vars:\n"
            "      shared: from_vars\n"
            "      vars_only: 1\n"
            "- job:\n"
            "    name: child\n"
            "    parent: parent\n"
            "    extra-vars:\n"
            "      shared: from_extra\n"
            "      extra_only: 2\n"
        )
        resolver = Resolver([str(tmp_path)])
        merged, sources, _ = resolver.resolve_job("child")
        assert merged["shared"] == "from_extra"
        assert merged["vars_only"] == 1
        assert merged["extra_only"] == 2
        assert sources["shared"]["selected"]["value"] == "from_extra"
        assert len(sources["shared"]["history"]) == 2


class TestResolverMultiRepo:
    """Test Resolver with multiple repos."""

    def test_cross_repo_inheritance(self, tmp_path):
        repo_a = tmp_path / "repo_a"
        repo_b = tmp_path / "repo_b"
        for r in (repo_a, repo_b):
            (r / "zuul.d").mkdir(parents=True)
        (repo_a / "zuul.d" / "jobs.yaml").write_text(
            "- job:\n    name: base-job\n    vars:\n      from_a: 1\n"
        )
        (repo_b / "zuul.d" / "jobs.yaml").write_text(
            "- job:\n"
            "    name: child-job\n"
            "    parent: base-job\n"
            "    vars:\n"
            "      from_b: 2\n"
        )
        resolver = Resolver([str(repo_a), str(repo_b)])
        merged, sources, chain = resolver.resolve_job("child-job")
        assert merged["from_a"] == 1
        assert merged["from_b"] == 2
        assert [j.name for j in chain] == ["base-job", "child-job"]
        assert sources["from_a"]["selected"]["repo_dir"] == str(repo_a)
        assert sources["from_b"]["selected"]["repo_dir"] == str(repo_b)

    def test_last_repo_wins_duplicate_job(self, tmp_path):
        repo_a = tmp_path / "repo_a"
        repo_b = tmp_path / "repo_b"
        for r in (repo_a, repo_b):
            (r / "zuul.d").mkdir(parents=True)
        (repo_a / "zuul.d" / "jobs.yaml").write_text(
            "- job:\n    name: shared-job\n    vars:\n      source: repo_a\n"
        )
        (repo_b / "zuul.d" / "jobs.yaml").write_text(
            "- job:\n    name: shared-job\n    vars:\n      source: repo_b\n"
        )
        resolver = Resolver([str(repo_a), str(repo_b)])
        merged, _, _ = resolver.resolve_job("shared-job")
        assert merged["source"] == "repo_b"

    def test_include_vars_resolve_per_repo(self, tmp_path):
        repo_a = tmp_path / "repo_a"
        repo_b = tmp_path / "repo_b"
        for r in (repo_a, repo_b):
            (r / "zuul.d").mkdir(parents=True)
            (r / "vars").mkdir()
        (repo_a / "vars" / "defaults.yaml").write_text("base_var: from_a\n")
        (repo_a / "zuul.d" / "jobs.yaml").write_text(
            "- job:\n"
            "    name: base-job\n"
            "    include-vars:\n"
            "      - name: vars/defaults.yaml\n"
        )
        (repo_b / "vars" / "defaults.yaml").write_text("leaf_var: from_b\n")
        (repo_b / "zuul.d" / "jobs.yaml").write_text(
            "- job:\n"
            "    name: leaf-job\n"
            "    parent: base-job\n"
            "    include-vars:\n"
            "      - name: vars/defaults.yaml\n"
        )
        resolver = Resolver([str(repo_a), str(repo_b)])
        merged, _, _ = resolver.resolve_job("leaf-job")
        assert merged["base_var"] == "from_a"
        assert merged["leaf_var"] == "from_b"

    def test_rejects_string_repo_dir(self):
        with pytest.raises(TypeError, match="must be a list"):
            Resolver("/some/path")


def _git(repo, *args):
    subprocess.run(
        ("git", *args),
        cwd=str(repo),
        capture_output=True,
        check=True,
    )


def _init_repo(tmp_path):
    repo = tmp_path / "repo"
    zuul_d = repo / "zuul.d"
    zuul_d.mkdir(parents=True)
    _git(repo, "init")
    _git(repo, "config", "user.email", "test@test.com")
    _git(repo, "config", "user.name", "Test")
    return repo, zuul_d


class TestComputeDiff:
    def test_changed_var_detected(self, tmp_path):
        repo, zuul_d = _init_repo(tmp_path)
        (zuul_d / "jobs.yaml").write_text(
            "- job:\n    name: my-job\n    vars:\n      key: old\n"
        )
        _git(repo, "add", ".")
        _git(repo, "commit", "-m", "initial")
        (zuul_d / "jobs.yaml").write_text(
            "- job:\n    name: my-job\n    vars:\n      key: new\n"
        )
        result = compute_diff(str(repo), "HEAD")
        assert "my-job" in result
        assert result["my-job"]["status"] == "changed"
        diff = result["my-job"]["diff"]
        assert "values_changed" in diff

    def test_added_job_detected(self, tmp_path):
        repo, zuul_d = _init_repo(tmp_path)
        (zuul_d / "jobs.yaml").write_text(
            "- job:\n    name: original\n    vars:\n      a: 1\n"
        )
        _git(repo, "add", ".")
        _git(repo, "commit", "-m", "initial")
        (zuul_d / "jobs.yaml").write_text(
            "- job:\n    name: original\n    vars:\n      a: 1\n"
            "- job:\n    name: new-job\n    vars:\n      b: 2\n"
        )
        result = compute_diff(str(repo), "HEAD")
        assert "new-job" in result
        assert result["new-job"]["status"] == "added"
        assert result["new-job"]["vars"]["b"] == 2
        assert "original" not in result

    def test_removed_job_detected(self, tmp_path):
        repo, zuul_d = _init_repo(tmp_path)
        (zuul_d / "jobs.yaml").write_text(
            "- job:\n    name: kept\n    vars:\n      a: 1\n"
            "- job:\n    name: doomed\n    vars:\n      b: 2\n"
        )
        _git(repo, "add", ".")
        _git(repo, "commit", "-m", "initial")
        (zuul_d / "jobs.yaml").write_text(
            "- job:\n    name: kept\n    vars:\n      a: 1\n"
        )
        result = compute_diff(str(repo), "HEAD")
        assert "doomed" in result
        assert result["doomed"]["status"] == "removed"
        assert "kept" not in result

    def test_no_changes_returns_empty(self, tmp_path):
        repo, zuul_d = _init_repo(tmp_path)
        (zuul_d / "jobs.yaml").write_text(
            "- job:\n    name: stable\n    vars:\n      a: 1\n"
        )
        _git(repo, "add", ".")
        _git(repo, "commit", "-m", "initial")
        result = compute_diff(str(repo), "HEAD")
        assert result == {}

    def test_resolved_vars_diffed_not_raw(self, tmp_path):
        repo, zuul_d = _init_repo(tmp_path)
        (zuul_d / "jobs.yaml").write_text(
            "- job:\n"
            "    name: parent\n"
            "    vars:\n"
            "      from_parent: old\n"
            "- job:\n"
            "    name: child\n"
            "    parent: parent\n"
            "    vars:\n"
            "      own: 1\n"
        )
        _git(repo, "add", ".")
        _git(repo, "commit", "-m", "initial")
        (zuul_d / "jobs.yaml").write_text(
            "- job:\n"
            "    name: parent\n"
            "    vars:\n"
            "      from_parent: new\n"
            "- job:\n"
            "    name: child\n"
            "    parent: parent\n"
            "    vars:\n"
            "      own: 1\n"
        )
        result = compute_diff(str(repo), "HEAD")
        assert "child" in result
        assert result["child"]["status"] == "changed"

    def test_include_vars_resolved_in_diff(self, tmp_path):
        repo, zuul_d = _init_repo(tmp_path)
        vars_dir = repo / "vars"
        vars_dir.mkdir()
        (vars_dir / "defaults.yaml").write_text("inc_key: old_val\n")
        (zuul_d / "jobs.yaml").write_text(
            "- job:\n"
            "    name: my-job\n"
            "    include-vars:\n"
            "      - name: vars/defaults.yaml\n"
            "    vars:\n"
            "      own: 1\n"
        )
        _git(repo, "add", ".")
        _git(repo, "commit", "-m", "initial")
        (vars_dir / "defaults.yaml").write_text("inc_key: new_val\n")
        result = compute_diff(str(repo), "HEAD")
        assert "my-job" in result
        assert result["my-job"]["status"] == "changed"
        assert "values_changed" in result["my-job"]["diff"]
