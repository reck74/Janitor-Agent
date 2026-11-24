"""janitor-opendesign: guided Open Design install (preflight, install, register, verify, uninstall).

Behaviour tests against temp homes with fake ``git``/``node``/``pnpm``/``janitor`` binaries
first on PATH, a fake Open Design source tree and a fake daemon on an ephemeral loopback
port. Nothing is cloned, installed or started for real.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
import yaml

from janitor import services

REPO_ROOT = Path(__file__).resolve().parents[2]
SKILL_DIR = REPO_ROOT / "janitor" / "skills" / "integrations" / "janitor-opendesign"
SCRIPT = SKILL_DIR / "scripts" / "opendesign_setup.py"

pytestmark = pytest.mark.linux_only

REGISTRY = """import { claudeAgentDef } from './defs/claude.js';
import { hermesAgentDef } from './defs/hermes.js';

export const BASE_AGENT_DEFS = [
  claudeAgentDef,
  hermesAgentDef,
];
"""
AGENT_ICON = """const ICON_EXT: Record<string, 'svg' | 'png'> = {
  claude: 'svg',
  hermes: 'svg',
};
const MONO_ICONS = new Set([
  'claude',
  'janitor',
]);
"""

FAKE_GIT = r'''
import json, os, sys
argv = sys.argv[1:]
with open(os.environ["FAKE_LOG"], "a") as fh:
    fh.write(json.dumps(["git", *argv]) + "\n")
if argv[:1] == ["--version"]:
    print("git version 2.47.0"); sys.exit(0)
if argv[:1] == ["clone"]:
    dest = argv[-1]
    tree = json.loads(os.environ["FAKE_TREE"])
    for rel, body in tree.items():
        path = os.path.join(dest, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        if body is not None:
            open(path, "w").write(body)
    sys.exit(0)
if "tag" in argv:
    print("open-design-v0.10.0\nopen-design-v0.9.0"); sys.exit(0)
sys.exit(0)
'''

FAKE_PNPM = r'''
import json, os, sys
argv = sys.argv[1:]
with open(os.environ["FAKE_LOG"], "a") as fh:
    fh.write(json.dumps(["pnpm", *argv]) + "\n")
if argv[:1] == ["--version"]:
    print("9.12.0"); sys.exit(0)
if argv[:1] == ["install"]:
    os.makedirs("node_modules/.bin", exist_ok=True)
    path = "node_modules/.bin/tools-dev"
    open(path, "w").write("#!/bin/sh\nexit 0\n")
    os.chmod(path, 0o755)
sys.exit(0)
'''

FAKE_SIMPLE = r'''
import json, os, sys
with open(os.environ["FAKE_LOG"], "a") as fh:
    fh.write(json.dumps([os.path.basename(sys.argv[0]), *sys.argv[1:]]) + "\n")
print("v22.11.0"); sys.exit(0)
'''

OD_TREE = {
    "package.json": "{}",
    "apps/daemon/src/runtimes/registry.ts": REGISTRY,
    "apps/daemon/src/runtimes/defs/hermes.ts": "export const hermesAgentDef = {};\n",
    "apps/web/src/components/AgentIcon.tsx": AGENT_ICON,
    "apps/web/public/agent-icons/hermes.svg": "<svg/>",
}


class FakeDaemon:
    def __init__(self, agents: list[dict]) -> None:
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                body = {"/api/health": {"ok": True, "version": "0.10.0"}, "/api/agents": agents}.get(self.path)
                data = json.dumps(body if body is not None else {}).encode()
                self.send_response(200 if body is not None or self.path == "/" else 404)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()


class Env:
    def __init__(self, tmp: Path) -> None:
        self.tmp = tmp
        self.home = tmp / ".janitor"
        self.home.mkdir()
        self.source = self.home / "src" / "open-design"
        self.bin = tmp / "bin"
        self.bin.mkdir()
        self.log = tmp / "calls.log"
        for name, body in (("git", FAKE_GIT), ("pnpm", FAKE_PNPM), ("node", FAKE_SIMPLE), ("janitor", FAKE_SIMPLE)):
            path = self.bin / name
            path.write_text(f"#!{sys.executable}\n{body}", encoding="utf-8")
            path.chmod(0o755)

    def plant_tree(self, **overrides) -> None:
        for rel, body in {**OD_TREE, **overrides}.items():
            path = self.source / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            if body is not None:
                path.write_text(body, encoding="utf-8")
        (self.source / "apps/daemon/src/runtimes/defs").mkdir(parents=True, exist_ok=True)

    def calls(self) -> list[list[str]]:
        return [json.loads(l) for l in self.log.read_text().splitlines()] if self.log.exists() else []

    def run(self, *args: str, without: tuple[str, ...] = (), expect: int | None = 0) -> dict:
        bin_dir = self.bin
        if without:
            bin_dir = self.tmp / ("bin-without-" + "-".join(without))
            bin_dir.mkdir(exist_ok=True)
            for tool in self.bin.iterdir():
                if tool.name not in without and not (bin_dir / tool.name).exists():
                    (bin_dir / tool.name).symlink_to(tool)
        env = {k: v for k, v in os.environ.items() if not k.startswith(("HERMES_", "JANITOR_", "OD_"))}
        env.update(HOME=str(self.tmp), HERMES_HOME=str(self.home), PATH=str(bin_dir), FAKE_LOG=str(self.log),
                   FAKE_TREE=json.dumps(OD_TREE))
        proc = subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True,
                              env=env, timeout=120)
        if expect is not None:
            assert proc.returncode == expect, proc.stdout + proc.stderr
        return json.loads(proc.stdout)


@pytest.fixture
def env(tmp_path):
    return Env(tmp_path)


def _tree(root: Path) -> dict[str, bytes]:
    return {str(p.relative_to(root)): p.read_bytes() for p in sorted(root.rglob("*")) if p.is_file()}


def _free_port() -> int:
    import socket

    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


# ── contract ────────────────────────────────────────────────────────────


def test_frontmatter_and_it_is_an_application_without_service_manifest():
    text = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
    meta = yaml.safe_load(text.split("---", 2)[1])
    assert meta["name"] == "janitor-opendesign"
    assert len(meta["description"]) <= 60
    assert set(meta["platforms"]) <= {"linux", "macos"}
    assert not (SKILL_DIR / "service.yaml").exists()
    assert "opendesign" not in {s.name for s in services.discover_services()}


# ── preflight / install ─────────────────────────────────────────────────


def test_preflight_is_read_only(env):
    env.plant_tree()
    before = _tree(env.tmp / ".janitor")
    doc = env.run("preflight", "--daemon-port", str(_free_port()), "--web-port", str(_free_port()))
    assert doc["source"]["state"] == "open-design" and doc["integration"]["registered"] is False
    assert doc["recommendation"] == "install"  # dependencies missing
    assert _tree(env.tmp / ".janitor") == before
    assert all(call[1:] == ["--version"] for call in env.calls()), env.calls()


@pytest.mark.parametrize("missing", ["git", "pnpm", "node"])
def test_install_refuses_without_prerequisites_and_writes_nothing(env, missing):
    doc = env.run("install", without=(missing,), expect=1)
    assert doc["reason"] == f"{missing}_missing"
    assert not env.source.exists()
    assert not [c for c in env.calls() if c[1:2] in (["clone"], ["install"])]


def test_install_clones_the_newest_release_once_and_installs_dependencies(env):
    first = env.run("install")
    second = env.run("install")
    assert first["clone"] == "cloned" and first["ref"] == "open-design-v0.10.0"
    assert first["dependencies"] == "installed"
    assert second["clone"] == "present" and second["dependencies"] == "present"
    calls = env.calls()
    assert len([c for c in calls if c[:2] == ["git", "clone"]]) == 1
    assert ["git", "-C", str(env.source), "checkout", "--quiet", "open-design-v0.10.0"] in calls
    assert len([c for c in calls if c[:2] == ["pnpm", "install"]]) == 1


# ── register / uninstall ────────────────────────────────────────────────


def test_register_is_idempotent_and_uninstall_restores_the_tree(env):
    env.plant_tree()
    original = _tree(env.source)
    first = env.run("register")
    second = env.run("register")
    assert first["integration"]["registered"] and len(first["changed"]) == 4
    assert second["changed"] == []
    registry = (env.source / "apps/daemon/src/runtimes/registry.ts").read_text()
    assert registry.count("janitorAgentDef") == 2
    icon = (env.source / "apps/web/src/components/AgentIcon.tsx").read_text()
    assert "  janitor: 'png',\n" in icon and "  'janitor',\n" not in icon

    undone = env.run("uninstall")
    assert undone["source_kept"] == str(env.source) and undone["trash_hint"]
    after = _tree(env.source)
    # The MONO_ICONS line register dropped was Open Design's own mistake: it stays out.
    expected = dict(original)
    expected["apps/web/src/components/AgentIcon.tsx"] = AGENT_ICON.replace("  'janitor',\n", "").encode()
    assert after == expected
    assert sorted(Path(p).name for p in undone["moved_aside"]) == ["janitor.png", "janitor.ts"]
    assert all(Path(p).is_file() for p in undone["moved_aside"])


def test_register_refuses_when_upstream_moved_an_anchor(env):
    env.plant_tree(**{"apps/daemon/src/runtimes/registry.ts": REGISTRY.replace("  hermesAgentDef,\n", "")})
    before = _tree(env.source)
    doc = env.run("register", expect=1)
    assert doc["reason"] == "anchor_missing"
    assert _tree(env.source) == before


# ── verify ──────────────────────────────────────────────────────────────


@pytest.mark.parametrize("agents, ok, reason", [([{"id": "claude"}, {"id": "janitor"}], True, None),
                                                ([{"id": "claude"}], False, "janitor_not_listed")])
def test_verify_needs_a_real_answer_and_janitor_in_the_agent_list(env, agents, ok, reason):
    silent = env.run("verify", "--daemon-port", str(_free_port()), "--web-port", str(_free_port()), expect=1)
    assert silent["reason"] == "service_unreachable"
    daemon = FakeDaemon(agents)
    try:
        doc = env.run("verify", "--daemon-port", str(daemon.port), "--web-port", str(daemon.port),
                      expect=0 if ok else 1)
    finally:
        daemon.close()
    assert doc["service"]["daemon"]["responds"] is True
    assert doc["ok"] is ok and doc.get("reason") == reason
    assert doc["service"]["mcp_url"] == f"http://127.0.0.1:{daemon.port}/mcp"
