"""Janitor desktop plugin (F4-02): the ``/api/plugins/janitor`` backend and its delivery.

Docker is always a FAKE binary that is the only ``docker`` on ``PATH`` (PATH holds
nothing else), so the developer's real containers are never inspected, started or
stopped. The fake records every invocation; a fake ``sudo`` beside it must stay unused.
"""

from __future__ import annotations

import importlib.util
import json
import socket
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
import yaml

# The Docker CLI is faked with POSIX shell scripts on PATH and the skill is Linux-only today
# (plan decision 2.7: Linux first). Windows and macOS get their own tests when supported.
pytestmark = pytest.mark.linux_only

from janitor import desktop_plugin, services
from janitor.desktop_plugin import api

FAKE_DOCKER = f"""#!{sys.executable}
import json, os, sys, time
root = os.environ["FAKE_DOCKER_DIR"]
args = sys.argv[1:]
with open(os.path.join(root, "calls.jsonl"), "a") as fh:
    fh.write(json.dumps(args) + "\\n")
with open(os.path.join(root, "state.json")) as fh:
    cfg = json.load(fh)
if cfg.get("hang"):
    time.sleep(cfg["hang"])
if cfg.get("daemon") == "down":
    sys.stderr.write("Cannot connect to the Docker daemon\\n")
    sys.exit(1)
containers = cfg["containers"]
cmd = args[0] if args else ""
if cmd == "version":
    print("27.0.0")
    sys.exit(0)
if cmd == "inspect":
    name = args[-1]
    if name in containers:
        print(containers[name])
        sys.exit(0)
    sys.stderr.write("No such object\\n")
    sys.exit(1)
if cmd in ("start", "stop"):
    if cfg.get("fail"):
        sys.exit(1)
    for name in args[1:]:
        containers[name] = "running" if cmd == "start" else "exited"
        print(name)
    with open(os.path.join(root, "state.json"), "w") as fh:
        json.dump(cfg, fh)
    sys.exit(0)
sys.exit(2)
"""

FAKE_SUDO = f"""#!{sys.executable}
import json, os, sys
with open(os.path.join(os.environ["FAKE_DOCKER_DIR"], "sudo.jsonl"), "a") as fh:
    fh.write(json.dumps(sys.argv[1:]) + "\\n")
sys.exit(1)
"""


class FakeDocker:
    def __init__(self, root: Path):
        self.root = root

    def set(self, containers: dict | None = None, **cfg) -> None:
        (self.root / "state.json").write_text(json.dumps({"containers": containers or {}, **cfg}))

    @property
    def containers(self) -> dict:
        return json.loads((self.root / "state.json").read_text())["containers"]

    def _lines(self, name: str) -> list:
        path = self.root / name
        return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []

    @property
    def calls(self) -> list:
        return self._lines("calls.jsonl")

    @property
    def sudo_calls(self) -> list:
        return self._lines("sudo.jsonl")


@pytest.fixture
def services_root(tmp_path):
    """Two services shaped like the shipped ones (one multi-container). No ``url``:
    a running service here must never make the listing call a real local port."""
    root = tmp_path / "services"
    for name, containers in (("alpha", ["janitor-alpha"]), ("beta", ["janitor-beta-api", "janitor-beta-db"])):
        skill = root / f"janitor-{name}"
        (skill / "scripts").mkdir(parents=True)
        (skill / "SKILL.md").write_text(f"---\nname: janitor-{name}\n---\n")
        (skill / "service.yaml").write_text(yaml.safe_dump({
            "name": name, "description": f"{name} service", "deploy": "scripts/deploy.sh",
            "containers": containers,
        }))
    return root


def _write_exec(path: Path, body: str) -> None:
    path.write_text(body)
    path.chmod(0o755)


