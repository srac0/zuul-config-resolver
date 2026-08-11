"""YAML loader with Zuul custom tag support (!override, !inherit, !unsafe)."""

import yaml


class OverrideValue:
    """Wraps a value with an override flag."""

    def __init__(self, value, override):
        self.value = value
        self.override = override

    def __repr__(self):
        tag = "!override" if self.override else "!inherit"
        return f"{tag} {self.value!r}"

    def __eq__(self, other):
        if isinstance(other, OverrideValue):
            return (
                self.value == other.value and self.override == other.override
            )
        return NotImplemented


class _Dropped:
    """Sentinel for values that should be excluded from parsed output."""


_DROPPED = _Dropped()


class ZuulLoader(yaml.SafeLoader):
    """SafeLoader extended with Zuul-specific YAML tags."""

    def construct_mapping(self, node, deep=False):
        mapping = super().construct_mapping(node, deep=deep)
        return {
            k: v for k, v in mapping.items() if not isinstance(v, _Dropped)
        }


def _override_constructor(loader, node):
    value = _construct_tagged_value(loader, node)
    return OverrideValue(value, override=True)


def _inherit_constructor(loader, node):
    value = _construct_tagged_value(loader, node)
    return OverrideValue(value, override=False)


def _construct_tagged_value(loader, node):
    if isinstance(node, yaml.MappingNode):
        return loader.construct_mapping(node, deep=True)
    elif isinstance(node, yaml.SequenceNode):
        return loader.construct_sequence(node, deep=True)
    elif isinstance(node, yaml.ScalarNode):
        return loader.construct_scalar(node)
    raise yaml.YAMLError(f"Unsupported node type for tag: {type(node)}")


def _unsafe_constructor(loader, node):
    return loader.construct_scalar(node)


def _secret_constructor(loader, suffix, node):
    """Do not parse secrets."""
    return _DROPPED


ZuulLoader.add_constructor("!override", _override_constructor)
ZuulLoader.add_constructor("!inherit", _inherit_constructor)
ZuulLoader.add_constructor("!unsafe", _unsafe_constructor)
ZuulLoader.add_multi_constructor("!encrypted/", _secret_constructor)


def load_yaml(path):
    """Load a YAML file and return its contents as a list of documents.

    Single-document files are wrapped in a list for consistency.
    Multi-document files (separated by ---) return one item per document.
    """
    with open(path) as f:
        docs = list(yaml.load_all(f, Loader=ZuulLoader))
    return docs
