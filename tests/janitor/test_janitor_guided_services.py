"""janitor-n8n, janitor-nocodb, janitor-lightrag: guided installs (preflight, deploy, verify, stop).

Behaviour tests against temp homes with a fake ``docker`` as the only one on PATH and
real HTTP servers on random loopback ports. No real container, volume, service port or
home is touched.
"""

from __future__ import annotations

import json
import re
import shutil
import socket
import subprocess
import sys
import threading
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
import yaml

from janitor import services
from tests.janitor.legacy_home import REPO_ROOT

pytestmark = pytest.mark.linux_only

SERVICES_DIR = REPO_ROOT / "janitor" / "skills" / "services"


@dataclass(frozen=True)
class Skill:
    key: str
    containers: tuple[str, ...]
    volumes: tuple[str, ...]
    health_path: str
    port_var: str

    @property
    def dir(self) -> Path:
        return SERVICES_DIR / f"janitor-{self.key}"

    @property
    def script(self) -> Path:
        return self.dir / "scripts" / f"{self.key}_setup.py"

    @property
    def compose(self) -> Path:
        return self.dir / "scripts" / f"{self.key}-compose.yml"


SKILLS = [
    Skill("n8n", ("janitor-n8n",), ("janitor-n8n-data",), "/healthz", "JANITOR_N8N_PORT"),
    Skill("nocodb", ("janitor-nocodb", "janitor-nocodb-db"), ("janitor-nocodb-data", "janitor-nocodb-pgdata"),
          "/", "JANITOR_NOCODB_PORT"),
    Skill("lightrag", ("janitor-lightrag", "janitor-lightrag-db"),
          ("janitor-lightrag-storage", "janitor-lightrag-inputs", "janitor-lightrag-pgdata"),
          "/health", "JANITOR_LIGHTRAG_PORT"),
]
PROFILE_SECRETS = {
    "OPENAI_API_KEY": "sk-openai-SEEDED-0001",
    "MINIMAX_API_KEY": "mm-minimax-SEEDED-0002",
    "TELEGRAM_BOT_TOKEN": "tg-bot-SEEDED-0003",
}

# Reads its state from the directory it lives in: the scripts run docker with a minimal
# environment, so nothing can be handed over through env vars.
FAKE_DOCKER = r'''
import json, os, sys
here = os.path.dirname(os.path.abspath(__file__))
state_path = os.path.join(here, "docker-state.json")
state = json.load(open(state_path))
argv = sys.argv[1:]
with open(os.path.join(here, "docker-calls.jsonl"), "a") as fh:
    fh.write(json.dumps({"argv": argv, "env": dict(os.environ)}) + "\n")
def save():
    json.dump(state, open(state_path, "w"))
cmd = argv[0] if argv else ""
if cmd == "info":
    if not state.get("daemon", True):
        print("Cannot connect to the Docker daemon", file=sys.stderr); sys.exit(1)
    print(state.get("root_dir", "/")); sys.exit(0)
if cmd == "version":
    print("27.0.1"); sys.exit(0)
if cmd == "compose":
    if argv[1:2] == ["version"]:
        print(state.get("compose", "2.29.1")); sys.exit(0)
    if "up" in argv:
        for flag in ("-f", "--env-file"):
            if not os.path.isfile(argv[argv.index(flag) + 1]):
                sys.exit(14)
        if state.get("after_up"):
            state["containers"] = state["after_up"]
        if state.get("serve_status") and not state.get("server_pid"):
            import subprocess
            # Stands in for the published container port; exits by itself after 30 s.
            server = ("import http.server, sys, time\n"
                      "class H(http.server.BaseHTTPRequestHandler):\n"
                      "    def log_message(self, *a): pass\n"
                      "    def do_GET(self):\n"
                      "        self.send_response(int(sys.argv[2])); self.end_headers()\n"
                      "srv = http.server.HTTPServer(('127.0.0.1', int(sys.argv[1])), H)\n"
                      "srv.timeout = 0.5\n"
                      "end = time.time() + 30\n"
                      "while time.time() < end: srv.handle_request()\n")
            port = os.environ[state["port_var"]]
            proc = subprocess.Popen([sys.executable, "-c", server, port, str(state["serve_status"])],
                                    start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            state["server_pid"] = proc.pid
        save(); sys.exit(state.get("up_rc", 0))
    sys.exit(0)
if cmd == "inspect":
    c = state.get("containers", {}).get(argv[-1])
    if not c:
        sys.exit(1)
    print(f"{c['status']}|{c.get('health') or ''}|{c.get('project') or ''}"); sys.exit(0)
if cmd in ("volume", "network") and argv[1:2] == ["inspect"]:
    sys.exit(0 if argv[2] in state.get(cmd + "s", []) else 1)
if cmd == "logs":
    print("log line"); sys.exit(0)
if cmd == "stop":
    for name in argv[1:]:
        state["containers"][name]["status"] = "exited"
    save(); sys.exit(0)
sys.exit(0)
'''


