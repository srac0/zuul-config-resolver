from types import SimpleNamespace

import yaml

from config_resolver.job_registry import JobDefinition
from config_resolver.output import (
    _unique_values,
    format_conflicts,
    format_overrides,
    list_jobs,
    show_conflicts,
    show_overrides,
    write_resolved_vars,
    write_sources,
)
from config_resolver.parent_walker import merge_parent_chain


class TestListJobs:
    def test_prints_sorted_jobs(self, capsys):
        resolver = SimpleNamespace(
            registry={"zebra-job": None, "alpha-job": None, "middle-job": None}
        )
        list_jobs(resolver)
        out = capsys.readouterr().out
        lines = out.strip().split("\n")
        assert "3 jobs" in lines[0]
        assert lines[1].strip() == "alpha-job"
        assert lines[2].strip() == "middle-job"
        assert lines[3].strip() == "zebra-job"

    def test_prints_count(self, capsys):
        resolver = SimpleNamespace(registry={"a": None, "b": None})
        list_jobs(resolver)
        out = capsys.readouterr().out
        assert "Found 2 jobs" in out

    def test_empty_registry(self, capsys):
        resolver = SimpleNamespace(registry={})
        list_jobs(resolver)
        out = capsys.readouterr().out
        assert "Found 0 jobs" in out


class TestWriteResolvedVars:
    def test_writes_valid_yaml(self, tmp_path):
        out = tmp_path / "resolved.yaml"
        data = {"a": 1, "nested": {"x": "hello"}}
        write_resolved_vars(data, str(out))
        loaded = yaml.safe_load(out.read_text())
        assert loaded == data

    def test_preserves_key_order(self, tmp_path):
        out = tmp_path / "resolved.yaml"
        data = {"zebra": 1, "alpha": 2, "middle": 3}
        write_resolved_vars(data, str(out))
        keys = list(yaml.safe_load(out.read_text()).keys())
        assert keys == ["zebra", "alpha", "middle"]

    def test_block_style_output(self, tmp_path):
        out = tmp_path / "resolved.yaml"
        data = {"nested": {"a": 1, "b": 2}}
        write_resolved_vars(data, str(out))
        text = out.read_text()
        assert "{" not in text

    def test_jinja_templates_round_trip(self, tmp_path):
        out = tmp_path / "resolved.yaml"
        data = {"path": "{{ ansible_user_dir }}/data"}
        write_resolved_vars(data, str(out))
        loaded = yaml.safe_load(out.read_text())
        assert "{{ ansible_user_dir }}" in loaded["path"]


class TestWriteSources:
    def test_writes_sorted_keys(self, tmp_path):
        out = tmp_path / "sources.yaml"
        data = {
            "z_var": {
                "selected": {
                    "file": "parent.yaml",
                    "job_name": "parent",
                    "repo_dir": "",
                    "value": 42,
                },
                "history": [
                    {
                        "file": "parent.yaml",
                        "job_name": "parent",
                        "repo_dir": "",
                        "value": 42,
                    }
                ],
            },
            "a_var": {
                "selected": {
                    "file": "child.yaml",
                    "job_name": "child",
                    "repo_dir": "",
                    "value": "hello",
                },
                "history": [
                    {
                        "file": "child.yaml",
                        "job_name": "child",
                        "repo_dir": "",
                        "value": "hello",
                    }
                ],
            },
        }
        write_sources(data, str(out))
        keys = list(yaml.safe_load(out.read_text()).keys())
        assert keys == ["a_var", "z_var"]

    def test_multiple_sources_shows_selected(self, tmp_path):
        out = tmp_path / "sources.yaml"
        data = {
            "app_basedir": {
                "selected": {
                    "file": "04-scenario-vars.yaml",
                    "job_name": "deploy-base",
                    "repo_dir": "",
                    "value": "/opt/data",
                },
                "history": [
                    {
                        "file": "defaults.yaml",
                        "job_name": "integration-base",
                        "repo_dir": "",
                        "value": "{{ ansible_user_dir }}/data",
                    },
                    {
                        "file": "04-scenario-vars.yaml",
                        "job_name": "deploy-base",
                        "repo_dir": "",
                        "value": "/opt/data",
                    },
                ],
            },
        }
        write_sources(data, str(out))
        loaded = yaml.safe_load(out.read_text())
        entry = loaded["app_basedir"]
        assert entry["selected"]["value"] == "/opt/data"
        assert entry["selected"]["file"] == "04-scenario-vars.yaml"
        assert len(entry["history"]) == 2
        assert entry["history"][0]["value"] == "{{ ansible_user_dir }}/data"

    def test_single_source(self, tmp_path):
        out = tmp_path / "sources.yaml"
        data = {
            "scenario": {
                "selected": {
                    "file": "deploy-jobs.yaml",
                    "job_name": "deploy-base",
                    "repo_dir": "",
                    "value": "staging",
                },
                "history": [
                    {
                        "file": "deploy-jobs.yaml",
                        "job_name": "deploy-base",
                        "repo_dir": "",
                        "value": "staging",
                    },
                ],
            },
        }
        write_sources(data, str(out))
        loaded = yaml.safe_load(out.read_text())
        entry = loaded["scenario"]
        assert entry["selected"]["value"] == "staging"
        assert entry["selected"] == entry["history"][0]


