"""Janitor MCP descriptor discovery and per-server log routes."""

from __future__ import annotations

import asyncio
from typing import Optional

from fastapi import APIRouter, HTTPException, Request

from hermes_cli.web_routers._common import config_scoped_to_thread

router = APIRouter()


def _require_dashboard_token(request: Request) -> None:
    from hermes_cli.web_server import _require_token

    _require_token(request)


@router.post("/api/mcp/servers/{name}/discover")
async def discover_mcp_server(name: str, request: Request, profile: Optional[str] = None):
    """Discover descriptors without registering tools or changing a conversation's toolset."""
    from hermes_cli.mcp_config import (
        _get_mcp_servers, _probe_single_server, _unwrap_exception_group, redact_mcp_probe_text,
    )
    from tools.mcp_tool_common import mcp_server_enabled
    from tui_gateway.mcp_rpc_helpers import server_configs_with_sources

    _require_dashboard_token(request)

    def _read():
        return server_configs_with_sources(_get_mcp_servers())[0]

    servers = await config_scoped_to_thread(profile, _read)
    if name not in servers:
        raise HTTPException(status_code=404, detail=f"MCP server '{name}' not found")
    config = servers[name]
    if not mcp_server_enabled(config):
        raise HTTPException(status_code=409, detail=f"MCP server '{name}' is disabled")
    details = {"rich_tools": []}

    def _probe():
        _probe_single_server(name, config, details=details)
        return details

    try:
        details = await config_scoped_to_thread(profile, _probe)
    except asyncio.CancelledError:
        raise
    except Exception as exc:  # health: allow BLE001 -- arbitrary MCP SDK failures become redacted HTTP errors; raw tracebacks may expose credentials
        root = _unwrap_exception_group(exc)
        if isinstance(root, TimeoutError):
            raise HTTPException(status_code=504, detail=f"MCP server '{name}' timed out on tools/list") from None
        unreachable = isinstance(root, (ConnectionError, OSError))
        status = 502 if unreachable else 500
        prefix = "unreachable" if unreachable else "discover failed"
        raise HTTPException(status_code=status, detail=f"{prefix}: {redact_mcp_probe_text(root)}") from None

    descriptors = [
        {"name": tool.name, "description": getattr(tool, "description", "") or "",
         "inputSchema": getattr(tool, "inputSchema", getattr(tool, "input_schema", None))}
        for tool in details["rich_tools"]
    ]
    return {"name": name, "tools": descriptors, "count": len(descriptors),
            "prompts": details.get("prompts", 0), "resources": details.get("resources", 0)}


@router.get("/api/mcp/servers/{name}/logs")
async def get_mcp_server_logs(name: str, request: Request, tail: int = 200, profile: Optional[str] = None):
    from hermes_constants import get_hermes_home
    from janitor_ext.mcp_logs import read_server_stderr

    _require_dashboard_token(request)
    if not 0 <= tail <= 1000:
        raise HTTPException(status_code=400, detail="tail must be between 0 and 1000")
    result = await config_scoped_to_thread(profile, lambda: read_server_stderr(get_hermes_home(), name, tail))
    return {"name": name, **result}
