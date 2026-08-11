---
name: janitor-nocodb
description: "Deploy and operate NocoDB self-hosted for Janitor."
version: 1.0.0
platforms: [linux, macos]

metadata:
  hermes:
    tags: [nocodb, docker, self-host, database, api, compose, devops]
    category: devops
---

# janitor-nocodb

Deploy and operate NocoDB self-hosted as a Janitor tool. NocoDB is a no-code
database platform that turns any database into a smart spreadsheet. This skill
covers the full lifecycle: deployment, API access, base/table management, and
container operations.

## Architecture

```
127.0.0.1:1980 → janitor-nocodb (nocodb/nocodb:latest)
                 ├── janitor-nocodb-worker (nocodb/nocodb:latest, NC_WORKER_MODE_ENABLED=true)
                 ├── janitor-nocodb-db (postgres:16-alpine)
                 └── janitor-nocodb-redis (redis:7-alpine)
                 Network: janitor-nocodb-network (isolated bridge)
```

## When to Use

- Deploy or repair the NocoDB Docker stack
- Create bases, tables, fields, and records programmatically via API
- Set up webhooks for record events
- Connect NocoDB MCP server to LLMs (Claude, Cursor, Windsurf) — verify MCP
  availability first (see MCP Server Integration section)
- Integrate NocoDB with other Janitor services (n8n workflows, Honcho)
- Store structured research metadata with relational queries (sources,
  concepts, findings, projects with cross-references) — NocoDB excels at
  structured data with relationships, NOT at semantic search over long text

## Deploy

```bash
bash ~/.janitor/skills/devops/janitor-nocodb/scripts/deploy.sh
```

This script:
1. Generates `NC_AUTH_JWT_SECRET` and DB credentials via `openssl rand`
2. Creates `~/.janitor/docker/nocodb.env` (chmod 600, never overwritten)
3. Pulls `nocodb/nocodb:latest`, `postgres:16-alpine`, `redis:7-alpine`
4. Starts 4 containers with healthchecks
5. Injects `NOCODB_API_URL` into `~/.janitor/.env`

**Bundled files (in this skill):**
- Compose: `~/.janitor/skills/devops/janitor-nocodb/scripts/nocodb-compose.yml`
- Setup script: `~/.janitor/skills/devops/janitor-nocodb/scripts/deploy.sh`

**Generated at deploy time (lives in docker/ dir):**
- Env: `~/.janitor/docker/nocodb.env` (contains JWT secret + DB password — chmod 600)

**First-time access:**
- URL: `http://127.0.0.1:1980`
- Email: `janitor@example.com`
- Password: check `nocodb.env` → `NC_ADMIN_PASSWORD`

## Authentication

NocoDB 2026.07+ requires **both** an `xc-token` header AND a cookie jar containing
`nc_token` + `refresh_token`. The token alone returns 401. Login via the user
signin endpoint, capture the cookies with `-c cookies.txt`, then send both on every
subsequent request.

```bash
# One-time login (capture cookies + token)
curl -s -c /tmp/nocodb-cookies.txt -H "Content-Type: application/json" \
  -X POST http://127.0.0.1:1980/api/v2/auth/user/signin \
  -d '{"email":"janitor@example.com","password":"<NC_ADMIN_PASSWORD>"}'

# Response: {"token":"eyJhbGc..."}
TOKEN=$(curl -s -b /tmp/nocodb-cookies.txt -H "Content-Type: application/json" \
  -X POST http://127.0.0.1:1980/api/v2/auth/user/signin \
  -d '{"email":"janitor@example.com","password":"<NC_ADMIN_PASSWORD>"}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['token'])")

# All subsequent API calls (cookie AND header both required)
curl -s -b /tmp/nocodb-cookies.txt -H "xc-token: $TOKEN" \
  http://127.0.0.1:1980/api/v2/meta/bases
```

**Cookies expire** (the `nc_token` cookie has a TTL). When API calls start returning
401, re-run the signin curl. The UI-based "API Tokens" path (Account Settings → API
Tokens → legacy full-access) **does not bypass** this — the cookie jar is still
required alongside.

For Python, pass both via `requests`:
```python
r = requests.get(
    f"{base}/api/v2/tables/{table}/records",
    headers={"xc-token": token, "Cookie": f"nc_token={nc_cookie}; refresh_token={refresh_cookie}"},
)
```

