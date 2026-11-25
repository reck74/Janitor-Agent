"""``janitor services`` and the ``service.yaml`` contract."""

from __future__ import annotations

import os
import stat
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from janitor import services
from janitor.home import SKILLS_ROOT
from tests.janitor.legacy_home import REPO_ROOT, launcher_env

ALL_SERVICES = services.discover_services()


def _compose_container_names(service: services.Service) -> set[str]:
    data = yaml.safe_load(service.compose_file.read_text(encoding="utf-8"))
    return {
        spec["container_name"]
        for spec in (data.get("services") or {}).values()
        if isinstance(spec, dict) and "container_name" in spec
    }


# ── service.yaml contract ──────────────────────────────────────────────────


def test_every_service_skill_has_a_manifest():
    with_compose = {p.parent.parent.name for p in SKILLS_ROOT.glob("services/*/scripts/*compose*.yml")}
    with_manifest = {s.skill_dir.name for s in ALL_SERVICES}
    assert with_compose and with_compose == with_manifest


@pytest.mark.parametrize("service", ALL_SERVICES, ids=lambda s: s.name)
def test_manifest_matches_compose_and_scripts(service):
    assert service.skill_dir.name == f"janitor-{service.name}"
    assert all(c.startswith("janitor-") for c in service.containers)
    assert set(service.containers) == _compose_container_names(service)
    script = service.deploy_script
    assert script.is_file()
    assert _is_executable(script), f"{script} is not executable"


