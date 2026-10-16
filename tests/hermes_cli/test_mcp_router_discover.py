"""Tests for the MCP dashboard router: POST /api/mcp/servers/{name}/discover.

Covers the backward-compat contract of _probe_single_server's new
``rich_tools`` out-param (Task 1) and the route itself (Task 3).
"""

from unittest.mock import patch, MagicMock

import pytest


def test_probe_descriptors_are_opt_in_and_shutdown_is_preserved(monkeypatch):
    import asyncio
    from types import SimpleNamespace
    from unittest.mock import AsyncMock
    from hermes_cli.mcp_config import _probe_single_server
    from tools import mcp_tool_discovery, mcp_tool_lifecycle, mcp_tool_loop

    tool = SimpleNamespace(name="ping", description="full descriptor", inputSchema={"type": "object"})
    shutdown = AsyncMock()
    server = SimpleNamespace(_tools=[tool], shutdown=shutdown, initialize_result=None)
    monkeypatch.setattr(mcp_tool_discovery, "_connect_server", AsyncMock(return_value=server))
    monkeypatch.setattr(mcp_tool_loop, "_ensure_mcp_loop", lambda: None)
    monkeypatch.setattr(mcp_tool_loop, "_run_on_mcp_loop", lambda coro, **kwargs: asyncio.run(coro))
    monkeypatch.setattr(mcp_tool_lifecycle, "_stop_mcp_loop_if_idle", lambda: None)
    config = {"url": "http://127.0.0.1:1/mcp", "tools": {"prompts": False, "resources": False}}
    plain = {}
    assert _probe_single_server("alpha", config, details=plain) == [("ping", "full descriptor")]
    assert "rich_tools" not in plain
    rich = {"rich_tools": []}
    assert _probe_single_server("alpha", config, details=rich) == [("ping", "full descriptor")]
    assert rich["rich_tools"] == [tool]
    assert shutdown.await_count == 2


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
        side_effect=TimeoutError(),
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


def test_discovery_requires_dashboard_auth():
    from starlette.testclient import TestClient
    from hermes_cli.web_server import app
    assert TestClient(app).post("/api/mcp/servers/alpha/discover").status_code == 401


def test_discovery_errors_redact_credential_headers():
    _seed_server("broken")
    with patch("hermes_cli.mcp_config._probe_single_server",
               side_effect=ConnectionError("Authorization: Bearer janitor-audit-fake-secret")):
        response = _client().post("/api/mcp/servers/broken/discover")
    assert response.status_code == 502
    assert "janitor-audit-fake-secret" not in response.text


def test_real_stdio_discovery_keeps_schema_and_captures_only_its_stderr(tmp_path):
    """Exercise the actual SDK/transport/cleanup path with a local protocol stand-in."""
    import sys
    from hermes_cli.mcp_config import _save_mcp_server

    child = tmp_path / "mcp_stand_in.py"
    child.write_text('''import json, sys
for line in sys.stdin:
    message = json.loads(line)
    if "id" not in message:
        continue
    method = message.get("method")
    if method == "initialize":
        print("janitor-real-mcp-stderr", file=sys.stderr, flush=True)
        result = {"protocolVersion": message["params"]["protocolVersion"],
                  "capabilities": {"tools": {}}, "serverInfo": {"name": "stand-in", "version": "1"}}
    elif method == "tools/list":
        result = {"tools": [{"name": "ping", "description": "local protocol stand-in",
                            "inputSchema": {"type": "object", "properties": {"value": {"type": "string"}}}}]}
    else:
        result = {}
    print(json.dumps({"jsonrpc": "2.0", "id": message["id"], "result": result}), flush=True)
''')
    assert _save_mcp_server("real-stdio", {"command": sys.executable, "args": [str(child)],
                                         "tools": {"prompts": False, "resources": False}, "connect_timeout": 10})
    response = _client().post("/api/mcp/servers/real-stdio/discover")
    assert response.status_code == 200, response.text
    assert response.json()["tools"][0]["inputSchema"]["properties"]["value"] == {"type": "string"}
    logs = _client().get("/api/mcp/servers/real-stdio/logs").json()
    assert logs["available"] is True
    assert any("janitor-real-mcp-stderr" in line for line in logs["lines"])


def test_discovery_errors_redact_url_userinfo():
    _seed_server("alpha")
    client = _client()
    with patch("hermes_cli.mcp_config._probe_single_server", side_effect=ConnectionError(
            "GET https://janitor-user:private-pass@example.invalid/mcp")):
        response = client.post("/api/mcp/servers/alpha/discover")
    assert response.status_code == 502
    assert "private-pass" not in response.text and "janitor-user" not in response.text
    assert "example.invalid" in response.text


def test_discovery_and_log_routes_have_one_authenticated_owner():
    from hermes_cli.web_routers.mcp import router
    from janitor_ext import mcp_dashboard

    for suffix, endpoint in (("discover", mcp_dashboard.discover_mcp_server),
                             ("logs", mcp_dashboard.get_mcp_server_logs)):
        matches = [route for route in router.routes
                   if route.path == "/api/mcp/servers/{name}/" + suffix]
        assert len(matches) == 1
        assert matches[0].endpoint is endpoint