@pytest.fixture
def docker(tmp_path, monkeypatch):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    state = tmp_path / "docker-state"
    state.mkdir()
    _write_exec(bin_dir / "docker", FAKE_DOCKER)
    _write_exec(bin_dir / "sudo", FAKE_SUDO)
    monkeypatch.setenv("PATH", str(bin_dir))
    monkeypatch.setenv("FAKE_DOCKER_DIR", str(state))
    fake = FakeDocker(state)
    fake.set()
    yield fake
    assert fake.sudo_calls == []


@pytest.fixture
def no_docker(tmp_path, monkeypatch):
    bin_dir = tmp_path / "empty-bin"
    bin_dir.mkdir()
    monkeypatch.setenv("PATH", str(bin_dir))


def _by_name(view: dict) -> dict:
    return {s["name"]: s for s in view["services"]}


# ── listing ────────────────────────────────────────────────────────────────


def test_lists_exactly_the_discovered_services(docker, services_root):
    view = api.list_view(root=services_root)
    assert sorted(_by_name(view)) == [s.name for s in services.discover_services(services_root)]
    beta = _by_name(view)["beta"]
    assert beta["skill"] == "janitor-beta"
    # The screen gets the catalog id of the guided skill, never a path (F4-04).
    assert not any("/" in str(v) for k, v in beta.items() if k != "url" and isinstance(v, str))
    assert [c["name"] for c in beta["containers"]] == ["janitor-beta-api", "janitor-beta-db"]


def test_shipped_services_are_all_listed(docker):
    view = api.list_view()
    assert sorted(_by_name(view)) == sorted(s.name for s in services.discover_services())
    managed = {s["skill"] for s in view["services"]}
    assert not managed & {a["skill"] for a in view["unmanaged"]}
    # «Instalar con Janitor» activates the guided skill by catalog id.
    from janitor import catalog as cat

    assert managed | {a["skill"] for a in view["unmanaged"]} <= set(cat.load_catalog().by_id())


@pytest.mark.parametrize(
    ("containers", "alpha", "beta"),
    [
        ({}, "not_installed", "not_installed"),
        ({"janitor-alpha": "running", "janitor-beta-api": "running", "janitor-beta-db": "running"},
         "running", "running"),
        ({"janitor-alpha": "exited", "janitor-beta-api": "running", "janitor-beta-db": "exited"},
         "stopped", "partial"),
        ({"janitor-beta-api": "exited"}, "not_installed", "stopped"),
    ],
)
def test_reports_each_state(docker, services_root, containers, alpha, beta):
    docker.set(containers)
    view = api.list_view(root=services_root)
    assert view["docker"] == {"available": True, "status": "ok"}
    assert _by_name(view)["alpha"]["state"] == alpha
    assert _by_name(view)["beta"]["state"] == beta
    assert all(call[0] in ("version", "inspect") for call in docker.calls)


def test_docker_missing_is_a_state_not_an_error(no_docker, services_root):
    view = api.list_view(root=services_root)
    assert view["docker"] == {"available": False, "status": "missing"}
    assert {s["state"] for s in view["services"]} == {"not_installed"}


def test_docker_daemon_down_hides_container_state(docker, services_root):
    docker.set({"janitor-alpha": "running"}, daemon="down")
    view = api.list_view(root=services_root)
    assert view["docker"] == {"available": False, "status": "unavailable"}
    assert {s["state"] for s in view["services"]} == {"docker_unavailable"}
    assert [call[0] for call in docker.calls] == ["version"]


def test_a_hanging_docker_is_bounded(docker, services_root, monkeypatch):
    monkeypatch.setattr(api, "PROBE_TIMEOUT", 0.5)
    docker.set({"janitor-alpha": "running"}, hang=10)
    view = api.list_view(root=services_root)
    assert view["docker"]["status"] == "timeout"
    assert {s["state"] for s in view["services"]} == {"docker_unavailable"}


# ── health: a running container is not a working service (F4-06) ─────────


class _Answers401(BaseHTTPRequestHandler):
    def do_GET(self):
        self.server.hits.append(self.path)
        self.send_response(401)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def log_message(self, *args):
        pass