def _is_executable(path: Path) -> bool:
    # Windows checkouts drop the exec bit; the committed mode is what ships.
    staged = subprocess.run(
        ["git", "ls-files", "-s", "--", str(path.relative_to(REPO_ROOT))],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    if staged.returncode == 0 and staged.stdout:
        return staged.stdout.startswith("100755")
    return bool(path.stat().st_mode & stat.S_IXUSR)


def test_manifest_rejects_unprefixed_containers(tmp_path):
    skill = tmp_path / "janitor-foo"
    skill.mkdir()
    (skill / "service.yaml").write_text(
        "name: foo\ndeploy: scripts/deploy.sh\ncontainers: [foo-db]\n", encoding="utf-8"
    )
    with pytest.raises(services.ServiceError, match="janitor-"):
        services.discover_services(tmp_path)


def test_get_service_accepts_prefixed_name():
    assert services.get_service("janitor-honcho").name == "honcho"
    with pytest.raises(services.ServiceError, match="honcho"):
        services.get_service("nope")


# ── lifecycle via an injected runner ───────────────────────────────────────


class FakeDocker:
    def __init__(self, states):
        self.states = states
        self.calls: list[list[str]] = []

    def __call__(self, argv, **kwargs):
        self.calls.append(argv)
        if argv[:2] == ["docker", "inspect"]:
            state = self.states.get(argv[-1])
            if state is None:
                return subprocess.CompletedProcess(argv, 1, "", "No such object")
            return subprocess.CompletedProcess(argv, 0, f"{state}\n", "")
        return subprocess.CompletedProcess(argv, 0, "", "")

    def mutating(self):
        return [c for c in self.calls if c[:2] != ["docker", "inspect"]]


def _args(action, name=None):
    return SimpleNamespace(services_action=action, name=name)


def test_status_reports_each_container():
    honcho = services.get_service("honcho")
    docker = FakeDocker({honcho.containers[0]: "running", honcho.containers[1]: "exited"})
    lines: list[str] = []
    assert services.handle(_args("status", "honcho"), runner=docker, out=lines.append) == 0
    assert lines[0] == f"honcho: {services.state_text('degraded', None)}"
    assert any(honcho.containers[0] in l and services.container_state_text("running") in l for l in lines)
    assert any(honcho.containers[-1] in l and services.container_state_text("absent") in l for l in lines)


# English the CLI must not show: the codes ``summarize`` / ``docker inspect`` return.
_ENGLISH_STATES = ("running", "stopped", "degraded", "not deployed", "exited", "absent")


@pytest.mark.parametrize("summary", ["running", "degraded", "stopped", "not deployed"])
def test_cli_state_text_is_spanish_and_distinct(summary):
    """The CLI shows each summary in Spanish; the codes themselves stay for the API."""
    texts = {s: services.state_text(s, None) for s in ("running", "degraded", "stopped", "not deployed")}
    assert len(set(texts.values())) == len(texts)
    assert not any(word in texts[summary] for word in _ENGLISH_STATES), texts[summary]
    for health in (services.HEALTH_RESPONDING, services.HEALTH_NOT_RESPONDING, services.HEALTH_UNCHECKED):
        assert not any(word in services.state_text("running", health) for word in _ENGLISH_STATES)


def test_list_shows_spanish_states_and_descriptions():
    """`janitor services list`: no English state word, and every description is the manifest's."""
    docker = FakeDocker({})
    lines: list[str] = []
    assert services.handle(_args("list"), runner=docker, out=lines.append) == 0
    assert len(lines) == len(ALL_SERVICES)
    for line, service in zip(lines, ALL_SERVICES):
        assert line.startswith(service.name)
        assert services.state_text("not deployed", None) in line
        assert line.endswith(service.description)
        assert not any(f" {word}" in line.lower() for word in _ENGLISH_STATES), line


@pytest.mark.parametrize("service", ALL_SERVICES, ids=lambda s: s.name)
def test_service_descriptions_are_spanish(service):
    """Descriptions reach `services list`: Spanish, so at least one Spanish function word."""
    words = set(service.description.lower().replace("(", " ").replace(",", " ").split())
    assert words & {"de", "con", "que", "tu", "en", "y", "para", "entre"}, service.description
    assert not words & {"the", "and", "for", "with", "backend", "memory"}, service.description


@pytest.mark.parametrize(
    "states, expected",
    [
        ({"a": "running", "b": "running"}, "running"),
        ({"a": "absent", "b": "absent"}, "not deployed"),
        ({"a": "running", "b": "exited"}, "degraded"),
        ({"a": "exited", "b": "absent"}, "stopped"),
    ],
)
def test_summarize(states, expected):
    assert services.summarize(states) == expected


def test_stop_and_uninstall_only_touch_existing_containers_and_never_volumes():
    n8n = services.get_service("nocodb")
    present = n8n.containers[:2]
    docker = FakeDocker({c: "running" for c in present})

    assert services.handle(_args("stop", "nocodb"), runner=docker, out=lambda _: None) == 0
    assert services.handle(_args("uninstall", "nocodb"), runner=docker, out=lambda _: None) == 0

    assert docker.mutating() == [
        ["docker", "stop", *present],
        ["docker", "rm", "-f", *present],
    ]
    flat = " ".join(" ".join(c) for c in docker.calls)
    assert "volume" not in flat and " -v" not in flat and "down" not in flat


def test_start_requires_a_deployed_service():
    docker = FakeDocker({})
    lines: list[str] = []
    assert services.handle(_args("start", "waha"), runner=docker, out=lines.append) == 1
    assert "janitor services deploy waha" in lines[0]
    assert docker.mutating() == []


def test_deploy_runs_the_skill_script_with_janitor_env(monkeypatch):
    monkeypatch.delenv("JANITOR_SOURCE_DIR", raising=False)
    seen = {}

    def runner(argv, **kwargs):
        seen.update(argv=argv, **kwargs)
        return subprocess.CompletedProcess(argv, 0)

    firecrawl = services.get_service("firecrawl")
    assert services.deploy(firecrawl, runner, platform="linux") == 0
    assert seen["argv"] == ["bash", str(firecrawl.deploy_script)]
    assert seen["cwd"] == str(firecrawl.skill_dir)
    assert seen["env"]["JANITOR_SOURCE_DIR"] == str(REPO_ROOT)


def test_status_tells_a_running_container_from_a_service_that_answers(tmp_path, monkeypatch):
    """`janitor services status` asks the loopback url of a running service (F4-06)."""
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    import socket
    import threading

    class NotFound(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(404)
            self.send_header("Content-Length", "0")
            self.end_headers()

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), NotFound)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        closed = sock.getsockname()[1]

    def svc(name, url):
        return services.Service(name, "", tmp_path, "deploy.sh", "", url, (f"janitor-{name}",))

    fleet = [svc("up", f"http://127.0.0.1:{server.server_port}"),
             svc("booting", f"http://127.0.0.1:{closed}"), svc("nourl", "")]
    monkeypatch.setattr(services, "discover_services", lambda root=None: fleet)
    docker = FakeDocker({f"janitor-{s.name}": "running" for s in fleet})
    lines: list[str] = []
    try:
        assert services.handle(_args("status"), runner=docker, out=lines.append) == 0
    finally:
        server.shutdown()
        server.server_close()

    heads = {l.split(":", 1)[0]: l for l in lines if not l.startswith(" ")}
    texts = {
        name: services.state_text("running", health)
        for name, health in (("up", services.HEALTH_RESPONDING), ("booting", services.HEALTH_NOT_RESPONDING),
                             ("nourl", services.HEALTH_UNCHECKED))
    }
    assert len(set(texts.values())) == 3
    assert {name: line.split(": ", 1)[1] for name, line in heads.items()} == texts
    assert docker.mutating() == []


