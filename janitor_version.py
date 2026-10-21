"""Compatibility alias for ``janitor.version``.

Core touchpoints (``cli.py``, ``hermes_cli/banner.py``,
``hermes_cli/_startup_fast.py``) import ``janitor_version`` by this name.
"""

import os
import sys

_REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from janitor import version as _impl  # noqa: E402

sys.modules[__name__] = _impl
