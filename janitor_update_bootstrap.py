"""Stdlib-safe branding shell; all update behavior belongs to the shared core."""
from __future__ import annotations

import janitor_update_core


def run_update(argv=None) -> int:
    print("\nTHE JANITOR: Updating the Janitor installation.\n")
    return janitor_update_core.run_janitor_update(argv)


if __name__ == "__main__":
    import sys
    sys.exit(run_update(sys.argv[1:]))
