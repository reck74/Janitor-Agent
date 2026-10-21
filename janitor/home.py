"""Janitor home (``~/.janitor``) and install-tree locations.

Janitor keeps its state isolated from any Hermes install by pointing
``HERMES_HOME`` at ``~/.janitor`` before Hermes is imported. This module must
stay import-light (stdlib only): the launcher calls it before any ``hermes_*``
module is loaded.
"""

from __future__ import annotations

import os
from pathlib import Path

# Bumped when the on-disk layout of ~/.janitor changes in a way that needs a
# migration (see janitor/migrations/). 0 = every pre-1.0 install.
LAYOUT_VERSION = 1
LAYOUT_MARKER = ".layout_version"

REPO_ROOT = Path(__file__).resolve().parent.parent
PACKAGE_ROOT = Path(__file__).resolve().parent
SKILLS_ROOT = PACKAGE_ROOT / "skills"
ASSETS_ROOT = REPO_ROOT / "assets" / "janitor"


def janitor_home() -> Path:
    """Return the Janitor state directory (``~/.janitor``)."""
    return Path(os.path.expanduser("~/.janitor"))


def read_layout_version(home: Path | None = None) -> int:
    marker = (home or janitor_home()) / LAYOUT_MARKER
    try:
        return int(marker.read_text(encoding="utf-8").strip() or "0")
    except (OSError, ValueError):
        return 0


def write_layout_version(version: int, home: Path | None = None) -> None:
    root = home or janitor_home()
    root.mkdir(parents=True, exist_ok=True)
    (root / LAYOUT_MARKER).write_text(f"{version}\n", encoding="utf-8")
