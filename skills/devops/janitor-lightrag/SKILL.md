---
name: janitor-lightrag
description: "Deploy and operate LightRAG self-hosted for Janitor."
version: 1.0.0
platforms: [linux]

metadata:
  hermes:
    tags: [lightrag, knowledge-graph, rag, docker, self-host, postgresql, pgvector]
    category: devops
---

# janitor-lightrag

Deploy and operate LightRAG as a Janitor knowledge graph service. LightRAG is a
graph-based RAG system that extracts entities and relationships from documents
using LLMs, builds a knowledge graph, and enables hybrid retrieval (semantic +
graph traversal) for querying.

## Architecture

```
127.0.0.1:9621 → janitor-lightrag (ghcr.io/hkuds/lightrag:latest)
                 ├── Storage: PostgreSQL (pgvector/pgvector:pg18)
                 ├── Graph: NetworkX (in-memory JSON files)
                 ├── LLM: GLM-5.2 via z.ai coding endpoint
                 ├── Embeddings: nomic-embed-text via Honcho Ollama
                 └── Networks: janitor-lightrag-network + janitor-honcho-network
```

## Prerequisites

- Docker daemon running (`docker info` must succeed)
- `docker compose` v2 available
- **janitor-honcho deployed FIRST** (cross-network Ollama dependency)
- `z.ai` API key in `${HERMES_HOME:-$HOME/.janitor}/.env` as `ZAI_API_KEY` (or
  pre-populate `LLM_API_KEY` in `~/.janitor/docker/lightrag.env` after first run)

## Key Design Decisions (Verified)

1. **NetworkX for graph storage (not PGGraphStorage):** PGGraphStorage requires
   Apache AGE extension which pgvector/pgvector:pg18 does NOT include. NetworkX
   loads the graph in-memory (persisted as JSON), perfect for research-scale
   datasets (thousands of nodes). Avoids needing Neo4j or AGE.

2. **Ollama for embeddings (not z.ai):** z.ai coding endpoint only serves GLM
   chat models, NOT embeddings. Use Honcho's local Ollama with nomic-embed-text
   (768d). This also stays under pgvector's HNSW 2000-dimension limit.

