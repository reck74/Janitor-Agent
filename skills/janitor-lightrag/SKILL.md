---
name: janitor-lightrag
description: "Deploy and operate LightRAG self-hosted for Janitor."
version: 1.0.0
author: Janitor Agent
license: MIT
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

Three containers share only `janitor-lightrag-network`: the LightRAG API,
PostgreSQL 18/pgvector, and `janitor-lightrag-embeddings` (Ollama). The app
uses NetworkX graph storage because this PostgreSQL image does not contain
Apache AGE. Images are fixed by digest in the bundled Compose file.

Fresh deployments use MiniMax-M2.7 through `https://api.minimax.io/v1` and
`MINIMAX_API_KEY` from the active Janitor profile's `.env`. Embeddings use
`nomic-embed-text:v1.5` (768 dimensions), downloaded explicitly during deploy.
This stack has no dependency on Honcho, its Ollama instance, or its network.

## Prerequisites and deployment

- Janitor installed with its PM runtime and Docker Compose v2 available.
- Docker daemon accessible to the current user.
- `MINIMAX_API_KEY` configured for a fresh deployment.

```bash
bash ~/.janitor/skills/janitor-lightrag/scripts/deploy.sh
```

Use `HERMES_HOME=/path/to/profile` when targeting another profile. Secrets
are read as data by Janitor's PM Python, without evaluating the `.env` file.
The script preserves existing credentials and custom LLM settings. It generates
`TOKEN_SECRET` for authenticated sessions and maps legacy `LLM_API_KEY` to the
current `LLM_BINDING_API_KEY` when needed, with a backup. A retired
Honcho embedding endpoint is changed to the isolated service after an automatic
backup of `~/.janitor/docker/lightrag.env`.

Compose: `~/.janitor/skills/janitor-lightrag/scripts/lightrag-compose.yml`.
Runtime copy and credentials: `~/.janitor/docker/lightrag-compose.yml` and
`~/.janitor/docker/lightrag.env` (mode 600). PostgreSQL 18 mounts at
`/var/lib/postgresql`. Local API/WebUI: `http://127.0.0.1:9621`; login
credentials are `AUTH_ACCOUNTS`, and REST calls use `LIGHTRAG_API_KEY`.

Deployment pulls the pinned images, migrates legacy named volumes offline,
starts PostgreSQL/Ollama, pulls the embedding model, and starts the app.
Successful health checks precede updating Janitor's API settings. A failure
exits nonzero. Legacy source volumes remain intact; stopped legacy containers
are preserved under `janitor-legacy-*`. Migration receipts live beside the
runtime Compose file. An existing destination without a completed receipt is
refused for manual inspection rather than overwritten.

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

Query latency depends on the configured LLM and document size.

## Container Management

```bash
# Status
docker ps --filter name=janitor-lightrag

# Logs
docker logs janitor-lightrag --tail 30

# Restart (MUST use deploy.sh or compose, not docker restart — env_file changes)
bash ~/.janitor/skills/janitor-lightrag/scripts/deploy.sh
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
| `LLM_BINDING_HOST` | `https://api.minimax.io/v1` | MiniMax OpenAI-compatible endpoint |
| `LLM_MODEL` | `MiniMax-M2.7` | Fresh deployment default |
| `EMBEDDING_BINDING` | `ollama` | Local embeddings |
| `EMBEDDING_BINDING_HOST` | `http://janitor-lightrag-embeddings:11434` | Isolated stack |
| `EMBEDDING_MODEL` | `nomic-embed-text:v1.5` | 768 dimensions |
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

3. Changing embedding models or vector dimensions requires an explicit re-index
   plan for existing documents. Preserve all volumes before such a change.

4. Re-run deploy to apply environment changes; `docker restart` does not reload
   an `env_file`. Each stack has its own Compose project, so do not use
   `--remove-orphans` against an old shared project.

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

## Configuration references

The supported binding and auth fields are documented in
[LightRAG env.example](https://github.com/HKUDS/LightRAG/blob/main/env.example).
The health probe uses Python included by the
[official Dockerfile](https://github.com/HKUDS/LightRAG/blob/main/Dockerfile),
without depending on an absent wget binary.
