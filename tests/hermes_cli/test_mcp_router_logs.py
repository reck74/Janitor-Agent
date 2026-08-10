"""Tests for the MCP dashboard router: GET /api/mcp/servers/{name}/logs.

Covers _slice_mcp_log_for_server (Task 2 pure helper) and the route
itself (Task 4).
"""

from pathlib import Path
from unittest.mock import patch

import pytest


# --- Header constant must match tools/mcp_tool.py:_write_stderr_log_header ---
_HEADER_FMT = "===== [{ts}] starting MCP server '{name}' ====="


def _write_log(log_path: Path, blocks: list[tuple[str, list[str]]]) -> None:
    """Write a fake mcp-stderr.log with the given (server_name, lines) blocks."""
    from datetime import datetime
    text_parts = []
    for i, (srv, lines) in enumerate(blocks):
        ts = datetime(2026, 1, 1, 0, 0, i).strftime("%Y-%m-%d %H:%M:%S")
        text_parts.append(_HEADER_FMT.format(ts=ts, name=srv))
        text_parts.extend(lines)
    log_path.write_text("\n".join(text_parts) + "\n", encoding="utf-8")


# === Task 2: pure helper tests ===


def test_slice_pure_helper_missing_file_returns_not_available(tmp_path):
    """Missing log_path → available=False, lines=[], size_bytes=0."""
    from hermes_cli.mcp_config import _slice_mcp_log_for_server

    missing = tmp_path / "does-not-exist.log"
    result = _slice_mcp_log_for_server("alpha", missing, tail=200)
    assert result == {"available": False, "lines": [], "size_bytes": 0}


def test_slice_pure_helper_empty_file_returns_not_available(tmp_path):
    """Empty log file → available=False (no header was ever written)."""
    from hermes_cli.mcp_config import _slice_mcp_log_for_server

    log_path = tmp_path / "mcp-stderr.log"
    log_path.write_text("", encoding="utf-8")
    result = _slice_mcp_log_for_server("alpha", log_path, tail=200)
    assert result["available"] is False
    assert result["lines"] == []
    assert result["size_bytes"] == 0


def test_slice_pure_helper_returns_only_requested_server(tmp_path):
    """Two server blocks (alpha, beta) → alpha request returns only alpha."""
    from hermes_cli.mcp_config import _slice_mcp_log_for_server

    log_path = tmp_path / "mcp-stderr.log"
    _write_log(log_path, [
        ("alpha", ["alpha line 1", "alpha line 2"]),
        ("beta", ["beta line 1"]),
    ])

    result = _slice_mcp_log_for_server("alpha", log_path, tail=200)
    assert result["available"] is True
    assert "alpha line 1" in result["lines"]
    assert "alpha line 2" in result["lines"]
    assert not any("beta" in line for line in result["lines"])


def test_slice_pure_helper_exact_name_match_no_substring(tmp_path):
    """'minimax' must not match 'minimax-coding' header."""
    from hermes_cli.mcp_config import _slice_mcp_log_for_server

    log_path = tmp_path / "mcp-stderr.log"
    _write_log(log_path, [
        ("minimax-coding", ["coding line"]),
        ("minimax", ["minimax line"]),
    ])

    result = _slice_mcp_log_for_server("minimax", log_path, tail=200)
    assert result["available"] is True
    assert "minimax line" in result["lines"]
    assert not any("coding" in line for line in result["lines"])


def test_slice_pure_helper_returns_most_recent_run(tmp_path):
    """Server restarted twice → returns the LAST run's lines only."""
    from hermes_cli.mcp_config import _slice_mcp_log_for_server

    log_path = tmp_path / "mcp-stderr.log"
    _write_log(log_path, [
        ("alpha", ["old run line"]),
        ("beta", ["beta interrupting"]),  # another server starts
        ("alpha", ["new run line"]),       # alpha restarts
    ])

    result = _slice_mcp_log_for_server("alpha", log_path, tail=200)
    assert result["available"] is True
    assert "new run line" in result["lines"]
    assert "old run line" not in result["lines"]  # only most recent run


def test_slice_pure_helper_tail_clamping(tmp_path):
    """tail=2 on a 5-line slice returns only the last 2 lines."""
    from hermes_cli.mcp_config import _slice_mcp_log_for_server

    log_path = tmp_path / "mcp-stderr.log"
    _write_log(log_path, [
        ("alpha", [f"line {i}" for i in range(5)]),
    ])

    result = _slice_mcp_log_for_server("alpha", log_path, tail=2)
    assert result["available"] is True
    assert len(result["lines"]) == 2
    assert "line 3" in result["lines"]
    assert "line 4" in result["lines"]
    assert "line 0" not in result["lines"]


def test_slice_pure_helper_unknown_server_returns_not_available(tmp_path):
    """Server never started → available=False but size_bytes reflects file."""
    from hermes_cli.mcp_config import _slice_mcp_log_for_server

    log_path = tmp_path / "mcp-stderr.log"
    _write_log(log_path, [("alpha", ["alpha line"])])

    result = _slice_mcp_log_for_server("never-started", log_path, tail=200)
    assert result["available"] is False
    assert result["lines"] == []
    assert result["size_bytes"] == log_path.stat().st_size


def test_slice_pure_helper_large_file_only_reads_tail(tmp_path):
    """Files larger than 256KB are read from the end only.

    A 500KB file where the requested server's only header is in the FIRST
    256KB (i.e. older than what we read) → available=False. This documents
    the cap, not a bug: very old starts are out of scope for the Logs UI.
    """
    from hermes_cli.mcp_config import _slice_mcp_log_for_server

    log_path = tmp_path / "mcp-stderr.log"
    with log_path.open("w", encoding="utf-8") as f:
        f.write(_HEADER_FMT.format(ts="2020-01-01 00:00:00", name="alpha") + "\n")
        f.write("alpha old line\n")
        f.write("x" * 600_000 + "\n")  # > 256KB of filler pushes alpha out of tail
    result = _slice_mcp_log_for_server("alpha", log_path, tail=200)
    assert result["available"] is False
