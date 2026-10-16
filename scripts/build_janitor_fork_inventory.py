#!/usr/bin/env python3
"""Inventory the historical fork and current engine delta without deleting files.

The classification table is a reviewed ownership policy, not a dead-code detector.
Unknown families fail so a future sync must declare their owner and consumer.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
ENGINE = "d923a5eb487a17c0a68801bba9ef0f56c81040a8"
FORK = "282a00fc0875455c5f611062eb1a6d2729600d7f"
BASE = "f80f453ae0679347e38abc917c7f94f717bf96c5"
OUTPUT = "legacy/fork-inventory.json"

# Explicit migrations; the historical path stays visible in the inventory.
MOVED = {
    "assets/janitor/config.yaml": "legacy/config/config-pre-1.0.yaml",
    "agent/opencode_orchestrator.py": "skills/janitor-opencode/scripts/client.py",
    "tools/opencode_orchestrator.py": "skills/janitor-opencode/scripts/client.py",
    "agent/opencode_session_manager.py": "legacy/prototypes/agent/opencode_session_manager.py.txt",
    "agent/janitor_language_guard.py": "legacy/prototypes/agent/janitor_language_guard.py.txt",
    "tools/agent_router.py": "legacy/prototypes/tools/agent_router.py.txt",
    "tools/specialized_agents.py": "legacy/prototypes/tools/specialized_agents.py.txt",
    "gateway/platforms/whatsapp.py": "legacy/prototypes/gateway/whatsapp.py.txt",
    "gateway/platforms/feishu_meeting_invite.py": "legacy/prototypes/gateway/feishu_meeting_invite.py.txt",
    "scripts/test_opencode_orchestrator.py": "legacy/prototypes/scripts/test_opencode_orchestrator.py.txt",
    "skills/janitor-onboarding/scripts/honcho-compose.yml": "skills/janitor-honcho/scripts/honcho-compose.yml",
    "optional-skills/devops/janitor-skill-integration/SKILL.md": "skills/janitor-skill-integration/SKILL.md",
}
CORE = {
    "gateway/run_busy.py": ("gateway/run.py", "Suppress only the original restart message using stable scoped transport identity."),
    'agent/anthropic_discovery_aliases.py': ('agent/anthropic_adapter.py', 'Round-trip only structured OAuth discovery references; preserve user data, schema literals and stored history.'),
    'agent/anthropic_adapter.py': ('agent/transports/anthropic.py', 'Render OAuth discovery names consistently in the copied outbound tool history.'),
    'agent/transports/anthropic.py': ('agent/turn_truncation.py', 'Resolve OAuth bridge names and structured references before dispatch without rewriting arbitrary arguments.'),
    'agent/copilot_acp_stream.py': ('agent/copilot_acp_client.py', 'Stream ACP progress with profile context, bounded lifecycle and per-call cancellation; hold tool envelopes for parsing.'),
    'agent/copilot_acp_client.py': ('agent/client_lifecycle.py', 'Incremental text/reasoning delivery and bounded draining of trailing ACP notifications.'),
    'agent/error_classifier.py': ('agent/turn_api_error.py', 'Read botocore HTTP status from structured response metadata so validation errors remain terminal.'),
    'agent/gemini_native_adapter.py': ('agent/client_lifecycle.py', 'Translate promptFeedback blocks into explicit terminal content-filter results in stream and non-stream paths.'),
    'agent/gemini_schema.py': ('agent/gemini_native_adapter.py', 'Resolve local schema references before legacy filtering and preserve unconstrained array elements.'),
    'agent/turn_failure_copy.py': ('agent/turn_api_error.py', 'Use Vertex credential/IAM and Copilot CLI remedies appropriate to their authentication modes.'),
    'agent/turn_response_check.py': ('agent/conversation_loop.py', 'Apply existing encrypted-replay recovery to HTTP-200 Responses failures before cross-provider fallback.'),
    'agent/transports/codex_app_server_session.py': ('agent/codex_runtime.py', 'Return the protocol-defined empty permission grant for declined escalation requests.'),
    'agent/transports/codex_event_projector.py': ('agent/transports/codex_app_server_session.py', 'Keep native compaction accounting events out of assistant conversation text.'),
    'agent/turn_api_call.py': ('agent/conversation_loop.py', 'Enable incremental ACP delivery only for clients declaring the implemented streaming capability.'),
    'agent/transports/chat_completions.py': ('agent/turn_api_call.py', 'Apply provider wire projection after canonical cache identity construction.'),
    'providers/base.py': ('agent/transports/chat_completions.py', 'Identity-by-default final request projection with a concrete Vertex native-schema consumer.'),
    'plugins/model-providers/vertex/__init__.py': ('providers/base.py', 'Preserve tool JSON Schema via documented native Google override instead of the lossy OpenAI translator.'),
    'gateway/restart_dedup.py': ('gateway/run_busy.py', 'Bind restart redelivery identity to platform, conversation, profile and sender.'),
    'gateway/slash_commands.py': ('gateway/run_busy.py', 'Persist stable restart-command identity alongside the existing restart marker.'),
    'gateway/kanban_watchers_dispatcher.py': ('hermes_cli/kanban_decompose.py', 'Reserve durable automatic-decomposition budgets before any billable auxiliary call.'),
    'hermes_cli/kanban_decompose_retry.py': ('hermes_cli/kanban_decompose.py', 'Persist bounded retries and cooldowns in existing task events; explicit manual retries remain available.'),
    'hermes_cli/kanban_worker_log.py': ('hermes_cli/kanban_db_dispatch.py', 'Fence diagnostics and exit trailers by worker attempt while retaining append-only history.'),
    'hermes_cli/kanban_db_graph.py': ('hermes_cli/kanban_decompose.py', 'Reject oversized child graphs before database writes.'),
    'hermes_cli/kanban_decompose.py': ('gateway/kanban_watchers_dispatcher.py', 'Enforce automatic-attempt reservations while keeping manual decomposition explicit.'),
    'hermes_cli/kanban_db_dispatch.py': ('gateway/kanban_watchers_dispatcher.py', 'Initialize fresh worker heartbeat and use attempt-scoped crash evidence without stale review errors.'),
    'hermes_cli/kanban_db.py': ('hermes_cli/kanban.py', 'Report artifacts outside the owned scratch directory as rejected instead of silently succeeding.'),
    'hermes_cli/cli_shutdown.py': ('hermes_cli/cli_single_query.py', 'Close only the native Codex session after durable settlement and background drain.'),
    'hermes_cli/cli_single_query.py': ('hermes_cli/main.py', 'Preserve partial stdout and surface a terminal error once, including after native agent text.'),
    'hermes_cli/runtime_provider.py': ('hermes_cli/oneshot.py', 'Walk explicitly configured fallbacks after credential transport outages; keep configuration errors visible.'),
    'hermes_cli/shared_session_attach.py': ('hermes_cli/tui.py', 'Authenticate owner discovery with a nonce-bound HMAC without transmitting the lease; unsupported owners keep their lease.'),
    'hermes_cli/mcp_catalog.py': ('hermes_cli/web_routers/mcp.py', 'Support non-interactive catalog installation independent of the server process TTY.'),
    'hermes_cli/update_cmd_git.py': ('hermes_cli/update_cmd.py', 'Accept alternate Git paths only after a successful safe version probe.'),
    'plugins/platforms/slack/stream_text.py': ('plugins/platforms/slack/adapter.py', 'Preserve complete word boundaries when restarting a rejected streamed message.'),
    'gateway/platforms/api_server.py': ('hermes_cli/web_server.py', 'Preserve accepted text inside the existing request-body bound and reject excess multimodal parts explicitly.'),
    'gateway/platforms/base.py': ('plugins/platforms/telegram/adapter.py', 'Recognize supported HEIC raster input through the existing detector while rejecting unsupported formats.'),
    'plugins/platforms/slack/adapter.py': ('gateway/stream_consumer.py', 'Use shared stream relation and continuation boundaries without splitting words.'),
    "gateway/stream_consumer_think.py": ('gateway/stream_consumer.py', 'Classify reasoning-tag boundaries from received text independently of credential buffering.'),
    "acp_adapter/entry.py": ('pyproject.toml', 'Use the declared distribution version formatter for human --version output; preserve engine identity on the ACP protocol.'),
    "agent/credential_pool.py": ("agent/client_lifecycle.py", "Preserve the profile-scoped Nous inference override during pool rotation without rewriting the stored origin."),
    "hermes_cli/_startup_fast.py": ('hermes_cli/main.py', 'Read the owning installation source stamp from PM generations for accurate version provenance.'),
    "pm/paths.py": ('pm/cli.py', 'Resolve an immutable runtime generation back to its verified owning installation while preserving workspace execution.'),
    "gateway/stream_consumer_transport.py": ('gateway/stream_consumer.py', 'Redact known profile secrets and credential patterns before sending or writing overflow output.'),
    "gateway/stream_consumer.py": ('gateway/stream_consumer_transport.py', 'Filter streamed display text before buffering and flush final redacted content.'),
    "agent/stream_redact.py": ('gateway/stream_consumer.py', 'Incremental display-only credential redaction across chunk boundaries, without mutating prompts or stored conversation context.'),
    "hermes_cli/plugins_cmd.py": ('hermes_cli/plugins.py', 'Use the shared manifest collision rule in CLI listings and report resources-only MCP connections accurately.'),
    "hermes_cli/plugins_discovery.py": ('hermes_cli/plugins.py', 'Resolve same-source manifest collisions consistently, preferring the canonical directory and warning about backup copies.'),
    "hermes_cli/plugins_activation_live.py": ('hermes_cli/plugins.py', 'Read portable MCP declarations without activation or unnecessary startup blocking.'),
    "hermes_cli/plugins.py": ('hermes_cli/cli_init_mixin.py', 'Expose portable MCP server names through the public plugin facade.'),
    "hermes_cli/cli_init_mixin.py": ('cli.py', 'Accept explicitly enabled portable plugin MCP server toolsets using the existing manifest cache.'),
    "tools/mcp_tool_handlers.py": ('tools/mcp_tool.py', 'Apply authentication classification under the per-server RPC lock and keep media failures visible.'),
    "tools/mcp_tool_content.py": ('tools/mcp_tool_handlers.py', 'Return explicit redacted media-cache failure notices; retain structured-content fallback.'),
    "tools/mcp_tool_errors.py": ('tools/mcp_tool_wire.py', 'Record request-scoped HTTP method/status so folded SDK failures retain authentication semantics.'),
    "tools/mcp_tool_wire.py": ('tools/mcp_tool_transport.py', 'Strip only empty request metadata and attribute folded HTTP authentication failures to the RPC holding the existing server lock.'),
    "agent/chat_completion_stream_tools.py": ("agent/chat_completion_helpers.py", "Unchanged stream argument assembler extracted to its phase module; preserve repair and dropped-stream detection."),
    "hermes_cli/auth_api_keys.py": ("hermes_cli/auth.py", "API-key credential resolver extracted behind its public facade; explicit catalog endpoint avoids native discovery."),
    "hermes_cli/auth.py": ("hermes_cli/models.py", "Explicit catalog endpoints bypass native region discovery, retaining credential resolution and default behavior elsewhere."),
    "hermes_cli/auth_device_flow.py": ("hermes_cli/auth_nous.py", "Respect server polling intervals and permanent slow_down backoff while preserving device deadlines and transient outage recovery."),
    "hermes_cli/auth_nous.py": ("hermes_cli/auth.py", "Display the actual server polling interval for device login."),
    "tools/write_approval.py": ("hermes_cli/write_approval_commands.py", "Restrict pending identifiers and reject symlinked stores/records; validate record identity before approval."),
    "agent/file_safety.py": ("tools/file_tools.py", "Protect corrupt credential copies through the same read/search boundary as auth.json."),
    "tools/skill_manager_tool.py": ("tools/registry.py", "Resolve pinned/essential deletion protection by actual skill directory, including category paths and display aliases."),
    "tools/skill_manager_guards.py": ("tools/skill_manager_batch.py", "Use canonical skill directory identity for background-curator pin protection."),
    "agent/chat_completion_helpers.py": ("agent/turn_response_check.py", "Keep provider terminal reasons so malformed completed calls reach validation instead of being silently discarded as output-cap retries."),
    "agent/turn_tool_validation.py": ("agent/turn_tool_round.py", "Report malformed calls with matching tool error results immediately, preserving prefix and role alternation."),
    "cron/scheduler_script.py": ("cron/scheduler.py", "Resolve shell scripts through PM Bash and reject Windows WSL launcher stubs; keep interpreter ownership unchanged."),
    "agent/prompt_builder.py": ("agent/system_prompt.py", "Use portable context-file provenance headers while preserving context ordering and conversation prefix stability."),
    "agent/context_references.py": ("agent/context_references.py:preprocess_context_references", "Render folder provenance with consistent separators on Windows and POSIX without changing allowed-path boundaries."),
    "agent/subdirectory_hints.py": ("agent/agent_init.py", "Preserve native Windows path hints and POSIX shell quoting while retaining workspace containment and incremental hint discovery."),
    "hermes_state_lockowners.py": ("hermes_state.py", "Attribute SQLite writer locks on Btrfs only after verifying descriptor device/inode and its fdinfo lock; preserve collision and permission boundaries."),
    "hermes_cli/models.py": ("hermes_cli/model_switch_providers.py", "Fix cold-cache concurrency and keep discovery at configured relays without probing native hosts; preserve facade seams."),
    "hermes_cli/models_custom_cache.py": ("hermes_cli/models.py", "Profile-and-credential scoped cold-cache coordination; independent providers stay concurrent."),
    "plugins/platforms/telegram/telegram_entities.py": ("plugins/platforms/telegram/adapter.py", "Unchanged HTML entity helper extracted to keep the adapter within its inherited size cap."),
    "agent/secret_sources/bitwarden.py": ("agent/secret_sources/registry.py", "Remove duplicated registration left by sync; retain upstream provider behavior."),
    "hermes_cli/distribution_identity.py": ("hermes_cli/version_info.py", "Generic distribution identity keeps engine/plugin compatibility separate from product version."),
    "hermes_cli/version_info.py": ("hermes_cli/main.py", "Display product identity while retaining the Hermes compatibility version."),
    "hermes_cli/source_stamp.py": ("hermes_cli/source_build.py", "Product provenance stamp carries its engine and source identity."),
    "hermes_cli/source_build.py": ("hermes_cli/update_cmd.py", "Generic declared distribution hooks prepare pinned memory dependencies and Desktop builds."),
    "hermes_cli/update_cmd_fleet.py": ("hermes_cli/update_cmd.py", "Remove accidental duplicate helper; preserve stable fleet update behavior."),
    "hermes_cli/mcp_config.py": ("hermes_cli/web_routers/mcp.py", "MCP discover configuration consumed by the authenticated dashboard."),
    "hermes_cli/web_routers/mcp.py": ("hermes_cli/web_server.py", "Authenticated Janitor MCP discovery/log adapter registration."),
    "tools/mcp_tool_transport.py": ("tools/mcp_tool.py", "Capture and redact stderr per server/profile before any sink; normalize only empty MCP request metadata for SDK interoperability."),
    "plugins/platforms/telegram/adapter.py": ("plugins/platforms/telegram/plugin.yaml", "Current platform adapter retains admissions/topic routing and Janitor avatar/welcome."),
}
EXT = {
    "ci_baseline.py": (".github/workflows/lint.yml", "User-approved exact-engine sync baseline for health and byte-identical inherited blobs; PR-base enforcement and existing limits remain intact."),
    "telegram_branding.py": ("plugins/platforms/telegram/adapter.py", "Isolated welcome/avatar mixin preserves authorization, pairing, topic and redaction contracts."),
    "ci_contracts.py": ("scripts/run_janitor_tests.py", "Canonical test manifest and reusable workflow contracts."),
    "ci_smoke.py": ("scripts/janitor-ci-smoke.sh", "Disposable installer acceptance fixtures."),
    "desktop.py": ("janitor_cli.py", "PM-aware Janitor Desktop command."),
    "fork_audit.py": ("scripts/audit_janitor_merge.py", "Verify fork isolation on deterministic Git diffs."),
    "honcho.py": ("skills/janitor-honcho/scripts/deploy.sh", "Pinned local memory deployment and existing-volume credential preservation."),
    "honcho_probe.py": ("janitor_ext/honcho.py", "Real backend/provider health probes with redacted failures."),
    "install.py": ("scripts/janitor-install.sh", "Idempotent defaults/overlay/credentials and pinned provider installation."),
    "mcp_dashboard.py": ("hermes_cli/web_routers/mcp.py", "Authenticated discovery/probes in the selected profile."),
    "mcp_logs.py": ("tools/mcp_tool_transport.py", "Scoped stderr storage and credential redaction."),
    "migrate.py": ("scripts/migrate-janitor-1.0.sh", "Verified snapshots and configuration/profile migration."),
    "migrate_compat.py": ("scripts/migrate-janitor-v0.20.1.sh", "Backward-compatible invocation of the canonical migration."),
    "optional_deploy.py": ("skills/janitor-onboarding/SKILL.md", "Explicit optional installer binding to PM, repository and selected profile."),
    "products.py": ("scripts/bootstrap.sh", "Build and publish the managed interfaces/private command."),
    "release.json": ("janitor_ext/version.py", "Pinned product, engine and memory-provider release identity."),
    "service_auth.py": ("skills/janitor-n8n/scripts/n8n-auth.sh", "Preserve service credentials for repeatable optional deployment."),
    "startup.py": ("janitor_cli.py", "Startup diagnosis retains help/repair when base credentials are missing."),
    "tips_es.py": ("janitor_cli.py", "Spanish CLI tips injected by the wrapper."),
    "version.py": ("janitor_version.py", "Product version independent from engine compatibility."),
    "volumes.py": ("skills/janitor-lightrag/scripts/deploy.sh", "Offline optional-service volume migration without deleting source data."),
    "__init__.py": ("janitor_cli.py", "Isolated extension package."),
    "homes.py": ("janitor_ext/install.py", "Shared root/profile resolution for installer, repair and migration."),
    "profiles.py": ("janitor_ext/install.py", "Shared root/profile resolution for installer, repair and migration."),
}


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True, encoding="utf-8", errors="replace", timeout=120)


def decision(status: str, consumers: list[str], reason: str, replacement: str | None = None) -> dict:
    return {"classification": status, "consumers": consumers, "reason": reason, "replacement": replacement}


def _classify_historical(path: str, current: set[str], engine_paths: set[str]) -> dict | None:
    exists = (ROOT / path).is_file()
    replacement = MOVED.get(path)
    if path.startswith("docs/"):
        candidate = "legacy/docs/pre-1.0/" + path[5:]
        if (ROOT / candidate).is_file():
            replacement = candidate
    if path.startswith("skills/devops/janitor-"):
        candidate = "skills/" + path.removeprefix("skills/devops/")
        if (ROOT / candidate).is_file():
            replacement = candidate
    if replacement and not exists:
        status = "legacy" if replacement.startswith("legacy/") else "active"
        return decision(status, [replacement], "Historical location migrated; source and user-owned copies are preserved by migration/backup.", replacement)
    if path not in current:
        if exists and path in engine_paths:
            return decision("replaced_by_upstream", [path], "The previous fork delta is gone; the current file uses the pinned stable implementation.", f"{ENGINE}:{path}")
        if path.startswith("apps/desktop/"):
            for ext in (".ts", ".mjs", ".tsx"):
                candidate = str(Path(path).with_suffix(ext))
                if (ROOT / candidate).is_file():
                    return decision("replaced_by_upstream", [candidate], "Old Desktop format removed; the stable refactor owns this behavior.", candidate)
            return decision("replaced_by_upstream", ["apps/desktop/package.json"], "Stable Desktop removed the old file; current package entrypoints/build pipeline replace it.", "apps/desktop/")
        if path.startswith(".github/"):
            return decision("replaced_by_upstream", [".github/workflows/ci.yaml"], "Retired workflow/action superseded by the stable workflow graph.", ".github/workflows/ci.yaml")
        if path in {"agent/google_oauth.py", "agent/google_code_assist.py"}:
            return decision("replaced_by_upstream", ["plugins/model-providers/"], "Stable explicitly removed this implementation; no imports remain. Credential-file protection is retained.", "plugins/model-providers/")
        return decision("replaced_by_upstream", [], "Historical fork-only delta was removed by stable; no active file is reintroduced.", f"{ENGINE} (removal)")
    return None


def _classify_extension(path: str) -> dict | None:
    if path.startswith("contributors/emails/"):
        return decision("active", ["scripts/releases/authors.py", ".github/workflows/contributor-check.yml"], "Contributor mapping backed by a public GitHub commit-author association; ambiguous identities remain unmapped.")
    if path.startswith("legacy/"):
        return decision("legacy", ["legacy/README.md"], "Historical source/reference only; excluded from runtime, skill discovery and executable tests.", None)
    if path == ".claude/agents/janitor-dev-boss-autonomous.md":
        return decision("experimental", [".claude/agents/", "skills/janitor-opencode/SKILL.md"], "Explicit compatibility health agent; retired autonomous session-manager instructions are archived.", "skills/janitor-opencode/SKILL.md")
    if path.startswith("skills/devops/kanban-"):
        return decision("experimental", ["agent/skill_utils.py", "tests/hermes_cli/test_kanban_core_functionality.py"], "Manual compatibility playbook remains discoverable; current dispatcher does not auto-load it.", "hermes_cli/kanban.py")
    if path.startswith("skills/autonomous-ai-agents/hermes-agent/references/"):
        return decision("legacy", [], "Loose historical references have no SKILL.md or runtime entrypoint; retained pending separate archival, never a base capability.", "website/docs/")
    if path.startswith("skills/janitor-opencode/"):
        return decision("experimental", ["skills/janitor-opencode/SKILL.md", "janitor_ext/optional_deploy.py"], "Single retained HTTP client and explicit health command; no automatic routing or server installation.")
    if path.startswith("skills/janitor-"):
        skill = "/".join(path.split("/")[:2]) + "/SKILL.md"
        return decision("active", [skill, "janitor_ext/optional_deploy.py", "agent/skill_utils.py"], "Isolated Janitor skill; deployment is explicit except mandatory base Honcho. Personalized installed copies are preserved.")
    if path in CORE:
        consumer, reason = CORE[path]
        return decision("active", [consumer], reason)
    if path.startswith("janitor_ext/"):
        name = Path(path).name
        if name not in EXT:
            raise ValueError(f"Classify new extension explicitly: {path}")
        consumer, reason = EXT[name]
        return decision("active", [consumer], reason)
    if path.startswith("janitor_") and path.endswith(".py"):
        return decision("active", ["scripts/janitor", "pyproject.toml"], "Fork entrypoint/version/update adapter delegates shared core and preserves engine compatibility.")
    return None


def _classify_support(path: str) -> dict:
    if path.startswith("assets/janitor/"):
        consumers = ["plugins/platforms/telegram/adapter.py", "apps/desktop/janitor/build.mjs"] if Path(path).suffix in {".jpg", ".png"} else ["janitor_ext/install.py"]
        return decision("active", consumers, "Product persona, configuration overlay, skin or referenced identity asset; installed without replacing user customizations.")
    if path.startswith("apps/desktop/"):
        return decision("active", ["apps/desktop/package.json", "apps/desktop/janitor/build.mjs"], "Janitor source/bootstrap overlay or tested stable interface/build compatibility; no broad core rename.")
    if path.startswith(".github/"):
        return decision("active", ["GitHub Actions", ".github/workflows/ci.yaml"], "CI/release interface or canonical fork gate; workflow interface tests verify call contracts.")
    if path.startswith("tests/"):
        consumer = ".github/janitor-tests.txt" if "janitor" in Path(path).name else ".github/workflows/tests.yml"
        if path.startswith("tests/fixtures/prompt_surface/"):
            consumer = "tests/ci/test_prompt_surface.py"
        return decision("active", [consumer], "Behavior/regression coverage or generated prompt surface; upstream tests remain available in sync verification.")
    if path.startswith("scripts/"):
        if path.startswith("scripts/migrate-janitor-") and path not in {"scripts/migrate-janitor-1.0.sh", "scripts/migrate-janitor-v0.20.1.sh"}:
            return decision("legacy", ["manual compatibility command"], "Historical migration retained for existing users; new installations use the backed-up 1.0 migration.", "scripts/migrate-janitor-1.0.sh")
        consumers = ["MERGE_GUIDE.md"] if "audit" in path or "inventory" in path else ["scripts/bootstrap.sh", "skills/janitor-onboarding/SKILL.md"]
        if path.startswith("scripts/ci/") or path.endswith("run_janitor_tests.py"):
            consumers = [".github/workflows/ci.yaml", ".github/workflows/docs-site-checks.yml"]
        if path.startswith("scripts/whatsapp-bridge/"):
            consumers = ["scripts/whatsapp-bridge/package.json"]
        return decision("active", consumers, "Declared installer, validation, migration adapter or pinned tooling dependency.")
    if path.startswith("ui-tui/"):
        return decision("active", ["ui-tui/package.json", "janitor_cli.py"], "Skin-compatible branding/contract tests or lint-only preservation of stable behavior.")
    if path.startswith("web/"):
        return decision("active", ["web/package.json"], "Stable dashboard build or lint-only cleanup; product behavior preserved.")
    if path.startswith("website/"):
        if path.endswith("/godmode.md"):
            return decision("legacy", ["website/sidebars.ts"], "Old translated URL now directs readers to the current optional skill; old text archived.", "website/docs/user-guide/skills/optional/security/security-godmode.md")
        if path.endswith("model-catalog.json"):
            return decision("active", ["hermes_cli/model_catalog.py", "tests/hermes_cli/test_model_catalog.py"], "Generated from current model definitions using scripts/build_model_catalog.py.")
        return decision("active", ["website/package.json", "website/sidebars.ts"], "Current docs/build dependency contract, generated skill catalog or historical-page redirect; website-only scope.")
    if path.startswith("validation-evidence/"):
        return decision("active", ["JANITOR_RECOVERY_AUDIT.md"], "Sanitized, persistent validation evidence; does not contain credentials or certify unexecuted acceptance.")
    if path.startswith(".opencode/"):
        return decision("active", ["OpenCode repository instruction discovery", "MERGE_GUIDE.md"], "Repository tooling instructions enforce merge isolation and TUI gates.")
    if path.startswith("infographic/") or path == "janitor-tui.png":
        return decision("legacy", [], "Historical illustration retained in place; no active runtime consumer found. Not evidence of current UI or behavior.")
    if path in {"AGENTS.md", "CHANGELOG.md", "MERGE_GUIDE.md", "README.md"} or (path.startswith("JANITOR_") and path.endswith(".md")):
        return decision("active", ["repository documentation entrypoint"], "Product instructions, contracts, provenance or recovery evidence; audit records retain their observation date.")
    if path in {"package.json", "package-lock.json", "pyproject.toml", ".npmrc", ".gitignore", ".env.example"}:
        return decision("active", ["scripts/bootstrap.sh", "Git/npm/PM tooling"], "Pinned dependency/configuration or distribution identity contract; secrets are never committed.")
    raise ValueError(f"Unclassified current fork path: {path}")


def classify(path: str, historical: set[str], current: set[str], engine_paths: set[str]) -> dict:
    return (_classify_historical(path, current, engine_paths)
            or _classify_extension(path) or _classify_support(path))


def inventory() -> dict:
    historical = set(git("diff", "--name-only", "--no-renames", BASE, FORK).splitlines())
    current = set(git("diff", "--name-only", "--no-renames", ENGINE).splitlines())
    current.update(git("ls-files", "--others", "--exclude-standard").splitlines())
    current.discard(OUTPUT)
    engine_paths = set(git("ls-tree", "-r", "--name-only", ENGINE).splitlines())
    entries = []
    for path in sorted(historical | current):
        item = classify(path, historical, current, engine_paths)
        exists = (ROOT / path).is_file()
        entries.append({
            "path": path,
            "historical_fork_delta": path in historical,
            "current_engine_delta": path in current,
            "present": exists,
            "sha256": hashlib.sha256((ROOT / path).read_bytes()).hexdigest() if exists else None,
            **item,
        })
    return {
        "schema": 1,
        "engine": ENGINE,
        "fork_before_revival": FORK,
        "fork_merge_base": BASE,
        "scope": "Union of the historical fork delta, current tracked engine delta and nonignored untracked files; includes deleted and migrated paths.",
        "excluded": {OUTPUT: "Inventory excludes itself to avoid recursive content hashes."},
        "classification_note": "Active names indicate ownership/consumers, not completed live acceptance. Consumer entries include declared command/discovery interfaces. Legacy retained in place is explicitly identified.",
        "counts": dict(sorted(Counter(entry["classification"] for entry in entries).items())),
        "entries": entries,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    rendered = json.dumps(inventory(), ensure_ascii=False, indent=2) + "\n"
    target = ROOT / OUTPUT
    if args.check:
        if not target.is_file() or target.read_text(encoding="utf-8-sig") != rendered:
            print("Fork inventory is stale; regenerate after reviewing changed consumers.")
            return 1
    else:
        target.write_text(rendered, encoding="utf-8")
    print(f"Fork inventory: {len(json.loads(rendered)['entries'])} paths")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
