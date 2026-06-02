#!/usr/bin/env python3
"""
OpenCode Orchestrator - HTTP client for opencode serve REST API.

Wraps the opencode serve endpoints:
- Health check / port detection
- Session lifecycle (create, query, delete)
- Message send / receive (sync and async)
- Abort running sessions

Usage:
    orchestrator = OpenCodeOrchestrator(port=3000)
    await orchestrator.connect()  # verify health
    session_id = await orchestrator.create_session()
    response = await orchestrator.send_message(session_id, "analiza X")
    await orchestrator.close()
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger(__name__)

try:
    import httpx
except ImportError:
    raise ImportError("httpx is required: pip install httpx")


@dataclass
class OpenCodeMessage:
    id: str
    role: str
    content: str
    created_at: Optional[str] = None


@dataclass
class OpenCodeSession:
    id: str
    title: Optional[str] = None
    created_at: Optional[str] = None
    status: Optional[str] = None


@dataclass
class OpenCodeOrchestrator:
    """
    HTTP client for opencode serve API.

    Args:
        host: Host where opencode serve is running (default: localhost)
        port: Port number (default: 3000)
        password: Optional password for authenticated servers
        timeout: Request timeout in seconds (default: 300)
    """

    host: str = "localhost"
    port: int = 3000
    password: Optional[str] = None
    timeout: int = 300
    _client: Optional[httpx.AsyncClient] = field(default=None, init=False, repr=False)

    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}"

    @property
    def auth(self) -> Optional[httpx.BasicAuth]:
        return httpx.BasicAuth("opencode", self.password) if self.password else None

    async def __aenter__(self) -> "OpenCodeOrchestrator":
        await self.connect()
        return self

    async def __aexit__(self, *args) -> None:
        await self.close()

    async def connect(self) -> bool:
        """
        Establish connection and verify server health.

        Returns:
            True if server is healthy, raises exception otherwise.
        """
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            auth=self.auth,
            timeout=httpx.Timeout(self.timeout),
            follow_redirects=True,
        )
        response = await self._client.get("/global/health")
        response.raise_for_status()
        data = response.json()
        logger.info(f"Connected to opencode serve {data.get('version', 'unknown')}")
        return True

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None

    async def _request(self, method: str, path: str, **kwargs) -> dict[str, Any]:
        """Make an authenticated request to the opencode API."""
        if not self._client:
            raise RuntimeError("Not connected. Call connect() first.")
        response = await self._client.request(method, path, **kwargs)
        response.raise_for_status()
        return response.json()

    # -------------------------------------------------------------------------
    # Session Management
    # -------------------------------------------------------------------------

    async def list_sessions(self) -> list[OpenCodeSession]:
        """List all active sessions."""
        data = await self._request("GET", "/session")
        sessions = []
        for s in data.get("sessions", []):
            sessions.append(OpenCodeSession(
                id=s.get("id", ""),
                title=s.get("title"),
                created_at=s.get("createdAt"),
                status=s.get("status"),
            ))
        return sessions

    async def create_session(self, title: Optional[str] = None) -> str:
        """
        Create a new session.

        Returns:
            session_id (str)
        """
        body = {}
        if title:
            body["title"] = title
        data = await self._request("POST", "/session", json=body)
        return data.get("id", "")

    async def get_session(self, session_id: str) -> OpenCodeSession:
        """Get details of a specific session."""
        data = await self._request("GET", f"/session/{session_id}")
        return OpenCodeSession(
            id=data.get("id", ""),
            title=data.get("title"),
            created_at=data.get("createdAt"),
            status=data.get("status"),
        )

    async def delete_session(self, session_id: str) -> None:
        """Delete a session and all its data."""
        await self._request("DELETE", f"/session/{session_id}")

    async def abort_session(self, session_id: str) -> None:
        """Abort a running session."""
        await self._request("POST", f"/session/{session_id}/abort")

    async def get_session_diff(self, session_id: str) -> dict[str, Any]:
        """Get the diff for a session."""
        return await self._request("GET", f"/session/{session_id}/diff")

    async def get_session_messages(self, session_id: str) -> list[OpenCodeMessage]:
        """Get all messages in a session."""
        data = await self._request("GET", f"/session/{session_id}/message")
        messages = []
        for m in data.get("messages", []):
            messages.append(OpenCodeMessage(
                id=m.get("id", ""),
                role=m.get("role", ""),
                content=m.get("content", ""),
                created_at=m.get("createdAt"),
            ))
        return messages

    # -------------------------------------------------------------------------
    # Message / Prompt
    # -------------------------------------------------------------------------

    async def send_message(
        self,
        session_id: str,
        content: str,
        role: str = "user",
    ) -> OpenCodeMessage:
        """
        Send a message and wait for a reply (synchronous).

        Args:
            session_id: The session to send the message to
            content: The prompt / message content
            role: Message role (default: "user")

        Returns:
            OpenCodeMessage with the assistant's response
        """
        body = {"content": content}
        if role:
            body["role"] = role
        data = await self._request("POST", f"/session/{session_id}/message", json=body)
        return OpenCodeMessage(
            id=data.get("id", ""),
            role=data.get("role", ""),
            content=data.get("content", ""),
            created_at=data.get("createdAt"),
        )

    async def send_message_async(
        self,
        session_id: str,
        content: str,
        role: str = "user",
    ) -> str:
        """
        Send a message without waiting for reply (fire-and-forget).

        Args:
            session_id: The session to send the message to.
            content: The prompt / message content.
            role: Message role (default: "user").

        Returns:
            message_id of the queued message.
        """
        body = {"content": content}
        if role:
            body["role"] = role
        data = await self._request("POST", f"/session/{session_id}/prompt_async", json=body)
        return data.get("messageId", "")

    async def send_command(
        self,
        session_id: str,
        command: str,
    ) -> dict[str, Any]:
        """
        Execute a slash command in the session.

        Args:
            session_id: The session to execute the command in.
            command: The slash command to execute (e.g. "/help").

        Returns:
            Response data from the command endpoint.
        """
        return await self._request("POST", f"/session/{session_id}/command", json={"command": command})

    async def send_shell(
        self,
        session_id: str,
        command: str,
    ) -> dict[str, Any]:
        """
        Run a shell command in the session.

        Args:
            session_id: The session to run the command in.
            command: The shell command to execute.

        Returns:
            Response data from the shell endpoint.
        """
        return await self._request("POST", f"/session/{session_id}/shell", json={"command": command})


async def detect_opencode_port(host: str = "localhost", start_port: int = 3000, end_port: int = 3010) -> int | None:
    """
    Scan ports to find opencode serve.

    Returns:
        Port number if found, None otherwise.
    """
    for port in range(start_port, end_port + 1):
        try:
            async with httpx.AsyncClient(
                base_url=f"http://{host}:{port}",
                timeout=httpx.Timeout(5.0),
            ) as client:
                response = await client.get("/global/health")
                if response.status_code == 200:
                    logger.info(f"opencode serve found on port {port}")
                    return port
        except Exception:
            continue
    return None
