# Knowledge Base MCP Servers — Research Summary

Research date: 2026-05-07
Use when: user asks about managing tool documentation, KB for AI agents, or searchable documentation for Janitor.

## Credibility Framework

Use GitHub stars as a first-pass filter before deep research:

| Tier | Stars | Trust level |
|------|-------|-------------|
| Established | 10k+ | Production-ready, community-validated |
| Viable | 1k–10k | Active maintenance, MIT license, investigate further |
| Niche | < 1k | High risk of abandonment — verify activity (commits, releases) before recommending |

**Red flag:** A tool with < 100 stars that has no releases and infrequent commits is not a viable knowledge base for an agent that needs long-term reliability.

---

## Knowledge Base MCP Servers

### AnythingLLM — 59.7k ⭐
**Repo:** https://github.com/Mintplex-Labs/anything-llm  
**License:** MIT | **Forks:** 6.5k | **Releases:** Active

Full RAG platform. Upload documents → index → query via chat. MCP-native. Multi-user. LanceDB default (or swap for PGVector, Chroma, Qdrant, etc.). Supports Ollama, LM Studio, LocalAI, or external API.

**Best for:** User has many documents (PDF, MD, TXT, DOCX) and wants a turnkey RAG system.

**Limitations:** Generic document management — not specialized for tool documentation.

**Install (Docker):**
```bash
docker run -d -p 3001:3000 \
  -v anything-llm:/app/backend/data \
  --name anything-llm \
  ghcr.io/mintplex-labs/anything-llm:latest
```

---

### Open WebUI — 136k ⭐
**Repo:** https://github.com/open-webui/open-webui  
**License:** MIT | **Forks:** 19.4k | **Releases:** 159 | **Contributors:** 767

Chat UI for LLMs with built-in RAG. Very mature, many deployment options. 9 vector DB options. Not specialized for tool docs — it's a general chat interface.

**Best for:** Teams wanting a full self-hosted ChatGPT replacement with RAG capabilities.

**Limitations:** Heavyweight for just documentation lookup. More UI than KB system.

**Install (Docker):**
```bash
docker run -d -p 3000:8080 \
  -v open-webui:/app/backend/data \
  --name open-webui \
  ghcr.io/open-webui/open-webui:main
```

---

### Grounded Docs MCP Server — 1.3k ⭐
**Repo:** https://github.com/arabold/docs-mcp-server  
**License:** MIT | **Releases:** 68 | **Commits:** 890 | **Last push:** Recent (2026)

**Most aligned with tool documentation use case.** Indexes docs from websites, GitHub, npm, PyPI, local files. MCP-native (HTTP/StreamableHTTP). Version-specific doc retrieval. Embedding models optional (OpenAI, Ollama, Gemini).

**Best for:** Giving Janitor access to official documentation of tools (Docker, kubectl, AWS CLI, etc.) via MCP tools.

**Workflow:**
```bash
# Index tool docs
npx @arabold/docs-mcp-server scrape kubectl "https://kubernetes.io/docs/reference/kubectl/"

# Query via MCP
npx @arabold/docs-mcp-server search kubectl "deployment rollout"

# Start MCP server
npx @arabold/docs-mcp-server
# MCP available at http://localhost:6280/mcp (SSE)
```

**Docker:**
```bash
docker run --rm \
  -v docs-mcp-data:/data \
  -v docs-mcp-config:/config \
  -p 6280:6280 \
  ghcr.io/arabold/docs-mcp-server:latest \
  --protocol http --host 0.0.0.0 --port 6280
```

**MCP config for Hermes:**
```yaml
mcp_servers:
  docs-mcp-server:
    type: sse
    url: http://localhost:6280/sse
```

**Status:** 1.3k stars is modest, but 68 releases and 890 commits indicate active maintenance — not abandoned.

---

### LocalAI — 40k ⭐
**Repo:** https://github.com/mudler/LocalAI  
**License:** MIT | **Contributors:** 500+

OpenAI API-compatible LLM engine. Includes LocalAGI agents, LocalRecall semantic search. Can function as a RAG backend.

**Best for:** Users who want a complete local AI stack with agent capabilities.

**Limitations:** More engine than KB system. Requires more configuration.

---

### Haystack — 24.6k ⭐
**Repo:** https://github.com/deepset-ai/haystack  
**License:** Apache 2.0 | **Since:** 2019

Open-source AI orchestration framework. Build RAG pipelines, agents, semantic search. MCP integration available.

**Best for:** Developers building custom RAG workflows.

**Limitations:** Framework, not turnkey. Requires Python code.

---

### Quivr — 38k ⭐
**Repo:** https://github.com/QuivrHQ/quivr  
**License:** MIT

"Second brain" RAG platform. Upload files, chat with them. Multi-modal support.

**Best for:** Personal knowledge management.

**Limitations:** Not specialized for tool documentation.

---

## NOT Recommended (insufficient credibility)

| Tool | Stars | Reason |
|------|-------|--------|
| llm-wiki-skills | 32 ⭐ | Too niche. No backend, no MCP. Karpathy-inspired but no community. |
| CodeDox | 28 ⭐ | Requires PostgreSQL. 28 stars. |
| OpenGPTs | 6.7k ⭐ | LangChain-based. Archived (last push mid-2025). |

---

## Decision Matrix for This User (reck)

| Criterion | AnythingLLM | Grounded Docs MCP | Open WebUI |
|-----------|-------------|-------------------|------------|
| MCP-native | ✅ | ✅ | ✅ |
| Tool documentation focus | ❌ | ✅ | ❌ |
| Docker-ready | ✅ | ✅ | ✅ |
| No extra infra | ❌ (LanceDB bundled) | ✅ | ❌ |
| Credibility | 59.7k ⭐ | 1.3k ⭐ (but active) | 136k ⭐ |
| reck's trust bar | ✅ | ✅ (after verification) | ✅ |

**Recommended for reck:** Grounded Docs MCP Server for indexed tool docs, AnythingLLM for personal documentation.

---

## Pitfalls

- **Low stars ≠ abandoned.** Always check release count and commit frequency. A tool with 500 stars and 60 releases is safer than one with 5k stars and 2 releases.
- **MCP transport matters.** Some servers only support stdio, others HTTP. Hermes supports both — verify before recommending.
- **Embeddings are optional** for most KB tools. Without them you get keyword search; with them you get semantic search. Factor in whether the user has an embedding provider.
