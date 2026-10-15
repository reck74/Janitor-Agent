"""Optional distribution identity, declared by the source tree's pyproject."""
from __future__ import annotations

from collections.abc import Mapping
import importlib
from pathlib import Path
import re
import tomllib


def distribution_provider(root: Path, key: str):
    """Return an explicitly declared source-tree adapter, or None for upstream."""
    manifest = Path(root) / "pyproject.toml"
    if not manifest.is_file():
        return None
    with manifest.open("rb") as handle:
        settings = tomllib.load(handle).get("tool", {}).get("hermes", {}).get("distribution", {})
    provider = settings.get(key)
    if not provider:
        return None
    if not isinstance(provider, str) or not re.fullmatch(r"[A-Za-z_][\w.]*:[A-Za-z_]\w*", provider):
        raise RuntimeError(f"Invalid distribution {key} declaration")
    module, _, attribute = provider.partition(":")
    adapter = getattr(importlib.import_module(module), attribute)
    if not callable(adapter):
        raise RuntimeError(f"Distribution {key} must be callable")
    return adapter


def distribution_identity(root: Path) -> dict[str, str]:
    """Separate product identity from engine compatibility without core branding."""
    provider = distribution_provider(root, "identity-provider")
    if provider is None:
        return {}
    value = provider(Path(root))
    if not isinstance(value, Mapping):
        raise RuntimeError("Distribution identity provider must return a mapping")
    result = {}
    for key in ("baseVersion", "displayVersion", "productVersion", "upstreamRef"):
        if key in value:
            if not isinstance(value[key], str) or not value[key].strip():
                raise RuntimeError(f"Invalid distribution identity {key}")
            result[key] = value[key]
    if not result.get("baseVersion") or not result.get("productVersion"):
        raise RuntimeError("Distribution identity requires baseVersion and productVersion")
    result.setdefault("displayVersion", result["productVersion"])
    return result
