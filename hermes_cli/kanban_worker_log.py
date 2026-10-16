"""Attempt-scoped diagnostics over append-only Kanban worker history."""
from __future__ import annotations

import re
from typing import Optional
from hermes_cli.quiet_single_query import KANBAN_WORKER_EXIT_TRAILER

_ATTEMPT_START = "HERMES_KANBAN_ATTEMPT_START:"


def begin_attempt(stream, run_id):
    """Fence old output before the child can emit a byte, including a killed child."""
    stream.write(f"\n{_ATTEMPT_START}{run_id}\n".encode())
    stream.flush()


def _attempt_output(task_id, board):
    from hermes_cli import kanban_db
    raw = kanban_db.read_worker_log(task_id, tail_bytes=4000, board=board) or ""
    # If the marker fell outside the tail, the tail contains only this run.
    # Marker-free legacy logs retain their pre-upgrade behavior.
    marker = raw.rfind("\n" + _ATTEMPT_START)
    if marker >= 0:
        return raw[raw.find("\n", marker + 1) + 1:]
    return raw


_EXIT_TRAILER_RE = re.compile(
    r"^" + re.escape(KANBAN_WORKER_EXIT_TRAILER) + r"(\d+)\s*$", re.MULTILINE,
)


def exit_code(task_id: str, board: Optional[str] = None) -> Optional[int]:
    """Exit code from the trailer the worker CLI wrote to its own log; None when absent.

    The durable twin of ``_recent_worker_exits``: written by the worker itself
    (``hermes_cli.quiet_single_query.exit_single_query``), so it is there whether
    or not the process running this sweep ever reaped the worker. Last trailer
    wins within the latest attempt only; prior attempts remain in the log.
    """
    try:
        raw = _attempt_output(task_id, board)
    except (OSError, ValueError):
        return None
    matches = _EXIT_TRAILER_RE.findall(raw or "")
    return int(matches[-1]) if matches else None


_LOG_CHROME = re.compile(r"[─━═╭╮╰╯│┃┌┐└┘]+|☤\s*Hermes")


def _exit_summary_marker() -> str:
    """The CLI exit-summary header (``cli_session_mixin.show_exit_summary``), in the active language."""
    from agent.i18n import t
    return t("cli.session.exit_resume_hint")


def _log_noise_prefixes() -> tuple[str, ...]:
    from agent.i18n import t
    return ("session_id:", "Query:", t("cli.chat.initializing_agent"))


def final_output(task_id: str, board: Optional[str] = None) -> str:
    """Best-effort read of a dead worker's last printed text, for the board diagnostic.

    A ``chat -q`` worker's stdout/stderr are redirected to its per-task log
    (``_default_spawn``), so when it exits without a terminal board call the
    reason is usually sitting there: the model's own explanation of why it could
    not comply (#88603), or the rendered provider error (#46593). The reap used to
    discard it in favour of a canned message on every retry. Trims the CLI exit
    summary, rule lines and the ``session_id:`` trailer; returns "" (never raises)
    on a missing/empty log.

    ``board`` must come from the dispatching tick: ambient current-board resolution
    is wrong for every board but the one the dispatcher thread happens to call
    "current", so the log would silently not be found.
    """
    try:
        raw = _attempt_output(task_id, board)
    except (OSError, ValueError):
        return ""
    if not raw:
        return ""
    raw = _EXIT_TRAILER_RE.sub("", raw)
    cut = raw.rfind(_exit_summary_marker())
    if cut != -1:
        raw = raw[:cut]
    lines = []
    for ln in raw.splitlines():
        ln = _LOG_CHROME.sub("", ln).strip()
        if ln and not ln.startswith(_log_noise_prefixes()):
            lines.append(ln)
    return " ".join(lines)[-400:]

