---
name: janitor-n8n
description: "Deploy and operate n8n self-hosted for Janitor."
version: 1.0.0
platforms: [linux, macos]

metadata:
  hermes:
    tags: [n8n, docker, self-host, workflows, automation, compose, devops]
    category: devops
---

# janitor-n8n

Deploy and operate n8n self-hosted workflow automation as a Janitor tool.
n8n provides visual workflow building with 400+ integrations, webhooks, and
code nodes. This skill covers the full lifecycle: deployment, API access
pattern (with the masked-API-key workaround), workflow CRUD, and webhook
triggering.

## Architecture

```
127.0.0.1:5678 → janitor-n8n (docker.n8n.io/n8nio/n8n:latest)
                  ├── SQLite DB at /home/node/.n8n/database.sqlite
                  ├── Encryption key in ~/.janitor/docker/n8n.env
                  └── Network: janitor-n8n-network (isolated bridge)
```

## When to Use

- Deploy or repair the n8n Docker stack
- Create, update, activate, or execute workflows programmatically
- Set up webhook-triggered automation pipelines
- Query execution history and status
- Integrate n8n with other Janitor services (Firecrawl, Honcho)

## Deploy (already done — reference for re-deploy)

```bash
bash ~/.janitor/skills/devops/janitor-n8n/scripts/deploy.sh
```

This script:
1. Generates `N8N_ENCRYPTION_KEY` via `openssl rand -hex 32`
2. Creates `~/.janitor/docker/n8n.env` (chmod 600, never overwritten)
3. Pulls `docker.n8n.io/n8nio/n8n:latest`
4. Starts container with healthcheck
5. Injects `N8N_API_URL` into `~/.janitor/.env`

**Files:**
- Compose: `~/.janitor/skills/devops/janitor-n8n/scripts/n8n-compose.yml`
  (copied to `~/.janitor/docker/n8n-compose.yml` on deploy)
- Env: `~/.janitor/docker/n8n.env` (contains encryption key — chmod 600)
- Deploy script: `~/.janitor/skills/devops/janitor-n8n/scripts/deploy.sh`
- Auth helper: `~/.janitor/skills/devops/janitor-n8n/scripts/n8n-auth.sh`
- Credentials in: `~/.janitor/.env` (`N8N_USER_EMAIL`, `N8N_USER_PASSWORD`)

## Authentication (CRITICAL — Read This)

### The API Key Masking Bug

n8n v2.x **masks** the `rawApiKey` field with literal `...` in the HTTP
response body, even on key creation. This is a security feature that makes
it impossible to extract the full JWT API key via REST API. The `/api/v1/`
endpoints require `X-N8N-API-KEY` header and do NOT accept cookies.

### Workaround: Cookie-Based Auth with /rest/ Endpoints

Use the `/rest/` internal endpoints (not `/api/v1/`) with cookie-based
session auth. The `/rest/` endpoints are the same ones the n8n web UI uses
and accept the `n8n-auth` session cookie.

**Step 1: Obtain a session cookie**

```bash
source ~/.janitor/skills/devops/janitor-n8n/scripts/n8n-auth.sh
# Sets $N8N_COOKIE_JAR to a cookie file path
# Cookie valid for 7 days (n8n default)
```

The auth helper reads `N8N_USER_EMAIL` and `N8N_USER_PASSWORD` from
`~/.janitor/.env` automatically.

**Step 2: Use cookie in all API calls**

```bash
curl -s -b "$N8N_COOKIE_JAR" http://127.0.0.1:5678/rest/workflows
```

## API Reference (Tested Endpoints)

### Login

```bash
curl -s -c /tmp/cookies.txt -X POST http://127.0.0.1:5678/rest/login \
  -H "Content-Type: application/json" \
  -d '{"emailOrLdapLoginId":"janitor@example.com","password":"${N8N_USER_PASSWORD}"}'
```

**Field name:** `emailOrLdapLoginId` (NOT `email` — this changed in v2.x)

### Health Check

```bash
curl -s http://127.0.0.1:5678/healthz
# Returns: {"status":"ok"}
```

### Workflow CRUD

#### List Workflows

```bash
curl -s -b "$N8N_COOKIE_JAR" http://127.0.0.1:5678/rest/workflows
# Returns: {"count": N, "data": [...]}
```

#### Create Workflow

```bash
curl -s -b "$N8N_COOKIE_JAR" -X POST http://127.0.0.1:5678/rest/workflows \
  -H "Content-Type: application/json" \
  -d '{
    "name": "My Workflow",
    "nodes": [
      {
        "parameters": {"path":"my-endpoint","responseMode":"lastNode","options":{}},
        "name": "Webhook",
        "type": "n8n-nodes-base.webhook",
        "typeVersion": 2,
        "position": [240, 300],
        "webhookId": "unique-id-here"
      },
      {
        "parameters": {"jsCode": "return [{json: {result: \"processed\"}}];"},
        "name": "Process",
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [460, 300]
      }
    ],
    "connections": {
      "Webhook": {"main": [[{"node": "Process", "type": "main", "index": 0}]]}
    },
    "settings": {}
  }'
```

