"""The gateway's cached-agent message count re-baselines against the real DB.

``GatewayRunner._session_db`` is an ``AsyncSessionDB`` facade, so
``_refresh_agent_cache_message_count`` must ``await`` it directly. Wrapping the
facade in ``asyncio.to_thread`` returns an un-awaited coroutine; the method
swallows the resulting error, the count never re-baselines, and every turn
rebuilds the agent (destroying prompt caching). The retired
``gateway-cache-refresh`` touchpoint shipped exactly that, and its sync-stub
test could not see it.
"""

from __future__ import annotations

import asyncio
import threading


def test_refresh_reads_message_count_through_async_session_db(tmp_path):
    from gateway.run import GatewayRunner
    from hermes_state import AsyncSessionDB, SessionDB

    db = SessionDB(db_path=tmp_path / "state.db")
    try:
        db.create_session("sid-1", "telegram")
        for role in ("user", "assistant", "user"):
            db.append_message("sid-1", role, content="hi")
        live = db.get_session("sid-1")["message_count"]
        assert live == 3

        runner = object.__new__(GatewayRunner)
        runner._session_db = AsyncSessionDB(db)
        runner._agent_cache_lock = threading.Lock()
        agent = object()
        runner._agent_cache = {"key": (agent, "sig", 1, "sid-1")}

        asyncio.run(runner._refresh_agent_cache_message_count("key", "sid-1"))

        assert runner._agent_cache["key"] == (agent, "sig", live, "sid-1")
    finally:
        db.close()