def _refusing_runner(argv, **kwargs):
    raise AssertionError(f"nothing may run on an unsupported OS: {argv}")


def test_services_on_windows_are_refused_with_a_spanish_reason_and_run_nothing():
    """Deploy scripts are bash and Docker is asked nothing: the reason is the answer."""
    with pytest.raises(services.ServiceError) as exc:
        services.deploy(services.get_service("firecrawl"), _refusing_runner, platform="win32")
    assert "Linux o macOS" in str(exc.value)
    assert services.docker_status(_refusing_runner, platform="win32") == services.DOCKER_UNSUPPORTED


@pytest.mark.windows_only
def test_windows_deploy_and_services_screen_report_why():
    """On a real Windows host: `janitor services deploy` explains itself, and the app's
    Servicios screen gets the reason in its payload instead of a Docker error."""
    from janitor.desktop_plugin import api

    lines: list[str] = []
    assert services.handle(_args("deploy", "firecrawl"), runner=_refusing_runner, out=lines.append) == 1
    assert "Linux o macOS" in lines[0]

    view = api.list_view(_refusing_runner)
    assert view["docker"] == {"available": False, "status": services.DOCKER_UNSUPPORTED}
    assert view["services"] and all(s["state"] == api.STATE_DOCKER_UNAVAILABLE for s in view["services"])


def test_missing_docker_is_a_clean_error():
    def runner(argv, **kwargs):
        raise FileNotFoundError(argv[0])

    lines: list[str] = []
    assert services.handle(_args("status", "n8n"), runner=runner, out=lines.append) == 1
    assert "Docker" in lines[0]


# ── E2E through the real launcher ──────────────────────────────────────────


@pytest.fixture
def fresh_home(tmp_path):
    """A brand-new install: the home ``janitor.seed`` leaves (what install.sh's
    config stage and the launcher's first start produce)."""
    from janitor.seed import ensure_home

    home = tmp_path / ".janitor"
    ensure_home(home)
    (home / ".env").write_text(
        "MINIMAX_API_KEY=sk-test\nHONCHO_BASE_URL=http://127.0.0.1:1973\n", encoding="utf-8"
    )
    return tmp_path


def _janitor(root, *args, env=None):
    code = "import sys; sys.argv = ['janitor', *sys.argv[1:]]; from janitor.cli import main; main()"
    return subprocess.run(
        [sys.executable, "-c", code, *args],
        capture_output=True,
        text=True,
        env=env or launcher_env(root),
        cwd=str(root),
        timeout=180,
    )


def test_skills_resolve_from_the_install_tree(fresh_home):
    """A fresh home lists its catalog skills (``main``) in place, once each; the
    other Janitor skills, services included, stay out until chosen (F2-01)."""
    from janitor import catalog

    result = _janitor(fresh_home, "skills", "list")
    assert result.returncode == 0, result.stderr
    rows = [line for line in result.stdout.splitlines() if line.startswith("│")]
    names = [row.split("│")[1].strip() for row in rows]
    main = catalog.skills_for_template("main")
    for name in main:
        assert names.count(name) == 1, f"{name} listed {names.count(name)}x\n{result.stdout}"
    shipped = {catalog.read_skill_name(md.parent) for md in SKILLS_ROOT.rglob("SKILL.md")}
    assert not (shipped - set(main)) & set(names), result.stdout
    assert not (fresh_home / ".janitor" / "skills" / "janitor-firecrawl").exists()


@pytest.mark.linux_only
def test_services_status_end_to_end_with_fake_docker(fresh_home):
    bin_dir = fresh_home / "bin"
    bin_dir.mkdir()
    log = fresh_home / "docker.log"
    fake = bin_dir / "docker"
    fake.write_text(
        f"#!{sys.executable}\n"
        "import sys\n"
        f"open({str(log)!r}, 'a').write(' '.join(sys.argv[1:]) + '\\n')\n"
        "print('exited' if sys.argv[1] == 'inspect' else '')\n",
        encoding="utf-8",
    )
    fake.chmod(0o755)
    env = launcher_env(fresh_home)
    env["PATH"] = f"{bin_dir}{os.pathsep}{env.get('PATH', '')}"

    result = _janitor(fresh_home, "services", "status", "honcho", env=env)
    assert result.returncode == 0, result.stderr
    # Containers reported stopped: a running one would make `status` call the
    # honcho url, which on a developer machine is the real local service.
    assert f"honcho: {services.state_text('stopped', None)}" in result.stdout

    result = _janitor(fresh_home, "services", "stop", "honcho", env=env)
    assert result.returncode == 0, result.stderr
    honcho = services.get_service("honcho")
    assert f"stop {' '.join(honcho.containers)}" in log.read_text(encoding="utf-8")
