"""Shared helpers for the janitor-waha scripts: homes, audit state, credentials, loopback URL.

Nothing here talks to the network. ``waha_audit.py`` owns the only GET helper and
``waha_send.py`` the only POST, so the read path has no code that could send.

State lives in ``$HERMES_HOME/janitor/waha/`` (the active profile):
  ``audit.json``   privacy acknowledgement, allowed chats, window and retention
  ``findings/``    one JSON file per saved summary; pruned after ``retention_days``
Message text is never written there by these scripts.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import re
import sys
import tempfile
import time
import urllib.parse
from pathlib import Path

SCHEMA_VERSION = 1
DEFAULT_SESSION = "default"
DEFAULT_BASE_URL = "http://127.0.0.1:3000"
LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})
DEFAULT_WINDOW_DAYS = 3
MAX_WINDOW_DAYS = 14
DEFAULT_RETENTION_DAYS = 30
MAX_RETENTION_DAYS = 90
# A WhatsApp chat id (JID): user, group, LID or newsletter.
CHAT_ID_RE = re.compile(r"^[0-9A-Za-z._:-]{3,64}@(c\.us|g\.us|lid|s\.whatsapp\.net|newsletter)$")


class Refused(Exception):
    """A contract refusal: printed as ``ok: false`` + ``reason``, exit 1."""

    def __init__(self, reason: str, hint: str = "", **extra) -> None:
        super().__init__(reason)
        self.reason, self.hint, self.extra = reason, hint, extra


def hint(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


def emit(doc: dict) -> int:
    doc.setdefault("schema_version", SCHEMA_VERSION)
    print(json.dumps(doc, ensure_ascii=False, indent=2), flush=True)
    return 0 if doc.get("ok", True) else 1


def refuse(command: str, exc: Refused) -> int:
    if exc.hint:
        hint(exc.hint)
    return emit({"command": command, "ok": False, "reason": exc.reason, **exc.extra})


# ── homes and state ─────────────────────────────────────────────────────


def profile_home() -> Path | None:
    raw = (os.environ.get("HERMES_HOME") or "").strip()
    return Path(raw).expanduser() if raw else None


def root_home(profile: Path) -> Path:
    """The Janitor root (where ``deploy.sh`` keeps ``docker/waha.env``)."""
    raw = (os.environ.get("JANITOR_HOME") or "").strip()
    if raw:
        return Path(raw).expanduser()
    return profile.parent.parent if profile.parent.name == "profiles" else profile


def state_dir(profile: Path) -> Path:
    return profile / "janitor" / "waha"


def atomic_write(path: Path, data: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(path.parent, 0o700)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(data)
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise


def default_state() -> dict:
    return {"privacy_ack": None, "session": DEFAULT_SESSION, "chats": [],
            "window_days": DEFAULT_WINDOW_DAYS, "retention_days": DEFAULT_RETENTION_DAYS}


def load_state(profile: Path) -> dict:
    state = default_state()
    try:
        data = json.loads((state_dir(profile) / "audit.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return state
    if isinstance(data, dict):
        state.update({k: data[k] for k in state if k in data})
    state["chats"] = [c for c in state["chats"] if isinstance(c, str) and CHAT_ID_RE.match(c)]
    state["window_days"] = clamp(state["window_days"], DEFAULT_WINDOW_DAYS, MAX_WINDOW_DAYS)
    state["retention_days"] = clamp(state["retention_days"], DEFAULT_RETENTION_DAYS, MAX_RETENTION_DAYS)
    return state


def save_state(profile: Path, state: dict) -> None:
    atomic_write(state_dir(profile) / "audit.json", json.dumps(state, ensure_ascii=False, indent=2))


def clamp(value, default: int, ceiling: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    return max(1, min(number, ceiling))


def findings_dir(profile: Path) -> Path:
    return state_dir(profile) / "findings"


def prune_findings(profile: Path, retention_days: int, now: float | None = None) -> list[str]:
    """Delete saved findings older than the retention window. Returns the removed names."""
    cutoff = (now or time.time()) - retention_days * 86400
    removed = []
    folder = findings_dir(profile)
    if not folder.is_dir():
        return removed
    for path in sorted(folder.glob("*.json")):
        with contextlib.suppress(OSError):
            if path.stat().st_mtime < cutoff:
                path.unlink()
                removed.append(path.name)
    return removed


# ── WAHA connection ─────────────────────────────────────────────────────


def read_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return values
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip().removeprefix("export ").strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        values[key] = value
    return values


def connection(profile: Path) -> tuple[str, str]:
    """``(base_url, api_key)``. The URL must be loopback; the key is never printed."""
    root = root_home(profile)
    sources = [os.environ, read_env_file(profile / ".env"), read_env_file(root / ".env"),
               read_env_file(root / "docker" / "waha.env")]
    base = next((s["WAHA_BASE_URL"].strip() for s in sources[:3] if s.get("WAHA_BASE_URL", "").strip()),
                DEFAULT_BASE_URL)
    key = next((s["WAHA_API_KEY"].strip() for s in sources if s.get("WAHA_API_KEY", "").strip()), "")
    parsed = urllib.parse.urlsplit(base)
    if parsed.scheme not in ("http", "https") or (parsed.hostname or "") not in LOOPBACK_HOSTS:
        raise Refused("non_loopback_url",
                      "WAHA_BASE_URL no apunta a este equipo (127.0.0.1/localhost). Esta skill solo habla "
                      "con un WAHA local; corrige la variable.", base_url_host=parsed.hostname)
    if not key:
        raise Refused("api_key_missing",
                      "No encuentro WAHA_API_KEY. ¿Desplegaste WAHA? `janitor services deploy waha`.")
    return base.rstrip("/"), key


def validate_chat_id(chat: str) -> str:
    chat = chat.strip()
    if not CHAT_ID_RE.match(chat):
        raise Refused("invalid_chat_id",
                      f"«{chat}» no es un id de chat de WhatsApp (ej. 573001234567@c.us o …@g.us).",
                      chat=chat)
    return chat


def path_segment(value: str) -> str:
    return urllib.parse.quote(value, safe="@.:")


def send_digest(session: str, chat: str, text: str) -> str:
    """Confirmation code bound to the exact session, recipient and text of one message."""
    payload = json.dumps(["janitor-waha-send", session, chat, text], ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:12]
