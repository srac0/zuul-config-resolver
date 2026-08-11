import pytest

from config_resolver.job_registry import JobDefinition
from config_resolver.parent_walker import (
    merge_parent_chain,
    resolve_parents,
    walk_parents,
)


class TestWalkParents:
    def test_single_job_no_parent(self):
        registry = {
            "leaf": JobDefinition(name="leaf"),
        }
        parent_chain = walk_parents("leaf", registry)
        assert len(parent_chain) == 1
        assert parent_chain[0].name == "leaf"

    def test_three_job_chain_root_first(self):
        registry = {
            "root": JobDefinition(name="root"),
            "middle": JobDefinition(name="middle", parent="root"),
            "leaf": JobDefinition(name="leaf", parent="middle"),
        }
        parent_chain = walk_parents("leaf", registry)
        assert [j.name for j in parent_chain] == ["root", "middle", "leaf"]

    def test_missing_parent_warns(self):
        registry = {
            "child": JobDefinition(name="child", parent="missing"),
        }
        with pytest.warns(UserWarning, match="not found in registry"):
            parent_chain = walk_parents("child", registry)
        assert len(parent_chain) == 1
        assert parent_chain[0].name == "child"

    def test_circular_parent_raises(self):
        registry = {
            "a": JobDefinition(name="a", parent="b"),
            "b": JobDefinition(name="b", parent="a"),
        }
        with pytest.raises(ValueError, match="Circular parent reference"):
            walk_parents("a", registry)

    def test_job_not_in_registry(self):
        registry = {}
        with pytest.warns(UserWarning, match="not found in registry"):
            parent_chain = walk_parents("nonexistent", registry)
        assert parent_chain == []


class TestMergeParentChain:
    def test_single_job_vars(self):
        parent_chain = [
            JobDefinition(name="only", vars={"a": 1, "b": 2}),
        ]
        merged, _ = merge_parent_chain(parent_chain)
        assert merged == {"a": 1, "b": 2}

    def test_child_overrides_parent_scalar(self):
        parent_chain = [
            JobDefinition(name="parent", vars={"a": 1, "b": 2}),
            JobDefinition(name="child", vars={"b": 3}),
        ]
        merged, _ = merge_parent_chain(parent_chain)
        assert merged == {"a": 1, "b": 3}

    def test_deep_merge_nested_dicts(self):
        parent_chain = [
            JobDefinition(name="parent", vars={"config": {"a": 1, "b": 2}}),
            JobDefinition(name="child", vars={"config": {"b": 3, "c": 4}}),
        ]
        merged, _ = merge_parent_chain(parent_chain)
        assert merged == {"config": {"a": 1, "b": 3, "c": 4}}

    def test_override_replaces_entire_dict(self):
        parent_chain = [
            JobDefinition(
                name="parent",
                vars={"config": {"a": 1, "b": 2}},
            ),
            JobDefinition(
                name="child",
                vars={"config": {"b": 3}},
                vars_override_control={"config": True},
            ),
        ]
        merged, _ = merge_parent_chain(parent_chain)
        assert merged == {"config": {"b": 3}}

    def test_inherit_deep_merges(self):
        parent_chain = [
            JobDefinition(
                name="parent",
                vars={"config": {"a": 1, "b": 2}},
            ),
            JobDefinition(
                name="child",
                vars={"config": {"c": 3}},
                vars_override_control={"config": False},
            ),
        ]
        merged, _ = merge_parent_chain(parent_chain)
        assert merged == {"config": {"a": 1, "b": 2, "c": 3}}

    def test_three_level_chain(self):
        parent_chain = [
            JobDefinition(name="root", vars={"a": 1, "config": {"x": 1}}),
            JobDefinition(name="middle", vars={"b": 2, "config": {"y": 2}}),
            JobDefinition(name="leaf", vars={"c": 3, "config": {"z": 3}}),
        ]
        merged, _ = merge_parent_chain(parent_chain)
        assert merged == {
            "a": 1,
            "b": 2,
            "c": 3,
            "config": {"x": 1, "y": 2, "z": 3},
        }

    def test_override_mid_chain_then_merge(self):
        parent_chain = [
            JobDefinition(name="root", vars={"config": {"a": 1, "b": 2}}),
            JobDefinition(
                name="middle",
                vars={"config": {"c": 3}},
                vars_override_control={"config": True},
            ),
            JobDefinition(name="leaf", vars={"config": {"d": 4}}),
        ]
        result, _ = merge_parent_chain(parent_chain)
        assert result == {"config": {"c": 3, "d": 4}}

    def test_list_replaced_not_merged(self):
        parent_chain = [
            JobDefinition(name="parent", vars={"items": [1, 2, 3]}),
            JobDefinition(name="child", vars={"items": [4, 5]}),
        ]
        merged, _ = merge_parent_chain(parent_chain)
        assert merged == {"items": [4, 5]}

    def test_empty_chain(self):
        merged, sources = merge_parent_chain([])
        assert merged == {}
        assert sources == {}


