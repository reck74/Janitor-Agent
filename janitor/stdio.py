"""UTF-8 console streams for paths that print before ``hermes_cli`` loads.

On Windows a redirected stdout (the desktop app capturing ``janitor update``,
a pipe) uses the ANSI code page (cp1252), so printing the Janitor banner
(«🔥», «→», «✓», acentos) raises ``UnicodeEncodeError``. ``hermes_cli``
repairs this when it is imported, but the early ``update`` intercept runs
before that and must keep working on a half-broken venv (directive #13), so
this module imports only the standard library.
"""

from __future__ import annotations

import os
import sys
from typing import Any, Optional, TextIO


def _is_utf8(stream: Optional[TextIO]) -> bool:
    encoding = (getattr(stream, "encoding", "") or "").lower().replace("-", "").replace("_", "")
    return encoding == "utf8"


def utf8_stream(stream: Optional[TextIO]) -> Optional[TextIO]:
    """Return ``stream`` writing UTF-8 with ``errors="replace"``.

    Reconfigures in place when possible (other holders of the object benefit);
    without ``reconfigure`` it reopens the file descriptor; a stream that
    supports neither is returned untouched.
    """
    if stream is None or _is_utf8(stream):
        return stream
    reconfigure: Any = getattr(stream, "reconfigure", None)
    try:
        if callable(reconfigure):
            reconfigure(encoding="utf-8", errors="replace")
            return stream
        return open(stream.fileno(), "w", encoding="utf-8", errors="replace",
                    buffering=1, closefd=False)
    except (AttributeError, OSError, ValueError):
        return stream


def ensure_utf8_stdio() -> None:
    """Make ``sys.stdout``/``sys.stderr`` UTF-8 and nudge children the same way."""
    repaired = False
    for name in ("stdout", "stderr"):
        stream = getattr(sys, name, None)
        if stream is None or _is_utf8(stream):
            continue
        fixed = utf8_stream(stream)
        if fixed is not stream:
            setattr(sys, name, fixed)
        repaired = repaired or _is_utf8(fixed)
    if repaired:
        os.environ.setdefault("PYTHONUTF8", "1")
        os.environ.setdefault("PYTHONIOENCODING", "utf-8")
