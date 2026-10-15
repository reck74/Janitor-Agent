"""Read-only health probe for an explicitly configured OpenCode server."""
import argparse
import asyncio
import json
import os

from client import OpenCodeOrchestrator


async def probe(host, port):
    client = OpenCodeOrchestrator(host=host, port=port, password=os.environ.get("OPENCODE_SERVER_PASSWORD"))
    try:
        await client.connect()
        print(json.dumps({"ok": True, "service": "opencode"}))
        return 0
    except Exception as error:
        print(json.dumps({"ok": False, "service": "opencode", "error": type(error).__name__}))
        return 1
    finally:
        await client.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", required=True, type=int)
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("port must be between 1 and 65535")
    raise SystemExit(asyncio.run(probe(args.host, args.port)))
