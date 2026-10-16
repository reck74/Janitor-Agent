"""Durable billing bounds for automatic triage decomposition.

Manual decomposition is an explicit retry. Automatic attempts are reserved
before network I/O, survive dispatcher restarts, and reset when the card's
input changes. The existing event log avoids a second state store.
"""
from __future__ import annotations

import hashlib
import json
import time

from hermes_cli import kanban_db as kb
from hermes_cli import kanban_db_connect as kbc

MAX_AUTO_ATTEMPTS = 3
RETRY_DELAY_SECONDS = 60


def reserve_attempt(task_id: str) -> str:
    """Return a refusal reason, or atomically reserve one automatic model call."""
    with kbc.connect_closing() as conn, kb.write_txn(conn):
        task = kb.get_task(conn, task_id)
        if task is None or task.status != "triage":
            return "task is no longer in triage"
        fingerprint = hashlib.sha256(json.dumps(
            [task.title, task.body, task.assignee, task.skills],
            ensure_ascii=False, separators=(",", ":"),
        ).encode()).hexdigest()
        rows = conn.execute(
            "SELECT payload, created_at FROM task_events WHERE task_id = ? "
            "AND kind = 'auto_decompose_attempted' ORDER BY id DESC LIMIT ?",
            (task_id, MAX_AUTO_ATTEMPTS),
        ).fetchall()
        attempts = []
        for row in rows:
            if kb._json_dict(row["payload"]).get("input") != fingerprint:
                break
            attempts.append(row)
        if len(attempts) >= MAX_AUTO_ATTEMPTS:
            return "automatic decomposition budget exhausted; edit the card or run hermes kanban decompose explicitly"
        now = int(time.time())
        if attempts and now - int(attempts[0]["created_at"]) < RETRY_DELAY_SECONDS * 2 ** (len(attempts) - 1):
            return "automatic decomposition is cooling down after an earlier attempt"
        kb._append_event(conn, task_id, "auto_decompose_attempted", {
            "input": fingerprint, "attempt": len(attempts) + 1,
            "limit": MAX_AUTO_ATTEMPTS,
        })
    return ""