#### Get Workflow (need versionId for mutations)

```bash
curl -s -b "$N8N_COOKIE_JAR" http://127.0.0.1:5678/rest/workflows/{id}
# Extract versionId: .data.versionId
```

#### Update Workflow

```bash
curl -s -b "$N8N_COOKIE_JAR" -X PATCH http://127.0.0.1:5678/rest/workflows/{id} \
  -H "Content-Type: application/json" \
  -d '{"versionId":"UUID-from-get","name":"New Name"}'
```

#### Activate / Deactivate

```bash
# Activate (requires versionId)
curl -s -b "$N8N_COOKIE_JAR" -X POST http://127.0.0.1:5678/rest/workflows/{id}/activate \
  -H "Content-Type: application/json" \
  -d '{"versionId":"UUID"}'

# Deactivate
curl -s -b "$N8N_COOKIE_JAR" -X POST http://127.0.0.1:5678/rest/workflows/{id}/deactivate \
  -H "Content-Type: application/json" \
  -d '{"versionId":"UUID"}'
```

#### Archive + Delete (two-step — delete requires archive first)

```bash
# Step 1: Archive
curl -s -b "$N8N_COOKIE_JAR" -X POST http://127.0.0.1:5678/rest/workflows/{id}/archive \
  -H "Content-Type: application/json" \
  -d '{"versionId":"UUID"}'

# Step 2: Delete
curl -s -b "$N8N_COOKIE_JAR" -X DELETE http://127.0.0.1:5678/rest/workflows/{id}
```

### Webhook Trigger

Once a workflow with a Webhook node is **active**, trigger it:

```bash
# GET (default for webhook nodes without httpMethod set)
curl -s "http://127.0.0.1:5678/webhook/{path}?param=value"

# POST (requires httpMethod: "POST" in webhook node parameters)
curl -s -X POST "http://127.0.0.1:5678/webhook/{path}" \
  -H "Content-Type: application/json" \
  -d '{"key": "value"}'
```

**CRITICAL:** The webhook is only live when the workflow is `active: true`.
Test URLs (`/webhook-test/`) work only from the editor. Production URLs
(`/webhook/`) require activation.

### Execution History

```bash
# List executions
curl -s -b "$N8N_COOKIE_JAR" http://127.0.0.1:5678/rest/executions

# Get specific execution
curl -s -b "$N8N_COOKIE_JAR" http://127.0.0.1:5678/rest/executions/{id}
```

## Python Helper for Complex Operations

For multi-step API calls (create → activate → trigger → poll), use Python
instead of chained curl commands:

```python
import http.cookiejar, urllib.request, json, os

# Login
cj = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
email = os.environ["N8N_USER_EMAIL"]            # janitor@example.com
password = os.environ["N8N_USER_PASSWORD"]      # set in ~/.janitor/.env
login = json.dumps({"emailOrLdapLoginId": email,
                    "password": password}).encode()
opener.open(urllib.request.Request("http://127.0.0.1:5678/rest/login", login,
            headers={"Content-Type": "application/json"}))

# Create workflow
wf = json.dumps({"name": "...", "nodes": [...], "connections": {...},
                 "settings": {}}).encode()
resp = opener.open(urllib.request.Request("http://127.0.0.1:5678/rest/workflows",
                  wf, headers={"Content-Type": "application/json"}))
wf_id = json.loads(resp.read())["data"]["id"]

# Get versionId
resp = opener.open(f"http://127.0.0.1:5678/rest/workflows/{wf_id}")
ver = json.loads(resp.read())["data"]["versionId"]

# Activate
act = json.dumps({"versionId": ver}).encode()
opener.open(urllib.request.Request(f"http://127.0.0.1:5678/rest/workflows/{wf_id}/activate",
            act, headers={"Content-Type": "application/json"}))
```

## Container Management

```bash
# Status
docker ps --filter name=janitor-n8n

# Logs
docker logs janitor-n8n --tail 30

# Restart
docker compose -f ~/.janitor/docker/n8n-compose.yml --env-file ~/.janitor/docker/n8n.env restart

# Stop / Start
docker compose -f ~/.janitor/docker/n8n-compose.yml --env-file ~/.janitor/docker/n8n.env stop
docker compose -f ~/.janitor/docker/n8n-compose.yml --env-file ~/.janitor/docker/n8n.env start

# Update to latest
docker compose -f ~/.janitor/docker/n8n-compose.yml --env-file ~/.janitor/docker/n8n.env pull
docker compose -f ~/.janitor/docker/n8n-compose.yml --env-file ~/.janitor/docker/n8n.env up -d
```

## Pitfalls

1. **Login field name:** Use `emailOrLdapLoginId`, not `email`. n8n v2.x
   renamed this field. Using `email` returns 400 `invalid_type`.

2. **API key masking:** n8n literally inserts `...` into the JWT in the
   HTTP response body for `rawApiKey`. This is NOT a display artifact —
   the bytes contain literal dots. Do NOT waste time trying to extract
   the full key. Use cookie-based auth with `/rest/` endpoints instead.

