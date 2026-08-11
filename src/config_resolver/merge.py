"""Recursive dict merge for Zuul job inheritance."""


def deep_update(base, override):
    """Recursively merge override into base, returning a new dict."""
    ret = {}
    for k, v in base.items():
        if k not in override:
            ret[k] = v
    for k, v in override.items():
        base_v = base.get(k)
        if isinstance(base_v, dict) and isinstance(v, dict):
            ret[k] = deep_update(base_v, v)
        else:
            ret[k] = v
    return ret
