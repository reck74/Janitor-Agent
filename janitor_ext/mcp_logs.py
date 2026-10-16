"""Bounded, profile-owned stderr captures for Janitor's MCP Logs view."""

from __future__ import annotations

import hashlib
import json
import logging
import os
from pathlib import Path
import threading
import time
import uuid

_MAX_BYTES = 1024 * 1024
_READ_BYTES = 256 * 1024
_KEEP_RUNS = 5
_log = logging.getLogger(__name__)


def _server_directory(home: Path, name: str) -> Path:
    # Never interpolate server names into a filesystem path.
    digest = hashlib.sha256(name.encode("utf-8")).hexdigest()
    return home / "logs" / "mcp-servers" / digest


def _redact(text: str) -> str:
    from hermes_cli.mcp_config import redact_mcp_probe_text

    return redact_mcp_probe_text(text)


class RedactedStderrLog:
    """Redact before any sink, including fallback when scoped storage fails."""

    def __init__(self, shared):
        self.shared = shared

    def write(self, text: str):
        try:
            safe = _redact(text)
        except Exception:  # health: allow BLE001 -- fail closed without logging potentially secret-bearing redactor exceptions
            # A diagnostic failure cannot expose the unredacted input or exception.
            safe = "[MCP stderr redaction unavailable]\n"
            _log.debug("MCP stderr redaction unavailable")
        self._write_redacted(safe)
        return len(text)

    def _write_redacted(self, text: str):
        try:
            self.shared.write(text)
        except (OSError, ValueError):
            _log.debug("Could not append shared MCP stderr")

    def flush(self):
        try:
            self.shared.flush()
        except (OSError, ValueError):
            _log.debug("Could not flush shared MCP stderr")


class ServerStderrLog(RedactedStderrLog):
    """File-like sink: retain upstream's shared log and capture this child alone.

    The owning home is captured before the MCP reader thread starts. Each
    spawn gets its own file, so overlapping servers or restarts cannot mix.
    No handle survives a write; transport teardown remains upstream-owned.
    """

    def __init__(self, shared, home: Path, name: str):
        super().__init__(shared)
        self._lock = threading.Lock()
        directory = _server_directory(home, name)
        from hermes_constants import mkdir_under_hermes_home

        mkdir_under_hermes_home(directory)
        filename = f"{time.time_ns()}-{os.getpid()}-{uuid.uuid4().hex}.log"
        self.path = directory / filename
        self._append("")
        pointer = directory / f".current-{uuid.uuid4().hex}.tmp"
        try:
            fd = os.open(pointer, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump({"file": filename}, stream)
            os.replace(pointer, directory / "current.json")
        finally:
            pointer.unlink(missing_ok=True)
        for old in sorted(directory.glob("*.log"), reverse=True)[_KEEP_RUNS:]:
            try:
                old.unlink()
            except OSError:
                _log.debug("Could not prune an old MCP stderr capture", exc_info=True)

    def _append(self, text: str) -> None:
        flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND | getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(self.path, flags, 0o600)
        with os.fdopen(fd, "a", encoding="utf-8", errors="replace") as stream:
            stream.write(text)
        if self.path.stat().st_size > _MAX_BYTES:
            with self.path.open("rb") as stream:
                stream.seek(-_READ_BYTES, os.SEEK_END)
                remaining = stream.read().split(b"\n", 1)[-1]
            # Each sink has one reader; the lock covers append plus trimming.
            fd = os.open(self.path, os.O_WRONLY | os.O_TRUNC | getattr(os, "O_NOFOLLOW", 0))
            with os.fdopen(fd, "wb") as stream:
                stream.write(remaining)

    def _write_redacted(self, text: str):
        super()._write_redacted(text)
        try:
            with self._lock:
                self._append(text)
        except (OSError, ValueError):
            # Diagnostic capture must never disrupt or stop draining MCP stderr.
            _log.debug("Could not append scoped MCP stderr", exc_info=True)


def capture_server_stderr(shared, name: str):
    """Concrete transport hook; fallback still redacts the shared sink on I/O failure."""
    from hermes_constants import get_hermes_home

    try:
        return ServerStderrLog(shared, get_hermes_home(), name)
    except (OSError, ValueError):
        _log.debug("Could not create scoped MCP stderr capture", exc_info=True)
        return RedactedStderrLog(shared)


def read_server_stderr(home: Path, name: str, tail: int = 200) -> dict:
    """Latest spawn of exactly one server; legacy shared logs are never misattributed."""
    if not 0 <= tail <= 1000:
        raise ValueError("tail must be between 0 and 1000")
    empty = {"available": False, "lines": [], "size_bytes": 0}
    directory = _server_directory(home, name)
    try:
        metadata = json.loads((directory / "current.json").read_text(encoding="utf-8"))
        filename = metadata["file"]
        if not isinstance(filename, str) or Path(filename).name != filename or not filename.endswith(".log"):
            return empty
        path = directory / filename
        if path.is_symlink():
            return empty
        size = path.stat().st_size
        with path.open("rb") as stream:
            offset = max(0, size - _READ_BYTES)
            stream.seek(offset)
            raw = stream.read(_READ_BYTES)
        if offset:
            raw = raw.split(b"\n", 1)[-1]
        lines = _redact(raw.decode("utf-8", "replace")).splitlines()
        return {"available": True, "lines": lines[-tail:] if tail else [], "size_bytes": size}
    except (OSError, ValueError, KeyError, TypeError):
        return empty
