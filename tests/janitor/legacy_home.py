"""Shared paths and the launcher environment for the Janitor tests.

The module name is historical: it used to also build a pre-1.0 home for the
layout migrations, retired with the old terminal installs (plan decision 2.9).
It keeps its name because several test files import these helpers from here.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Dict

REPO_ROOT = Path(__file__).resolve().parents[2]
ASSETS = REPO_ROOT / "assets" / "janitor"


def launcher_env(root: Path) -> Dict[str, str]:
    """Environment for running the real ``janitor`` launcher against ``root``."""
    env = {k: v for k, v in os.environ.items() if not k.startswith("HERMES_")}
    env.update(
        {
            "HOME": str(root),
            "USERPROFILE": str(root),
            "HERMES_QUIET": "1",
            "PYTHONPATH": str(REPO_ROOT),
        }
    )
    return env