class TestMergeParentChainWithIncludeVars:
    def test_loads_include_vars(self, tmp_path):
        (tmp_path / "vars").mkdir()
        (tmp_path / "vars" / "extra.yaml").write_text(
            "extra_key: extra_value\n"
        )
        parent_chain = [
            JobDefinition(
                name="job",
                vars={"own_key": "own_value"},
                include_vars=["vars/extra.yaml"],
                repo_dir=tmp_path,
            ),
        ]
        result, _ = merge_parent_chain(parent_chain)
        assert result["extra_key"] == "extra_value"
        assert result["own_key"] == "own_value"

    def test_job_vars_override_include_vars(self, tmp_path):
        (tmp_path / "vars").mkdir()
        (tmp_path / "vars" / "extra.yaml").write_text("shared: from_include\n")
        parent_chain = [
            JobDefinition(
                name="job",
                vars={"shared": "from_job"},
                include_vars=["vars/extra.yaml"],
                repo_dir=tmp_path,
            ),
        ]
        result, _ = merge_parent_chain(parent_chain)
        assert result["shared"] == "from_job"

    def test_missing_include_file_warns(self):
        parent_chain = [
            JobDefinition(
                name="job",
                vars={"a": 1},
                include_vars=["nonexistent.yaml"],
            ),
        ]
        with pytest.warns(UserWarning, match="not found"):
            result, _ = merge_parent_chain(parent_chain)
        assert result == {"a": 1}


class TestJinjaPreservationThroughMerge:
    def test_jinja_scalar_preserved(self):
        parent_chain = [
            JobDefinition(
                name="parent",
                vars={"basedir": "{{ ansible_user_dir }}/data"},
            ),
            JobDefinition(name="child", vars={"extra": "value"}),
        ]
        result, _ = merge_parent_chain(parent_chain)
        assert result["basedir"] == "{{ ansible_user_dir }}/data"

    def test_jinja_in_nested_dict_preserved(self):
        parent_chain = [
            JobDefinition(
                name="parent",
                vars={"config": {"path": "{{ ansible_user_dir }}/bin"}},
            ),
            JobDefinition(
                name="child",
                vars={"config": {"count": 3}},
            ),
        ]
        result, _ = merge_parent_chain(parent_chain)
        assert result["config"]["path"] == "{{ ansible_user_dir }}/bin"
        assert result["config"]["count"] == 3

    def test_child_jinja_overrides_parent_jinja(self):
        parent_chain = [
            JobDefinition(
                name="parent",
                vars={"path": "{{ old_var }}/data"},
            ),
            JobDefinition(
                name="child",
                vars={"path": "{{ new_var }}/data"},
            ),
        ]
        result, _ = merge_parent_chain(parent_chain)
        assert result["path"] == "{{ new_var }}/data"

    def test_jinja_list_items_preserved(self):
        parent_chain = [
            JobDefinition(
                name="job",
                vars={
                    "variable_files": [
                        "{{ ansible_user_dir }}/secrets/creds.yaml",
                        "plain-file.yaml",
                    ]
                },
            ),
        ]
        result, _ = merge_parent_chain(parent_chain)
        assert result["variable_files"] == [
            "{{ ansible_user_dir }}/secrets/creds.yaml",
            "plain-file.yaml",
        ]

    def test_jinja_survives_vars_override_control(self):
        parent_chain = [
            JobDefinition(
                name="parent",
                vars={"config": {"old": "{{ old_var }}"}},
            ),
            JobDefinition(
                name="child",
                vars={"config": {"new": "{{ new_var }}"}},
                vars_override_control={"config": True},
            ),
        ]
        result, _ = merge_parent_chain(parent_chain)
        assert result["config"] == {"new": "{{ new_var }}"}
        assert "old" not in result["config"]

    def test_multiple_jinja_expressions_in_one_value(self):
        parent_chain = [
            JobDefinition(
                name="job",
                vars={
                    "path": "{{ ansible_user_dir }}/bin:{{ ansible_env.PATH }}"
                },
            ),
        ]
        result, _ = merge_parent_chain(parent_chain)
        assert (
            result["path"]
            == "{{ ansible_user_dir }}/bin:{{ ansible_env.PATH }}"
        )