class TestWriteSourcesFromMerge:
    """Round-trip: merge_parent_chain -> write_sources -> read back."""

    def test_generated_sources_round_trip(self, tmp_path):
        chain = [
            JobDefinition(
                name="parent",
                vars={"shared": "old", "parent_only": 1},
                source_file="zuul.d/parent.yaml",
            ),
            JobDefinition(
                name="child",
                vars={"shared": "new", "child_only": 2},
                source_file="zuul.d/child.yaml",
            ),
        ]
        _, sources = merge_parent_chain(chain)
        out = tmp_path / "sources.yaml"
        write_sources(sources, str(out))
        loaded = yaml.safe_load(out.read_text())

        assert loaded["shared"]["selected"]["value"] == "new"
        assert loaded["shared"]["selected"]["job_name"] == "child"
        assert len(loaded["shared"]["history"]) == 2
        assert loaded["parent_only"]["selected"]["job_name"] == "parent"
        assert loaded["child_only"]["selected"]["job_name"] == "child"

    def test_generated_sources_sorted_on_write(self, tmp_path):
        chain = [
            JobDefinition(
                name="job",
                vars={"zebra": 1, "alpha": 2, "middle": 3},
                source_file="zuul.d/jobs.yaml",
            ),
        ]
        _, sources = merge_parent_chain(chain)
        out = tmp_path / "sources.yaml"
        write_sources(sources, str(out))
        keys = list(yaml.safe_load(out.read_text()).keys())
        assert keys == ["alpha", "middle", "zebra"]

    def test_deep_merged_dict_round_trip(self, tmp_path):
        chain = [
            JobDefinition(
                name="parent",
                vars={"config": {"a": 1}},
                source_file="zuul.d/parent.yaml",
            ),
            JobDefinition(
                name="child",
                vars={"config": {"b": 2}},
                source_file="zuul.d/child.yaml",
            ),
        ]
        merged, sources = merge_parent_chain(chain)
        out = tmp_path / "sources.yaml"
        write_sources(sources, str(out))
        loaded = yaml.safe_load(out.read_text())
        entry = loaded["config"]
        assert entry["selected"]["value"] == merged["config"]
        assert entry["history"][0]["value"] == {"a": 1}
        assert entry["history"][1]["value"] == {"b": 2}


def _source_entry(file, job_name, value):
    return {"file": file, "job_name": job_name, "repo_dir": "", "value": value}


