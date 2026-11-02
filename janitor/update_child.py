"""Post-pull update steps, each run as ``python -m janitor.update_child <step>``.

``janitor/update_core.py`` spawns this module from the checkout after the pull,
so every step executes the freshly-pulled code in a fresh interpreter rather
than in the updater process, whose modules (and, for a PM-managed checkout,
whose dependency generation) predate the pull. Upstream retired its
in-process "fresh" helpers for the same reason.

Steps that need the application's dependencies import ``hermes_bootstrap``
first, exactly like every Hermes entry point: a classic ``.venv`` keeps its
packages, and a PM-managed checkout activates its committed generation.
``uv`` and ``pm-sync`` stay stdlib-only because they provision those
dependencies. Only stdlib may be imported at module level.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def _project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _uv() -> int:
    """Print PM's ``uv`` (installed into the active home's tool store when missing)."""
    import pm

    pm.ensure("uv", explicit=True)
    uv = pm.uv_launcher("uv")
    if uv is None:
        return 1
    print(uv)
    return 0


def _pm_sync() -> int:
    """Sync a PM-managed checkout's dependency generation to the pulled inputs."""
    from pm.client import ensure_tools_for_sync, sync_venv

    ensure_tools_for_sync()
    sync_venv(None, explicit=True, project_root=_project_root())
    return 0


def _products(result_path: str) -> int:
    """Node dependencies, TUI and web builds, plus upstream's left-core migrations.

    Every independent product is attempted; the failed ones are written to
    ``result_path`` so build output can stream to the terminal uncaptured.
    """
    import hermes_bootstrap
    from hermes_cli.source_build import ProductBuildError, build_update_products

    failures: list[str] = []
    try:
        build_update_products(_project_root(), desktop=False)
    except ProductBuildError as exc:
        failures = [name for name, _error in exc.failures]
    Path(result_path).write_text(json.dumps(failures), encoding="utf-8")
    return 1 if failures else 0


def _config_check(result_path: str) -> int:
    import hermes_bootstrap
    from hermes_cli.config import check_config_version

    current, latest = check_config_version(raise_on_parse_error=True)
    Path(result_path).write_text(json.dumps([current, latest]), encoding="utf-8")
    return 0


def _config_migrate(result_path: str, interactive: str, quiet: str) -> int:
    import hermes_bootstrap
    from hermes_cli.config import migrate_config

    results = migrate_config(interactive=interactive == "1", quiet=quiet == "1")
    Path(result_path).write_text(json.dumps(results, default=str), encoding="utf-8")
    return 0


_STEPS = {
    "uv": _uv,
    "pm-sync": _pm_sync,
    "products": _products,
    "config-check": _config_check,
    "config-migrate": _config_migrate,
}


def main(argv: list[str]) -> int:
    if not argv or argv[0] not in _STEPS:
        print(f"usage: python -m janitor.update_child {{{','.join(_STEPS)}}} ...", file=sys.stderr)
        return 2
    return _STEPS[argv[0]](*argv[1:])


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
