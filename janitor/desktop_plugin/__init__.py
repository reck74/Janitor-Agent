"""The Janitor desktop plugin, delivered into the Janitor home.

Hermes Desktop loads standalone runtime plugins from
``<home>/desktop-plugins/<id>/plugin.js`` (enabled unless the plugin says
``defaultEnabled: false`` or the user turned it off) and mounts a plugin's
backend from ``<home>/plugins/<id>/dashboard/manifest.json`` +
``plugin_api.py`` when ``<id>`` is in ``plugins.enabled``. The id is
``janitor``, the name the Janitor seed config already enables, so both halves
are live on a fresh install with no user step and no upstream change.

:func:`sync` places the shipped files and refreshes them on every launcher
start (``janitor.seed.ensure_home``), so ``janitor update`` brings a new
screen with the next start. The backend file is a one-line shim: the logic
lives in :mod:`janitor.desktop_plugin.api` and updates with the package.

A copy the user edited is never overwritten without a backup: what this
module last wrote is recorded (sha256) in ``plugins/janitor/.janitor-shipped.json``;
a file that matches neither that record nor the shipped bytes is copied to
``<home>/.backup/desktop-plugin-<timestamp>/`` before the shipped version
replaces it. A symlinked file (a developer's live checkout) is left alone.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
import time
from pathlib import Path
from typing import Dict, List, Optional

PLUGIN_ID = "janitor"
ASSETS_ROOT = Path(__file__).resolve().parent / "assets"
STAMP = Path("plugins") / PLUGIN_ID / ".janitor-shipped.json"

# Home-relative path -> shipped asset (same relative path under ``assets/``).
FILES = (
    f"desktop-plugins/{PLUGIN_ID}/plugin.js",
    f"plugins/{PLUGIN_ID}/dashboard/manifest.json",
    f"plugins/{PLUGIN_ID}/dashboard/plugin_api.py",
    f"plugins/{PLUGIN_ID}/dashboard/dist/index.js",
)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _read_stamp(home: Path) -> Dict[str, str]:
    try:
        data = json.loads((home / STAMP).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {k: v for k, v in data.items() if isinstance(v, str)}


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".seed", dir=str(path.parent))
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
        os.chmod(tmp, 0o644)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def _backup_dir(home: Path) -> Path:
    base = home / ".backup" / f"desktop-plugin-{time.strftime('%Y%m%d-%H%M%S')}"
    candidate, n = base, 1
    while candidate.exists():
        n += 1
        candidate = base.with_name(f"{base.name}-{n}")
    return candidate


def sync(home: Path) -> List[str]:
    """Install or refresh the plugin files in ``home``. Returns what changed (empty = no-op)."""
    home = Path(home)
    recorded = _read_stamp(home)
    stamp = dict(recorded)
    changes: List[str] = []
    backup: Optional[Path] = None

    for rel in FILES:
        shipped = (ASSETS_ROOT / rel).read_bytes()
        target = home / rel
        if target.is_symlink():
            continue
        if target.is_file():
            current = target.read_bytes()
            if current == shipped:
                stamp[rel] = _sha256(shipped)
                continue
            if recorded.get(rel) != _sha256(current):
                backup = backup or _backup_dir(home)
                saved = backup / rel
                saved.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(target, saved)
                changes.append(f"backup {rel} -> {saved.relative_to(home).as_posix()}")
        elif target.exists():
            continue
        _atomic_write(target, shipped)
        stamp[rel] = _sha256(shipped)
        changes.append(rel)

    if stamp != recorded:
        _atomic_write(home / STAMP, (json.dumps(stamp, indent=2, sort_keys=True) + "\n").encode("utf-8"))
    return changes
