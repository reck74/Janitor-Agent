#!/usr/bin/env python3
"""Send ONE WhatsApp text through the local WAHA, only on the user's direct order.

  preview --chat ID --text TEXT                    no network; prints the message + DIGEST
  send    --chat ID --text TEXT --confirm DIGEST   POST /api/sendText, once

The DIGEST is bound to the session, the recipient and the exact text: changing any of
them after the user approved the preview makes ``send`` refuse without touching the
network, and a mismatch never reveals the right code. This file is the only place in
the skill that can write to WhatsApp; ``waha_audit.py`` cannot.

Exit codes: 0 ok, 1 refused/failed (``ok: false`` + ``reason``), 2 ``HERMES_HOME`` unset.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from waha_common import (  # noqa: E402
    Refused,
    connection,
    emit,
    hint,
    load_state,
    profile_home,
    refuse,
    send_digest,
    validate_chat_id,
)

MAX_TEXT_CHARS = 4000
_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def checked(args) -> tuple[str, str]:
    chat = validate_chat_id(args.chat)
    text = args.text
    if not text.strip():
        raise Refused("empty_text", "El mensaje está vacío.")
    if len(text) > MAX_TEXT_CHARS:
        raise Refused("text_too_long", f"Máximo {MAX_TEXT_CHARS} caracteres.", length=len(text))
    return chat, text


def post_text(base: str, key: str, session: str, chat: str, text: str) -> dict:
    body = json.dumps({"session": session, "chatId": chat, "text": text}).encode("utf-8")
    request = urllib.request.Request(base + "/api/sendText", data=body, method="POST",
                                     headers={"X-Api-Key": key, "Content-Type": "application/json"})
    try:
        with _OPENER.open(request, timeout=30) as resp:
            reply = json.loads(resp.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as exc:
        raise Refused("send_failed", f"WAHA respondió {exc.code}; el mensaje no salió.", status=exc.code) from None
    except (urllib.error.URLError, OSError, ValueError):
        raise Refused("waha_unreachable", "WAHA no responde; el mensaje no salió.") from None
    return {"id": reply.get("id") if isinstance(reply, dict) else None}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="waha_send.py", description="Send one confirmed WhatsApp text")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("preview", "send"):
        p = sub.add_parser(name)
        p.add_argument("--chat", required=True)
        p.add_argument("--text", required=True)
        if name == "send":
            p.add_argument("--confirm", required=True)
    args = parser.parse_args(argv)

    profile = profile_home()
    if profile is None:
        hint("HERMES_HOME no está definido: ejecuta esto desde el terminal del agente.")
        emit({"command": args.command, "ok": False, "reason": "hermes_home_unset"})
        return 2
    session = load_state(profile)["session"]
    try:
        chat, text = checked(args)
        digest = send_digest(session, chat, text)
        if args.command == "preview":
            return emit({"command": "preview", "ok": True, "session": session, "chat": chat,
                         "text": text, "digest": digest})
        if args.confirm != digest:
            raise Refused("digest_mismatch",
                          "El código no corresponde a este destinatario y este texto. Haz `preview`, "
                          "enséñaselo al usuario tal cual y espera su sí.")
        base, key = connection(profile)
        sent = post_text(base, key, session, chat, text)
        return emit({"command": "send", "ok": True, "chat": chat, "message_id": sent["id"]})
    except Refused as exc:
        return refuse(args.command, exc)


if __name__ == "__main__":
    sys.exit(main())