# ── fixtures ─────────────────────────────────────────────────────────────


class Env:
    def __init__(self, tmp: Path, skill: Skill) -> None:
        self.tmp, self.skill = tmp, skill
        self.home = tmp / ".janitor"
        self.home.mkdir()
        self.bin = tmp / "bin"
        self.bin.mkdir()
        docker = self.bin / "docker"
        docker.write_text(f"#!{sys.executable}\n{FAKE_DOCKER}", encoding="utf-8")
        docker.chmod(0o755)
        for tool, target in (("python3", sys.executable), ("dirname", shutil.which("dirname"))):
            (self.bin / tool).symlink_to(target)
        self.state = self.bin / "docker-state.json"
        self.set_docker()
        (self.home / ".env").write_text("".join(f"{k}={v}\n" for k, v in PROFILE_SECRETS.items()),
                                        encoding="utf-8")

    def set_docker(self, **state) -> None:
        base = {"daemon": True, "compose": "2.29.1", "root_dir": str(self.tmp), "containers": {},
                "volumes": [], "networks": [], "port_var": self.skill.port_var}
        self.state.write_text(json.dumps({**base, **state}), encoding="utf-8")

    def docker(self) -> dict:
        return json.loads(self.state.read_text(encoding="utf-8"))

    def calls(self) -> list[dict]:
        path = self.bin / "docker-calls.jsonl"
        return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines()] if path.exists() else []

    def env(self, *, docker: bool = True) -> dict:
        bin_dir = self.bin
        if not docker:
            bin_dir = self.tmp / "bin-nodocker"
            bin_dir.mkdir(exist_ok=True)
        return {"HOME": str(self.tmp), "HERMES_HOME": str(self.home), "PATH": str(bin_dir), "USER": "tester",
                "LANG": "C.UTF-8", "SOME_SHELL_SECRET_TOKEN": "shell-SEEDED-0005"}

    def secrets(self) -> list[str]:
        generated = [v for k, v in _env_file(self.home / "docker" / f"{self.skill.key}.env").items()
                     if re.search(r"KEY|SECRET|PASSWORD|AUTH|TOKEN", k)]
        return [*PROFILE_SECRETS.values(), "shell-SEEDED-0005", *generated]

    def check_no_leak(self, proc) -> None:
        for value in self.secrets():
            assert value not in proc.stdout and value not in proc.stderr, "secret printed"

    def run(self, *args: str, docker: bool = True, expect: int | None = 0) -> dict:
        proc = subprocess.run([sys.executable, str(self.skill.script), *args], capture_output=True, text=True,
                              env=self.env(docker=docker), timeout=120)
        if expect is not None:
            assert proc.returncode == expect, proc.stdout + proc.stderr
        self.check_no_leak(proc)
        return json.loads(proc.stdout)

    def deploy_sh(self, *args: str) -> dict:
        env = {**self.env(), "JANITOR_HOME": str(self.home)}
        proc = subprocess.run([shutil.which("bash"), str(self.skill.dir / "scripts" / "deploy.sh"), *args],
                              capture_output=True, text=True, env=env, timeout=120)
        assert proc.returncode == 0, proc.stdout + proc.stderr
        self.check_no_leak(proc)
        return json.loads(proc.stdout)

    def tree(self) -> dict[str, bytes]:
        return {str(p.relative_to(self.home)): p.read_bytes() for p in sorted(self.home.rglob("*")) if p.is_file()}


