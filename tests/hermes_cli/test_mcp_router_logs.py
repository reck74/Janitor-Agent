"""MCP log responses contain only the requested profile/server/spawn and redact secrets."""

import io
import os
from pathlib import Path
import threading

import pytest

from janitor_ext.mcp_logs import ServerStderrLog, read_server_stderr


def _client(authenticated=True):
    from starlette.testclient import TestClient
    from hermes_cli.web_server import app, _SESSION_HEADER_NAME, _SESSION_TOKEN

    app.state.auth_required = False
    return TestClient(app, headers={_SESSION_HEADER_NAME: _SESSION_TOKEN} if authenticated else {})


def test_missing_capture_and_legacy_shared_log_are_not_misattributed(tmp_path):
    assert read_server_stderr(tmp_path, "alpha") == {"available": False, "lines": [], "size_bytes": 0}
    (tmp_path / "logs").mkdir()
    (tmp_path / "logs/mcp-stderr.log").write_text(
        "===== [2026-08-09 15:42:16] starting MCP server 'alpha' =====\nlegacy\n"
        "[2026-10-15 09:00:00] ===== starting MCP server 'alpha' =====\nnew shared\n")
    assert not read_server_stderr(tmp_path, "alpha")["available"]


def test_concurrent_servers_never_share_lines(tmp_path):
    shared = io.StringIO()
    alpha = ServerStderrLog(shared, tmp_path, "alpha")
    beta = ServerStderrLog(shared, tmp_path, "beta")
    start = threading.Barrier(3)

    def write(log, name):
        start.wait(timeout=5)
        for i in range(30):
            log.write(f"{name} {i}\n")

    workers = [threading.Thread(target=write, args=(alpha, "alpha")),
               threading.Thread(target=write, args=(beta, "beta"))]
    for worker in workers:
        worker.start()
    start.wait(timeout=5)
    for worker in workers:
        worker.join(timeout=5)
        assert not worker.is_alive()
    assert read_server_stderr(tmp_path, "alpha")["lines"] == [f"alpha {i}" for i in range(30)]
    assert read_server_stderr(tmp_path, "beta")["lines"] == [f"beta {i}" for i in range(30)]


def test_exact_server_profile_and_latest_spawn_are_isolated(tmp_path):
    home = tmp_path / "primary"
    other = tmp_path / "secondary"
    old = ServerStderrLog(io.StringIO(), home, "minimax")
    old.write("old run\n")
    current = ServerStderrLog(io.StringIO(), home, "minimax")
    current.write("current run\n")
    old.write("late old process\n")
    ServerStderrLog(io.StringIO(), home, "minimax-coding").write("other server\n")
    ServerStderrLog(io.StringIO(), other, "minimax").write("other profile\n")
    assert read_server_stderr(home, "minimax")["lines"] == ["current run"]
    assert read_server_stderr(other, "minimax")["lines"] == ["other profile"]


def test_secret_headers_are_redacted_on_disk_and_in_response(tmp_path):
    shared = io.StringIO()
    capture = ServerStderrLog(shared, tmp_path, "alpha")
    capture.write("Authorization: Bearer janitor-audit-fake-token\n")
    capture.write("https://janitor-user:private-pass@example.invalid/mcp\n")
    assert "private-pass" not in shared.getvalue()
    assert "janitor-audit-fake-token" not in shared.getvalue()
    assert "private-pass" not in capture.path.read_text()
    assert "janitor-user" not in str(read_server_stderr(tmp_path, "alpha"))
    assert "janitor-audit-fake-token" not in capture.path.read_text()
    assert "janitor-audit-fake-token" not in str(read_server_stderr(tmp_path, "alpha"))


def test_capture_is_bounded_and_tail_is_respected(tmp_path):
    capture = ServerStderrLog(io.StringIO(), tmp_path, "alpha")
    capture.write("x\n" * 600_000)
    capture.write("one\ntwo\nthree\n")
    assert capture.path.stat().st_size < 1024 * 1024
    assert read_server_stderr(tmp_path, "alpha", tail=2)["lines"] == ["two", "three"]
    assert read_server_stderr(tmp_path, "alpha", tail=0)["lines"] == []


def test_server_name_cannot_escape_capture_directory(tmp_path):
    capture = ServerStderrLog(io.StringIO(), tmp_path, "../../outside")
    capture.write("inside\n")
    assert capture.path.is_relative_to(tmp_path / "logs/mcp-servers")
    assert read_server_stderr(tmp_path, "../../outside")["lines"] == ["inside"]


@pytest.mark.platforms("posix")
def test_log_permissions_are_private(tmp_path):
    capture = ServerStderrLog(io.StringIO(), tmp_path, "alpha")
    assert capture.path.stat().st_mode & 0o777 == 0o600


def test_restarts_keep_bounded_run_history(tmp_path):
    for i in range(8):
        ServerStderrLog(io.StringIO(), tmp_path, "alpha").write(f"run {i}\n")
    assert len(list((tmp_path / "logs/mcp-servers").rglob("*.log"))) == 5
    assert read_server_stderr(tmp_path, "alpha")["lines"] == ["run 7"]


def test_http_logs_require_dashboard_auth_and_validate_tail():
    assert _client(False).get("/api/mcp/servers/alpha/logs").status_code == 401
    for tail in (-1, 1001):
        assert _client().get(f"/api/mcp/servers/alpha/logs?tail={tail}").status_code == 400


def test_http_logs_return_real_capture_without_absolute_path(tmp_path, monkeypatch):
    import hermes_constants

    monkeypatch.setattr(hermes_constants, "get_hermes_home", lambda: tmp_path)
    capture = ServerStderrLog(io.StringIO(), tmp_path, "alpha")
    capture.write("a1\na2\n")
    response = _client().get("/api/mcp/servers/alpha/logs?tail=1")
    assert response.status_code == 200
    assert response.json()["lines"] == ["a2"]
    assert str(tmp_path) not in response.text
    assert not _client().get("/api/mcp/servers/unknown/logs").json()["available"]


@pytest.mark.parametrize("failure", ["capture", "redactor"])
def test_stderr_fallback_never_writes_unredacted_credentials(tmp_path, monkeypatch, failure):
    import janitor_ext.mcp_logs as logs
    import hermes_constants

    monkeypatch.setattr(hermes_constants, "get_hermes_home", lambda: tmp_path)
    def fail(*args, **kwargs):
        raise OSError("synthetic failure")
    monkeypatch.setattr(logs, "ServerStderrLog" if failure == "capture" else "_redact", fail)
    shared = io.StringIO()
    capture = logs.capture_server_stderr(shared, "alpha")
    raw = "Authorization: Bearer janitor-fallback-test-token\n"
    assert capture.write(raw) == len(raw)
    capture.flush()
    assert shared.getvalue()
    assert "janitor-fallback-test-token" not in shared.getvalue()


def test_scoped_capture_survives_closed_shared_sink(tmp_path):
    shared = io.StringIO()
    capture = ServerStderrLog(shared, tmp_path, "alpha")
    shared.close()
    assert capture.write("alpha survived\n") == len("alpha survived\n")
    assert read_server_stderr(tmp_path, "alpha")["lines"] == ["alpha survived"]
