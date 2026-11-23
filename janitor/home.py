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
# migration (see janitor/migrations/). 2 is the baseline: every home the
# desktop app / scripts/install.sh seeds is stamped with it. Lower numbers
# belonged to the old terminal installs, which are uninstalled, not migrated
# (plan decision 2.9).
LAYOUT_VERSION = 2
LAYOUT_MARKER = ".layout_version"

REPO_ROOT = Path(__file__).resolve().parent.parent
PACKAGE_ROOT = Path(__file__).resolve().parent
SKILLS_ROOT = PACKAGE_ROOT / "skills"
ASSETS_ROOT = REPO_ROOT / "assets" / "janitor"


# ``skills.external_dirs`` entries that resolve Janitor's skills in place.
# ``${JANITOR_SKILLS_ROOT}`` is exported by the launcher; the absolute path of
# this install's tree covers backends started without the launcher (e.g. a
# gateway service running ``hermes_cli.main`` directly). Both resolve to the
# same directory and Hermes deduplicates them.
SKILLS_EXTERNAL_DIRS = ("${JANITOR_SKILLS_ROOT}", str(SKILLS_ROOT))


def janitor_home() -> Path:
    """Return the Janitor state directory (``~/.janitor``)."""
    return Path(os.path.expanduser("~/.janitor"))


def resolve_hermes_home(current: str | None = None) -> Path:
    """The ``HERMES_HOME`` the launcher runs with.

    Always the Janitor home, so an exported ``HERMES_HOME=~/.hermes`` never
    leaks a real Hermes install into Janitor, except when ``current`` already
    names one of the Janitor home's own profiles (``~/.janitor/profiles/<n>``):
    a profile-pinned process (gateway service, ``served_profile_child_env``
    spawn) must keep its profile instead of falling back to the root.
    """
    root = janitor_home()
    raw = (current or "").strip()
    if raw:
        candidate = Path(os.path.expanduser(raw))
        try:
            if candidate.parent.name == "profiles" and candidate.parent.parent.resolve() == root.resolve():
                return candidate
        except OSError:
            pass
    return root


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