@pytest.fixture(params=SKILLS, ids=lambda s: s.key)
def env(request, tmp_path):
    return Env(tmp_path, request.param)


class Health:
    """A real HTTP server on an ephemeral loopback port answering every GET with ``status``."""

    def __init__(self, status: int) -> None:
        self.paths: list[str] = []
        paths = self.paths

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                paths.append(self.path)
                self.send_response(status)
                self.end_headers()

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()


def _env_file(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    return dict(line.split("=", 1) for line in path.read_text(encoding="utf-8").splitlines()
                if line and not line.startswith("#"))


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _running(skill: Skill, project: str | None = None) -> dict:
    return {c: {"status": "running", "health": "healthy", "project": project or f"janitor-{skill.key}"}
            for c in skill.containers}


def _mutating(argv: list[str]) -> bool:
    read_only = argv[:1] in (["info"], ["inspect"], ["version"], ["logs"]) or argv[:2] in (
        ["compose", "version"], ["volume", "inspect"], ["network", "inspect"])
    return not read_only


def _forbidden(argv: list[str]) -> bool:
    joined = " ".join(argv)
    return (argv[:1] in (["rm"], ["rmi"]) or "down" in argv or "-v" in argv or "--volumes" in argv
            or "prune" in argv or re.search(r"\bvolume (rm|prune)\b", joined) is not None
            or "--remove-orphans" in argv)


# ── skill package ────────────────────────────────────────────────────────


@pytest.mark.parametrize("skill", SKILLS, ids=lambda s: s.key)
def test_skill_package_is_consistent_prefixed_and_loopback_only(skill):
    text = (skill.dir / "SKILL.md").read_text(encoding="utf-8")
    meta = yaml.safe_load(text.split("---", 2)[1])
    assert meta["name"] == f"janitor-{skill.key}"
    assert len(meta["description"]) <= 60
    assert meta["platforms"] and set(meta["platforms"]) <= {"linux", "macos"}
    for ref in set(re.findall(r"\$\{HERMES_SKILL_DIR\}/([\w./-]+)", text)):
        assert (skill.dir / ref).exists(), ref

    service = services.get_service(skill.key)
    compose = yaml.safe_load(skill.compose.read_text(encoding="utf-8"))
    specs = compose["services"].values()
    assert set(service.containers) == {s["container_name"] for s in specs} == set(skill.containers)
    assert {v["name"] for v in compose["volumes"].values()} == set(skill.volumes)
    assert all(n["name"].startswith("janitor-") for n in compose["networks"].values())
    assert not [s for s in specs if "env_file" in s], "containers must get only the variables they list"
    ports = [p for s in specs for p in s.get("ports", [])]
    assert ports and all(p.startswith("127.0.0.1:") for p in ports)
    default = re.search(r":-(\d+)\}", ports[0]).group(1)
    assert service.url == f"http://127.0.0.1:{default}"


# ── preflight ────────────────────────────────────────────────────────────


def test_preflight_is_read_only(env):
    doc = env.run("preflight", docker=False)
    assert "docker_missing" in doc["blockers"] and doc["docker"]["install_hint"]["command"]
    assert doc["ready_to_deploy"] is False and env.calls() == []

    before = env.tree()
    doc = env.run("preflight", "--port", str(_free_port()))
    assert doc["blockers"] == [] and doc["ready_to_deploy"] is True
    assert doc["service"]["state"] == "not deployed"
    assert env.tree() == before
    assert not [c["argv"] for c in env.calls() if _mutating(c["argv"])]


# ── deploy ───────────────────────────────────────────────────────────────


def test_deploy_refuses_without_confirmation_or_prerequisites_and_changes_nothing(env):
    port = str(_free_port())
    before = env.tree()
    doc = env.run("deploy", "--port", port, expect=1)
    assert doc["reason"] == "confirmation_required" and doc["changed"] == []
    assert doc["plan"]["listen"] == f"127.0.0.1:{port}"
    assert set(doc["plan"]["containers"]) == set(env.skill.containers)

    env.set_docker(daemon=False)
    assert env.run("deploy", "--port", port, "--yes", expect=1)["reason"] == "docker_daemon_down"
    env.set_docker(containers=_running(env.skill, project="docker"))  # an older install's stack
    doc = env.run("deploy", "--port", port, "--yes", expect=1)
    assert doc["reason"] == "foreign_containers" and doc["foreign_containers"]
    assert env.tree() == before
    if env.skill.key == "lightrag":
        env.set_docker()
        (env.home / ".env").write_text("TELEGRAM_BOT_TOKEN=tg-bot-SEEDED-0003\n", encoding="utf-8")
        before = env.tree()
        assert env.run("deploy", "--port", port, "--yes", expect=1)["reason"] == "embeddings_credential_missing"
        assert env.tree() == before
    assert not [c["argv"] for c in env.calls() if _mutating(c["argv"])]


def test_deploy_is_idempotent_and_containers_never_see_the_profile_env(env):
    skill = env.skill
    port = str(_free_port())
    env.set_docker(after_up=_running(skill), serve_status=200 if skill.key != "nocodb" else 302)
    first = env.run("deploy", "--port", port, "--yes", "--timeout", "15", "--interval", "0.2")
    env_path = env.home / "docker" / f"{skill.key}.env"
    values_before = _env_file(env_path)
    second = env.deploy_sh("--timeout", "15", "--interval", "0.2")  # `janitor services deploy` entry point
    assert first["ok"] and second["ok"] and second["url"] == f"http://127.0.0.1:{port}"
    assert first["compose"] == "installed" and second["compose"] == "unchanged"
    assert first["env_file"] == "generated" and second["env_file"] == "unchanged"
    assert _env_file(env_path) == values_before, "generated secrets must survive a redeploy"

    deployed = env.home / "docker" / f"{skill.key}-compose.yml"
    assert deployed.read_bytes() == skill.compose.read_bytes()
    assert oct(env_path.stat().st_mode & 0o777) == "0o600"
    needed = set(re.findall(r"\$\{([A-Z0-9_]+)", deployed.read_text(encoding="utf-8")))
    assert needed <= set(values_before), needed - set(values_before)
    assert PROFILE_SECRETS["TELEGRAM_BOT_TOKEN"] not in env_path.read_text(encoding="utf-8")

    calls = env.calls()
    ups = [c for c in calls if "up" in c["argv"]]
    assert len(ups) == 2 and all(c["argv"][-2:] == ["up", "-d"] for c in ups)
    assert all(c["argv"][c["argv"].index("-p") + 1] == f"janitor-{skill.key}" for c in ups)
    for call in ups:
        assert call["env"][skill.port_var] == port
        leaked = [v for v in (*PROFILE_SECRETS.values(), "shell-SEEDED-0005") if v in call["env"].values()]
        assert not leaked, "docker compose must not inherit secrets from the process environment"
    assert not [c["argv"] for c in calls if _forbidden(c["argv"])]


# ── verify / stop ────────────────────────────────────────────────────────


def test_verify_distinguishes_answering_from_not_answering(env):
    ok = Health(200)
    try:
        doc = env.run("verify", "--port", str(ok.port))
        assert doc["ok"] is True and doc["health"]["status"] == 200
        assert ok.paths == [env.skill.health_path]
    finally:
        ok.close()

    broken = Health(503)
    try:
        doc = env.run("verify", "--port", str(broken.port), expect=1)
        assert doc["reason"] == "unhealthy_status" and doc["health"]["responding"] is True
    finally:
        broken.close()

    doc = env.run("verify", "--port", str(_free_port()), expect=1)
    assert doc["reason"] == "not_responding" and doc["health"]["responding"] is False


def test_stop_needs_confirmation_and_never_removes_anything(env):
    env.set_docker(containers=_running(env.skill), volumes=list(env.skill.volumes))
    doc = env.run("stop", expect=1)
    assert doc["reason"] == "confirmation_required" and set(doc["would_stop"]) == set(env.skill.containers)
    assert all(s["status"] == "running" for s in env.docker()["containers"].values())

    doc = env.run("stop", "--yes")
    assert doc["ok"] and doc["volumes_removed"] is False
    mutating = [c["argv"] for c in env.calls() if _mutating(c["argv"])]
    assert mutating == [["stop", *env.skill.containers]]
    assert env.docker()["volumes"] == list(env.skill.volumes)