3. **Cross-network Ollama access:** LightRAG must be connected to
   `janitor-honcho-network` (external: true) to reach `janitor-honcho-ollama:11434`.
   `host.docker.internal` is unreliable because Docker uses a dynamic gateway
   IP (Docker picks the bridge gateway at container start — depends on the
   host's network namespace and bridge driver), which may not be reachable
   when the bridge is in NO-CARRIER state. Use cross-network container
   names instead — Docker's `host-gateway` extra hosts entry in the compose
   handles dynamic gateway resolution at container start.

4. **z.ai LLM endpoint:** Must use `https://api.z.ai/api/coding/paas/v4` (NOT
   `/api/paas/v4`). Model is `glm-5.2` (NOT `glm-4-flash` which is unknown).

5. **PostgreSQL 18+ volume mount:** Must mount at `/var/lib/postgresql` (NOT
   `/var/lib/postgresql/data`). PG 18+ changed data directory structure.

## Files

- Compose: `~/.janitor/skills/devops/janitor-lightrag/scripts/lightrag-compose.yml`
- Env: `~/.janitor/docker/lightrag.env` (chmod 600 — contains API keys + passwords)

**First-time access:**
- URL: `http://127.0.0.1:9621`
- WebUI login: `admin` / password in lightrag.env → AUTH_ACCOUNTS
- API Key: in lightrag.env → LIGHTRAG_API_KEY (header: `X-API-Key`)

## Deploy

```bash
bash ~/.janitor/skills/devops/janitor-lightrag/scripts/deploy.sh
```

The deploy script is idempotent: it preserves existing `lightrag.env`
credentials (won't break existing volumes), copies the compose file from
`scripts/` into `~/.janitor/docker/`, pulls images, brings up the stack,
waits for health, and injects `LIGHTRAG_API_URL` + `LIGHTRAG_API_KEY` into
`~/.janitor/.env`.

Manual equivalent:

```bash
cd ~/.janitor/docker
docker compose -f lightrag-compose.yml --env-file lightrag.env pull
docker compose -f lightrag-compose.yml --env-file lightrag.env up -d
```

## API Reference

### Health Check

```bash
curl http://127.0.0.1:9621/health
```

### Index a Document

```bash
curl -X POST "http://127.0.0.1:9621/documents/text" \
  -H "X-API-Key: $LIGHTRAG_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"text": "...", "file_source": "filename.txt"}'
```

**IMPORTANT:** `file_source` is REQUIRED for text insertion. Without it you
get HTTP 400: "A valid file_source is required for text insertion".

Processing runs in background. Poll status:

```bash
curl -H "X-API-Key: $LIGHTRAG_API_KEY" \
  "http://127.0.0.1:9621/documents/pipeline_status"
```

### List Knowledge Graph Entities

```bash
curl -H "X-API-Key: $LIGHTRAG_API_KEY" \
  "http://127.0.0.1:9621/graph/label/list"
```

### Query

```bash
curl -X POST "http://127.0.0.1:9621/query" \
  -H "X-API-Key: $LIGHTRAG_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"query": "...", "mode": "hybrid"}'
```

Query modes: `naive`, `local`, `global`, `hybrid`, `mix`.

**WARNING:** GLM-5.2 is a reasoning model — queries can take 60-120s due to
chain-of-thought before response generation. For faster queries, consider
switching LLM_MODEL to a non-reasoning model like glm-4-flash (requires the
correct endpoint for that model).

## Container Management

```bash
# Status
docker ps --filter name=janitor-lightrag

# Logs
docker logs janitor-lightrag --tail 30

# Restart (MUST use deploy.sh or compose, not docker restart — env_file changes)
bash ~/.janitor/skills/devops/janitor-lightrag/scripts/deploy.sh
# or manually:
cd ~/.janitor/docker
docker compose -f lightrag-compose.yml --env-file lightrag.env down
docker compose -f lightrag-compose.yml --env-file lightrag.env up -d

# Update
docker compose -f lightrag-compose.yml --env-file lightrag.env pull
docker compose -f lightrag-compose.yml --env-file lightrag.env up -d
```

## Environment Variables (Critical)

| Variable | Value | Notes |
|----------|-------|-------|
| `LIGHTRAG_GRAPH_STORAGE` | `NetworkXStorage` | NOT PGGraphStorage (needs AGE) |
| `LIGHTRAG_KV_STORAGE` | `PGKVStorage` | PostgreSQL for KV |
| `LIGHTRAG_VECTOR_STORAGE` | `PGVectorStorage` | PostgreSQL + pgvector |
| `LIGHTRAG_DOC_STATUS_STORAGE` | `PGDocStatusStorage` | Pipeline state tracking |
| `LLM_BINDING` | `openai` | OpenAI-compatible endpoint |
| `LLM_BINDING_HOST` | `https://api.z.ai/api/coding/paas/v4` | Coding endpoint, not /api/paas/v4 |
| `LLM_MODEL` | `glm-5.2` | Reasoning model, slow but capable |
| `EMBEDDING_BINDING` | `ollama` | Local embeddings |
| `EMBEDDING_BINDING_HOST` | `http://janitor-honcho-ollama:11434` | Cross-network |
| `EMBEDDING_MODEL` | `nomic-embed-text` | 768 dimensions |
| `EMBEDDING_DIM` | `768` | Under HNSW 2000 limit |
| `WHITELIST_PATHS` | `/health` | Require auth on all routes including Ollama-compatible |
| `SUMMARY_LANGUAGE` | `Spanish` | Entity/relation summaries in Spanish |
| `ENTITY_EXTRACTION_USE_JSON` | `true` | Structured output for reliability |

## Pitfalls

1. **PGGraphStorage + pgvector image:** The pgvector/pgvector:pg18 image does
   NOT include Apache AGE. If you set `LIGHTRAG_GRAPH_STORAGE=PGGraphStorage`,
   LightRAG will crash with `function create_graph(unknown) does not exist`.
   Use `NetworkXStorage` instead.

2. **PostgreSQL 18 volume path:** PG 18+ Docker images require mounting at
   `/var/lib/postgresql`, NOT `/var/lib/postgresql/data`. Otherwise:
   "in 18+, these Docker images are configured to store database data in a
   format which is compatible with pg_ctlcluster".

3. **z.ai model names:** Only `glm-5.2` works on the `/api/coding/paas/v4`
   endpoint. `glm-4-flash`, `glm-4.6-flash` return error 1211 "Unknown Model".
   z.ai does NOT serve embeddings at all.

4. **host.docker.internal unreachable:** Docker uses a dynamic bridge gateway
   IP — the bridge driver assigns it at network creation (default bridge uses
   one range, user-defined bridges another). On hosts where the docker0 bridge
   is in NO-CARRIER state, the gateway IP may be unreachable. The compose file
   uses `extra_hosts: host.docker.internal:host-gateway` which Docker resolves
   at container start (dynamic gateway detection), and the cross-network Ollama
   access goes through the `janitor-honcho-network` (external: true) instead.

5. **Embedding dimension limit:** pgvector HNSW indexes support max 2000
   dimensions. Models like embedding-3 (2048d) will fail to create HNSW
   indexes (WARNING, not fatal — falls back to sequential scan). Use
   nomic-embed-text (768d) for proper index support.

6. **Orphan containers warning:** Running LightRAG compose shows orphan
   warnings for NocoDB/Honcho/n8n/Firecrawl containers. This is cosmetic —
   do NOT use `--remove-orphans` or you'll kill other stacks.

7. **docker restart vs compose down/up:** `docker restart janitor-lightrag`
   does NOT pick up env_file changes. Must use `docker compose down && up`
   (or re-run `deploy.sh`) to apply config changes.

8. **GLM-5.2 is a reasoning model:** Entity extraction and queries take
   60-120s because GLM-5.2 generates reasoning_content before answering.
   This is normal, not a timeout bug.

## Integration with NocoDB

LightRAG and NocoDB are complementary:
- **LightRAG:** Unstructured text → automatic entity/relation extraction →
  knowledge graph → semantic + graph queries
- **NocoDB:** Structured metadata (investigation status, reviewer, dates,
  LightRAG document IDs) → relational queries, kanban views, webhooks

Suggested NocoDB schema:
- Table "Investigaciones" → title, status, team, dates
- Table "Fuentes" → type, author, DOI, URL, lightrag_doc_id
- Table "Hallazgos" → description, fuente_id, investigacion_id

## See Also

- Skill `janitor-nocodb` — NocoDB structured metadata integration
- Skill `janitor-honcho` — Honcho Ollama (embedding model provider)
- LightRAG docs: https://github.com/HKUDS/LightRAG
- LightRAG env reference: https://github.com/HKUDS/LightRAG/blob/main/env.example