class TestFormatOverrides:
    def test_single_override(self):
        sources = {
            "my_var": {
                "selected": _source_entry("zuul.d/child.yaml", "child", "new"),
                "history": [
                    _source_entry("zuul.d/parent.yaml", "parent", "old"),
                    _source_entry("zuul.d/child.yaml", "child", "new"),
                ],
            },
        }
        lines = format_overrides(sources)
        assert len(lines) == 1
        assert "my_var" in lines[0]
        assert "1 override" in lines[0]
        assert "child (child.yaml) <- parent (parent.yaml)" in lines[0]

    def test_multiple_overrides_pluralized(self):
        sources = {
            "my_var": {
                "selected": _source_entry("c.yaml", "grandchild", 3),
                "history": [
                    _source_entry("a.yaml", "grandparent", 1),
                    _source_entry("b.yaml", "parent", 2),
                    _source_entry("c.yaml", "grandchild", 3),
                ],
            },
        }
        lines = format_overrides(sources)
        assert "2 overrides" in lines[0]

    def test_no_overrides_returns_empty(self):
        sources = {
            "only_set_once": {
                "selected": _source_entry("a.yaml", "job", "val"),
                "history": [_source_entry("a.yaml", "job", "val")],
            },
        }
        assert format_overrides(sources) == []

    def test_basename_strips_path(self):
        sources = {
            "var": {
                "selected": _source_entry(
                    "zuul.d/deep/nested/child.yaml", "child", "v"
                ),
                "history": [
                    _source_entry(
                        "vars/staging/scenario-vars.yaml",
                        "parent",
                        "old",
                    ),
                    _source_entry(
                        "zuul.d/deep/nested/child.yaml", "child", "v"
                    ),
                ],
            },
        }
        lines = format_overrides(sources)
        assert "child (child.yaml)" in lines[0]
        assert "parent (scenario-vars.yaml)" in lines[0]

    def test_mixed_overridden_and_not(self):
        sources = {
            "no_override": {
                "selected": _source_entry("a.yaml", "job", 1),
                "history": [_source_entry("a.yaml", "job", 1)],
            },
            "has_override": {
                "selected": _source_entry("b.yaml", "child", 2),
                "history": [
                    _source_entry("a.yaml", "parent", 1),
                    _source_entry("b.yaml", "child", 2),
                ],
            },
        }
        lines = format_overrides(sources)
        assert len(lines) == 1
        assert "has_override" in lines[0]


class TestShowOverrides:
    def test_prints_to_stdout(self, capsys):
        sources = {
            "var_a": {
                "selected": _source_entry("b.yaml", "child", "new"),
                "history": [
                    _source_entry("a.yaml", "parent", "old"),
                    _source_entry("b.yaml", "child", "new"),
                ],
            },
        }
        show_overrides(sources)
        out = capsys.readouterr().out
        assert "var_a" in out
        assert "1 override" in out

    def test_no_output_when_no_overrides(self, capsys):
        sources = {
            "single": {
                "selected": _source_entry("a.yaml", "job", 1),
                "history": [_source_entry("a.yaml", "job", 1)],
            },
        }
        show_overrides(sources)
        assert capsys.readouterr().out == ""


class TestUniqueValues:
    def test_scalars(self):
        assert len(_unique_values(["a", "b", "a"])) == 2

    def test_all_same(self):
        assert len(_unique_values([42, 42, 42])) == 1

    def test_none_values_same(self):
        assert len(_unique_values([None, None])) == 1

    def test_none_vs_string(self):
        assert len(_unique_values([None, "value"])) == 2

    def test_int_vs_string(self):
        assert len(_unique_values([1, "1"])) == 2

    def test_bool_vs_string(self):
        assert len(_unique_values([True, "true"])) == 2

    def test_empty_dict_same(self):
        assert len(_unique_values([{}, {}])) == 1

    def test_empty_list_same(self):
        assert len(_unique_values([[], []])) == 1

    def test_dict_key_order_irrelevant(self):
        assert len(_unique_values([{"a": 1, "b": 2}, {"b": 2, "a": 1}])) == 1

    def test_nested_dict_same(self):
        assert len(_unique_values([{"a": {"x": 1}}, {"a": {"x": 1}}])) == 1

    def test_nested_dict_different(self):
        assert len(_unique_values([{"a": {"x": 1}}, {"a": {"x": 2}}])) == 2

    def test_mixed_types(self):
        assert len(_unique_values(["hello", 42, {"a": 1}])) == 3