@pytest.fixture
def http_server():
    """A real HTTP server on an ephemeral loopback port that answers 401 to everything."""
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Answers401)
    server.hits = []
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server
    server.shutdown()
    server.server_close()


def _closed_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _set_url(root: Path, name: str, url: str) -> None:
    manifest = root / f"janitor-{name}" / "service.yaml"
    data = yaml.safe_load(manifest.read_text())
    manifest.write_text(yaml.safe_dump({**data, "url": url}))


_ALL_RUNNING = {"janitor-alpha": "running", "janitor-beta-api": "running", "janitor-beta-db": "running"}


def test_running_service_that_answers_is_responding(docker, services_root, http_server):
    _set_url(services_root, "alpha", f"http://127.0.0.1:{http_server.server_port}/health")
    docker.set(_ALL_RUNNING)

    view = _by_name(api.list_view(root=services_root))

    assert view["alpha"]["state"] == "running" and view["alpha"]["health"] == "responding"
    assert http_server.hits == ["/health"]
    # No url: the plain container state, honestly unchecked.
    assert view["beta"]["state"] == "running" and view["beta"]["health"] == "unchecked"


def test_running_container_on_a_closed_port_is_not_responding(docker, services_root):
    _set_url(services_root, "alpha", f"http://localhost:{_closed_port()}")
    docker.set(_ALL_RUNNING)

    alpha = _by_name(api.list_view(root=services_root))["alpha"]

    assert alpha["state"] == "running" and alpha["health"] == "not_responding"


def test_a_silent_listener_is_not_responding_within_the_budget(docker, services_root, monkeypatch):
    """Accepts the connection, never answers: the listing still returns, bounded."""
    monkeypatch.setattr(api, "HEALTH_BUDGET", 0.5)
    with socket.socket() as silent:
        silent.bind(("127.0.0.1", 0))
        silent.listen(8)
        for name in ("alpha", "beta"):
            _set_url(services_root, name, f"http://127.0.0.1:{silent.getsockname()[1]}")
        docker.set(_ALL_RUNNING)

        started = time.monotonic()
        view = _by_name(api.list_view(root=services_root))
        elapsed = time.monotonic() - started

    assert {s["health"] for s in view.values()} == {"not_responding"}
    assert elapsed < 4.0  # both probes in parallel, under the budget (+ fake docker)


@pytest.mark.parametrize("url", [
    "http://192.0.2.10:{port}", "http://127.0.0.2:{port}", "http://127.0.0.1@example.invalid:{port}",
    "http://localhost.example.invalid:{port}", "file:///etc/passwd", "ftp://127.0.0.1:{port}",
])
def test_non_loopback_urls_are_never_requested(docker, services_root, http_server, monkeypatch, url):
    connects = []
    real = socket.create_connection
    monkeypatch.setattr(socket, "create_connection", lambda *a, **k: connects.append(a) or real(*a, **k))
    _set_url(services_root, "alpha", url.format(port=http_server.server_port))
    docker.set(_ALL_RUNNING)

    alpha = _by_name(api.list_view(root=services_root))["alpha"]

    assert alpha["state"] == "running" and alpha["health"] == "unchecked"
    assert connects == [] and http_server.hits == []


def test_health_is_only_reported_for_running_services(docker, services_root, http_server):
    _set_url(services_root, "beta", f"http://127.0.0.1:{http_server.server_port}")
    docker.set({"janitor-beta-api": "running", "janitor-beta-db": "exited"})

    view = _by_name(api.list_view(root=services_root))

    assert view["beta"]["state"] == "partial" and view["beta"]["health"] is None
    assert view["alpha"]["state"] == "not_installed" and view["alpha"]["health"] is None
    assert http_server.hits == []


# ── actions ────────────────────────────────────────────────────────────────


