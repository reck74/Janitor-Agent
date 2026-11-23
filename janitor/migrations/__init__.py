"""On-disk layout migrations for the Janitor home (``~/.janitor``).

``~/.janitor/.layout_version`` records the last layout a home was migrated
to. The ``janitor`` launcher calls :func:`auto_migrate` before Hermes starts,
because the code that pulls a new release is the *previous* release's update
command and cannot be relied on to migrate anything.

The desktop app is Janitor's starting point (plan decision 2.9): homes from
the old terminal installers are uninstalled, not migrated, so there are no
layout steps today. Layout v2 is the baseline every home the app or
``scripts/install.sh`` creates already carries (``janitor.seed`` stamps it),
and :func:`auto_migrate` only stamps a home that lacks the marker. The next
restructuring of ``~/.janitor`` bumps ``LAYOUT_VERSION`` in ``janitor/home.py``
and adds its step here, with the backup and ``--dry-run`` of directive #10.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

from janitor.home import LAYOUT_VERSION, janitor_home, read_layout_version, write_layout_version


def pending(home: Optional[Path] = None) -> bool:
    return read_layout_version(home or janitor_home()) < LAYOUT_VERSION


def auto_migrate(home: Optional[Path] = None) -> None:
    """Launcher hook: bring ``home`` to the current layout; never block startup."""
    home = home or janitor_home()
    if not home.exists() or not pending(home):
        return
    try:
        write_layout_version(LAYOUT_VERSION, home)
    except OSError as exc:
        print(f"⚠ Janitor could not record the layout version in {home}: {exc}", file=sys.stderr)