**Extract admin credentials** (for the initial login) from the local env file:
```bash
grep -E '^NC_ADMIN_EMAIL=|^NC_ADMIN_PASSWORD=' ~/.janitor/docker/nocodb.env
```

### API Tokens (legacy UI path)

Generate tokens from the UI: **Account Settings → API Tokens**. Two token types:
- **Legacy tokens**: full access to all bases in the workspace.
- **Fine-grained tokens** (☁️ Cloud / licensed): scoped per-base with specific permissions.

Even UI-generated tokens still require the cookie jar on v2026.07. The token
header alone is rejected.

### Swagger / Interactive API Docs

Swagger UI is served from the app root, not `/apis/`. On v2026.07.0:
- `/apis/v3/data` and `/apis/v3/meta` return 404 (documented but not exposed).
- The interactive Swagger UI is at `http://127.0.0.1:1980/` (root) — navigate
  to it from a browser after login to explore available endpoints interactively.
- If you need to discover the correct API paths programmatically, use the
  PostgreSQL inspection method (see "Inspection without API Token" below).

## API Reference (Core Operations)

### List Bases

```bash
curl -s -H "xc-token: $TOKEN" http://127.0.0.1:1980/api/v2/meta/bases
```

### Create a Base

```bash
curl -s -H "xc-token: $TOKEN" -H "Content-Type: application/json" \
  -X POST http://127.0.0.1:1980/api/v2/meta/bases \
  -d '{"title": "My Database"}'
```

### List Tables in a Base

```bash
curl -s -H "xc-token: $TOKEN" \
  "http://127.0.0.1:1980/api/v2/meta/bases/<BASE_ID>/tables"
```

### Create a Table

```bash
curl -s -H "xc-token: $TOKEN" -H "Content-Type: application/json" \
  -X POST "http://127.0.0.1:1980/api/v2/meta/bases/<BASE_ID>/tables" \
  -d '{
    "table_name": "customers",
    "title": "Customers",
    "columns": [
      {"column_name": "name", "title": "Name", "uidt": "SingleLineText"},
      {"column_name": "email", "title": "Email", "uidt": "Email"},
      {"column_name": "age", "title": "Age", "uidt": "Number"}
    ]
  }'
```

### Insert Records (v3 Data API)

```bash
curl -s -H "xc-token: $TOKEN" -H "Content-Type: application/json" \
  -X POST "http://127.0.0.1:1980/api/v3/tables/<TABLE_ID>/records" \
  -d '{"Id": 1, "name": "Alice", "email": "alice@example.com", "age": 30}'
```

### List Records

```bash
curl -s -H "xc-token: $TOKEN" \
  "http://127.0.0.1:1980/api/v3/tables/<TABLE_ID>/records?limit=25&offset=0"
```

### Query with Filter

```bash
curl -s -H "xc-token: $TOKEN" \
  "http://127.0.0.1:1980/api/v3/tables/<TABLE_ID>/records?where=(age,gt,25)"
```

### Update Record

```bash
curl -s -H "xc-token: $TOKEN" -H "Content-Type: application/json" \
  -X PATCH "http://127.0.0.1:1980/api/v3/tables/<TABLE_ID>/records" \
  -d '{"Id": 1, "age": 31}'
```

### Delete Record

```bash
curl -s -H "xc-token: $TOKEN" -H "Content-Type: application/json" \
  -X DELETE "http://127.0.0.1:1980/api/v3/tables/<TABLE_ID>/records" \
  -d '{"Id": 1}'
```

### Upload File via API

```bash
curl -s -H "xc-token: $TOKEN" \
  -F "files[]=@/path/to/file.pdf" \
  "http://127.0.0.1:1980/api/v3/tables/<TABLE_ID>/upload"
```

## Webhooks

### Create a Webhook (v3)

```bash
curl -s -H "xc-token: $TOKEN" -H "Content-Type: application/json" \
  -X POST "http://127.0.0.1:1980/api/v2/meta/hooks/<TABLE_ID>" \
  -d '{
    "event": "record-created",
    "url": "http://janitor-n8n:5678/webhook/nocodb-trigger",
    "title": "On Record Created"
  }'
```

Supported events: `record-created`, `record-updated`, `record-deleted`.

### Webhook v2 vs v3

- **v3** (current): unified event model, supports bulk operation payloads.
- **v2** (deprecated): per-operation hooks, limited payload format.
- v3 supports custom payloads via Handlebars templates.

## MCP Server Integration

