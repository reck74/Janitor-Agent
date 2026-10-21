"""``janitor services`` / ``janitor agents`` and the ``service.yaml`` contract."""

from __future__ import annotations

import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from janitor import agents, services
from janitor.home import SKILLS_ROOT
from tests.janitor.legacy_home import ASSETS, REPO_ROOT, launcher_env

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
    assert script.stat().st_mode & stat.S_IXUSR, f"{script} is not executable"


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
    with pytest.raises(services.ServiceError, match="available"):
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
    assert lines[0] == "honcho: degraded"
    assert any(honcho.containers[0] in l and "running" in l for l in lines)
    assert any(honcho.containers[-1] in l and "absent" in l for l in lines)


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
    assert services.deploy(firecrawl, runner) == 0
    assert seen["argv"] == ["bash", str(firecrawl.deploy_script)]
    assert seen["cwd"] == str(firecrawl.skill_dir)
    assert seen["env"]["JANITOR_SOURCE_DIR"] == str(REPO_ROOT)


def test_missing_docker_is_a_clean_error():
    def runner(argv, **kwargs):
        raise FileNotFoundError(argv[0])

    lines: list[str] = []
    assert services.handle(_args("status", "n8n"), runner=runner, out=lines.append) == 1
    assert "Docker" in lines[0]


# ── agents ─────────────────────────────────────────────────────────────────


def test_agents_are_discovered_from_janitor_skills():
    found = agents.get_agents()
    expected = {p for p in (SKILLS_ROOT / "agents").glob("janitor-*-agent")}
    assert expected and {Path(a["path"]) for a in found} == expected
    for agent in found:
        by_name = agents.load_agent_spec(agent["name"])
        by_dir = agents.load_agent_spec(Path(agent["path"]).name)
        assert by_name is not None and by_name == by_dir


# ── E2E through the real launcher ──────────────────────────────────────────


@pytest.fixture
def fresh_home(tmp_path):
    """A brand-new 1.0 install: seed files copied verbatim from assets/."""
    home = tmp_path / ".janitor"
    (home / "skins").mkdir(parents=True)
    for name in ("config.yaml", "SOUL.md", "honcho.json"):
        shutil.copy2(ASSETS / name, home / name)
    shutil.copy2(ASSETS / "sentry-janitor.yaml", home / "skins" / "sentry-janitor.yaml")
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


def test_agents_command_is_wired_through_the_plugin(fresh_home):
    result = _janitor(fresh_home, "agents", "list")
    assert result.returncode == 0, result.stderr
    for agent in agents.get_agents():
        assert agent["name"] in result.stdout


def test_skills_resolve_from_the_install_tree(fresh_home):
    result = _janitor(fresh_home, "skills", "list")
    assert result.returncode == 0, result.stderr
    rows = [line for line in result.stdout.splitlines() if line.startswith("│")]
    names = [row.split("│")[1].strip() for row in rows]
    shipped = sorted(p.parent.name for p in SKILLS_ROOT.rglob("SKILL.md"))
    for name in shipped:
        assert names.count(name) == 1, f"{name} listed {names.count(name)}x\n{result.stdout}"
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
        "print('running' if sys.argv[1] == 'inspect' else '')\n",
        encoding="utf-8",
    )
    fake.chmod(0o755)
    env = launcher_env(fresh_home)
    env["PATH"] = f"{bin_dir}{os.pathsep}{env.get('PATH', '')}"

    result = _janitor(fresh_home, "services", "status", "honcho", env=env)
    assert result.returncode == 0, result.stderr
    assert "honcho: running" in result.stdout

    result = _janitor(fresh_home, "services", "stop", "honcho", env=env)
    assert result.returncode == 0, result.stderr
    honcho = services.get_service("honcho")
    assert f"stop {' '.join(honcho.containers)}" in log.read_text(encoding="utf-8")
