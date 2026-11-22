"""Gateways started through the Janitor launcher are visible to upstream's discovery (F1-17).

Upstream finds gateways by command line (``gateway.status.looks_like_gateway_command_line``,
behind ``find_gateway_pids``, PID-file validation and the update fleet restart), and only
Hermes entrypoints match. ``janitor gateway run`` therefore hands off to
``python -m hermes_cli.main gateway run`` (``janitor.cli._hand_off_gateway``). These tests
drive upstream's real matchers and discovery with the argv the launcher builds.
"""

from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
import time
from pathlib import Path

import pytest

from gateway.status import (
    looks_like_gateway_command_line,
    looks_like_gateway_runtime_command_line,
    profile_flag_value,
)
from tests.janitor.legacy_home import launcher_env

REPO_ROOT = Path(__file__).resolve().parents[2]
PYTHON = "/opt/janitor/venv/bin/python"
CONSOLE_SCRIPT = "/opt/janitor/venv/bin/janitor"  # `janitor gateway run` (shebang → python <script>)
MODULE_ARGV0 = str(REPO_ROOT / "janitor" / "cli.py")  # `python -m janitor.cli gateway run`


@pytest.fixture(scope="module")
def jc(tmp_path_factory):
    """``janitor.cli`` imported against a temp HOME (the import seeds ``~/.janitor``)."""
    patch = pytest.MonkeyPatch()
    patch.setenv("HOME", str(tmp_path_factory.mktemp("home")))
    import janitor.cli as module

    yield module
    patch.undo()


def _line(argv: list[str]) -> str:
    return shlex.join(argv)


# Launcher argv forms that host a gateway runtime: (argv after argv[0], strict `run` matcher?)
_RUNTIME_FORMS = [
    (["gateway", "run"], True),
    (["gateway", "run", "--replace"], True),
    (["gateway"], True),  # bare `gateway` defaults to `run`
    (["-p", "coder", "gateway", "run"], True),
    (["--profile", "coder", "gateway", "run", "--replace"], True),
    (["gateway", "restart"], False),  # no service manager: the restart runs the gateway in-process
]


@pytest.mark.parametrize("argv0", [CONSOLE_SCRIPT, MODULE_ARGV0])
@pytest.mark.parametrize("args,strict", _RUNTIME_FORMS)
def test_launcher_gateway_is_handed_off_to_a_line_upstream_recognises(jc, argv0, args, strict):
    as_launched = [PYTHON, argv0, *args]
    assert not looks_like_gateway_runtime_command_line(_line(as_launched)), "premise: launcher argv is invisible"

    handed = jc._gateway_handoff_argv([argv0, *args], PYTHON)

    assert handed == [PYTHON, "-m", "hermes_cli.main", *args]
    assert looks_like_gateway_runtime_command_line(_line(handed))
    assert looks_like_gateway_command_line(_line(handed)) is strict
    # A named profile keeps its flag, which is how upstream ties a gateway to its profile.
    assert profile_flag_value(_line(handed)) == ("coder" if "coder" in args else None)


@pytest.mark.parametrize("args", [
    ["gateway", "status"],
    ["gateway", "stop"],
    ["gateway", "install"],
    ["gateway", "start"],  # goes through the service manager, whose unit runs hermes_cli.main
    ["-p", "gateway", "status"],  # a profile named "gateway"
    ["chat", "-q", "gateway run"],
    [],
])
def test_other_commands_stay_in_the_launcher(jc, args):
    assert jc._gateway_handoff_argv([CONSOLE_SCRIPT, *args], PYTHON) is None


_LAUNCH = """
import json, os, sys
sys.argv = [{argv0!r}, *{args!r}]
import janitor.cli as jc
def fake_execve(path, argv, env):
    print(json.dumps({{"path": path, "argv": argv, "env": {{k: env.get(k) for k in
        ("HERMES_HOME", "JANITOR_SKILLS_ROOT", "HERMES_BUNDLED_LOCALES")}}}}))
    sys.stdout.flush()
    os._exit(0)
os.execve = fake_execve
jc.main()
print("NO-HANDOFF")
"""