NocoDB documents a built-in MCP server for LLM integration, but **endpoint
availability varies by version and configuration**. On v2026.07.0 self-hosted,
`/api/v3/mcp` returns 404 — the MCP server may require activation from the UI
or may not be available on all builds. Always verify before relying on it:

```bash
curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:1980/api/v3/mcp
# 200 = available, 404 = not enabled on this build
```

### Claude Desktop / Cursor config (when MCP is available)

```json
{
  "mcpServers": {
    "nocodb": {
      "command": "npx",
      "args": ["mcp-remote", "http://127.0.0.1:1980/api/v3/mcp"]
    }
  }
}
```

When available, the MCP server exposes tools for: listing bases, tables,
fields; querying, creating, updating records; and executing filtered searches
— all with the same `xc-token` authentication.

If MCP is not available, the REST API (documented above) is the primary
integration channel and provides identical capabilities.

## Inspection Without API Token (PostgreSQL Direct)

When you need to audit NocoDB state without creating an API token (e.g., the
user hasn't set one up yet, or you need to verify schema programmatically),
query the PostgreSQL metadata tables directly via `docker exec`:

```bash
# List all user-created bases
docker exec janitor-nocodb-db psql -U nocodb -d nocodb -c \
  "SELECT id, title FROM nc_bases_v2 ORDER BY id;"

# List all tables across all bases
docker exec janitor-nocodb-db psql -U nocodb -d nocodb -c \
  "SELECT base_id, title, table_name FROM nc_tables_v2 ORDER BY base_id;"

# Check if any API tokens exist
docker exec janitor-nocodb-db psql -U nocodb -d nocodb -c \
  "SELECT id, title, created_at FROM nc_api_tokens LIMIT 10;"

# Check total NocoDB metadata tables (health indicator)
docker exec janitor-nocodb-db psql -U nocodb -d nocodb -c \
  "SELECT count(*) FROM information_schema.tables
   WHERE table_schema='public' AND table_name LIKE 'nc_%';"

# Database size
docker exec janitor-nocodb-db psql -U nocodb -d nocodb -c \
  "SELECT pg_size_pretty(pg_database_size('nocodb'));"
```

All NocoDB metadata lives in tables prefixed `nc_` (125+ tables on a fresh
install). User-created data tables are created in the same `public` schema but
without the `nc_` prefix. Use `\dt public.nc_*` in psql to explore available
metadata tables.

This method bypasses HTTP entirely — useful for automation scripts and
read-only auditing. Requires the DB container to be running.

## Container Management

```bash
# Status
docker ps --filter name=janitor-nocodb

# Logs
docker logs janitor-nocodb --tail 30
docker logs janitor-nocodb-worker --tail 30

# Restart
docker compose -f ~/.janitor/skills/devops/janitor-nocodb/scripts/nocodb-compose.yml --env-file ~/.janitor/docker/nocodb.env restart

# Stop / Start
docker compose -f ~/.janitor/skills/devops/janitor-nocodb/scripts/nocodb-compose.yml --env-file ~/.janitor/docker/nocodb.env stop
docker compose -f ~/.janitor/skills/devops/janitor-nocodb/scripts/nocodb-compose.yml --env-file ~/.janitor/docker/nocodb.env start

# Update to latest
docker compose -f ~/.janitor/skills/devops/janitor-nocodb/scripts/nocodb-compose.yml --env-file ~/.janitor/docker/nocodb.env pull
docker compose -f ~/.janitor/skills/devops/janitor-nocodb/scripts/nocodb-compose.yml --env-file ~/.janitor/docker/nocodb.env up -d
```

> **Note:** If you cloned this skill from the Janitor-Agent repo, the bundled
> `nocodb-compose.yml` lives in `scripts/` next to `deploy.sh`. If you
> symlinked or installed it elsewhere, adjust the path accordingly.

## Environment Variables (Critical)

| Variable | Default | Description |
|----------|---------|-------------|
| `NC_DB` | SQLite fallback | `pg://nocodb-db:5432?u=nocodb&p=<PASS>&d=nocodb` |
| `NC_AUTH_JWT_SECRET` | auto-generated | JWT signing secret |
| `NC_CACHE_REDIS_URL` | none | `redis://nocodb-redis:6379` |
| `NC_JOBS_REDIS_URL` | none | Job queue Redis (same instance OK) |
| `NC_ADMIN_EMAIL` | none | Pre-set super admin email |
| `NC_ADMIN_PASSWORD` | none | Pre-set super admin password |
| `NC_WORKER_MODE_ENABLED` | `false` | Set `true` on worker container only |
| `NC_DISABLE_TELE` | unset | Set `true` to disable telemetry |
| `NC_WEBHOOK_ALLOW_PRIVATE_NETWORK` | `false` | Set `true` for localhost webhooks |
| `NC_ATTACHMENT_FIELD_SIZE` | `20971520` | Max attachment size (20 MiB) |

Full reference: `https://nocodb.com/docs/self-hosting/environment-variables`

## Web UI Access

NocoDB web UI is accessible at `http://127.0.0.1:1980` from any browser.
The super admin account is pre-configured via environment variables:
- Email: `janitor@example.com`
- Password: in `~/.janitor/docker/nocodb.env` → `NC_ADMIN_PASSWORD`

## Documentation Reference

Complete operational documentation is available from the official sources:
- NocoDB docs: https://nocodb.com/docs/product-docs
- NocoDB self-hosting: https://nocodb.com/docs/self-hosting
- NocoDB env vars: https://nocodb.com/docs/self-hosting/environment-variables

See also `references/multiselect-api.md` for the working MultiSelect API pattern.

## Pitfalls

1. **Healthcheck endpoint:** Use `http://localhost:8080/` (root), NOT
   `/api/v2/metainfo` — the meta API returns 404 without auth and the
   healthcheck will never pass.

2. **Worker container has no port mapping:** The worker runs with
   `NC_WORKER_MODE_ENABLED=true` and processes background jobs only. It
   does NOT serve HTTP. Don't expect it to respond to curl.

3. **Orphan containers warning:** Running NocoDB compose shows orphan
   warnings for n8n/Firecrawl/Honcho containers. This is cosmetic — do
   NOT use `--remove-orphans` or you'll kill other stacks.

4. **NC_WEBHOOK_ALLOW_PRIVATE_NETWORK:** Set to `true` in the env file
   if webhooks need to reach localhost services (n8n at 5678, etc).
   Without this, NocoDB blocks RFC1918 addresses in webhook targets.

5. **API version mismatch:** NocoDB latest (2026.x) defaults to v3 API.
   The v2 endpoints still work but are deprecated. Always check which
   version your code targets — the URL patterns differ:
   - v2: `/api/v2/meta/bases/<id>/tables`
   - v3: `/api/v3/tables/<id>/records`

   **However, on v2026.07.0 self-hosted, the v3 data endpoint
   `/api/v3/tables/<id>/records` returns 404** despite being the
   documented path. The working fallback is the **v2 equivalent
   `/api/v2/tables/<id>/records`** — it handles list / POST / PATCH / DELETE
   of records identically. Probe with curl before committing to v3.

6. **Token in header:** Use `xc-token` header (not `Authorization`).
   NocoDB's own auth scheme, not standard Bearer.

7. **PostgreSQL version:** Pin to `postgres:16-alpine`. NocoDB's migration
   scripts are tested against PG 16. PG 17+ may work but is not officially
   supported.

8. **MCP and Swagger endpoints may 404 on self-hosted:** On v2026.07.0
   self-hosted, `/api/v3/mcp`, `/apis/v3/data`, and `/apis/v3/meta` all
   return 404 despite being documented upstream. Do NOT present MCP as a
   guaranteed feature without verifying with a curl probe first. The REST
   API under `/api/v2/` and `/api/v3/` is the reliable integration surface.

9. **NocoDB is not a knowledge graph or semantic search engine:** It stores
   long text in LongText fields but does not index it semantically. For
   research storage that needs "find by concept, not by exact keyword,"
   pair NocoDB (structured metadata) with Obsidian/notes (full content)
   or pgvector/Honcho (semantic search). Do not sell NocoDB as a
   replacement for a wiki or notebook.

10. **Cookie jar + xc-token both required:** On v2026.07+, API calls with
    `xc-token` alone return 401. Login via `/api/v2/auth/user/signin` and
    capture both `nc_token` + `refresh_token` cookies (HttpOnly) with
    `curl -c cookies.txt`. Subsequent calls need `-b cookies.txt -H "xc-token: $TOKEN"`.
    Cookies expire — re-login when auth breaks. See Authentication section.

11. **API responses use column TITLES, not column_names:** When you `GET /api/v2/tables/{id}/records`,
    the response uses the human-readable `title` you set when creating the column,
    not the snake_case `column_name`. Example: a column with `column_name: "lid"` and
    `title: "WA LID"` returns `{"WA LID": "...", "Phone": "...", "Role in source group": "..."}`.
    Scripts using `record["lid"]` will silently get `KeyError`/`None`. **Always
    discover titles via `GET /api/v2/meta/tables/{id}` and build a column_name→title
    map before parsing responses.** This affects all read paths (list, post response
    echoes, PATCH responses). Same gotcha applies to `GET /api/v2/meta/tables/{id}/columns`
    — the response uses `title` as the display label and `column_name` for scripting.

12. **DEFAULT values not applied on POST inserts:** Setting `default: "uncontacted"`
    on a SingleSelect column in the schema does NOT auto-fill on `POST /records`.
    Records created via API will have `null` in that column unless you set the value
    explicitly per record. **Always send all default values explicitly in bulk
    insert payloads.** The UI applies defaults via its own form binding layer;
    the API does not.

13. **`unique: true` works, but `required: true` is sometimes ignored on initial
    column create:** If a column with `unique=True, required=True` accepts rows with
    null after creation, do a follow-up PATCH to the column with `rqd: true` to
    force the constraint. Verified on v2026.07.0 self-hosted.

## Integration Opportunities

- **n8n:** Use webhook nodes to trigger n8n workflows on record events
  (`http://janitor-n8n:5678/webhook/...`)

14. **MultiSelect field creation requires the `colOptions.options` array, not the
    `dtxp` CSV string shown in docs.** On v2026.07+, the only working path is
    `POST /columns` (creates empty column) → `PATCH /columns/{id}` with
    `{"colOptions":{"options":[{"title":"x","color":"#hex"}]}}`. The documented
    endpoints `POST /columns/{id}/options`, `/options/bulk`, and `/select-options/{id}`
    all return 404. Reads return the field as a **comma-separated string**, not a
    JSON array. **See `references/multiselect-api.md` for the full pattern including
    bulk-assign, destructive PATCH semantics, and the broken `?where=` filter
    workaround.**

15. **Cookie jar expiration produces silent false-positive diffs.** When
    `nc_token`/`refresh_token` cookies expire mid-session, the API returns `401`
    for read calls — which scripts often conflate with "no records match this
    query." An expired cookie can make a diff script think the base has zero
    records, and report every existing record as "newly arrived" — when in fact
    the records were already present and a fresh login would have returned the
    correct count.

    **Probe cookie freshness BEFORE any diff/reconciliation run:**

    ```bash
    curl -s -m 5 -b /tmp/nocodb-cookies.txt -H "xc-token: $TOKEN" \
      -o /dev/null -w "%{http_code}" \
      http://127.0.0.1:1980/api/v2/tables/$TABLE_ID/records?limit=1
    # 401 → re-login needed (see Authentication section above)
    ```

    Use `-c /tmp/nocodb-cookies-fresh.txt` to write a new jar (don't overwrite
    the original — saves a debug step if you want to compare). Cookies
    typically have short TTLs during active agent sessions; daily re-login is
    a safe default.

    **Reusable NocoDB login one-liner** (saves the new cookie jar):

    ```bash
    EMAIL=$(grep '^NC_ADMIN_EMAIL=' ~/.janitor/docker/nocodb.env | cut -d= -f2)
    PASS=$(grep '^NC_ADMIN_PASSWORD=' ~/.janitor/docker/nocodb.env | cut -d= -f2)
    curl -s -m 10 -c /tmp/nocodb-cookies-fresh.txt \
      -H "Content-Type: application/json" \
      -X POST http://127.0.0.1:1980/api/v2/auth/user/signin \
      -d "{\"email\":\"$EMAIL\",\"password\":\"$PASS\"}"
    ```

## See Also

- Skill `janitor-docker-selfhost` — Docker Compose deployment patterns
- Skill `janitor-n8n` — n8n integration (webhook-triggered workflows)
- Skill `janitor-honcho` — Honcho memory integration
- Skill `janitor-waha` — group member diff methodology + `scripts/diff-waha-group.py`
- NocoDB docs: https://nocodb.com/docs/product-docs
- NocoDB self-hosting: https://nocodb.com/docs/self-hosting
- NocoDB env vars: https://nocodb.com/docs/self-hosting/environment-variables
- `references/multiselect-api.md` — complete MultiSelect API pattern
