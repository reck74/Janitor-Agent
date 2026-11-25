#!/usr/bin/env python3
"""Guided LightRAG install for Janitor: preflight, deploy, verify, stop.

One JSON document per command on stdout; Spanish hints on stderr. The engine is shared
with janitor-n8n and janitor-nocodb: ``../../_shared/compose_service.py``.

LightRAG needs an LLM (entity extraction, answers) and an embeddings model. Both are
reached over OpenAI-compatible APIs with keys read from the profile ``.env``: embeddings
always use ``OPENAI_API_KEY``; the LLM uses MiniMax when ``MINIMAX_API_KEY`` is present
(``--llm auto``), else OpenAI. Only those keys are copied into ``lightrag.env``.
"""

from __future__ import annotations

import sys
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
sys.dont_write_bytecode = True
sys.path.insert(0, str(SKILL_DIR.parent / "_shared"))

import compose_service as cs  # noqa: E402

OPENAI_URL = "https://api.openai.com/v1"
LLMS = {
    "openai": {"host": OPENAI_URL, "model": "gpt-4o-mini", "key": "OPENAI_API_KEY"},
    "minimax": {"host": "https://api.minimax.io/v1", "model": "MiniMax-M3", "key": "MINIMAX_API_KEY"},
}
EMBEDDINGS = {"host": OPENAI_URL, "model": "text-embedding-3-small", "dim": "1536", "key": "OPENAI_API_KEY"}


def credential_check(creds: dict) -> list[str]:
    blockers = []
    if not creds.get("OPENAI_API_KEY"):
        blockers.append("embeddings_credential_missing")
        if not creds.get("MINIMAX_API_KEY"):
            blockers.append("llm_credential_missing")
    return blockers


def pick_llm(ctx: cs.Context) -> str:
    choice = getattr(ctx.args, "llm", "auto")
    if choice == "auto":
        return "minimax" if ctx.creds.get("MINIMAX_API_KEY") else "openai"
    return choice


def build_env(ctx: cs.Context) -> dict:
    if not ctx.creds.get(EMBEDDINGS["key"]):
        raise cs.Refusal("embeddings_credential_missing", needs=[EMBEDDINGS["key"]])
    llm_name = pick_llm(ctx)
    llm = LLMS[llm_name]
    if not ctx.creds.get(llm["key"]):
        raise cs.Refusal("llm_credential_missing", needs=[llm["key"]], llm=llm_name)
    ctx.notes.append(f"llm={llm_name}:{llm['model']}; embeddings=openai:{EMBEDDINGS['model']}")
    return {
        "LIGHTRAG_DB_PASSWORD": ctx.secrets["LIGHTRAG_DB_PASSWORD"],
        "LIGHTRAG_API_KEY": ctx.secrets["LIGHTRAG_API_KEY"],
        "LIGHTRAG_TOKEN_SECRET": ctx.secrets["LIGHTRAG_TOKEN_SECRET"],
        "AUTH_ACCOUNTS": f"admin:{ctx.secrets['LIGHTRAG_WEBUI_PASSWORD']}",
        "LLM_BINDING_HOST": llm["host"],
        "LLM_MODEL": llm["model"],
        "LLM_BINDING_API_KEY": ctx.creds[llm["key"]],
        "EMBEDDING_BINDING_HOST": EMBEDDINGS["host"],
        "EMBEDDING_MODEL": EMBEDDINGS["model"],
        "EMBEDDING_DIM": EMBEDDINGS["dim"],
        "EMBEDDING_BINDING_API_KEY": ctx.creds[EMBEDDINGS["key"]],
    }


def add_deploy_args(parser) -> None:
    parser.add_argument("--llm", choices=("auto", "openai", "minimax"), default="auto")


SPEC = cs.ServiceSpec(
    key="lightrag",
    title="LightRAG",
    script="lightrag_setup.py",
    skill_dir=SKILL_DIR,
    containers=("janitor-lightrag", "janitor-lightrag-db"),
    main_container="janitor-lightrag",
    volumes=("janitor-lightrag-storage", "janitor-lightrag-inputs", "janitor-lightrag-pgdata"),
    network="janitor-lightrag-network",
    images=("ghcr.io/hkuds/lightrag:latest", "pgvector/pgvector:pg18"),
    default_port=9621,
    health_path="/health",
    healthy_status=lambda status: status == 200,
    generated_secrets=("LIGHTRAG_DB_PASSWORD", "LIGHTRAG_API_KEY", "LIGHTRAG_TOKEN_SECRET",
                       "LIGHTRAG_WEBUI_PASSWORD"),
    build_env=build_env,
    min_free_gb=3.0,
    credential_names=("OPENAI_API_KEY", "MINIMAX_API_KEY"),
    credential_check=credential_check,
)


if __name__ == "__main__":
    raise SystemExit(cs.main(SPEC, add_deploy_args=add_deploy_args))