class TestExtraVarsMerge:
    """Extra-vars merge through the chain, then flat-squash onto vars."""

    def test_extra_vars_merged_into_result(self):
        chain = [
            JobDefinition(
                name="job",
                vars={"a": 1},
                extra_vars={"b": 2},
                source_file="zuul.d/jobs.yaml",
            ),
        ]
        merged, _ = merge_parent_chain(chain)
        assert merged == {"a": 1, "b": 2}

    def test_extra_vars_flat_replace_vars(self):
        chain = [
            JobDefinition(
                name="job",
                vars={"config": {"a": 1, "b": 2}},
                extra_vars={"config": {"c": 3}},
                source_file="zuul.d/jobs.yaml",
            ),
        ]
        merged, _ = merge_parent_chain(chain)
        assert merged["config"] == {"c": 3}

    def test_extra_vars_through_chain(self):
        chain = [
            JobDefinition(
                name="parent",
                extra_vars={"config": {"a": 1}},
                source_file="zuul.d/parent.yaml",
            ),
            JobDefinition(
                name="child",
                extra_vars={"config": {"b": 2}},
                source_file="zuul.d/child.yaml",
            ),
        ]
        merged, _ = merge_parent_chain(chain)
        assert merged["config"] == {"a": 1, "b": 2}

    def test_extra_vars_source_tracking(self):
        chain = [
            JobDefinition(
                name="job",
                vars={"shared": "from_vars"},
                extra_vars={"shared": "from_extra"},
                source_file="zuul.d/jobs.yaml",
            ),
        ]
        _, sources = merge_parent_chain(chain)
        entry = sources["shared"]
        assert entry["selected"]["value"] == "from_extra"
        assert len(entry["history"]) == 2
        assert entry["history"][0]["value"] == "from_vars"
        assert entry["history"][1]["value"] == "from_extra"

    def test_extra_vars_only_job(self):
        chain = [
            JobDefinition(
                name="job",
                extra_vars={"only_extra": "val"},
                source_file="zuul.d/jobs.yaml",
            ),
        ]
        merged, sources = merge_parent_chain(chain)
        assert merged == {"only_extra": "val"}
        assert sources["only_extra"]["selected"]["value"] == "val"
        assert len(sources["only_extra"]["history"]) == 1

    def test_extra_vars_override_control(self):
        chain = [
            JobDefinition(
                name="parent",
                extra_vars={"config": {"a": 1, "b": 2}},
                source_file="zuul.d/parent.yaml",
            ),
            JobDefinition(
                name="child",
                extra_vars={"config": {"c": 3}},
                extra_vars_override_control={"config": True},
                source_file="zuul.d/child.yaml",
            ),
        ]
        merged, _ = merge_parent_chain(chain)
        assert merged["config"] == {"c": 3}


class TestResolveParents:
    def test_combines_walk_and_merge(self):
        registry = {
            "parent": JobDefinition(name="parent", vars={"a": 1}),
            "child": JobDefinition(
                name="child", parent="parent", vars={"b": 2}
            ),
        }
        merged_vars, _, parent_chain = resolve_parents("child", registry)
        assert merged_vars == {"a": 1, "b": 2}
        assert [j.name for j in parent_chain] == ["parent", "child"]

    def test_sources_passed_through(self):
        registry = {
            "parent": JobDefinition(
                name="parent",
                vars={"key": "old"},
                source_file="zuul.d/parent.yaml",
            ),
            "child": JobDefinition(
                name="child",
                parent="parent",
                vars={"key": "new"},
                source_file="zuul.d/child.yaml",
            ),
        }
        _, sources, _ = resolve_parents("child", registry)
        assert "key" in sources
        assert sources["key"]["selected"]["job_name"] == "child"
        assert len(sources["key"]["history"]) == 2