def test_start_and_stop_touch_only_the_declared_containers(docker, services_root):
    docker.set({"janitor-beta-api": "exited", "janitor-beta-db": "exited"})

    started = api.act("beta", "start", root=services_root)
    assert started["ok"] is True and started["service"]["state"] == "running"
    stopped = api.act("beta", "stop", root=services_root)
    assert stopped["ok"] is True and stopped["service"]["state"] == "stopped"

    lifecycle = [c for c in docker.calls if c[0] not in ("version", "inspect")]
    assert lifecycle == [
        ["start", "janitor-beta-api", "janitor-beta-db"],
        ["stop", "janitor-beta-api", "janitor-beta-db"],
    ]
    flat = [arg for call in docker.calls for arg in call]
    for forbidden in ("rm", "prune", "-v", "--volumes", "down", "kill", "volume", "compose"):
        assert forbidden not in flat
    assert {c for call in docker.calls if call[0] == "inspect" for c in call[3:]} <= {
        "janitor-beta-api", "janitor-beta-db"}


def test_start_of_a_service_that_is_not_installed_is_refused(docker, services_root):
    result = api.act("alpha", "start", root=services_root)
    assert result["ok"] is False and result["error"] == "not_installed"
    assert not [c for c in docker.calls if c[0] == "start"]


def test_actions_report_docker_unavailable(no_docker, services_root):
    result = api.act("alpha", "stop", root=services_root)
    assert result == {"ok": False, "error": "docker_unavailable", "service": result["service"]}


def test_a_failed_docker_command_is_reported(docker, services_root):
    docker.set({"janitor-alpha": "exited"}, fail=True)
    result = api.act("alpha", "start", root=services_root)
    assert result["ok"] is False and result["error"] == "docker_failed"
    assert result["service"]["state"] == "stopped"


def test_one_action_per_service_at_a_time(docker, services_root):
    docker.set({"janitor-alpha": "exited"})
    lock = api._lock_for("alpha")
    lock.acquire()
    try:
        assert api.act("alpha", "start", root=services_root) == {"ok": False, "error": "busy"}
    finally:
        lock.release()
    assert docker.calls == []


@pytest.mark.parametrize(
    "name",
    ["gamma", "../alpha", "alpha/../beta", "/etc/passwd", "ALPHA", "janitor-alpha", "alpha;rm", "-v", "", "a" * 41],
)
def test_unknown_and_path_like_names_are_rejected(docker, services_root, name):
    with pytest.raises(api.UnknownService):
        api.act(name, "start", root=services_root)
    assert docker.calls == []


def test_only_start_and_stop_exist(docker, services_root):
    for action in ("deploy", "uninstall", "rm"):
        with pytest.raises(ValueError):
            api.act("alpha", action, root=services_root)
    assert docker.calls == []


# ── HTTP surface ───────────────────────────────────────────────────────────


@pytest.fixture
def client(docker, services_root):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    app = FastAPI()
    app.include_router(api.build_router(root=services_root), prefix="/api/plugins/janitor")
    return TestClient(app)


def test_http_routes(client, docker):
    docker.set({"janitor-alpha": "exited"})
    assert client.get("/api/plugins/janitor/servicios").json()["docker"]["available"] is True
    assert client.post("/api/plugins/janitor/servicios/alpha/start").json()["ok"] is True
    assert client.post("/api/plugins/janitor/servicios/gamma/start").status_code == 404
    assert client.post("/api/plugins/janitor/servicios/..%2Falpha/start").status_code == 404
    assert client.post("/api/plugins/janitor/servicios/alpha/uninstall").status_code in (404, 405)
    assert client.get("/api/plugins/janitor/servicios/alpha/start").status_code == 405
    assert docker.containers == {"janitor-alpha": "running"}


# ── delivery into the home ────────────────────────────────────────────────


def _tree(home: Path) -> dict:
    return {p.relative_to(home).as_posix(): p.read_bytes() for p in sorted(home.rglob("*")) if p.is_file()}


