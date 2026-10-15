# Upstream Compatibility

This skill patches the Open Design source tree in four places:

1. `apps/daemon/src/runtimes/defs/janitor.ts` — new file (no upstream conflict)
2. `apps/daemon/src/runtimes/registry.ts` — adds one import + one array entry
3. `apps/web/src/components/AgentIcon.tsx` — adds one entry in `ICON_EXT`
4. `apps/web/public/agent-icons/janitor.png` — new asset (no upstream conflict)

This document explains what to do when upstream changes conflict with
our patches.

## Scenario 1: Upstream renames `registry.ts`

The patch uses this anchor in `02-patch-registry.sh`:

```bash
sed -i '/^  hermesAgentDef,$/a\  janitorAgentDef,' "${REGISTRY}"
```

If upstream renames the file or the array, this sed fails silently
(no match). Symptoms:

- `integrate-janitor.sh register` says "registry ya tiene..."
  but Janitor is not in the picker
- `/api/agents` returns no entry with `id: "janitor"`

**Fix**: Find the new location of the SHIPPED_AGENT_DEFS array (BASE_AGENT_DEFS on older releases) and update
the sed anchor. Re-run the script.

## Scenario 2: Upstream moves `defs/` to a different package

Currently `apps/daemon/src/runtimes/defs/`. If upstream restructures the
package layout, `01-register-agent-def.sh` will copy the file to a path
that's no longer in the import graph.

**Fix**: Update the `JANITOR_DEF_DST` variable in the script.

## Scenario 3: Upstream changes `AgentIcon.tsx` API

The current API uses two structures:

```ts
const ICON_EXT: Record<string, 'svg' | 'png'> = { ... };
const MONO_ICONS = new Set([ ... ]);
```

If upstream replaces these with a different lookup (e.g. a map of
component references, or auto-discovery from a manifest file), the sed
patterns in `04-patch-agent-icon.sh` will fail.

**Fix**: Rewrite the patch as a TypeScript-aware edit using
`ts-morph`, or hand-merge the conflict the first time and document the
new anchor.

## Scenario 4: Upstream changes the agent def interface

`RuntimeAgentDef` (in `apps/daemon/src/runtimes/types.ts`) gains a
required field. Janitor's def file in `agent-defs/janitor.ts` will fail
TypeScript checks and the daemon won't start.

**Fix**: Add the new required field to `janitor.ts` with a sane default.
The def file in this skill is the source of truth — keep it in sync
with upstream's `RuntimeAgentDef` interface.

## Verifying After an Upstream Sync

Use the pinned source release documented in SKILL.md. Do not merge a moving
upstream branch into an existing customized installation as part of setup.
After reviewing and backing up a deliberately selected upgrade, validate it:

```bash
cd "$OD_SOURCE_DIR"
mise exec -- bash "$JANITOR_SKILLS_DIR/janitor-opendesign/scripts/integrate-janitor.sh" register
mise exec -- bash "$JANITOR_SKILLS_DIR/janitor-opendesign/scripts/safe-pnpm-install.sh" install --frozen-lockfile
mise exec -- bash "$JANITOR_SKILLS_DIR/janitor-opendesign/scripts/start.sh" web
bash "$JANITOR_SKILLS_DIR/janitor-opendesign/scripts/status.sh"
curl --fail --max-time 30 http://127.0.0.1:45351/api/agents
```

Confirm exactly one available agent with `id: "janitor"`. Read the stdio MCP
configuration from `/api/mcp/install-info` and validate initialize/tools/list;
0.25.0 does not implement an HTTP `/mcp` route.

If any of those fail, check the relevant log:

```bash
tail -100 ~/open-design/.tmp/tools-dev/default/logs/daemon/latest.log
```

## Minimal-Surface Principle

We patch the **minimum** number of files. Specifically:

- We do NOT touch `tools/dev/src/index.ts` (would require rebuild)
- We do NOT touch `apps/daemon/src/runtimes/detection.ts` (Janitor uses
  the same detection pipeline as every other agent)
- We do NOT modify `package.json` or `pnpm-workspace.yaml` (the def
  file lives in the standard `defs/` directory which is already in
  the workspace)

A new upstream version still requires compilation and runtime validation.
Idempotent source patching does not certify an upgrade or database migration.
