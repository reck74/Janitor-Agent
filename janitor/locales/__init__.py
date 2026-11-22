"""Janitor's backend message catalogs: upstream's ``locales/`` plus the fork's overlays.

The engine reads its static user-facing strings through ``agent.i18n.t()``,
which loads ``<lang>.yaml`` from ``HERMES_BUNDLED_LOCALES`` when that names a
directory, else from the source tree's ``locales/``. The launcher builds a
merged copy of upstream's catalogs with each ``janitor/locales/<lang>.yaml``
overlay applied key by key, and exports ``HERMES_BUNDLED_LOCALES`` at it, so
no upstream catalog is edited and only the keys Janitor changes live in the
fork. Every process the launcher starts (TUI gateway, desktop backend,
detached gateways) inherits the variable.

Stdlib + PyYAML only: the launcher runs this before any ``hermes_*`` import.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from janitor.home import REPO_ROOT, janitor_home

OVERLAY_DIR = Path(__file__).resolve().parent
UPSTREAM_LOCALES = REPO_ROOT / "locales"
ENV_VAR = "HERMES_BUNDLED_LOCALES"


def default_output_dir() -> Path:
    # Root home, not the profile's: catalogs are install data, shared by every profile.
    return janitor_home() / "cache" / "janitor-locales"


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
