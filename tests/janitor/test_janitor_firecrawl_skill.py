"""janitor-firecrawl: guided self-hosted Firecrawl (preflight, deploy, verify, activate, rollback).

Behaviour tests against temp homes with fake ``docker``/``sudo`` binaries first on PATH and a
fake Firecrawl HTTP API on an ephemeral loopback port. No real container, volume or home is
touched.
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

SKILL_DIR = REPO_ROOT / "janitor" / "skills" / "services" / "janitor-firecrawl"
SCRIPT = SKILL_DIR / "scripts" / "firecrawl_setup.py"
DEPLOY_SH = SKILL_DIR / "scripts" / "deploy.sh"
COMPOSE = SKILL_DIR / "scripts" / "firecrawl-compose.yml"
PROFILE_SECRETS = {"OPENAI_API_KEY": "sk-openai-SEEDED-0001", "TELEGRAM_BOT_TOKEN": "tg-bot-SEEDED-0003"}

pytestmark = pytest.mark.linux_only

FAKE_DOCKER = r'''
import json, os, subprocess, sys
state_path, log_path = os.environ["FAKE_DOCKER_STATE"], os.environ["FAKE_DOCKER_LOG"]
state = json.load(open(state_path))
argv = sys.argv[1:]
with open(log_path, "a") as fh:
    fh.write(json.dumps(argv) + "\n")
def save():
    json.dump(state, open(state_path, "w"))
cmd = argv[0] if argv else ""
if cmd == "info":
    if not state.get("daemon", True):
        print("Cannot connect to the Docker daemon", file=sys.stderr); sys.exit(1)
    print(state.get("root_dir", "/")); sys.exit(0)
if cmd == "compose":
    if argv[1:2] == ["version"]:
        print(state.get("compose", "2.29.1")); sys.exit(0)
    if "up" in argv:
        state["up_env_port"] = os.environ.get("JANITOR_FIRECRAWL_PORT")
        state["containers"] = state.get("after_up", {})
        if state.get("serve") and not state.get("server_pid"):
            # Stands in for the published API port; exits by itself after 20 s.
            server = ("import http.server, sys, time\n"
                      "class H(http.server.BaseHTTPRequestHandler):\n"
                      "    def log_message(self, *a): pass\n"
                      "    def do_GET(self):\n"
                      "        self.send_response(200); self.end_headers(); self.wfile.write(b'{}')\n"
                      "srv = http.server.HTTPServer(('127.0.0.1', int(sys.argv[1])), H)\n"
                      "srv.timeout = 0.5\n"
                      "end = time.time() + 20\n"
                      "while time.time() < end: srv.handle_request()\n")
            proc = subprocess.Popen([sys.executable, "-c", server, os.environ["JANITOR_FIRECRAWL_PORT"]],
                                    start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            state["server_pid"] = proc.pid
        save(); sys.exit(0)
    sys.exit(0)
if cmd == "inspect":
    c = state.get("containers", {}).get(argv[-1])
    if not c:
        sys.exit(1)
    print(f"{c['status']}|{c.get('health') or ''}"); sys.exit(0)
if cmd == "volume":
    sys.exit(1)
sys.exit(0)
'''

FAKE_SUDO = r'''
import json, os, sys
with open(os.environ["FAKE_SUDO_LOG"], "a") as fh:
    fh.write(json.dumps(sys.argv[1:]) + "\n")
sys.exit(1)
'''


class FakeFirecrawl:
    """Answers liveness and /v2/scrape like a self-hosted Firecrawl."""

    def __init__(self) -> None:
        self.calls: list[tuple] = []
        calls = self.calls

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def _send(self, code, body):
                data = json.dumps(body).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self):
                calls.append(("GET", self.path))
                self._send(200 if self.path == "/v0/health/liveness" else 404, {"status": "ok"})

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
                calls.append(("POST", self.path, body))
                self._send(200, {"success": True, "data": {"markdown": "# Example Domain"}})

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()


@pytest.fixture
def firecrawl_api():
    api = FakeFirecrawl()
    yield api
    api.close()


class Env:
    def __init__(self, tmp: Path) -> None:
        self.tmp = tmp
        self.home = tmp / ".janitor"
        self.home.mkdir()
        self.bin = tmp / "bin"
        self.bin.mkdir()
        self.state = tmp / "docker-state.json"
        self.logs = {name: tmp / f"{name}.log" for name in ("docker", "sudo")}
        for name, body in (("docker", FAKE_DOCKER), ("sudo", FAKE_SUDO)):
            path = self.bin / name
            path.write_text(f"#!{sys.executable}\n{body}", encoding="utf-8")
            path.chmod(0o755)
        self.set_docker(daemon=True, root_dir=str(tmp), containers={})
        (self.home / ".env").write_text("".join(f"{k}={v}\n" for k, v in PROFILE_SECRETS.items()), encoding="utf-8")

    def set_docker(self, **state) -> None:
        self.state.write_text(json.dumps(state), encoding="utf-8")

    def docker(self) -> dict:
        return json.loads(self.state.read_text(encoding="utf-8"))

    def calls(self, tool: str) -> list[list[str]]:
        path = self.logs[tool]
        return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines()] if path.exists() else []

    def run(self, *args: str, docker: bool = True, expect: int | None = 0):
        env = {k: v for k, v in os.environ.items() if not k.startswith(("HERMES_", "FIRECRAWL_", "JANITOR_"))}
        bin_dir = self.bin
        if not docker:
            bin_dir = self.tmp / "bin-nodocker"
            bin_dir.mkdir(exist_ok=True)
            if not (bin_dir / "sudo").exists():
                (bin_dir / "sudo").symlink_to(self.bin / "sudo")
        env.update(HOME=str(self.tmp), HERMES_HOME=str(self.home), PATH=str(bin_dir),
                   FAKE_DOCKER_STATE=str(self.state), FAKE_DOCKER_LOG=str(self.logs["docker"]),
                   FAKE_SUDO_LOG=str(self.logs["sudo"]))
        proc = subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True,
                              env=env, timeout=180)
        if expect is not None:
            assert proc.returncode == expect, proc.stdout + proc.stderr
        for value in PROFILE_SECRETS.values():
            assert value not in proc.stdout and value not in proc.stderr, f"secret leaked by {args}"
        return json.loads(proc.stdout)


@pytest.fixture
def env(tmp_path):
    e = Env(tmp_path)
    yield e
    assert e.calls("sudo") == [], "the skill must never call sudo"


def _running() -> dict:
    return {c: {"status": "running", "health": None} for c in services.get_service("firecrawl").containers}


def _tree(root: Path) -> dict[str, bytes]:
    return {str(p.relative_to(root)): p.read_bytes() for p in sorted(root.rglob("*")) if p.is_file()}


def _free_port() -> int:
    import socket

    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _forbidden(call: list[str]) -> bool:
    return ("down" in call or "rm" in call or "-v" in call or "--volumes" in call or "prune" in call
            or "--remove-orphans" in call)


# ── skill + manifest contract ────────────────────────────────────────────


def test_frontmatter_and_manifest_follow_the_contract():
    text = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
    meta = yaml.safe_load(text.split("---", 2)[1])
    assert meta["name"] == "janitor-firecrawl"
    assert len(meta["description"]) <= 60
    assert set(meta["platforms"]) <= {"linux", "macos"}
    port = meta["metadata"]["hermes"]["config"]["janitor.firecrawl_port"]["default"]
    service = services.get_service("firecrawl")
    assert service.url == f"http://127.0.0.1:{port}"
    assert subprocess.run(["bash", "-n", str(DEPLOY_SH)], capture_output=True).returncode == 0


def test_compose_is_prefixed_loopback_only_and_never_sees_the_profile_env():
    compose = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))
    names = {spec["container_name"] for spec in compose["services"].values()}
    assert names == set(services.get_service("firecrawl").containers)
    assert all(n.startswith("janitor-") for n in names)
    assert all(v["name"].startswith("janitor-") for v in compose["volumes"].values())
    assert all(n["name"].startswith("janitor-") for n in compose["networks"].values())
    ports = [p for spec in compose["services"].values() for p in spec.get("ports", [])]
    assert ports and all(p.startswith("127.0.0.1:") for p in ports)
    env_files = [e["path"] if isinstance(e, dict) else e
                 for spec in compose["services"].values() for e in spec.get("env_file", [])]
    assert env_files and set(env_files) == {"./firecrawl.env"}


# ── preflight / deploy ───────────────────────────────────────────────────


def test_preflight_is_read_only(env):
    env.set_docker(daemon=True, root_dir=str(env.tmp), containers=_running())
    before = _tree(env.tmp / ".janitor")
    doc = env.run("preflight", "--port", str(_free_port()))
    assert doc["ok"] and doc["docker"]["daemon"] and doc["service"]["state"] == "running"
    assert doc["activation"]["active"] is False
    assert _tree(env.tmp / ".janitor") == before
    readonly = {"info", "inspect", "volume", "compose"}
    for call in env.calls("docker"):
        assert call[0] in readonly and "up" not in call and not _forbidden(call), call


@pytest.mark.parametrize("docker, daemon, reason", [(False, True, "docker_missing"),
                                                    (True, False, "docker_daemon_down")])
def test_deploy_refuses_without_prerequisites_and_writes_nothing(env, docker, daemon, reason):
    env.set_docker(daemon=daemon, root_dir=str(env.tmp), containers={})
    doc = env.run("deploy", docker=docker, expect=1)
    assert doc["reason"] == reason
    assert not (env.home / "docker").exists()
    assert not [c for c in env.calls("docker") if "up" in c]


def test_deploy_is_idempotent_and_the_stack_gets_only_its_own_credentials(env):
    env.set_docker(daemon=True, root_dir=str(env.tmp), containers={}, after_up=_running(), serve=True)
    port = str(_free_port())
    first = env.run("deploy", "--port", port, "--timeout", "15", "--interval", "0.2")
    stack_env = env.home / "docker" / "firecrawl.env"
    credentials = stack_env.read_bytes()
    second = env.run("deploy", "--port", port, "--timeout", "15", "--interval", "0.2")
    assert first["ok"] and second["ok"] and not first["activated"]
    assert (first["compose"], second["compose"]) == ("installed", "unchanged")
    assert (first["stack_env"], second["stack_env"]) == ("generated", "kept")
    assert stack_env.read_bytes() == credentials, "credentials are never regenerated"
    assert oct(stack_env.stat().st_mode & 0o777) == "0o600"
    body = stack_env.read_text(encoding="utf-8")
    assert not any(v in body for v in PROFILE_SECRETS.values())
    for key in ("RABBITMQ_DEFAULT_PASS", "POSTGRES_PASSWORD"):
        value = next(l.split("=", 1)[1] for l in body.splitlines() if l.startswith(key + "="))
        assert value not in json.dumps(first) + json.dumps(second), "stack password printed"
    assert env.docker()["up_env_port"] == port
    ups = [c for c in env.calls("docker") if "up" in c]
    assert len(ups) == 2 and all(c[-2:] == ["up", "-d"] for c in ups)
    assert not [c for c in env.calls("docker") if _forbidden(c)]
    assert "FIRECRAWL" not in (env.home / ".env").read_text(encoding="utf-8"), "deploy never activates"


# ── verify / activate / rollback ─────────────────────────────────────────


def test_verify_tells_an_answering_instance_from_a_silent_port(env, firecrawl_api):
    silent = env.run("verify", "--port", str(_free_port()), expect=1)
    assert silent["reason"] == "service_unreachable" and silent["liveness"]["responds"] is False
    answering = env.run("verify", "--port", str(firecrawl_api.port), "--scrape", "https://example.com")
    assert answering["ok"] and answering["liveness"]["responds"] and answering["scrape"]["ok"]
    assert ("POST", "/v2/scrape", {"url": "https://example.com", "formats": ["markdown"]}) in firecrawl_api.calls


def test_activation_needs_an_answering_instance_and_rollback_restores_everything(env, firecrawl_api):
    (env.home / "config.yaml").write_text("web:\n  backend: ddgs\n", encoding="utf-8")
    before = _tree(env.home)
    refused = env.run("activate", "--port", str(_free_port()), expect=1)
    assert refused["reason"] == "service_unreachable"
    assert _tree(env.home) == before

    url = f"http://127.0.0.1:{firecrawl_api.port}"
    doc = env.run("activate", "--port", str(firecrawl_api.port))
    assert doc["ok"] and doc["activation"]["active"]
    assert yaml.safe_load((env.home / "config.yaml").read_text())["web"]["backend"] == "firecrawl"
    assert f"FIRECRAWL_API_URL={url}" in (env.home / ".env").read_text(encoding="utf-8")
    resolution = doc["hermes_resolution"]  # what Hermes' own web layer resolves after the writes
    assert resolution["ok"], resolution
    assert resolution["extract_backend"] == resolution["search_backend"] == "firecrawl"
    assert resolution["api_url"] == url

    undone = env.run("rollback")
    assert undone["ok"] and undone["volumes_removed"] is False
    assert yaml.safe_load((env.home / "config.yaml").read_text())["web"]["backend"] == "ddgs"
    env_text = (env.home / ".env").read_text(encoding="utf-8")
    assert "FIRECRAWL_API_URL" not in env_text
    assert all(f"{k}={v}" in env_text for k, v in PROFILE_SECRETS.items())