class TestSourceTracking:
    """Source tracking in merge_parent_chain.

    Each var in the returned sources dict maps to:
      selected: {file, job_name, value}  -- the last contributor
      history: [{file, job_name, value}, ...]  -- all contributors
    """

    def test_single_job_all_vars_tracked(self):
        chain = [
            JobDefinition(
                name="only",
                vars={"a": 1, "b": "hello"},
                source_file="zuul.d/jobs.yaml",
            ),
        ]
        _, sources = merge_parent_chain(chain)
        assert set(sources.keys()) == {"a", "b"}
        assert sources["a"]["selected"] == {
            "file": "zuul.d/jobs.yaml",
            "job_name": "only",
            "repo_dir": "",
            "value": 1,
        }
        assert sources["a"]["selected"] == sources["a"]["history"][0]
        assert sources["b"]["selected"] == {
            "file": "zuul.d/jobs.yaml",
            "job_name": "only",
            "repo_dir": "",
            "value": "hello",
        }
        assert sources["b"]["selected"] == sources["b"]["history"][0]

    def test_child_overrides_parent_scalar(self):
        chain = [
            JobDefinition(
                name="parent",
                vars={"key": "old"},
                source_file="zuul.d/parent.yaml",
            ),
            JobDefinition(
                name="child",
                vars={"key": "new"},
                source_file="zuul.d/child.yaml",
            ),
        ]
        _, sources = merge_parent_chain(chain)
        entry = sources["key"]
        assert entry["selected"]["value"] == "new"
        assert entry["selected"]["job_name"] == "child"
        assert len(entry["history"]) == 2
        assert entry["history"][0] == {
            "file": "zuul.d/parent.yaml",
            "job_name": "parent",
            "repo_dir": "",
            "value": "old",
        }
        assert entry["history"][1] == {
            "file": "zuul.d/child.yaml",
            "job_name": "child",
            "repo_dir": "",
            "value": "new",
        }

    def test_parent_only_key(self):
        chain = [
            JobDefinition(
                name="parent",
                vars={"only_in_parent": 42},
                source_file="zuul.d/parent.yaml",
            ),
            JobDefinition(
                name="child",
                vars={"other": "x"},
                source_file="zuul.d/child.yaml",
            ),
        ]
        _, sources = merge_parent_chain(chain)
        entry = sources["only_in_parent"]
        assert entry["selected"]["job_name"] == "parent"
        assert len(entry["history"]) == 1

    def test_child_introduces_new_key(self):
        chain = [
            JobDefinition(
                name="parent",
                vars={"a": 1},
                source_file="zuul.d/parent.yaml",
            ),
            JobDefinition(
                name="child",
                vars={"new_key": "fresh"},
                source_file="zuul.d/child.yaml",
            ),
        ]
        _, sources = merge_parent_chain(chain)
        entry = sources["new_key"]
        assert entry["selected"]["job_name"] == "child"
        assert entry["selected"]["file"] == "zuul.d/child.yaml"
        assert len(entry["history"]) == 1

    def test_three_level_chain_history_order(self):
        chain = [
            JobDefinition(
                name="root",
                vars={"key": "from_root"},
                source_file="zuul.d/root.yaml",
            ),
            JobDefinition(
                name="middle",
                vars={"key": "from_middle"},
                source_file="zuul.d/middle.yaml",
            ),
            JobDefinition(
                name="leaf",
                vars={"key": "from_leaf"},
                source_file="zuul.d/leaf.yaml",
            ),
        ]
        _, sources = merge_parent_chain(chain)
        entry = sources["key"]
        assert entry["selected"]["value"] == "from_leaf"
        assert entry["selected"]["job_name"] == "leaf"
        assert [h["job_name"] for h in entry["history"]] == [
            "root",
            "middle",
            "leaf",
        ]

    def test_include_vars_tracked_with_file_path(self, tmp_path):
        (tmp_path / "vars").mkdir()
        (tmp_path / "vars" / "extra.yaml").write_text(
            "from_include: included_value\n"
        )
        chain = [
            JobDefinition(
                name="job",
                vars={"own_key": "own_value"},
                include_vars=["vars/extra.yaml"],
                source_file="zuul.d/jobs.yaml",
                repo_dir=tmp_path,
            ),
        ]
        _, sources = merge_parent_chain(chain)
        inc = sources["from_include"]
        assert inc["selected"]["file"] == "vars/extra.yaml"
        assert inc["selected"]["job_name"] == "job"
        own = sources["own_key"]
        assert own["selected"]["file"] == "zuul.d/jobs.yaml"

    def test_job_vars_win_over_include_vars_in_sources(self, tmp_path):
        (tmp_path / "vars").mkdir()
        (tmp_path / "vars" / "defaults.yaml").write_text(
            "shared: from_include\n"
        )
        chain = [
            JobDefinition(
                name="job",
                vars={"shared": "from_job"},
                include_vars=["vars/defaults.yaml"],
                source_file="zuul.d/jobs.yaml",
                repo_dir=tmp_path,
            ),
        ]
        _, sources = merge_parent_chain(chain)
        entry = sources["shared"]
        assert entry["selected"]["value"] == "from_job"
        assert entry["selected"]["file"] == "zuul.d/jobs.yaml"
        assert len(entry["history"]) == 2
        assert entry["history"][0]["file"] == "vars/defaults.yaml"
        assert entry["history"][0]["value"] == "from_include"
        assert entry["history"][1]["file"] == "zuul.d/jobs.yaml"
        assert entry["history"][1]["value"] == "from_job"

    def test_include_vars_and_job_vars_dict_same_key(self, tmp_path):
        (tmp_path / "vars").mkdir()
        (tmp_path / "vars" / "defaults.yaml").write_text(
            "config:\n  from_include: true\n  shared: included\n"
        )
        chain = [
            JobDefinition(
                name="job",
                vars={"config": {"from_job": True, "shared": "from_job"}},
                include_vars=["vars/defaults.yaml"],
                source_file="zuul.d/jobs.yaml",
                repo_dir=tmp_path,
            ),
        ]
        merged, sources = merge_parent_chain(chain)
        assert merged["config"] == {
            "from_include": True,
            "shared": "from_job",
            "from_job": True,
        }
        entry = sources["config"]
        assert len(entry["history"]) == 2
        assert entry["history"][0]["file"] == "vars/defaults.yaml"
        assert entry["history"][0]["value"] == {
            "from_include": True,
            "shared": "included",
        }
        assert entry["history"][1]["file"] == "zuul.d/jobs.yaml"
        assert entry["history"][1]["value"] == {
            "from_job": True,
            "shared": "from_job",
        }
        assert entry["selected"]["value"] == merged["config"]

    def test_vars_override_control_tracked(self):
        chain = [
            JobDefinition(
                name="parent",
                vars={"config": {"a": 1, "b": 2}},
                source_file="zuul.d/parent.yaml",
            ),
            JobDefinition(
                name="child",
                vars={"config": {"b": 3}},
                vars_override_control={"config": True},
                source_file="zuul.d/child.yaml",
            ),
        ]
        _, sources = merge_parent_chain(chain)
        entry = sources["config"]
        assert entry["selected"] == {
            "file": "zuul.d/child.yaml",
            "job_name": "child",
            "repo_dir": "",
            "value": {"b": 3},
        }
        assert len(entry["history"]) == 2
        assert entry["history"][0] == {
            "file": "zuul.d/parent.yaml",
            "job_name": "parent",
            "repo_dir": "",
            "value": {"a": 1, "b": 2},
        }

    def test_override_mid_chain_tracked(self):
        chain = [
            JobDefinition(
                name="root",
                vars={"config": {"a": 1, "b": 2}},
                source_file="zuul.d/root.yaml",
            ),
            JobDefinition(
                name="middle",
                vars={"config": {"c": 3}},
                vars_override_control={"config": True},
                source_file="zuul.d/middle.yaml",
            ),
            JobDefinition(
                name="leaf",
                vars={"config": {"d": 4}},
                source_file="zuul.d/leaf.yaml",
            ),
        ]
        _, sources = merge_parent_chain(chain)
        entry = sources["config"]
        assert entry["selected"]["job_name"] == "leaf"
        assert entry["selected"]["value"] == {"c": 3, "d": 4}
        assert [h["job_name"] for h in entry["history"]] == [
            "root",
            "middle",
            "leaf",
        ]

    def test_override_with_include_vars_tracked(self, tmp_path):
        (tmp_path / "vars").mkdir()
        (tmp_path / "vars" / "defaults.yaml").write_text(
            "config:\n  from_include: true\n  shared: included\n"
        )
        chain = [
            JobDefinition(
                name="parent",
                vars={},
                include_vars=["vars/defaults.yaml"],
                source_file="zuul.d/parent.yaml",
                repo_dir=str(tmp_path),
            ),
            JobDefinition(
                name="child",
                vars={"config": {"shared": "overridden"}},
                vars_override_control={"config": True},
                source_file="zuul.d/child.yaml",
            ),
        ]
        _, sources = merge_parent_chain(chain)
        entry = sources["config"]
        assert entry["selected"]["job_name"] == "child"
        assert entry["selected"]["value"] == {"shared": "overridden"}
        assert entry["history"][0]["file"] == "vars/defaults.yaml"
        assert entry["history"][0]["value"] == {
            "from_include": True,
            "shared": "included",
        }

    def test_nested_dict_merge_both_in_history(self):
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
        _, sources = merge_parent_chain(chain)
        entry = sources["config"]
        assert entry["selected"]["job_name"] == "child"
        assert entry["selected"]["value"] == {"a": 1, "b": 2}
        assert len(entry["history"]) == 2
        assert entry["history"][0]["value"] == {"a": 1}
        assert entry["history"][1]["value"] == {"b": 2}

    def test_nested_dict_merge_overlapping_keys(self):
        chain = [
            JobDefinition(
                name="parent",
                vars={"config": {"a": 1, "shared": "from_parent"}},
                source_file="zuul.d/parent.yaml",
            ),
            JobDefinition(
                name="child",
                vars={"config": {"shared": "from_child", "b": 2}},
                source_file="zuul.d/child.yaml",
            ),
        ]
        merged, sources = merge_parent_chain(chain)
        assert merged["config"] == {"a": 1, "shared": "from_child", "b": 2}
        entry = sources["config"]
        assert entry["selected"]["value"] == {
            "a": 1,
            "shared": "from_child",
            "b": 2,
        }
        assert entry["history"][0]["value"] == {
            "a": 1,
            "shared": "from_parent",
        }
        assert entry["history"][1]["value"] == {"shared": "from_child", "b": 2}

    def test_list_replaced_tracked(self):
        chain = [
            JobDefinition(
                name="parent",
                vars={"items": [1, 2, 3]},
                source_file="zuul.d/parent.yaml",
            ),
            JobDefinition(
                name="child",
                vars={"items": [4, 5]},
                source_file="zuul.d/child.yaml",
            ),
        ]
        _, sources = merge_parent_chain(chain)
        entry = sources["items"]
        assert entry["selected"]["value"] == [4, 5]
        assert entry["selected"]["job_name"] == "child"
        assert len(entry["history"]) == 2
        assert entry["history"][0]["value"] == [1, 2, 3]
        assert entry["history"][1]["value"] == [4, 5]

    def test_explicit_inherit_tracked(self):
        chain = [
            JobDefinition(
                name="parent",
                vars={"config": {"a": 1, "b": 2}},
                source_file="zuul.d/parent.yaml",
            ),
            JobDefinition(
                name="child",
                vars={"config": {"c": 3}},
                vars_override_control={"config": False},
                source_file="zuul.d/child.yaml",
            ),
        ]
        _, sources = merge_parent_chain(chain)
        entry = sources["config"]
        assert entry["selected"]["value"] == {"a": 1, "b": 2, "c": 3}
        assert entry["selected"]["job_name"] == "child"
        assert entry["history"][0]["value"] == {"a": 1, "b": 2}
        assert entry["history"][1]["value"] == {"c": 3}

    def test_multiple_include_vars_files(self, tmp_path):
        (tmp_path / "vars").mkdir()
        (tmp_path / "vars" / "net.yaml").write_text("net_cidr: 10.0.0.0/8\n")
        (tmp_path / "vars" / "storage.yaml").write_text("ceph_enabled: true\n")
        chain = [
            JobDefinition(
                name="job",
                vars={"own": "val"},
                include_vars=["vars/net.yaml", "vars/storage.yaml"],
                source_file="zuul.d/jobs.yaml",
                repo_dir=str(tmp_path),
            ),
        ]
        _, sources = merge_parent_chain(chain)
        assert sources["net_cidr"]["selected"]["file"] == "vars/net.yaml"
        assert sources["net_cidr"]["selected"]["job_name"] == "job"
        assert (
            sources["ceph_enabled"]["selected"]["file"] == "vars/storage.yaml"
        )
        assert sources["own"]["selected"]["file"] == "zuul.d/jobs.yaml"

    def test_include_vars_cross_chain_same_key(self, tmp_path):
        (tmp_path / "vars").mkdir()
        (tmp_path / "vars" / "parent-defaults.yaml").write_text(
            "shared: from_parent_include\n"
        )
        (tmp_path / "vars" / "child-defaults.yaml").write_text(
            "shared: from_child_include\n"
        )
        chain = [
            JobDefinition(
                name="parent",
                vars={},
                include_vars=["vars/parent-defaults.yaml"],
                source_file="zuul.d/parent.yaml",
                repo_dir=str(tmp_path),
            ),
            JobDefinition(
                name="child",
                vars={},
                include_vars=["vars/child-defaults.yaml"],
                source_file="zuul.d/child.yaml",
                repo_dir=str(tmp_path),
            ),
        ]
        _, sources = merge_parent_chain(chain)
        entry = sources["shared"]
        assert entry["selected"]["value"] == "from_child_include"
        assert entry["selected"]["file"] == "vars/child-defaults.yaml"
        assert len(entry["history"]) == 2
        assert entry["history"][0]["file"] == "vars/parent-defaults.yaml"
        assert entry["history"][0]["value"] == "from_parent_include"
        assert entry["history"][1]["file"] == "vars/child-defaults.yaml"

    def test_three_level_deep_merge_dict(self):
        chain = [
            JobDefinition(
                name="root",
                vars={"config": {"a": 1}},
                source_file="zuul.d/root.yaml",
            ),
            JobDefinition(
                name="middle",
                vars={"config": {"b": 2}},
                source_file="zuul.d/middle.yaml",
            ),
            JobDefinition(
                name="leaf",
                vars={"config": {"c": 3}},
                source_file="zuul.d/leaf.yaml",
            ),
        ]
        merged, sources = merge_parent_chain(chain)
        assert merged["config"] == {"a": 1, "b": 2, "c": 3}
        entry = sources["config"]
        assert entry["selected"]["value"] == {"a": 1, "b": 2, "c": 3}
        assert entry["selected"]["job_name"] == "leaf"
        assert [h["job_name"] for h in entry["history"]] == [
            "root",
            "middle",
            "leaf",
        ]
        assert entry["history"][0]["value"] == {"a": 1}
        assert entry["history"][1]["value"] == {"b": 2}
        assert entry["history"][2]["value"] == {"c": 3}

    def test_jinja_in_source_values(self):
        chain = [
            JobDefinition(
                name="parent",
                vars={"basedir": "{{ ansible_user_dir }}/data"},
                source_file="zuul.d/parent.yaml",
            ),
            JobDefinition(
                name="child",
                vars={"basedir": "{{ ansible_user_dir }}/override"},
                source_file="zuul.d/child.yaml",
            ),
        ]
        _, sources = merge_parent_chain(chain)
        entry = sources["basedir"]
        assert "{{ ansible_user_dir }}" in entry["selected"]["value"]
        assert entry["selected"]["value"] == "{{ ansible_user_dir }}/override"
        assert entry["history"][0]["value"] == "{{ ansible_user_dir }}/data"
        assert (
            entry["history"][1]["value"] == "{{ ansible_user_dir }}/override"
        )

    def test_empty_chain_no_sources(self):
        _, sources = merge_parent_chain([])
        assert sources == {}


