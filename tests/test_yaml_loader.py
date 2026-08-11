import pytest
import yaml

from config_resolver.yaml_loader import OverrideValue, load_yaml


class TestLoadPlainYaml:
    def test_loads_mapping(self, tmp_path):
        f = tmp_path / "test.yaml"
        f.write_text("foo: bar\ncount: 3\n")
        result = load_yaml(str(f))
        assert result == [{"foo": "bar", "count": 3}]

    def test_loads_list_of_mappings(self, tmp_path):
        f = tmp_path / "test.yaml"
        f.write_text("- job:\n    name: my-job\n- job:\n    name: other-job\n")
        result = load_yaml(str(f))
        assert result == [
            [{"job": {"name": "my-job"}}, {"job": {"name": "other-job"}}]
        ]

    def test_loads_multi_document(self, tmp_path):
        f = tmp_path / "test.yaml"
        f.write_text("a: 1\n---\nb: 2\n")
        result = load_yaml(str(f))
        assert result == [{"a": 1}, {"b": 2}]

    def test_empty_file(self, tmp_path):
        f = tmp_path / "test.yaml"
        f.write_text("")
        result = load_yaml(str(f))
        assert result == []


class TestOverrideTag:
    def test_override_dict(self, tmp_path):
        f = tmp_path / "test.yaml"
        f.write_text("vars: !override\n  a: 1\n  b: 2\n")
        result = load_yaml(str(f))
        val = result[0]["vars"]
        assert isinstance(val, OverrideValue)
        assert val.override is True
        assert val.value == {"a": 1, "b": 2}

    def test_override_list(self, tmp_path):
        f = tmp_path / "test.yaml"
        f.write_text("items: !override\n  - one\n  - two\n")
        result = load_yaml(str(f))
        val = result[0]["items"]
        assert isinstance(val, OverrideValue)
        assert val.override is True
        assert val.value == ["one", "two"]

    def test_override_scalar(self, tmp_path):
        f = tmp_path / "test.yaml"
        f.write_text("name: !override replaced\n")
        result = load_yaml(str(f))
        val = result[0]["name"]
        assert isinstance(val, OverrideValue)
        assert val.override is True
        assert val.value == "replaced"

    def test_override_nested_dict(self, tmp_path):
        f = tmp_path / "test.yaml"
        f.write_text("config: !override\n  outer:\n    inner: value\n")
        result = load_yaml(str(f))
        val = result[0]["config"]
        assert isinstance(val, OverrideValue)
        assert val.value == {"outer": {"inner": "value"}}


class TestInheritTag:
    def test_inherit_dict(self, tmp_path):
        f = tmp_path / "test.yaml"
        f.write_text("vars: !inherit\n  a: 1\n")
        result = load_yaml(str(f))
        val = result[0]["vars"]
        assert isinstance(val, OverrideValue)
        assert val.override is False
        assert val.value == {"a": 1}

    def test_inherit_list(self, tmp_path):
        f = tmp_path / "test.yaml"
        f.write_text("items: !inherit\n  - one\n")
        result = load_yaml(str(f))
        val = result[0]["items"]
        assert isinstance(val, OverrideValue)
        assert val.override is False
        assert val.value == ["one"]


class TestUnsafeTag:
    def test_unsafe_passthrough(self, tmp_path):
        f = tmp_path / "test.yaml"
        f.write_text("password: !unsafe 's3cret{value}'\n")
        result = load_yaml(str(f))
        assert result[0]["password"] == "s3cret{value}"
        assert isinstance(result[0]["password"], str)


