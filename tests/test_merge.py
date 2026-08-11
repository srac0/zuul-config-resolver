from config_resolver.merge import deep_update


class TestDeepUpdate:
    def test_disjoint_keys_merged(self):
        a = {"a": 1, "b": 2}
        b = {"c": 3}
        assert deep_update(a, b) == {"a": 1, "b": 2, "c": 3}

    def test_child_overrides_scalar(self):
        a = {"a": 1, "b": 2}
        b = {"b": 3}
        assert deep_update(a, b) == {"a": 1, "b": 3}

    def test_nested_dicts_recurse(self):
        a = {"a": 1, "b": {"a": 3}}
        b = {"a": 2, "b": {"b": 4}}
        assert deep_update(a, b) == {"a": 2, "b": {"a": 3, "b": 4}}

    def test_nested_dicts_child_wins(self):
        a = {"a": 1, "b": {"a": 1, "b": 2}}
        b = {"a": 1, "b": {"a": 3, "b": 4}}
        assert deep_update(a, b) == {"a": 1, "b": {"a": 3, "b": 4}}

    def test_list_replaced_not_merged(self):
        a = {"items": [1, 2, 3]}
        b = {"items": [4, 5]}
        assert deep_update(a, b) == {"items": [4, 5]}

    def test_parent_keys_preserved(self):
        a = {"only_parent": "kept", "shared": "old"}
        b = {"shared": "new"}
        result = deep_update(a, b)
        assert result["only_parent"] == "kept"
        assert result["shared"] == "new"

    def test_empty_child_preserves_parent(self):
        a = {"a": 1, "b": 2}
        b = {}
        assert deep_update(a, b) == {"a": 1, "b": 2}

    def test_empty_parent(self):
        a = {}
        b = {"a": 1}
        assert deep_update(a, b) == {"a": 1}

    def test_non_dict_replaces_dict(self):
        a = {"config": {"a": 1, "b": 2}}
        b = {"config": "replaced"}
        assert deep_update(a, b) == {"config": "replaced"}

    def test_dict_replaces_non_dict(self):
        a = {"config": "old"}
        b = {"config": {"a": 1}}
        assert deep_update(a, b) == {"config": {"a": 1}}
