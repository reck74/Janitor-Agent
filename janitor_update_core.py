"""Compatibility alias for ``janitor.update_core`` (pre-1.0 import path)."""

import os
import sys

_REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from janitor import update_core as _impl  # noqa: E402

sys.modules[__name__] = _impl
