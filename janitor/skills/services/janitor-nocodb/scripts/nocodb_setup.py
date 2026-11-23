#!/usr/bin/env python3
"""Guided NocoDB install for Janitor: preflight, deploy, verify, stop.

One JSON document per command on stdout; Spanish hints on stderr. The engine is shared
with janitor-n8n and janitor-lightrag: ``../../_shared/compose_service.py``.
"""

from __future__ import annotations

import sys
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
sys.dont_write_bytecode = True
sys.path.insert(0, str(SKILL_DIR.parent / "_shared"))

import compose_service as cs  # noqa: E402


def build_env(ctx: cs.Context) -> dict:
    # No admin account is pre-created: the user signs up in the web UI (loopback only),
    # so Janitor never generates, stores or shows a NocoDB password.
    return {
        "NOCODB_DB_PASSWORD": ctx.secrets["NOCODB_DB_PASSWORD"],
        "NC_AUTH_JWT_SECRET": ctx.secrets["NC_AUTH_JWT_SECRET"],
    }


SPEC = cs.ServiceSpec(
    key="nocodb",
    title="NocoDB",
    script="nocodb_setup.py",
    skill_dir=SKILL_DIR,
    containers=("janitor-nocodb", "janitor-nocodb-db"),
    main_container="janitor-nocodb",
    volumes=("janitor-nocodb-data", "janitor-nocodb-pgdata"),
    network="janitor-nocodb-network",
    images=("nocodb/nocodb:latest", "postgres:16-alpine"),
    default_port=1980,
    # The root page answers once the app is up (a redirect to the UI counts).
    health_path="/",
    healthy_status=lambda status: 200 <= status < 400,
    # The database password must stay stable: the pgdata volume was initialised with it.
    generated_secrets=("NOCODB_DB_PASSWORD", "NC_AUTH_JWT_SECRET"),
    build_env=build_env,
    min_free_gb=2.0,
    # The previous 4-container stack; present = an old install that must go first.
    legacy_containers=("janitor-nocodb-worker", "janitor-nocodb-redis"),
)


if __name__ == "__main__":
    raise SystemExit(cs.main(SPEC))
