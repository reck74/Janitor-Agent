"""On-disk layout migrations for the Janitor home (``~/.janitor``).

``~/.janitor/.layout_version`` records the last layout a home was migrated
to. The ``janitor`` launcher calls :func:`auto_migrate` before Hermes starts,
because the code that pulls a new release is the *previous* release's update
command and cannot be relied on to migrate anything.

Every layout step is idempotent and planned from what is on disk, so
:func:`run` plans them all in order (v1 then v2; each sees the config as the
previous one leaves it), takes ONE backup and applies them. A home on any
older layout, pre-1.0 included, reaches the current one in a single run.

Run manually with ``scripts/migrate-janitor-v2.sh`` or
``python -m janitor.migrations [--dry-run]``.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Callable, Optional

from janitor.home import LAYOUT_VERSION, janitor_home, read_layout_version, write_layout_version
from janitor.migrations import v1, v2

Out = Callable[[str], None]


def pending(home: Optional[Path] = None) -> bool:
    return read_layout_version(home or janitor_home()) < LAYOUT_VERSION


def run(home: Optional[Path] = None, *, dry_run: bool = False, out: Out = print) -> Optional[Path]:
    """Migrate ``home`` to the current layout. Returns the backup dir, if any."""
    home = home or janitor_home()
    plan1 = v1.build_plan(home)
    plan2 = v2.build_plan(home, base_config=plan1.config)
    steps = ((v1, plan1), (v2, plan2))
    empty = all(plan.empty for _, plan in steps)

    if empty:
        out(f"Janitor home {home} already uses layout v{LAYOUT_VERSION}.")
    else:
        out(f"Janitor home {home}: migrating to layout v{LAYOUT_VERSION}{' (dry run)' if dry_run else ''}")
    for module, plan in steps:
        module.describe(plan, out)

    if dry_run:
        return None

    backup = None
    if not empty:
        backup = v1.make_backup(plan1, version=LAYOUT_VERSION)
        for module, plan in steps:
            if not plan.empty:
                module.apply(plan)
        out(f"  backup: {backup}")
    if home.exists():
        write_layout_version(LAYOUT_VERSION, home)
    return backup


def auto_migrate(home: Optional[Path] = None) -> None:
    """Launcher hook: migrate once, never block startup on failure."""
    home = home or janitor_home()
    if not home.exists() or not pending(home):
        return

    def _err(line: str) -> None:
        print(line, file=sys.stderr)

    try:
        run(home, out=_err)
    except Exception as exc:
        _err(f"⚠ Janitor layout migration failed: {exc}")
        _err("  Your data was not deleted. Retry with: bash scripts/migrate-janitor-v2.sh")


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="migrate-janitor",
        description=f"Migrate ~/.janitor to the current Janitor layout (v{LAYOUT_VERSION}; backup first, idempotent).",
    )
    parser.add_argument("--dry-run", action="store_true", help="show what would change, write nothing")
    parser.add_argument("--home", type=Path, default=None, help="Janitor home (default: ~/.janitor)")
    args = parser.parse_args(argv)

    home = (args.home or janitor_home()).expanduser()
    if not home.exists():
        print(f"Nothing to migrate: {home} does not exist.")
        return 0
    run(home, dry_run=args.dry_run)
    return 0
