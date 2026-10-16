#!/usr/bin/env python3
"""
Test script for OpenCode orchestrator.
Run with: python3 scripts/test_opencode_orchestrator.py

Requires opencode serve running on port 3000 (or specified).
"""

import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.opencode_orchestrator import OpenCodeOrchestrator, detect_opencode_port


async def test_orchestrator():
    print("=== OpenCode Orchestrator Test ===")

    # Test 1: Port detection
    print("\n[Test 1] Detecting opencode serve port...")
    port = await detect_opencode_port()
    if port:
        print(f"Found on port {port}")
    else:
        print("opencode serve not found on ports 3000-3010")
        print("  Start with: opencode serve")
        return

    # Test 2: Connect
    print(f"\n[Test 2] Connecting to opencode serve...")
    async with OpenCodeOrchestrator(port=port) as orch:
        print("Connected")

        # Test 3: List sessions
        print("\n[Test 3] Listing sessions...")
        sessions = await orch.list_sessions()
        print(f"Found {len(sessions)} active session(s)")

        # Test 4: Create session
        print("\n[Test 4] Creating new session...")
        session_id = await orch.create_session(title="test-session")
        print(f"Session created: {session_id}")

        # Test 5: Send message (Plan agent test)
        print("\n[Test 5] Sending prompt to Plan agent...")
        response = await orch.send_message(
            session_id,
            "List the files in the current directory. Return just the file names."
        )
        print(f"Response received: {response.content[:100]}...")

        # Test 6: Get messages
        print("\n[Test 6] Getting session messages...")
        messages = await orch.get_session_messages(session_id)
        print(f"Session has {len(messages)} message(s)")

        # Test 7: Get diff
        print("\n[Test 7] Getting session diff...")
        diff = await orch.get_session_diff(session_id)
        print(f"Diff retrieved (keys: {list(diff.keys()) if isinstance(diff, dict) else 'N/A'})")

        print("\n=== All tests passed ===")


if __name__ == "__main__":
    asyncio.run(test_orchestrator())