# Janitor Fork Changelog

Notable changes specific to the Janitor fork of hermes-agent. Upstream
changes are documented in the upstream release notes.

## Unreleased

### Added
- **MCP dashboard endpoints:** `POST /api/mcp/servers/{name}/discover` (returns
  full tool descriptors with `inputSchema`) and `GET /api/mcp/servers/{name}/logs`
  (returns per-server tail of `mcp-stderr.log`). The workspace UI image
  expects both; previously the fork returned 404 and the workspace fell back
  to `config.yaml`. The auth gap between workspace and dashboard (workspace
  sends `HERMES_API_TOKEN` as bearer; dashboard requires `_SESSION_TOKEN`) is
  tracked separately — these endpoints are reachable today via browser cookie
  or `X-Hermes-Session-Token` header. See
  `docs/superpowers/specs/2026-08-09-mcp-discover-logs-endpoints-design.md`.