class TestFormatConflictsEdgeCases:
    def test_none_values_same_excluded(self):
        sources = {
            "var": {
                "selected": _source_entry("b.yaml", "child", None),
                "history": [
                    _source_entry("a.yaml", "parent", None),
                    _source_entry("b.yaml", "child", None),
                ],
            },
        }
        assert format_conflicts(sources) == []

    def test_none_vs_string_shown(self):
        sources = {
            "var": {
                "selected": _source_entry("b.yaml", "child", "value"),
                "history": [
                    _source_entry("a.yaml", "parent", None),
                    _source_entry("b.yaml", "child", "value"),
                ],
            },
        }
        assert len(format_conflicts(sources)) == 1

    def test_int_vs_string_shown(self):
        sources = {
            "port": {
                "selected": _source_entry("b.yaml", "child", "8080"),
                "history": [
                    _source_entry("a.yaml", "parent", 8080),
                    _source_entry("b.yaml", "child", "8080"),
                ],
            },
        }
        assert len(format_conflicts(sources)) == 1

    def test_empty_dict_same_excluded(self):
        sources = {
            "config": {
                "selected": _source_entry("b.yaml", "child", {}),
                "history": [
                    _source_entry("a.yaml", "parent", {}),
                    _source_entry("b.yaml", "child", {}),
                ],
            },
        }
        assert format_conflicts(sources) == []

    def test_string_vs_dict_shown(self):
        sources = {
            "config": {
                "selected": _source_entry("b.yaml", "child", {"key": "val"}),
                "history": [
                    _source_entry("a.yaml", "parent", "flat_value"),
                    _source_entry("b.yaml", "child", {"key": "val"}),
                ],
            },
        }
        assert len(format_conflicts(sources)) == 1