class TestJinjaTemplatePreservation:
    def test_simple_var_reference(self, tmp_path):
        f = tmp_path / "test.yaml"
        f.write_text('basedir: "{{ ansible_user_dir }}/project-data"\n')
        result = load_yaml(str(f))
        assert result[0]["basedir"] == "{{ ansible_user_dir }}/project-data"

    def test_nested_property_access(self, tmp_path):
        f = tmp_path / "test.yaml"
        f.write_text('username: "{{ registry_token.credentials.username }}"\n')
        result = load_yaml(str(f))
        assert (
            result[0]["username"]
            == "{{ registry_token.credentials.username }}"
        )

    def test_multiple_expressions_in_one_string(self, tmp_path):
        f = tmp_path / "test.yaml"
        f.write_text(
            'path: "{{ ansible_user_dir }}/bin:{{ ansible_env.PATH }}"\n'
        )
        result = load_yaml(str(f))
        assert (
            result[0]["path"]
            == "{{ ansible_user_dir }}/bin:{{ ansible_env.PATH }}"
        )

    def test_filter_expression(self, tmp_path):
        f = tmp_path / "test.yaml"
        f.write_text("release: \"{{ app_release | default('v2.0') }}\"\n")
        result = load_yaml(str(f))
        assert result[0]["release"] == "{{ app_release | default('v2.0') }}"

    def test_multiline_folded_path_join(self, tmp_path):
        f = tmp_path / "test.yaml"
        f.write_text(
            "dirs:\n"
            "  - >-\n"
            "    {{\n"
            "      (\n"
            "        ansible_user_dir,\n"
            "        'scenarios', 'uni', scenario\n"
            "      ) | ansible.builtin.path_join\n"
            "    }}\n"
        )
        result = load_yaml(str(f))
        value = result[0]["dirs"][0]
        assert "ansible.builtin.path_join" in value
        assert "{{" in value and "}}" in value

    def test_jinja_in_dict_value(self, tmp_path):
        f = tmp_path / "test.yaml"
        f.write_text(
            'vars:\n  basedir: "{{ ansible_user_dir }}/data"\n  count: 3\n'
        )
        result = load_yaml(str(f))
        assert result[0]["vars"]["basedir"] == "{{ ansible_user_dir }}/data"
        assert result[0]["vars"]["count"] == 3

    def test_jinja_in_list_item(self, tmp_path):
        f = tmp_path / "test.yaml"
        f.write_text(
            "files:\n"
            '  - "{{ ansible_user_dir }}/secrets/creds.yaml"\n'
            "  - plain-file.yaml\n"
        )
        result = load_yaml(str(f))
        assert (
            result[0]["files"][0]
            == "{{ ansible_user_dir }}/secrets/creds.yaml"
        )
        assert result[0]["files"][1] == "plain-file.yaml"

    def test_jinja_survives_override_tag(self, tmp_path):
        f = tmp_path / "test.yaml"
        f.write_text(
            'config: !override\n  path: "{{ ansible_user_dir }}/data"\n'
        )
        result = load_yaml(str(f))
        val = result[0]["config"]
        assert isinstance(val, OverrideValue)
        assert val.value["path"] == "{{ ansible_user_dir }}/data"


class TestMalformedJinja:
    def test_unquoted_jinja_raises_yaml_error(self, tmp_path):
        f = tmp_path / "test.yaml"
        f.write_text("path: {{ ansible_user_dir }}/data\n")
        with pytest.raises(yaml.YAMLError):
            load_yaml(str(f))

    def test_unquoted_jinja_in_list_raises(self, tmp_path):
        f = tmp_path / "test.yaml"
        f.write_text("files:\n  - {{ ansible_user_dir }}/creds.yaml\n")
        with pytest.raises(yaml.YAMLError):
            load_yaml(str(f))

    def test_unquoted_single_brace_raises(self, tmp_path):
        f = tmp_path / "test.yaml"
        f.write_text("path: {ansible_user_dir}/data\n")
        with pytest.raises(yaml.YAMLError):
            load_yaml(str(f))


class TestEncryptedSecrets:
    def test_encrypted_key_dropped(self, tmp_path):
        f = tmp_path / "test.yaml"
        f.write_text("api_token: !encrypted/pkcs1-oaep\n  - abc123encrypted\n")
        result = load_yaml(str(f))
        assert "api_token" not in result[0]

    def test_encrypted_mixed_with_plain(self, tmp_path):
        f = tmp_path / "test.yaml"
        f.write_text(
            "plain_var: hello\n"
            "secret: !encrypted/pkcs1-oaep\n"
            "  - ciphertext\n"
            "other_var: world\n"
        )
        result = load_yaml(str(f))
        assert result[0] == {"plain_var": "hello", "other_var": "world"}

    def test_encrypted_256_variant_dropped(self, tmp_path):
        f = tmp_path / "test.yaml"
        f.write_text(
            "token: !encrypted/pkcs1-oaep-256\n  - sha256ciphertext\n"
        )
        result = load_yaml(str(f))
        assert "token" not in result[0]

    def test_encrypted_in_nested_dict(self, tmp_path):
        f = tmp_path / "test.yaml"
        f.write_text(
            "outer:\n"
            "  visible: true\n"
            "  key: !encrypted/pkcs1-oaep\n"
            "    - nested_secret\n"
        )
        result = load_yaml(str(f))
        assert result[0]["outer"] == {"visible": True}


class TestOverrideValueEquality:
    def test_equal(self):
        a = OverrideValue({"x": 1}, override=True)
        b = OverrideValue({"x": 1}, override=True)
        assert a == b

    def test_different_value(self):
        a = OverrideValue({"x": 1}, override=True)
        b = OverrideValue({"x": 2}, override=True)
        assert a != b

    def test_different_override_flag(self):
        a = OverrideValue({"x": 1}, override=True)
        b = OverrideValue({"x": 1}, override=False)
        assert a != b