3. **Workflow deletion requires archive first:** `DELETE /rest/workflows/{id}`
   returns 400 `"Workflow must be archived before it can be deleted."`.
   You must call `POST /rest/workflows/{id}/archive` with `versionId`
   first, THEN `DELETE`.

4. **Activation requires versionId:** The `/activate` and `/deactivate`
   endpoints require `{"versionId":"UUID"}` in the body. Get it from
   `GET /rest/workflows/{id}` → `.data.versionId`.

5. **PATCH vs PUT:** Use `PATCH /rest/workflows/{id}` for partial updates.
   `PUT` is NOT supported (returns 404 HTML error page).

6. **Webhook HTTP method:** Default webhook nodes accept GET. For POST,
   set `"httpMethod": "POST"` in the webhook node parameters.

7. **Webhook only works when active:** Production webhooks (`/webhook/`)
   are only registered when the workflow is activated. Inactive workflows
   return 404 `"webhook is not registered"`.

8. **N8N_SECURE_COOKIE:** Set to `false` in the compose for localhost HTTP.
   If `true`, the auth cookie requires HTTPS and won't work over plain HTTP.

9. **Orphan containers warning:** Running n8n compose shows orphan warnings
   for Firecrawl/Honcho containers. This is cosmetic — add `--project-name`
   or ignore it. Do NOT use `--remove-orphans` or you'll kill other stacks.

10. **Python in n8n container:** The n8n image doesn't include Python 3.
    Code nodes using Python mode will show a warning. JS mode works fine.
    For Python, deploy an external task runner (see n8n docs).

11. **Two CLI surfaces, not one:** n8n has BOTH a *Server CLI* (runs in
    the container via `docker exec n8n n8n ...`) AND a *n8n CLI*
    (the newer `n8n-cli` package that wraps the public REST API and
    runs anywhere with network access). Server CLI bypasses access
    controls and requires DB access; n8n CLI requires an API key but
    respects user permissions. Commands differ: e.g. `n8n-cli package
    export --workflow-id=...` (API wrapper) is NOT `n8n
    export:workflow` (server-side, direct DB).

12. **HTML webhook responses are sandboxed (v1.103.0+):** Since v1.103.0
    n8n automatically wraps HTML webhook responses in `<iframe>` tags.
    JavaScript that tries to access the top-level window or local
    storage FAILS inside the iframe. Authentication headers (basic
    auth) are NOT available in the sandbox. Relative URLs
    (`<form action="/">`) do NOT work — use absolute URLs. This is
    intentional security; no env var disables it.

13. **`EXECUTION_DATA_STORAGE_MODE` is tier-gated:** `database`,
    `filesystem` work on all plans. **`s3` and `azure` modes require
    an Enterprise license** — setting these on Community or Pro will
    fail at startup.

14. **`N8N_CONCURRENCY_PRODUCTION_LIMIT` controls BOTH modes:**
    In regular mode it caps concurrent production executions. In
    queue mode, when set to a value other than `-1`, n8n uses it
    INSTEAD of the worker's `--concurrency` flag. Pick one source of
    truth — setting both leads to quiet surprises.

15. **Queue mode requires shared encryption key:** Workers cannot
    decrypt credentials without `N8N_ENCRYPTION_KEY` set to the SAME
    value as the main instance. Forget this and workers will appear
    "alive" but execution will fail at every credential lookup with
    opaque decryption errors. Always export `N8N_ENCRYPTION_KEY`
    alongside the worker env.

## Web UI Access

n8n web UI is accessible at `http://127.0.0.1:5678` from any browser.
The first-time setup creates the Owner account. The Owner account is
already created:
- Email: `janitor@example.com`
- Password: in `~/.janitor/.env` → `N8N_USER_PASSWORD`

## Integration Opportunities

- **Firecrawl:** Use HTTP Request nodes to call `http://127.0.0.1:1974/v0/*`
- **Honcho:** Use HTTP Request nodes with Bearer Auth to call Honcho API
- **Ollama:** Direct LLM calls to `http://127.0.0.1:11434/api/generate`
- **External services:** Slack, Gmail, Telegram via n8n's built-in nodes

## Authoritative Documentation Source

n8n publishes a full docs index optimized for LLM consumption at
`https://docs.n8n.io/llms.txt` (~280KB, all pages listed). Every docs page
is available as clean markdown by appending `.md` to the URL (e.g.
`docs.n8n.io/build/flow-logic` → `docs.n8n.io/build/flow-logic.md`).

**When building n8n documentation, workflows, or reference material:** extract
from these `.md` endpoints via `web_extract` instead of relying on model
knowledge (which goes stale every release). See
`references/n8n-docs-extraction.md` for the full technique — URL patterns,
section map, and the 3-subagent parallelization pattern used to build
a local n8n docs project.

## See Also

- Skill `janitor-docker-selfhost` — Docker Compose deployment patterns
- Skill `janitor-firecrawl` — Firecrawl integration (scraping from workflows)
- Skill `janitor-honcho` — Honcho integration (memory in workflows)
- n8n docs: https://docs.n8n.io
- n8n llms.txt index: https://docs.n8n.io/llms.txt
- n8n API reference: https://docs.n8n.io/api/reference