class TestFormatConflicts:
    def test_different_values_shown(self):
        sources = {
            "my_var": {
                "selected": _source_entry("zuul.d/child.yaml", "child", "new"),
                "history": [
                    _source_entry("zuul.d/parent.yaml", "parent", "old"),
                    _source_entry("zuul.d/child.yaml", "child", "new"),
                ],
            },
        }
        lines = format_conflicts(sources)
        assert len(lines) == 1
        assert "my_var" in lines[0]
        assert "child" in lines[0]
        assert "parent" in lines[0]

    def test_same_value_excluded(self):
        sources = {
            "redundant": {
                "selected": _source_entry("b.yaml", "child", True),
                "history": [
                    _source_entry("a.yaml", "parent", True),
                    _source_entry("b.yaml", "child", True),
                ],
            },
        }
        assert format_conflicts(sources) == []

    def test_single_writer_excluded(self):
        sources = {
            "only_once": {
                "selected": _source_entry("a.yaml", "job", "val"),
                "history": [_source_entry("a.yaml", "job", "val")],
            },
        }
        assert format_conflicts(sources) == []

    def test_mixed_conflict_and_redundant(self):
        sources = {
            "redundant_var": {
                "selected": _source_entry("b.yaml", "child", 42),
                "history": [
                    _source_entry("a.yaml", "parent", 42),
                    _source_entry("b.yaml", "child", 42),
                ],
            },
            "conflict_var": {
                "selected": _source_entry("b.yaml", "child", "new"),
                "history": [
                    _source_entry("a.yaml", "parent", "old"),
                    _source_entry("b.yaml", "child", "new"),
                ],
            },
        }
        lines = format_conflicts(sources)
        assert len(lines) == 1
        assert "conflict_var" in lines[0]

    def test_three_writers_partial_conflict(self):
        sources = {
            "var": {
                "selected": _source_entry("c.yaml", "grandchild", "final"),
                "history": [
                    _source_entry("a.yaml", "grandparent", "original"),
                    _source_entry("b.yaml", "parent", "original"),
                    _source_entry("c.yaml", "grandchild", "final"),
                ],
            },
        }
        lines = format_conflicts(sources)
        assert len(lines) == 1
        assert "grandchild" in lines[0]

    def test_dict_same_value_excluded(self):
        sources = {
            "config": {
                "selected": _source_entry("b.yaml", "child", {"a": 1, "b": 2}),
                "history": [
                    _source_entry("a.yaml", "parent", {"a": 1, "b": 2}),
                    _source_entry("b.yaml", "child", {"a": 1, "b": 2}),
                ],
            },
        }
        assert format_conflicts(sources) == []

    def test_dict_different_value_shown(self):
        sources = {
            "config": {
                "selected": _source_entry("b.yaml", "child", {"a": 1, "b": 3}),
                "history": [
                    _source_entry("a.yaml", "parent", {"a": 1, "b": 2}),
                    _source_entry("b.yaml", "child", {"a": 1, "b": 3}),
                ],
            },
        }
        lines = format_conflicts(sources)
        assert len(lines) == 1
        assert "config" in lines[0]

    def test_list_same_value_excluded(self):
        sources = {
            "hooks": {
                "selected": _source_entry(
                    "b.yaml", "child", ["hook1", "hook2"]
                ),
                "history": [
                    _source_entry("a.yaml", "parent", ["hook1", "hook2"]),
                    _source_entry("b.yaml", "child", ["hook1", "hook2"]),
                ],
            },
        }
        assert format_conflicts(sources) == []

    def test_list_different_value_shown(self):
        sources = {
            "hooks": {
                "selected": _source_entry(
                    "b.yaml", "child", ["hook1", "hook2", "hook3"]
                ),
                "history": [
                    _source_entry("a.yaml", "parent", ["hook1", "hook2"]),
                    _source_entry(
                        "b.yaml", "child", ["hook1", "hook2", "hook3"]
                    ),
                ],
            },
        }
        lines = format_conflicts(sources)
        assert len(lines) == 1
        assert "hooks" in lines[0]

    def test_list_different_order_shown(self):
        sources = {
            "hooks": {
                "selected": _source_entry("b.yaml", "child", ["b", "a"]),
                "history": [
                    _source_entry("a.yaml", "parent", ["a", "b"]),
                    _source_entry("b.yaml", "child", ["b", "a"]),
                ],
            },
        }
        lines = format_conflicts(sources)
        assert len(lines) == 1

    def test_include_vars_same_job_different_value_shown(self):
        sources = {
            "var": {
                "selected": _source_entry(
                    "zuul.d/jobs.yaml", "my-job", "from_vars"
                ),
                "history": [
                    _source_entry(
                        "vars/defaults.yaml", "my-job", "from_include"
                    ),
                    _source_entry("zuul.d/jobs.yaml", "my-job", "from_vars"),
                ],
            },
        }
        lines = format_conflicts(sources)
        assert len(lines) == 1
        assert "my-job" in lines[0]

    def test_include_vars_same_job_same_value_excluded(self):
        sources = {
            "var": {
                "selected": _source_entry(
                    "zuul.d/jobs.yaml", "my-job", "same"
                ),
                "history": [
                    _source_entry("vars/defaults.yaml", "my-job", "same"),
                    _source_entry("zuul.d/jobs.yaml", "my-job", "same"),
                ],
            },
        }
        assert format_conflicts(sources) == []


class TestShowConflicts:
    def test_prints_to_stdout(self, capsys):
        sources = {
            "var_a": {
                "selected": _source_entry("b.yaml", "child", "new"),
                "history": [
                    _source_entry("a.yaml", "parent", "old"),
                    _source_entry("b.yaml", "child", "new"),
                ],
            },
        }
        show_conflicts(sources)
        out = capsys.readouterr().out
        assert "var_a" in out

    def test_no_output_when_no_conflicts(self, capsys):
        sources = {
            "same_val": {
                "selected": _source_entry("b.yaml", "child", 1),
                "history": [
                    _source_entry("a.yaml", "parent", 1),
                    _source_entry("b.yaml", "child", 1),
                ],
            },
        }
        show_conflicts(sources)
        assert capsys.readouterr().out == ""
