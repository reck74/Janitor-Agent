"""Compatibility alias for ``janitor.tips_es`` (pre-1.0 import path)."""

import sys

from janitor import tips_es as _impl

sys.modules[__name__] = _impl
