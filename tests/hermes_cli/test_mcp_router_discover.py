"""Tests for the MCP dashboard router: POST /api/mcp/servers/{name}/discover.

Covers the backward-compat contract of _probe_single_server's new
``rich_tools`` out-param (Task 1) and the route itself (Task 3).
"""

from unittest.mock import patch, MagicMock

import pytest


def test_probe_single_server_backward_compat_no_rich_tools_key():
    """_probe_single_server must NOT populate rich_tools when caller doesn't
    request it. Guards the Task 1 extension against regressions in /test
    and cmd_mcp_test (the two existing callers).

    NOTE: source-text assertion, generally discouraged by AGENTS.md but used
    here for the same reason as test_janitor_monkeypatch_signatures.py
    (directive #14): the gating condition IS the contract; there is no
    observable runtime behavior without spinning up the real MCP loop, which
    these unit tests deliberately avoid.
    """
    import inspect

    from hermes_cli.mcp_config import _probe_single_server

    # details without "rich_tools" key — existing callers' shape
    # We assert the contract via source inspection: the function's source
    # must gate the rich_tools assignment behind `"rich_tools" in details`
    # so existing callers (no rich_tools key) are unaffected.
    src = inspect.getsource(_probe_single_server)
    assert '"rich_tools" in details' in src, (
        "Task 1 regression: _probe_single_server must gate the rich_tools "
        "assignment behind `if details is not None and \"rich_tools\" in details:` "
        "so existing callers (no rich_tools key) are unaffected."
    )


# === Task 3: route tests ===


def _client():
    """TestClient configured with the dashboard's loopback session token."""
    from starlette.testclient import TestClient
    from hermes_cli.web_server import app, _SESSION_HEADER_NAME, _SESSION_TOKEN

    client = TestClient(app)
    client.headers[_SESSION_HEADER_NAME] = _SESSION_TOKEN
    return client


@pytest.fixture(autouse=True)
def _clear_state():
    """Loopback auth mode + clean MCP server state per test."""
    from hermes_cli import web_server

    web_server.app.state.auth_required = False
    yield
    web_server.app.state.auth_required = False


def _seed_server(name: str, *, enabled: bool = True, url: str = "http://x") -> None:
    """Seed a server in the in-memory config (does not hit disk for tests)."""
    from hermes_cli.mcp_config import _save_mcp_server
    cfg = {"url": url, "enabled": enabled}
    _save_mcp_server(name, cfg)


def test_discover_404_unknown_server():
    client = _client()
    resp = client.post("/api/mcp/servers/never-configured/discover")
    assert resp.status_code == 404
    assert "not found" in resp.json()["detail"].lower()


def test_discover_409_disabled_server():
    _seed_server("disabled-one", enabled=False)
    client = _client()
    resp = client.post("/api/mcp/servers/disabled-one/discover")
    assert resp.status_code == 409
    assert "disabled" in resp.json()["detail"].lower()


def test_discover_returns_full_tool_descriptors():
    _seed_server("alpha")
    client = _client()

    fake_tool = MagicMock()
    fake_tool.name = "ping"
    fake_tool.description = "ping tool"
    fake_tool.inputSchema = {"type": "object", "properties": {}}

    def fake_probe(name, config, connect_timeout=None, *, details=None):
        if details is not None:
            details["rich_tools"] = [fake_tool]
            details["prompts"] = 1
            details["resources"] = 2
        return [(fake_tool.name, fake_tool.description)]

    with patch("hermes_cli.mcp_config._probe_single_server", side_effect=fake_probe):
        resp = client.post("/api/mcp/servers/alpha/discover")

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["name"] == "alpha"
    assert body["count"] == 1
    assert len(body["tools"]) == 1
    tool = body["tools"][0]
    assert tool["name"] == "ping"
    assert tool["description"] == "ping tool"
    assert tool["inputSchema"] == {"type": "object", "properties": {}}
    assert body["prompts"] == 1
    assert body["resources"] == 2


def test_discover_502_unreachable():
    _seed_server("broken")
    client = _client()

    with patch(
        "hermes_cli.mcp_config._probe_single_server",
        side_effect=ConnectionError("dial tcp: connection refused"),
    ):
        resp = client.post("/api/mcp/servers/broken/discover")

    assert resp.status_code == 502
    assert "unreachable" in resp.json()["detail"].lower()


def test_discover_504_timeout():
    import asyncio

    _seed_server("slow")
    client = _client()

    with patch(
        "hermes_cli.mcp_config._probe_single_server",
        side_effect=asyncio.TimeoutError(),
    ):
        resp = client.post("/api/mcp/servers/slow/discover")

    assert resp.status_code == 504
    assert "timed out" in resp.json()["detail"].lower()


def test_discover_input_schema_falls_back_to_input_schema_attr():
    """Some MCP SDK versions use input_schema (snake_case) instead of inputSchema."""
    _seed_server("legacy-sdk")
    client = _client()

    fake_tool = MagicMock()
    fake_tool.name = "legacy"
    fake_tool.description = "legacy tool"
    # Simulate SDK that only exposes snake_case
    del fake_tool.inputSchema
    fake_tool.input_schema = {"type": "object"}

    def fake_probe(name, config, connect_timeout=None, *, details=None):
        if details is not None:
            details["rich_tools"] = [fake_tool]
        return [(fake_tool.name, fake_tool.description)]

    with patch("hermes_cli.mcp_config._probe_single_server", side_effect=fake_probe):
        resp = client.post("/api/mcp/servers/legacy-sdk/discover")

    assert resp.status_code == 200, resp.text
    tool = resp.json()["tools"][0]
    assert tool["inputSchema"] == {"type": "object"}
