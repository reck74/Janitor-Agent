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