def test_sync_is_idempotent(tmp_path):
    home = tmp_path / ".janitor"
    first = desktop_plugin.sync(home)
    assert sorted(first) == sorted(desktop_plugin.FILES)
    before = _tree(home)
    assert desktop_plugin.sync(home) == []
    assert _tree(home) == before
    for rel in desktop_plugin.FILES:
        assert (home / rel).read_bytes() == (desktop_plugin.ASSETS_ROOT / rel).read_bytes()


def test_sync_refreshes_an_unmodified_older_copy(tmp_path, monkeypatch):
    home = tmp_path / ".janitor"
    old_assets = tmp_path / "old-assets"
    for rel in desktop_plugin.FILES:
        (old_assets / rel).parent.mkdir(parents=True, exist_ok=True)
        (old_assets / rel).write_bytes(b"// previous release\n")
    monkeypatch.setattr(desktop_plugin, "ASSETS_ROOT", old_assets)
    desktop_plugin.sync(home)
    monkeypatch.undo()

    assert sorted(desktop_plugin.sync(home)) == sorted(desktop_plugin.FILES)
    assert not (home / ".backup").exists()


def test_sync_backs_up_a_user_modified_copy(tmp_path):
    home = tmp_path / ".janitor"
    desktop_plugin.sync(home)
    plugin = home / desktop_plugin.FILES[0]
    plugin.write_text("// my own tweak\n")

    changes = desktop_plugin.sync(home)

    backups = list((home / ".backup").glob(f"desktop-plugin-*/{desktop_plugin.FILES[0]}"))
    assert [b.read_text() for b in backups] == ["// my own tweak\n"]
    assert plugin.read_bytes() == (desktop_plugin.ASSETS_ROOT / desktop_plugin.FILES[0]).read_bytes()
    assert desktop_plugin.FILES[0] in changes
    assert desktop_plugin.sync(home) == []


def test_sync_leaves_a_symlinked_copy_alone(tmp_path):
    home = tmp_path / ".janitor"
    mine = tmp_path / "dev-plugin.js"
    mine.write_text("// live checkout\n")
    link = home / desktop_plugin.FILES[0]
    link.parent.mkdir(parents=True)
    link.symlink_to(mine)

    desktop_plugin.sync(home)

    assert link.is_symlink() and mine.read_text() == "// live checkout\n"


def test_seed_delivers_a_plugin_hermes_mounts_and_loads(tmp_path, monkeypatch):
    """The seeded home holds both halves where upstream discovers them, the seed
    config allows the backend, and the shim imports a router with the routes."""
    from janitor.seed import ensure_home
    from hermes_cli import web_server_dashboard as dash

    home = tmp_path / ".janitor"
    ensure_home(home)
    monkeypatch.setenv("HERMES_HOME", str(home))

    assert (home / "desktop-plugins" / "janitor" / "plugin.js").is_file()
    assert not (home / "desktop-plugins" / "janitor" / ".hermes-package.json").exists()
    assert not (home / "plugins" / "janitor" / "desktop").exists()  # no opt-in unified-package copy

    found = {p["name"]: p for p in dash._discover_dashboard_plugins()}
    plugin = found["janitor"]
    assert plugin["source"] == "user" and plugin["has_api"] is True

    enabled = set(yaml.safe_load((home / "config.yaml").read_text())["plugins"]["enabled"])
    assert dash._plugin_api_mount_skip_reason(plugin, enabled, set()) is None
    assert dash._plugin_api_mount_skip_reason(plugin, set(), set()) is not None

    spec = importlib.util.spec_from_file_location(
        "janitor_test_plugin_api", Path(plugin["_dir"]) / plugin["_api_file"])
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    paths = {route.path for route in module.router.routes}
    assert {"/servicios", "/servicios/{name}/start", "/servicios/{name}/stop",
            "/perfiles/{perfil}/skills", "/perfiles/{perfil}/skills/{skill}", "/agentes"} == paths