class TestMultiRepoMerge:
    """Multi-repo: jobs from different repos merge through the parent chain."""

    def test_cross_repo_parent_chain(self, tmp_path):
        repo_a = tmp_path / "repo_a"
        repo_b = tmp_path / "repo_b"
        repo_a.mkdir()
        repo_b.mkdir()
        chain = [
            JobDefinition(
                name="parent",
                vars={"from_a": 1, "config": {"x": 10}},
                source_file="zuul.d/jobs.yaml",
                repo_dir=str(repo_a),
            ),
            JobDefinition(
                name="child",
                vars={"from_b": 2, "config": {"y": 20}},
                source_file="zuul.d/jobs.yaml",
                repo_dir=str(repo_b),
            ),
        ]
        merged, sources = merge_parent_chain(chain)
        assert merged["from_a"] == 1
        assert merged["from_b"] == 2
        assert merged["config"] == {"x": 10, "y": 20}
        assert sources["from_a"]["selected"]["job_name"] == "parent"
        assert sources["from_a"]["selected"]["repo_dir"] == str(repo_a)
        assert sources["from_b"]["selected"]["job_name"] == "child"
        assert sources["from_b"]["selected"]["repo_dir"] == str(repo_b)

    def test_include_vars_resolve_per_repo(self, tmp_path):
        repo_a = tmp_path / "repo_a"
        repo_b = tmp_path / "repo_b"
        for repo in (repo_a, repo_b):
            (repo / "vars").mkdir(parents=True)
        (repo_a / "vars" / "defaults.yaml").write_text("shared: from_repo_a\n")
        (repo_b / "vars" / "defaults.yaml").write_text("shared: from_repo_b\n")
        chain = [
            JobDefinition(
                name="parent",
                vars={},
                include_vars=["vars/defaults.yaml"],
                source_file="zuul.d/jobs.yaml",
                repo_dir=str(repo_a),
            ),
            JobDefinition(
                name="child",
                vars={},
                include_vars=["vars/defaults.yaml"],
                source_file="zuul.d/jobs.yaml",
                repo_dir=str(repo_b),
            ),
        ]
        merged, sources = merge_parent_chain(chain)
        assert merged["shared"] == "from_repo_b"
        assert len(sources["shared"]["history"]) == 2
        assert sources["shared"]["history"][0]["value"] == "from_repo_a"
        assert sources["shared"]["history"][0]["repo_dir"] == str(repo_a)
        assert sources["shared"]["history"][1]["value"] == "from_repo_b"
        assert sources["shared"]["history"][1]["repo_dir"] == str(repo_b)

    def test_include_vars_from_correct_repo(self, tmp_path):
        repo_a = tmp_path / "repo_a"
        repo_b = tmp_path / "repo_b"
        (repo_a / "vars").mkdir(parents=True)
        repo_b.mkdir()
        (repo_a / "vars" / "extra.yaml").write_text("from_a: true\n")
        chain = [
            JobDefinition(
                name="parent",
                vars={},
                include_vars=["vars/extra.yaml"],
                source_file="zuul.d/jobs.yaml",
                repo_dir=str(repo_a),
            ),
            JobDefinition(
                name="child",
                vars={"own": "val"},
                source_file="zuul.d/jobs.yaml",
                repo_dir=str(repo_b),
            ),
        ]
        merged, _ = merge_parent_chain(chain)
        assert merged["from_a"] is True
        assert merged["own"] == "val"

    def test_source_tracking_records_repo_specific_files(self, tmp_path):
        repo_a = tmp_path / "repo_a"
        repo_b = tmp_path / "repo_b"
        repo_a.mkdir()
        repo_b.mkdir()
        chain = [
            JobDefinition(
                name="base-job",
                vars={"key": "from_base"},
                source_file="zuul.d/base.yaml",
                repo_dir=str(repo_a),
            ),
            JobDefinition(
                name="leaf-job",
                vars={"key": "from_leaf"},
                source_file=".zuul.yaml",
                repo_dir=str(repo_b),
            ),
        ]
        _, sources = merge_parent_chain(chain)
        assert sources["key"]["history"][0]["file"] == "zuul.d/base.yaml"
        assert sources["key"]["history"][0]["repo_dir"] == str(repo_a)
        assert sources["key"]["history"][1]["file"] == ".zuul.yaml"
        assert sources["key"]["history"][1]["repo_dir"] == str(repo_b)
