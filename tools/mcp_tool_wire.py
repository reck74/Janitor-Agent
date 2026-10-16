"""MCP wire compatibility without changing SDK request IDs, metadata or recovery policy."""

from __future__ import annotations

from contextlib import asynccontextmanager
from copy import copy

from tools.mcp_tool_errors import MCPHTTPAuthenticationError


def without_empty_request_meta(envelope):
    """Copy only a request carrying empty params._meta; preserve all useful metadata.

    SDK 1.x wraps JSON-RPC in a RootModel; 2.x carries the request directly.
    Transport metadata, request IDs and nested tool arguments remain untouched.
    """
    message = envelope.message
    request = getattr(message, "root", message)
    params = getattr(request, "params", None)
    if (getattr(request, "id", None) is None or not getattr(request, "method", None)
            or not isinstance(params, dict) or "_meta" not in params
            or params["_meta"] not in ({}, None)):
        return envelope
    cleaned = dict(params)
    del cleaned["_meta"]
    request = request.model_copy(update={"params": cleaned})
    result = copy(envelope)
    result.message = message.model_copy(update={"root": request}) if hasattr(message, "root") else request
    return result


class RequestMetadataStream:
    """Delegate stream lifetime to the SDK while dropping information-free request metadata."""

    def __init__(self, stream):
        self._stream = stream

    def __getattr__(self, name):
        return getattr(self._stream, name)

    async def send(self, envelope):
        await self._stream.send(without_empty_request_meta(envelope))

    async def __aenter__(self):
        await self._stream.__aenter__()
        return self

    async def __aexit__(self, *args):
        return await self._stream.__aexit__(*args)


@asynccontextmanager
async def classify_http_auth_failure(server):
    """Restore a folded SDK 401 only for the RPC owning the server's existing lock.

    Clear stale handshake/previous-call evidence first. Keepalive and utility calls use
    that same lock, so another request cannot lend its rejection to this call.
    """
    rejection = getattr(server, "_http_rejection", None)
    if isinstance(rejection, dict):
        rejection.clear()
    try:
        yield
    except Exception as exc:
        opaque = (getattr(getattr(exc, "error", None), "code", None) == -32603
                  and "server returned an error response" in str(exc).lower())
        if (opaque and isinstance(rejection, dict) and rejection.get("status") == 401
                and rejection.get("method") == "POST"):
            raise MCPHTTPAuthenticationError("MCP server rejected the request with HTTP 401") from exc
        raise
