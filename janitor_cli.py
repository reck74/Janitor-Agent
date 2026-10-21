"""Compatibility alias for ``janitor.cli``.

Installs created before Janitor 1.0 have a ``janitor`` console script that
runs ``from janitor_cli import main``, and their editable-install finder only
knows the old top-level module names. This module must keep working until
the venv is reinstalled with the ``janitor`` package registered.
"""

import os
import sys

_REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from janitor import cli as _impl  # noqa: E402

if __name__ == "__main__":
    _impl.main()
else:
    sys.modules[__name__] = _impl
