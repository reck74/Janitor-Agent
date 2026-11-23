#!/usr/bin/env python3
"""Guided n8n install for Janitor: preflight, deploy, verify, stop.

One JSON document per command on stdout; Spanish hints on stderr. The engine is shared
with janitor-nocodb and janitor-lightrag: ``../../_shared/compose_service.py``.
"""

from __future__ import annotations

import sys
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
sys.dont_write_bytecode = True
sys.path.insert(0, str(SKILL_DIR.parent / "_shared"))

import compose_service as cs  # noqa: E402


def build_env(ctx: cs.Context) -> dict:
    return {
        "N8N_ENCRYPTION_KEY": ctx.secrets["N8N_ENCRYPTION_KEY"],
        "GENERIC_TIMEZONE": ctx.timezone,
    }


SPEC = cs.ServiceSpec(
    key="n8n",
    title="n8n",
    script="n8n_setup.py",
    skill_dir=SKILL_DIR,
    containers=("janitor-n8n",),
    main_container="janitor-n8n",
    volumes=("janitor-n8n-data",),
    network="janitor-n8n-network",
    images=("docker.n8n.io/n8nio/n8n:latest",),
    default_port=5678,
    health_path="/healthz",
    healthy_status=lambda status: status == 200,
    # The key encrypts the credentials n8n stores: losing it makes them unreadable.
    generated_secrets=("N8N_ENCRYPTION_KEY",),
    build_env=build_env,
    min_free_gb=2.0,
    extra_dirs=("n8n-files",),
)


if __name__ == "__main__":
    raise SystemExit(cs.main(SPEC))
