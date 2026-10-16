"""Where the store, lockfile, and installed-state file live."""

from __future__ import annotations

import os
from pathlib import Path


def repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def install_root() -> Path:
    """The install owning the executing code, distinct from a PM build snapshot.

    A steward wrapper may explicitly bind it (Nix keeps its stamp outside the
    package dir). PM generations use their existing checkout ownership record;
    ``repo_root()`` continues to name the code actually executing.
    """
    env = os.environ.get("HERMES_INSTALL_ROOT")
    root = repo_root()
    return Path(env) if env else (_generation_install_root(root) or root)


def _generation_install_root(root: Path) -> Path | None:
    """Resolve only a recorded PM workspace, independent of the active profile."""
    import re

    from pm.environments import install_key

    root = root.resolve()
    generation, generations, state = root.parent, root.parent.parent, root.parent.parent.parent
    if (root.name != "workspace" or generations.name != "environments"
            or state.parent.name != "installs" or not re.fullmatch(r"[0-9a-f]{32}", generation.name)):
        return None
    try:
        recorded = (state / "inputs" / ".project-root").read_text(encoding="utf-8-sig").strip()
        owner = Path(recorded)
        if owner.is_absolute() and owner.is_dir() and install_key(owner) == state.name:
            return owner.resolve()
    except (OSError, ValueError):
        return None
    return None


def install_stamp_path(project_root: Path) -> Path:
    """THE stamp location for ``project_root``, shared by every stamp reader.

    Beside the code in checkouts, Docker and desktop payloads. A Nix package
    bakes the stamp outside the store's package dir and its wrapper carries
    ``HERMES_INSTALL_ROOT`` for the executing tree only — so the executing
    tree resolves through install_root, any other tree is taken literally.
    PM reads it in sealed stages (the Docker runtime base) before hermes_cli
    ships, so it lives here rather than beside the stewards.
    """
    root = Path(project_root)
    if root.resolve() == repo_root():
        root = install_root()
    return root / "install-stamp.json"


def lockfile_path() -> Path:
    return Path(__file__).resolve().parent / "lock.json"


def store_root() -> Path:
    from pm.environments import store_root as resolve

    return resolve(repo_root())


def partials_root() -> Path:
    """The downloader's managed partials area: machine-scoped and shared
    (keyed by sha256(url), so two callers or two profiles reuse one
    partial), but anchored to the DEFAULT hermes root — NOT the byte
    store. The store can live inside a read-only sealed payload
    (WindowsApps/agent-payload), and partials are mutable state the
    downloader writes continuously, so they must land somewhere writable
    on every install kind: ``%LOCALAPPDATA%\\hermes\\cache\\partials`` on
    Windows, ``~/.hermes/cache/partials`` on POSIX.
    """
    from hermes_constants import get_default_hermes_root

    return get_default_hermes_root() / "cache" / "partials"


def facts_path() -> Path:
    return store_root() / "facts.json"


def writable_store_root() -> Path:
    if not (store_root().parent / "manifest.json").is_file():
        return store_root()
    from hermes_constants import get_default_hermes_root

    return get_default_hermes_root() / "tools"


def runtime_facts_path() -> Path:
    from pm.environments import runtime_facts_path as resolve

    return resolve(repo_root())
