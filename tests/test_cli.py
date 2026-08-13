import subprocess

import pytest
import yaml

from config_resolver.cli import main


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


class TestCliSynthetic:
    def test_no_args_errors(self, capsys):
        rc = main([])
        assert rc == 2

    def test_defaults_to_cwd(self, tmp_path, monkeypatch):
        zuul_d = tmp_path / "zuul.d"
        zuul_d.mkdir()
        (zuul_d / "jobs.yaml").write_text(
            "- job:\n    name: my-job\n    vars:\n      key: value\n"
        )
        out_dir = tmp_path / "output"
        monkeypatch.chdir(tmp_path)
        rc = main(["my-job", "--output-dir", str(out_dir)])
        assert rc == 0
        resolved = yaml.safe_load((out_dir / "resolved-vars.yaml").read_text())
        assert resolved["key"] == "value"

    def test_cwd_prepended_when_repo_dir_given(
        self, tmp_path, monkeypatch, capsys
    ):
        cwd_repo = tmp_path / "cwd-repo"
        zuul_cwd = cwd_repo / "zuul.d"
        zuul_cwd.mkdir(parents=True)
        (zuul_cwd / "jobs.yaml").write_text(
            "- job:\n    name: cwd-job\n    vars:\n      from_cwd: yes\n"
        )
        other_repo = tmp_path / "other-repo"
        zuul_other = other_repo / "zuul.d"
        zuul_other.mkdir(parents=True)
        (zuul_other / "jobs.yaml").write_text(
            "- job:\n    name: other-job\n    vars:\n      from_other: yes\n"
        )
        monkeypatch.chdir(cwd_repo)
        rc = main(["--list-jobs", "--repo-dir", str(other_repo)])
        assert rc == 0
        out = capsys.readouterr().out
        assert "cwd-job" in out
        assert "other-job" in out

    def test_cwd_not_duplicated_when_already_in_repo_dir(
        self, tmp_path, monkeypatch
    ):
        zuul_d = tmp_path / "zuul.d"
        zuul_d.mkdir()
        (zuul_d / "jobs.yaml").write_text(
            "- job:\n    name: my-job\n    vars:\n      key: value\n"
        )
        monkeypatch.chdir(tmp_path)
        out_dir = tmp_path / "output"
        rc = main(
            [
                "my-job",
                "--repo-dir",
                str(tmp_path),
                "--output-dir",
                str(out_dir),
            ]
        )
        assert rc == 0
        resolved = yaml.safe_load((out_dir / "resolved-vars.yaml").read_text())
        assert resolved["key"] == "value"

    def test_cwd_not_duplicated_with_relative_path(
        self, tmp_path, monkeypatch
    ):
        zuul_d = tmp_path / "zuul.d"
        zuul_d.mkdir()
        (zuul_d / "jobs.yaml").write_text(
            "- job:\n    name: my-job\n    vars:\n      key: value\n"
        )
        monkeypatch.chdir(tmp_path)
        out_dir = tmp_path / "output"
        rc = main(["my-job", "--repo-dir", ".", "--output-dir", str(out_dir)])
        assert rc == 0
        resolved = yaml.safe_load((out_dir / "resolved-vars.yaml").read_text())
        assert resolved["key"] == "value"

    def test_resolves_job_and_writes_file(self, tmp_path):
        zuul_d = tmp_path / "zuul.d"
        zuul_d.mkdir()
        (zuul_d / "jobs.yaml").write_text(
            "- job:\n    name: my-job\n    vars:\n      key: value\n"
        )
        out_dir = tmp_path / "output"
        rc = main(
            [
                "my-job",
                "--repo-dir",
                str(tmp_path),
                "--output-dir",
                str(out_dir),
            ]
        )
        assert rc == 0
        resolved = yaml.safe_load((out_dir / "resolved-vars.yaml").read_text())
        assert resolved["key"] == "value"

    def test_unknown_job(self, tmp_path, capsys):
        zuul_d = tmp_path / "zuul.d"
        zuul_d.mkdir()
        (zuul_d / "jobs.yaml").write_text("- job:\n    name: real-job\n")
        with pytest.warns(UserWarning, match="not found in registry"):
            rc = main(["nonexistent", "--repo-dir", str(tmp_path)])
        assert rc == 1
        assert "not found" in capsys.readouterr().err

    def test_writes_sources_yaml(self, tmp_path):
        zuul_d = tmp_path / "zuul.d"
        zuul_d.mkdir()
        (zuul_d / "jobs.yaml").write_text(
            "- job:\n"
            "    name: parent\n"
            "    vars:\n"
            "      shared: from_parent\n"
            "- job:\n"
            "    name: child\n"
            "    parent: parent\n"
            "    vars:\n"
            "      shared: from_child\n"
        )
        out_dir = tmp_path / "output"
        rc = main(
            [
                "child",
                "--repo-dir",
                str(tmp_path),
                "--output-dir",
                str(out_dir),
            ]
        )
        assert rc == 0
        sources_path = out_dir / "resolved-vars-sources.yaml"
        assert sources_path.exists()
        sources = yaml.safe_load(sources_path.read_text())
        assert sources["shared"]["selected"]["value"] == "from_child"
        assert len(sources["shared"]["history"]) == 2

    def test_verbose_output(self, tmp_path, capsys):
        zuul_d = tmp_path / "zuul.d"
        zuul_d.mkdir()
        (zuul_d / "jobs.yaml").write_text(
            "- job:\n    name: my-job\n    vars:\n      a: 1\n      b: 2\n"
        )
        rc = main(
            [
                "my-job",
                "--repo-dir",
                str(tmp_path),
                "--output-dir",
                str(tmp_path / "out"),
                "--verbose",
            ]
        )
        assert rc == 0
        out = capsys.readouterr().out
        assert "Resolved 2 variables" in out
        assert "Chain:" in out

    def test_show_overrides(self, tmp_path, capsys):
        zuul_d = tmp_path / "zuul.d"
        zuul_d.mkdir()
        (zuul_d / "jobs.yaml").write_text(
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
        )
        rc = main(
            [
                "child",
                "--repo-dir",
                str(tmp_path),
                "--output-dir",
                str(tmp_path / "out"),
                "--show-overrides",
            ]
        )
        assert rc == 0
        out = capsys.readouterr().out
        assert "shared" in out
        assert "1 override" in out
        assert "child" in out
        assert "parent" in out
        assert "parent_only" not in out

    def test_show_overrides_include_vars_same_job(self, tmp_path, capsys):
        zuul_d = tmp_path / "zuul.d"
        zuul_d.mkdir()
        vars_dir = tmp_path / "vars"
        vars_dir.mkdir()
        (vars_dir / "defaults.yaml").write_text("shared: from_include\n")
        (zuul_d / "jobs.yaml").write_text(
            "- job:\n"
            "    name: my-job\n"
            "    include-vars:\n"
            "      - name: vars/defaults.yaml\n"
            "    vars:\n"
            "      shared: from_vars\n"
        )
        rc = main(
            [
                "my-job",
                "--repo-dir",
                str(tmp_path),
                "--output-dir",
                str(tmp_path / "out"),
                "--show-overrides",
            ]
        )
        assert rc == 0
        out = capsys.readouterr().out
        assert "shared" in out
        assert "1 override" in out
        assert "defaults.yaml" in out
        assert "jobs.yaml" in out

    def test_show_overrides_no_overrides(self, tmp_path, capsys):
        zuul_d = tmp_path / "zuul.d"
        zuul_d.mkdir()
        (zuul_d / "jobs.yaml").write_text(
            "- job:\n    name: my-job\n    vars:\n      a: 1\n"
        )
        rc = main(
            [
                "my-job",
                "--repo-dir",
                str(tmp_path),
                "--output-dir",
                str(tmp_path / "out"),
                "--show-overrides",
            ]
        )
        assert rc == 0
        out = capsys.readouterr().out
        lines_with_override = [
            line
            for line in out.splitlines()
            if "override" in line and not line.startswith("Wrote")
        ]
        assert lines_with_override == []

    def test_show_conflicts_different_values(self, tmp_path, capsys):
        zuul_d = tmp_path / "zuul.d"
        zuul_d.mkdir()
        (zuul_d / "jobs.yaml").write_text(
            "- job:\n"
            "    name: parent\n"
            "    vars:\n"
            "      conflicting: old_value\n"
            "      same_value: identical\n"
            "- job:\n"
            "    name: child\n"
            "    parent: parent\n"
            "    vars:\n"
            "      conflicting: new_value\n"
            "      same_value: identical\n"
        )
        rc = main(
            [
                "child",
                "--repo-dir",
                str(tmp_path),
                "--output-dir",
                str(tmp_path / "out"),
                "--show-conflicts",
            ]
        )
        assert rc == 0
        out = capsys.readouterr().out
        assert "conflicting" in out
        assert "same_value" not in out

    def test_show_conflicts_no_conflicts(self, tmp_path, capsys):
        zuul_d = tmp_path / "zuul.d"
        zuul_d.mkdir()
        (zuul_d / "jobs.yaml").write_text(
            "- job:\n"
            "    name: parent\n"
            "    vars:\n"
            "      shared: same\n"
            "- job:\n"
            "    name: child\n"
            "    parent: parent\n"
            "    vars:\n"
            "      shared: same\n"
        )
        rc = main(
            [
                "child",
                "--repo-dir",
                str(tmp_path),
                "--output-dir",
                str(tmp_path / "out"),
                "--show-conflicts",
            ]
        )
        assert rc == 0
        out = capsys.readouterr().out
        lines_with_conflict = [
            line
            for line in out.splitlines()
            if "conflict" in line.lower() and not line.startswith("Wrote")
        ]
        assert lines_with_conflict == []

    def test_show_conflicts_include_vars(self, tmp_path, capsys):
        zuul_d = tmp_path / "zuul.d"
        zuul_d.mkdir()
        vars_dir = tmp_path / "vars"
        vars_dir.mkdir()
        (vars_dir / "defaults.yaml").write_text("shared: from_include\n")
        (zuul_d / "jobs.yaml").write_text(
            "- job:\n"
            "    name: my-job\n"
            "    include-vars:\n"
            "      - name: vars/defaults.yaml\n"
            "    vars:\n"
            "      shared: from_vars\n"
        )
        rc = main(
            [
                "my-job",
                "--repo-dir",
                str(tmp_path),
                "--output-dir",
                str(tmp_path / "out"),
                "--show-conflicts",
            ]
        )
        assert rc == 0
        out = capsys.readouterr().out
        assert "shared" in out

    def test_list_jobs(self, tmp_path, capsys):
        zuul_d = tmp_path / "zuul.d"
        zuul_d.mkdir()
        (zuul_d / "jobs.yaml").write_text(
            "- job:\n"
            "    name: zebra-job\n"
            "- job:\n"
            "    name: alpha-job\n"
            "- job:\n"
            "    name: middle-job\n"
        )
        rc = main(["--list-jobs", "--repo-dir", str(tmp_path)])
        assert rc == 0
        out = capsys.readouterr().out
        assert "Found 3 jobs" in out
        lines = out.strip().split("\n")
        job_lines = [line.strip() for line in lines[1:]]
        assert job_lines == ["alpha-job", "middle-job", "zebra-job"]

    def test_list_jobs_no_job_name_required(self, tmp_path):
        zuul_d = tmp_path / "zuul.d"
        zuul_d.mkdir()
        (zuul_d / "jobs.yaml").write_text("- job:\n    name: a-job\n")
        rc = main(["--list-jobs", "--repo-dir", str(tmp_path)])
        assert rc == 0

    def test_no_job_name_without_list_jobs_errors(self, tmp_path):
        zuul_d = tmp_path / "zuul.d"
        zuul_d.mkdir()
        (zuul_d / "jobs.yaml").write_text("- job:\n    name: a-job\n")
        rc = main(["--repo-dir", str(tmp_path)])
        assert rc == 2

    def test_show_parents(self, tmp_path, capsys):
        zuul_d = tmp_path / "zuul.d"
        zuul_d.mkdir()
        vars_dir = tmp_path / "vars"
        vars_dir.mkdir()
        (vars_dir / "defaults.yaml").write_text("from_include: 1\n")
        (zuul_d / "jobs.yaml").write_text(
            "- job:\n"
            "    name: grandparent\n"
            "    vars:\n"
            "      a: 1\n"
            "      b: 2\n"
            "- job:\n"
            "    name: parent\n"
            "    parent: grandparent\n"
            "    include-vars:\n"
            "      - name: vars/defaults.yaml\n"
            "    vars:\n"
            "      c: 3\n"
            "- job:\n"
            "    name: child\n"
            "    parent: parent\n"
            "    extra-vars:\n"
            "      d: 4\n"
        )
        rc = main(["child", "--repo-dir", str(tmp_path), "--show-parents"])
        assert rc == 0
        out = capsys.readouterr().out
        lines = out.strip().split("\n")
        assert len(lines) == 5
        assert "grandparent" in lines[0]
        assert "2 vars" in lines[0]
        assert "parent" in lines[1]
        assert "1 vars" in lines[1]
        assert "1 include-vars" in lines[1]
        assert "child" in lines[2]
        assert "1 extra-vars" in lines[2]

    def test_show_parents_single_job(self, tmp_path, capsys):
        zuul_d = tmp_path / "zuul.d"
        zuul_d.mkdir()
        (zuul_d / "jobs.yaml").write_text(
            "- job:\n    name: solo\n    vars:\n      x: 1\n"
        )
        rc = main(["solo", "--repo-dir", str(tmp_path), "--show-parents"])
        assert rc == 0
        out = capsys.readouterr().out
        lines = out.strip().split("\n")
        assert len(lines) == 3
        assert "solo" in lines[0]
        assert "1 vars" in lines[0]

    def test_config_file(self, tmp_path):
        repo = tmp_path / "repo"
        zuul_d = repo / "zuul.d"
        zuul_d.mkdir(parents=True)
        (zuul_d / "jobs.yaml").write_text(
            "- job:\n    name: my-job\n    vars:\n      key: value\n"
        )
        config = tmp_path / "repos.yaml"
        config.write_text(f"repos:\n  - {repo}\n")
        out_dir = tmp_path / "output"
        rc = main(
            [
                "my-job",
                "--config",
                str(config),
                "--output-dir",
                str(out_dir),
            ]
        )
        assert rc == 0
        resolved = yaml.safe_load((out_dir / "resolved-vars.yaml").read_text())
        assert resolved["key"] == "value"

    def test_config_file_multiple_repos(self, tmp_path):
        repo_a = tmp_path / "repo-a"
        zuul_a = repo_a / "zuul.d"
        zuul_a.mkdir(parents=True)
        (zuul_a / "jobs.yaml").write_text(
            "- job:\n    name: parent\n    vars:\n      a: 1\n"
        )
        repo_b = tmp_path / "repo-b"
        zuul_b = repo_b / "zuul.d"
        zuul_b.mkdir(parents=True)
        (zuul_b / "jobs.yaml").write_text(
            "- job:\n    name: child\n    parent: parent\n"
            "    vars:\n      b: 2\n"
        )
        config = tmp_path / "repos.yaml"
        config.write_text(f"repos:\n  - {repo_a}\n  - {repo_b}\n")
        out_dir = tmp_path / "output"
        rc = main(
            [
                "child",
                "--config",
                str(config),
                "--output-dir",
                str(out_dir),
            ]
        )
        assert rc == 0
        resolved = yaml.safe_load((out_dir / "resolved-vars.yaml").read_text())
        assert resolved["a"] == 1
        assert resolved["b"] == 2

    def test_config_file_overrides_repo_dir(self, tmp_path, capsys):
        repo = tmp_path / "repo"
        zuul_d = repo / "zuul.d"
        zuul_d.mkdir(parents=True)
        (zuul_d / "jobs.yaml").write_text(
            "- job:\n    name: cfg-job\n    vars:\n      x: 1\n"
        )
        config = tmp_path / "repos.yaml"
        config.write_text(f"repos:\n  - {repo}\n")
        rc = main(
            [
                "--list-jobs",
                "--config",
                str(config),
                "--repo-dir",
                str(tmp_path),
            ]
        )
        assert rc == 0
        out = capsys.readouterr().out
        assert "cfg-job" in out

    def test_diff_rejects_multiple_repo_dirs(self, capsys):
        rc = main(
            [
                "--diff",
                "HEAD",
                "--repo-dir",
                "/repo-a",
                "--repo-dir",
                "/repo-b",
            ]
        )
        assert rc == 2
        err = capsys.readouterr().err
        assert "--diff supports a single --repo-dir" in err

    def test_diff_rejects_config(self, capsys):
        rc = main(
            [
                "--diff",
                "HEAD",
                "--config",
                "repos.yaml",
            ]
        )
        assert rc == 2
        err = capsys.readouterr().err
        assert "--diff and --config cannot be used together" in err

    def test_diff_writes_output(self, tmp_path, capsys):
        repo, zuul_d = _init_repo(tmp_path)
        (zuul_d / "jobs.yaml").write_text(
            "- job:\n    name: my-job\n    vars:\n      key: old\n"
        )
        _git(repo, "add", ".")
        _git(repo, "commit", "-m", "initial")
        (zuul_d / "jobs.yaml").write_text(
            "- job:\n    name: my-job\n    vars:\n      key: new\n"
        )
        out_dir = tmp_path / "output"
        rc = main(
            [
                "--diff",
                "HEAD",
                "--repo-dir",
                str(repo),
                "--output-dir",
                str(out_dir),
            ]
        )
        assert rc == 0
        diff_file = out_dir / "resolved-vars-diff.yaml"
        assert diff_file.exists()
        diff_data = yaml.safe_load(diff_file.read_text())
        assert "my-job" in diff_data
        assert diff_data["my-job"]["status"] == "changed"
        out = capsys.readouterr().out
        assert "~ my-job" in out
