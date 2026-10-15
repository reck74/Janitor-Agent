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
    "hermes_cli/models.py": ("hermes_cli/model_switch_providers.py", "Fix deterministic cold-cache duplicate fetch and lost-row races while retaining facade seams."),
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
    "tools/mcp_tool_transport.py": ("tools/mcp_tool.py", "Capture and redact stderr per server/profile before any sink."),
    "plugins/platforms/telegram/adapter.py": ("plugins/platforms/telegram/plugin.yaml", "Current platform adapter retains admissions/topic routing and Janitor avatar/welcome."),
}
EXT = {
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
