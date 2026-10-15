"""Janitor product identity, separate from the upstream engine version."""
from __future__ import annotations

import json
from pathlib import Path

_METADATA = Path(__file__).resolve().parent / "janitor_ext" / "release.json"


def release_metadata() -> dict:
    with _METADATA.open(encoding="utf-8") as stream:
        metadata = json.load(stream)
    if not isinstance(metadata, dict):
        raise ValueError("Janitor release metadata must be an object")
    for field in ("janitorVersion", "upstreamVersion", "upstreamRef", "repository"):
        if not isinstance(metadata.get(field), str) or not metadata[field].strip():
            raise ValueError(f"Janitor release metadata is missing {field}")
    return metadata


def display_version(raw: str | None = None) -> str:
    """Legacy formatter remains usable; product callers omit the upstream version."""
    return raw.replace("+", "-", 1) if raw is not None else release_metadata()["janitorVersion"]


def format_version() -> str:
    data = release_metadata()
    return (f"THE JANITOR v{data['janitorVersion']} "
            f"(Hermes {data['upstreamVersion']}; {data['upstreamRef'][:12]})")