@pytest.mark.linux_only
@pytest.mark.parametrize("args", [["gateway", "run"], ["-p", "coder", "gateway", "run", "--replace"]])
def test_launcher_main_execs_the_canonical_gateway_with_its_environment(tmp_path, args):
    """The real launcher (seed, migration, fail-safe) ends in the exec, carrying the home it resolved."""
    from janitor.seed import ensure_home

    root = tmp_path / ".janitor"
    ensure_home(root)
    profile = root / "profiles" / "coder"
    profile.mkdir(parents=True)
    (profile / "config.yaml").write_text("display:\n  language: es\n", encoding="utf-8")
    env = launcher_env(tmp_path)
    env["HERMES_HOME"] = str(root)
    code = _LAUNCH.format(argv0=MODULE_ARGV0, args=args)
    result = subprocess.run([sys.executable, "-c", code], env=env, cwd=str(tmp_path),
                            capture_output=True, text=True, timeout=300)
    assert result.returncode == 0, result.stderr[-2000:]
    seen = json.loads(result.stdout.strip().splitlines()[-1])

    assert seen["path"] == sys.executable
    assert seen["argv"] == [sys.executable, "-m", "hermes_cli.main", *args]
    assert looks_like_gateway_command_line(_line(seen["argv"]))
    # Root home + the user's -p: the child resolves the profile exactly as the launcher did.
    assert seen["env"]["HERMES_HOME"] == str(root)
    assert seen["env"]["JANITOR_SKILLS_ROOT"] == str(REPO_ROOT / "janitor" / "skills")
    assert seen["env"]["HERMES_BUNDLED_LOCALES"] == str(root / "cache" / "janitor-locales")


# ── discovery: janitor.update_core._gateways_in_update_scope ─────────────────

_SLEEPER = "import time\ntime.sleep(120)\n"


def _stand_in(tmp_path: Path, argv: list[str], home: Path) -> subprocess.Popen:
    """A process whose command line is exactly ``argv`` but which only sleeps: the cwd holds a
    ``hermes_cli/main.py`` and a ``janitor/cli.py`` that shadow the real ones for ``-m``."""
    fake = tmp_path / "fake"
    for rel in ("hermes_cli/__init__.py", "janitor/__init__.py"):
        (fake / rel).parent.mkdir(parents=True, exist_ok=True)
        (fake / rel).write_text("", encoding="utf-8")
    for rel in ("hermes_cli/main.py", "janitor/cli.py"):
        (fake / rel).write_text(_SLEEPER, encoding="utf-8")
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    env["HERMES_HOME"] = str(home)
    proc = subprocess.Popen(argv, cwd=str(fake), env=env)
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline and not Path(f"/proc/{proc.pid}/cmdline").read_bytes():
        time.sleep(0.05)
    return proc


@pytest.mark.linux_only
@pytest.mark.spawns_gateway_lookalike
def test_update_scope_sees_the_handed_off_gateway_and_not_the_launcher_form(jc, tmp_path, monkeypatch):
    import janitor.update_core as juc

    home = tmp_path / ".janitor"
    home.mkdir()
    monkeypatch.setenv("HERMES_HOME", str(home))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setattr(juc, "get_hermes_home", lambda: home)

    handed = jc._gateway_handoff_argv([MODULE_ARGV0, "gateway", "run"], sys.executable)
    launcher_form = [sys.executable, "-m", "janitor.cli", "gateway", "run"]
    procs = [_stand_in(tmp_path, handed, home), _stand_in(tmp_path, launcher_form, home)]
    try:
        rows = dict(juc._gateways_in_update_scope())
    finally:
        for proc in procs:
            proc.kill()
            proc.wait(timeout=10)

    assert procs[0].pid in rows, "the handed-off gateway is discovered and in this home's scope"
    assert procs[1].pid not in rows, "premise: the launcher's own command line is invisible"
