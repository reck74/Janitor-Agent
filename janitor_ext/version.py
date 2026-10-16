"""Janitor product identity and the pinned Hermes compatibility version."""
from __future__ import annotations

import json
from pathlib import Path
import re


def distribution_identity(root: Path) -> dict[str, str]:
    with (Path(root) / "janitor_ext" / "release.json").open(encoding="utf-8") as handle:
        metadata = json.load(handle)
    for key in ("janitorVersion", "upstreamVersion"):
        if not isinstance(metadata.get(key), str) or not re.fullmatch(r"(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)", metadata[key]):
            raise RuntimeError(f"Invalid release metadata {key}")
    if not isinstance(metadata.get("upstreamRef"), str) or not re.fullmatch(r"[0-9a-f]{40}", metadata["upstreamRef"]):
        raise RuntimeError("Invalid release metadata upstreamRef")
    return {"baseVersion": metadata["upstreamVersion"],
            "productVersion": metadata["janitorVersion"],
            "displayVersion": metadata["janitorVersion"],
            "upstreamRef": metadata["upstreamRef"]}
