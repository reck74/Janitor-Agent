"""Janitor's backend message catalogs: upstream's ``locales/`` plus the fork's overlays.

The engine reads its static user-facing strings through ``agent.i18n.t()``,
which loads ``<lang>.yaml`` from ``HERMES_BUNDLED_LOCALES`` when that names a
directory, else from the source tree's ``locales/``. The launcher builds a
merged copy of upstream's catalogs with each ``janitor/locales/<lang>.yaml``
overlay applied key by key, and exports ``HERMES_BUNDLED_LOCALES`` at it, so
no upstream catalog is edited and only the keys Janitor changes live in the
fork. Every process the launcher starts (TUI gateway, desktop backend,
detached gateways) inherits the variable; a process started without the
launcher (a gateway installed as a systemd/launchd service, ``python -m
hermes_cli.main ...``) gets it from the Janitor plugin's ``register()``
through :func:`ensure_exported`.

Stdlib + PyYAML only: the launcher runs this before any ``hermes_*`` import.
"""

from __future__ import annotations

import os
import sys
import threading
from pathlib import Path
from typing import Any

from janitor.home import REPO_ROOT, janitor_home

OVERLAY_DIR = Path(__file__).resolve().parent
UPSTREAM_LOCALES = REPO_ROOT / "locales"
ENV_VAR = "HERMES_BUNDLED_LOCALES"
# Overlay namespaces only Janitor defines: upstream call sites read them through a
# touchpoint with their English inline (backend-user-copy, runtime-copy). Every
# other overlay key fixes an upstream key and must exist in upstream's en.yaml.
FORK_NAMESPACES = ("tui_gateway.", "runtime_copy.")


def root_home() -> Path:
    """The process' root home: ``HERMES_HOME`` without a ``profiles/<name>`` suffix.

    The launcher sets ``HERMES_HOME`` to ``~/.janitor`` or one of its profiles,
    so this is ``janitor_home()`` there; a service unit sets it explicitly.
    """
    raw = os.environ.get("HERMES_HOME", "").strip()
    if not raw:
        return janitor_home()
    home = Path(os.path.expanduser(raw))
    return home.parent.parent if home.parent.name == "profiles" else home


def default_output_dir() -> Path:
    # Root home, not the profile's: catalogs are install data, identical for every
    # profile of one install, so a multi-profile process shares one copy.
    return root_home() / "cache" / "janitor-locales"


def overlay_files() -> dict[str, Path]:
    return {p.stem: p for p in sorted(OVERLAY_DIR.glob("*.yaml"))}


def merge(base: Any, overlay: Any) -> Any:
    """``overlay`` over ``base`` key by key; a non-mapping overlay value replaces the base one."""
    if not (isinstance(base, dict) and isinstance(overlay, dict)):
        return overlay
    merged = dict(base)
    for key, value in overlay.items():
        merged[key] = merge(base.get(key), value) if key in base else value
    return merged


def _base_dir(output: Path) -> Path:
    """Upstream's catalogs: a sealed-packaging override (Nix) wins unless it is our own output."""
    override = os.environ.get(ENV_VAR, "").strip()
    if override and Path(override).is_dir():
        try:
            if Path(override).resolve() != output.resolve():
                return Path(override)
        except OSError:
            pass
    return UPSTREAM_LOCALES


def _write_if_changed(path: Path, data: bytes) -> None:
    try:
        if path.read_bytes() == data:
            return
    except OSError:
        pass
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)  # atomic: concurrent backends never read a half-written catalog


def build(output: Path | None = None, base: Path | None = None) -> Path:
    """Write upstream's catalogs to ``output`` with the Janitor overlays merged in; return ``output``."""
    import yaml

    output = output or default_output_dir()
    base = base or _base_dir(output)
    output.mkdir(parents=True, exist_ok=True)
    overlays = overlay_files()
    for src in sorted(base.glob("*.yaml")):
        if src.stem in overlays:
            upstream = yaml.safe_load(src.read_text(encoding="utf-8")) or {}
            fork = yaml.safe_load(overlays[src.stem].read_text(encoding="utf-8")) or {}
            data = yaml.safe_dump(merge(upstream, fork), allow_unicode=True, sort_keys=False, width=1 << 16)
            _write_if_changed(output / src.name, data.encode("utf-8"))
        else:
            _write_if_changed(output / src.name, src.read_bytes())
    return output


def export_env(output: Path | None = None) -> Path:
    """Build the merged catalogs and point ``HERMES_BUNDLED_LOCALES`` at them."""
    path = build(output)
    os.environ[ENV_VAR] = str(path)
    return path


_ensured: Path | None = None
_ensure_lock = threading.Lock()


def ensure_exported() -> Path:
    """:func:`export_env` once per process, then drop ``agent.i18n``'s catalog cache.

    ``agent.i18n`` caches each catalog on first use, so a ``t()`` that ran
    before the export would keep upstream's text for the life of the process;
    ``reset_language_cache()`` (its public reset) makes the next ``t()`` read
    the merged copy. Later calls return the first result without touching disk.
    Raises on a broken overlay; callers that must not fail catch it.
    """
    global _ensured
    with _ensure_lock:
        if _ensured is None:
            _ensured = export_env()
            i18n = sys.modules.get("agent.i18n")
            if i18n is not None:
                i18n.reset_language_cache()
        return _ensured
