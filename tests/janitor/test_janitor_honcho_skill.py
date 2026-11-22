"""janitor-honcho: guided Honcho install (preflight, deploy, verify, activate, rollback).

Behaviour tests against temp homes with fake ``docker``/``git``/``sudo`` binaries first on
PATH and a fake Honcho HTTP API on a random loopback port. No real container, volume or
home is touched.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
import yaml

from janitor import services
from tests.janitor.legacy_home import REPO_ROOT, launcher_env

SKILL_DIR = REPO_ROOT / "janitor" / "skills" / "services" / "janitor-honcho"
SCRIPT = SKILL_DIR / "scripts" / "honcho_setup.py"
DEPLOY_SH = SKILL_DIR / "scripts" / "deploy.sh"
COMPOSE = SKILL_DIR / "scripts" / "honcho-compose.yml"
CONTAINERS = ("janitor-honcho-api", "janitor-honcho-deriver", "janitor-honcho-database", "janitor-honcho-redis")
SECRETS = {
    "OPENAI_API_KEY": "sk-openai-SEEDED-0001",
    "MINIMAX_API_KEY": "mm-minimax-SEEDED-0002",
    "TELEGRAM_BOT_TOKEN": "tg-bot-SEEDED-0003",
}
HONCHO_JSON_SECRET = "hch-apikey-SEEDED-0004"

pytestmark = pytest.mark.linux_only

FAKE_DOCKER = r'''
import json, os, sys
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
        print("Cannot connect to the Docker daemon at unix:///var/run/docker.sock", file=sys.stderr); sys.exit(1)
    print(state.get("root_dir", "/")); sys.exit(0)
if cmd == "compose":
    if state.get("compose") is None:
        print("docker: 'compose' is not a docker command.", file=sys.stderr); sys.exit(1)
    if argv[1:2] == ["version"]:
        print(state["compose"]); sys.exit(0)
    if "up" in argv:
        if not os.path.isfile(argv[argv.index("-f") + 1]):
            sys.exit(14)
        state["up_env_port"] = os.environ.get("JANITOR_HONCHO_PORT")
        if state.get("after_up"):
            state["containers"] = state["after_up"]
        if state.get("serve_health") and not state.get("server_pid"):
            import subprocess
            # Stands in for the published container port; exits by itself after 60 s.
            server = ("import http.server, sys, time\n"
                      "class H(http.server.BaseHTTPRequestHandler):\n"
                      "    def log_message(self, *a): pass\n"
                      "    def do_GET(self):\n"
                      "        self.send_response(200); self.end_headers(); self.wfile.write(b'{}')\n"
                      "srv = http.server.HTTPServer(('127.0.0.1', int(sys.argv[1])), H)\n"
                      "srv.timeout = 0.5\n"
                      "end = time.time() + 60\n"
                      "while time.time() < end: srv.handle_request()\n")
            proc = subprocess.Popen([sys.executable, "-c", server, os.environ["JANITOR_HONCHO_PORT"]],
                                    start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            state["server_pid"] = proc.pid
        state["volumes"] = sorted(set(state.get("volumes", [])) | {"janitor-honcho-pgdata", "janitor-honcho-redis-data", "janitor-honcho-api-data"})
        state["networks"] = ["janitor-honcho-network"]
        save(); sys.exit(state.get("up_rc", 0))
    sys.exit(0)
if cmd == "inspect":
    c = state.get("containers", {}).get(argv[-1])
    if not c or c["status"] == "absent":
        sys.exit(1)
    print(f"{c['status']}|{c.get('health') or ''}"); sys.exit(0)
if cmd in ("volume", "network") and argv[1:2] == ["inspect"]:
    sys.exit(0 if argv[2] in state.get(cmd + "s", []) else 1)
if cmd == "logs":
    print(state.get("logs", "")); sys.exit(0)
if cmd == "stop":
    for name in argv[1:]:
        if name in state.get("containers", {}):
            state["containers"][name]["status"] = "exited"
    save(); sys.exit(0)
sys.exit(0)
'''

FAKE_GIT = r'''
import json, os, sys
argv = sys.argv[1:]
with open(os.environ["FAKE_GIT_LOG"], "a") as fh:
    fh.write(json.dumps(argv) + "\n")
if argv and argv[0] == "clone":
    dest = argv[-1]
    os.makedirs(os.path.join(dest, "database"), exist_ok=True)
    open(os.path.join(dest, "Dockerfile"), "w").write("FROM scratch\n")
    open(os.path.join(dest, "database", "init.sql"), "w").write("")
sys.exit(0)
'''

FAKE_SUDO = r'''
import json, os, sys
with open(os.environ["FAKE_SUDO_LOG"], "a") as fh:
    fh.write(json.dumps(sys.argv[1:]) + "\n")
sys.exit(1)
'''


# ── fixtures ─────────────────────────────────────────────────────────────


class FakeHoncho:
    def __init__(self) -> None:
        self.calls: list[tuple] = []
        calls = self.calls

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def _send(self, body):
                data = json.dumps(body).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self):
                calls.append(("GET", self.path))
                self._send({"status": "ok"})

            def do_POST(self):
                length = int(self.headers.get("Content-Length") or 0)
                body = json.loads(self.rfile.read(length) or b"{}")
                calls.append(("POST", self.path, body))
                self._send({"id": body.get("id", "x"), "workspace_id": "w", "metadata": {},
                            "configuration": {}, "created_at": "2026-01-01T00:00:00Z"})

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()


@pytest.fixture
def honcho_api():
    api = FakeHoncho()
    yield api
    api.close()


class Env:
    def __init__(self, tmp: Path) -> None:
        self.tmp = tmp
        self.home = tmp / ".janitor"
        self.home.mkdir(exist_ok=True)
        self.bin = tmp / "bin"
        self.bin.mkdir()
        self.docker_state = tmp / "docker-state.json"
        self.logs = {name: tmp / f"{name}.log" for name in ("docker", "git", "sudo")}
        for name, body in (("docker", FAKE_DOCKER), ("git", FAKE_GIT), ("sudo", FAKE_SUDO)):
            path = self.bin / name
            path.write_text(f"#!{sys.executable}\n{body}", encoding="utf-8")
            path.chmod(0o755)
        self.set_docker(daemon=True, compose="2.29.1", root_dir=str(tmp), containers={}, volumes=[], networks=[])

    def set_docker(self, **state) -> None:
        self.docker_state.write_text(json.dumps(state), encoding="utf-8")

    def docker(self) -> dict:
        return json.loads(self.docker_state.read_text(encoding="utf-8"))

    def calls(self, tool: str) -> list[list[str]]:
        path = self.logs[tool]
        if not path.exists():
            return []
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]

    def env(self, *, docker: bool = True) -> dict:
        env = {k: v for k, v in os.environ.items() if not k.startswith(("HERMES_", "HONCHO_", "JANITOR_"))}
        bin_dir = self.bin
        if not docker:
            bin_dir = self.tmp / "bin-nodocker"
            bin_dir.mkdir(exist_ok=True)
            for name in ("git", "sudo"):
                link = bin_dir / name
                if not link.exists():
                    link.symlink_to(self.bin / name)
        env.update(HOME=str(self.tmp), HERMES_HOME=str(self.home), PATH=str(bin_dir), USER="tester",
                   FAKE_DOCKER_STATE=str(self.docker_state), FAKE_DOCKER_LOG=str(self.logs["docker"]),
                   FAKE_GIT_LOG=str(self.logs["git"]), FAKE_SUDO_LOG=str(self.logs["sudo"]))
        return env

    def run(self, *args: str, docker: bool = True, expect: int | None = 0):
        proc = subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True,
                              env=self.env(docker=docker), timeout=120)
        if expect is not None:
            assert proc.returncode == expect, proc.stdout + proc.stderr
        for value in [*SECRETS.values(), HONCHO_JSON_SECRET]:
            assert value not in proc.stdout and value not in proc.stderr, f"secret leaked by {args}"
        return json.loads(proc.stdout) if proc.stdout.strip().startswith("{") else proc.stdout, proc

    def write_env(self, **extra: str) -> None:
        values = {**SECRETS, **extra}
        (self.home / ".env").write_text("".join(f"{k}={v}\n" for k, v in values.items()), encoding="utf-8")


@pytest.fixture
def env(tmp_path):
    e = Env(tmp_path)
    e.write_env()
    yield e
    assert e.calls("sudo") == [], "the skill must never call sudo"


def _running(health: str = "healthy") -> dict:
    return {c: {"status": "running", "health": health if c != "janitor-honcho-deriver" else None} for c in CONTAINERS}


def _snapshot(env: Env) -> dict[str, bytes | None]:
    files = {}
    for name in ("config.yaml", ".env", "honcho.json"):
        path = env.home / name
        files[name] = path.read_bytes() if path.exists() else None
    return files


def _provider(env: Env):
    cfg = yaml.safe_load((env.home / "config.yaml").read_text(encoding="utf-8")) or {}
    return (cfg.get("memory") or {}).get("provider", "<absent>")


def _free_port() -> int:
    import socket

    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


# ── skill + manifest contract ────────────────────────────────────────────


def test_frontmatter_follows_the_authoring_standard():
    text = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
    meta = yaml.safe_load(text.split("---", 2)[1])
    assert meta["name"] == "janitor-honcho"
    description = meta["description"]
    assert len(description) <= 60 and description.endswith(".")
    assert meta["platforms"] and set(meta["platforms"]) <= {"linux", "macos"}
    assert meta["metadata"]["hermes"]["config"]["janitor.honcho_port"]["default"] == 1973
    for section in ("## When to Use", "## Prerequisites", "## How to Run", "## Quick Reference",
                    "## Procedure", "## Pitfalls", "## Verification"):
        assert section in text


def test_manifest_and_compose_are_consistent_and_prefixed():
    service = services.get_service("honcho")
    compose = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))
    names = {spec["container_name"] for spec in compose["services"].values()}
    assert set(service.containers) == names
    assert all(n.startswith("janitor-") for n in names)
    assert all(v["name"].startswith("janitor-") for v in compose["volumes"].values())
    assert all(n["name"].startswith("janitor-") for n in compose["networks"].values())
    images = {spec.get("image") for spec in compose["services"].values() if spec.get("build")}
    assert images and all(i.startswith("janitor-") for i in images)
    ports = [p for spec in compose["services"].values() for p in spec.get("ports", [])]
    assert ports and all(p.startswith("127.0.0.1:") for p in ports)
    env_files = [e for spec in compose["services"].values() for e in spec.get("env_file", [])]
    assert env_files and all("honcho-llm.env" in (e["path"] if isinstance(e, dict) else e) for e in env_files)
    assert service.url.startswith("http://127.0.0.1:")


def test_scripts_parse():
    assert subprocess.run(["bash", "-n", str(DEPLOY_SH)], capture_output=True).returncode == 0
    compile(SCRIPT.read_text(encoding="utf-8"), str(SCRIPT), "exec")


# ── preflight ────────────────────────────────────────────────────────────


def test_preflight_without_docker_suggests_an_install_and_falls_back_to_cloud(env):
    doc, _ = env.run("preflight", docker=False)
    assert doc["docker"]["cli"] is False
    assert "docker_missing" in doc["modes"]["local"]["blockers"]
    assert doc["docker"]["install_hint"]["command"]
    assert doc["recommendation"] == "cloud"
    assert env.calls("docker") == []


def test_preflight_daemon_down(env):
    env.set_docker(daemon=False, compose="2.29.1", containers={})
    doc, _ = env.run("preflight")
    assert doc["docker"]["error"] == "docker_daemon_down"
    assert "docker_daemon_down" in doc["modes"]["local"]["blockers"]
    assert doc["docker"]["fix_hint"]


def test_preflight_port_busy_by_another_process(env):
    import socket

    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        sock.listen(1)
        port = sock.getsockname()[1]
        doc, _ = env.run("preflight", "--port", str(port))
    assert doc["port"] == {"number": port, "free": False, "owner": "other"}
    assert "port_busy" in doc["modes"]["local"]["blockers"]


def test_preflight_fresh_machine_with_credentials_recommends_local(env):
    doc, _ = env.run("preflight", "--port", str(_free_port()))
    assert doc["service"]["state"] == "not deployed"
    assert doc["modes"]["local"] == {"feasible": True, "blockers": []}
    assert doc["deriver"]["profile"] == "minimax" and doc["deriver"]["embeddings"] is True
    assert doc["credentials"]["OPENAI_API_KEY"] is True and doc["credentials"]["HONCHO_API_KEY"] is False
    assert doc["memory"]["built_in"] is True
    assert doc["recommendation"] == "local"


def test_preflight_without_llm_key_blocks_local(env):
    (env.home / ".env").write_text("TELEGRAM_BOT_TOKEN=tg-bot-SEEDED-0003\n", encoding="utf-8")
    doc, _ = env.run("preflight", "--port", str(_free_port()))
    assert "llm_credential_missing" in doc["modes"]["local"]["blockers"]
    (env.home / ".env").write_text("MINIMAX_API_KEY=mm-minimax-SEEDED-0002\n", encoding="utf-8")
    doc, _ = env.run("preflight", "--port", str(_free_port()))
    assert "embeddings_credential_missing" in doc["modes"]["local"]["blockers"]


def test_preflight_reports_an_installed_running_service(env, honcho_api):
    env.set_docker(daemon=True, compose="2.29.1", root_dir=str(env.tmp), containers=_running(),
                   volumes=["janitor-honcho-pgdata"], networks=["janitor-honcho-network"])
    doc, _ = env.run("preflight", "--port", str(honcho_api.port))
    assert doc["service"]["state"] == "running"
    assert doc["service"]["api_healthy"] is True
    assert doc["port"]["owner"] == "janitor-honcho-api"
    assert doc["service"]["volumes"]["janitor-honcho-pgdata"] is True
    assert doc["modes"]["local"]["feasible"] is True


def test_preflight_reports_an_existing_activation_without_leaking_secrets(env):
    (env.home / "config.yaml").write_text("memory:\n  provider: honcho\n", encoding="utf-8")
    (env.home / "honcho.json").write_text(json.dumps({"apiKey": HONCHO_JSON_SECRET, "hosts": {}}), encoding="utf-8")
    doc, _ = env.run("preflight", "--port", str(_free_port()))
    assert doc["memory"]["provider"] == "honcho"
    assert doc["recommendation"] == "already-active"
    assert doc["honcho_json"]["profile_file_exists"] is True and doc["honcho_json"]["has_api_key"] is True


# ── deploy ───────────────────────────────────────────────────────────────


def _forbidden(call: list[str]) -> bool:
    joined = " ".join(call)
    return (call[:1] in (["rm"], ["rmi"]) or "down" in call or "-v" in call or "--volumes" in call
            or "prune" in call or re.search(r"\bvolume (rm|prune)\b", joined) is not None
            or "--remove-orphans" in call or "--force-recreate" in call)


def test_deploy_is_idempotent_loopback_only_and_never_removes_volumes(env):
    env.set_docker(daemon=True, compose="2.29.1", root_dir=str(env.tmp), containers={}, volumes=[],
                   networks=[], after_up=_running(), serve_health=True)
    port = str(_free_port())
    first, _ = env.run("deploy", "--port", port, "--timeout", "10", "--interval", "0.2")
    second, _ = env.run("deploy", "--port", port, "--timeout", "10", "--interval", "0.2")
    assert first["ok"] and second["ok"]
    assert first["compose"] == "installed" and second["compose"] == "unchanged"
    assert first["llm_env"] == "generated" and second["llm_env"] == "unchanged"
    assert first["source"] == "cloned" and second["source"] == "present"
    assert len([c for c in env.calls("git") if c[0] == "clone"]) == 1
    calls = env.calls("docker")
    ups = [c for c in calls if "up" in c]
    assert len(ups) == 2 and all(c[-2:] == ["up", "-d"] for c in ups)
    assert not [c for c in calls if _forbidden(c)]
    assert env.docker()["up_env_port"] == port

    deployed = env.home / "docker" / "honcho-compose.yml"
    compose = yaml.safe_load(deployed.read_text(encoding="utf-8"))
    for spec in compose["services"].values():
        assert spec["container_name"].startswith("janitor-")
        assert all(p.startswith("127.0.0.1:") for p in spec.get("ports", []))
    llm_env = env.home / "docker" / "honcho-llm.env"
    assert oct(llm_env.stat().st_mode & 0o777) == "0o600"
    body = llm_env.read_text(encoding="utf-8")
    assert SECRETS["MINIMAX_API_KEY"] in body and SECRETS["OPENAI_API_KEY"] in body
    assert SECRETS["TELEGRAM_BOT_TOKEN"] not in body, "containers get only the LLM credentials"


def test_deploy_keeps_user_customised_files(env, honcho_api):
    docker_dir = env.home / "docker"
    docker_dir.mkdir()
    custom_compose = COMPOSE.read_text(encoding="utf-8") + "\n# my ollama tweak\n"
    (docker_dir / "honcho-compose.yml").write_text(custom_compose, encoding="utf-8")
    (docker_dir / "honcho-llm.env").write_text("LLM_OPENAI_API_KEY=mine\n", encoding="utf-8")
    (env.home / "src" / "honcho").mkdir(parents=True)
    (env.home / "src" / "honcho" / "Dockerfile").write_text("FROM scratch\n", encoding="utf-8")
    env.set_docker(daemon=True, compose="2.29.1", root_dir=str(env.tmp), containers=_running(),
                   volumes=["janitor-honcho-pgdata"], networks=["janitor-honcho-network"])
    doc, _ = env.run("deploy", "--port", str(honcho_api.port), "--timeout", "10", "--interval", "0.2")
    assert doc["compose"] == "kept-user-file" and doc["llm_env"] == "kept-user-file"
    assert (docker_dir / "honcho-compose.yml").read_text(encoding="utf-8") == custom_compose
    assert (docker_dir / "honcho-llm.env").read_text(encoding="utf-8") == "LLM_OPENAI_API_KEY=mine\n"
    assert env.calls("git") == []


def test_deploy_reports_the_failing_container_with_redacted_logs(env):
    broken = _running()
    broken["janitor-honcho-api"] = {"status": "exited", "health": None}
    env.set_docker(daemon=True, compose="2.29.1", root_dir=str(env.tmp), containers={}, volumes=[],
                   networks=[], after_up=broken,
                   logs=f"boot\nauth failed for key {SECRETS['OPENAI_API_KEY']}\nTraceback: boom")
    doc, _ = env.run("deploy", "--port", str(_free_port()), "--timeout", "1", "--interval", "0.2", expect=1)
    assert doc["reason"] == "health_timeout"
    failing = {f["container"]: f for f in doc["failing"]}
    assert "janitor-honcho-api" in failing
    assert any("Traceback: boom" in line for line in failing["janitor-honcho-api"]["log_tail"])
    assert not [c for c in env.calls("docker") if _forbidden(c)]


def test_deploy_refuses_without_docker_and_never_escalates(env):
    doc, _ = env.run("deploy", docker=False, expect=1)
    assert doc["reason"] == "docker_missing"
    assert not (env.home / "docker").exists()


# ── activate / verify / rollback ─────────────────────────────────────────


def test_activation_is_refused_when_verification_fails_and_touches_nothing(env):
    (env.home / "config.yaml").write_text("memory:\n  provider: holographic\n", encoding="utf-8")
    (env.home / "honcho.json").write_text('{"peerName": "me", "hosts": {"hermes": {"aiPeer": "x"}}}\n',
                                          encoding="utf-8")
    before = _snapshot(env)
    doc, _ = env.run("activate", "--mode", "local", "--port", str(_free_port()), expect=1)
    assert doc["reason"] == "verification_failed"
    assert _snapshot(env) == before
    assert not (env.home / "janitor" / "honcho" / "state.json").exists()


def test_cloud_activation_without_a_launcher_credential_is_refused(env, honcho_api):
    # An OAuth grant alone does not satisfy the launcher fail-safe today: refuse, write nothing.
    (env.home / "honcho.json").write_text(json.dumps({
        "baseUrl": f"http://127.0.0.1:{honcho_api.port}",
        "hosts": {"hermes": {"apiKey": HONCHO_JSON_SECRET, "oauth": {"refresh_token": "rt-SEEDED-77777"}}},
    }), encoding="utf-8")
    before = _snapshot(env)
    doc, _ = env.run("activate", "--mode", "cloud", expect=1)
    assert doc["reason"] == "failsafe_would_block"
    assert _snapshot(env) == before


def test_local_activation_backs_up_a_user_edited_honcho_json(env, honcho_api):
    (env.home / "config.yaml").write_text("memory:\n  provider: holographic\n", encoding="utf-8")
    user_json = {"peerName": "reck", "dialecticCadence": 7,
                 "hosts": {"hermes": {"aiPeer": "Janitor", "workspace": "mine", "recallMode": "tools"}}}
    original = json.dumps(user_json, indent=4).encode()
    (env.home / "honcho.json").write_bytes(original)

    doc, _ = env.run("activate", "--mode", "local", "--port", str(honcho_api.port))
    assert doc["ok"] and doc["takes_effect"] == "next_session"
    assert doc["post_check"]["ok"] is True
    assert Path(doc["honcho_json_backup"]).read_bytes() == original
    written = json.loads((env.home / "honcho.json").read_text(encoding="utf-8"))
    assert written["baseUrl"] == f"http://127.0.0.1:{honcho_api.port}"
    assert written["dialecticCadence"] == 7 and written["peerName"] == "reck"
    assert written["hosts"]["hermes"]["workspace"] == "mine" and written["hosts"]["hermes"]["recallMode"] == "tools"
    assert _provider(env) == "honcho"
    env_text = (env.home / ".env").read_text(encoding="utf-8")
    assert f"HONCHO_BASE_URL=http://127.0.0.1:{honcho_api.port}" in env_text
    assert all(f"{k}={v}" in env_text for k, v in SECRETS.items())
    assert any(c[:2] == ("POST", "/v3/workspaces/mine/peers") for c in honcho_api.calls)


def test_rollback_restores_the_previous_provider_and_keeps_data(env, honcho_api):
    (env.home / "config.yaml").write_text("memory:\n  provider: holographic\n", encoding="utf-8")
    env.set_docker(daemon=True, compose="2.29.1", root_dir=str(env.tmp), containers=_running(),
                   volumes=["janitor-honcho-pgdata"], networks=["janitor-honcho-network"])
    env.run("activate", "--mode", "local", "--port", str(honcho_api.port))
    assert _provider(env) == "honcho"

    doc, _ = env.run("rollback", "--stop-containers")
    assert doc["ok"] and doc["volumes_removed"] is False
    assert _provider(env) == "holographic"
    assert "HONCHO_BASE_URL" not in (env.home / ".env").read_text(encoding="utf-8")
    assert (env.home / "honcho.json").exists()
    calls = env.calls("docker")
    assert ["stop", *CONTAINERS] in calls
    assert not [c for c in calls if _forbidden(c)]
    assert "janitor-honcho-pgdata" in env.docker()["volumes"]


def test_rollback_without_an_activation_record_changes_nothing(env):
    (env.home / "config.yaml").write_text("memory:\n  provider: honcho\n", encoding="utf-8")
    before = _snapshot(env)
    doc, _ = env.run("rollback", expect=1)
    assert doc["reason"] == "no_activation_record"
    assert _snapshot(env) == before


def _launcher_fail_safe(root: Path) -> subprocess.CompletedProcess:
    code = "import janitor.cli as launcher; launcher._owasp_honcho_fail_safe(); print('PASSED')"
    env = launcher_env(root)
    env = {k: v for k, v in env.items() if not k.startswith("HONCHO_")}
    return subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=env,
                          cwd=str(root), timeout=180)


def test_seeded_home_activation_passes_the_launcher_fail_safe(env, honcho_api):
    from janitor.seed import ensure_home

    ensure_home(env.home)
    env.write_env()
    doc, _ = env.run("activate", "--mode", "local", "--port", str(honcho_api.port))
    assert doc["ok"] and _provider(env) == "honcho"

    result = _launcher_fail_safe(env.tmp)
    assert result.returncode == 0 and "PASSED" in result.stdout, result.stderr[-2000:]

    # Control: the same home without the URL activation wrote does trip the fail-safe.
    env_file = env.home / ".env"
    env_file.write_text("".join(l for l in env_file.read_text(encoding="utf-8").splitlines(True)
                                if not l.startswith("HONCHO_BASE_URL=")), encoding="utf-8")
    blocked = _launcher_fail_safe(env.tmp)
    assert blocked.returncode == 1 and "FATAL" in blocked.stderr
