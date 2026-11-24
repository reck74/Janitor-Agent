"""The fork's ``scripts/install.sh`` (touchpoint ``install-sh``), run offline.

The desktop app drives it stage by stage (``--manifest``, then ``--stage <name>
--non-interactive --json``). These runs use a temp HOME, a fake checkout and,
for the repository stage, a fake ``git``: nothing is downloaded and the real
home is never touched.
"""

from __future__ import annotations

import json
import os
import re
import shutil

import pytest
import yaml

from janitor.home import ASSETS_ROOT
from tests.janitor.install_sh_harness import (
    fake_install_dir,
    run_install_sh,
    run_stage,
    stage_frame,
    tree_snapshot,
    write_fakes,
)

pytestmark = pytest.mark.linux_only


def test_manifest_is_json_and_installs_nothing(tmp_path):
    root = tmp_path / "home"
    root.mkdir()
    result = run_install_sh(root, "--manifest", "--dir", str(root / "install"), "--hermes-home", str(root / ".janitor"))
    assert result.returncode == 0, result.stderr
    manifest = json.loads(result.stdout.strip().splitlines()[-1])
    names = [stage["name"] for stage in manifest["stages"]]
    assert {"repository", "venv", "path", "config"} <= set(names)
    assert list(root.iterdir()) == []


def test_repository_stage_clones_the_fork(tmp_path):
    """A fake ``git`` records every clone and fails it; fake ``sleep`` skips backoff."""
    bin_dir = tmp_path / "fakebin"
    bin_dir.mkdir()
    log = tmp_path / "git.log"
    fakes = {
        "git": (
            "#!/bin/sh\n"
            f'echo "$@" >> "{log}"\n'
            'if [ "$1" = "--version" ]; then echo "git version 2.99.0"; fi\n'
            'if [ "$1" = "clone" ]; then exit 1; fi\n'
            "exit 0\n"
        ),
        "sleep": "#!/bin/sh\nexit 0\n",
    }
    for name, body in fakes.items():
        (bin_dir / name).write_text(body, encoding="utf-8")
        (bin_dir / name).chmod(0o755)

    result = run_stage(tmp_path, "repository", tmp_path / "install", tmp_path / ".janitor", path_prefix=bin_dir)

    assert stage_frame(result.stdout)["ok"] is False
    clones = [line for line in log.read_text(encoding="utf-8").splitlines() if line.startswith("clone")]
    assert clones, result.stdout + result.stderr
    assert all("reck74/Janitor-Agent" in line for line in clones), clones
    assert {"git@github.com:reck74/Janitor-Agent.git", "https://github.com/reck74/Janitor-Agent.git"} <= {
        word for line in clones for word in line.split()
    }


def test_config_stage_leaves_a_seeded_janitor_home(tmp_path):
    install = fake_install_dir(tmp_path)
    home = tmp_path / ".janitor"

    result = run_stage(tmp_path, "config", install, home)

    assert result.returncode == 0, result.stdout + result.stderr
    assert stage_frame(result.stdout) == {"ok": True, "stage": "config", "skipped": False}
    config = yaml.safe_load((home / "config.yaml").read_text(encoding="utf-8"))
    assert "janitor" in config["plugins"]["enabled"]
    assert (home / "SOUL.md").read_bytes() == (ASSETS_ROOT / "SOUL.md").read_bytes()
    assert (home / "skins" / "sentry-janitor.yaml").is_file()
    assert (home / ".no-bundled-skills").is_file()
    # No upstream bundled skill was copied in.
    assert not list((home / "skills").rglob("SKILL.md"))


def test_config_stage_rerun_keeps_user_files(tmp_path):
    install = fake_install_dir(tmp_path)
    home = tmp_path / ".janitor"
    home.mkdir()
    user = {
        "config.yaml": b"model:\n  default: mine\n",
        "SOUL.md": b"Mi alma.\n",
        ".env": b"MINIMAX_API_KEY=sk-user\n",
    }
    for name, data in user.items():
        (home / name).write_bytes(data)

    result = run_stage(tmp_path, "config", install, home)

    assert stage_frame(result.stdout)["ok"] is True, result.stdout + result.stderr
    for name, data in user.items():
        if name == ".env":
            # install.sh may append a detected browser override; never drop the key.
            assert (home / name).read_bytes().startswith(data)
        else:
            assert (home / name).read_bytes() == data, name


def test_path_stage_installs_janitor_and_no_hermes_commands(tmp_path):
    install = fake_install_dir(tmp_path)
    link_dir = tmp_path / ".local" / "bin"
    link_dir.mkdir(parents=True)
    real_hermes = link_dir / "hermes"
    real_hermes.write_bytes(b"#!/bin/sh\necho real hermes\n")

    for _ in range(2):  # idempotent
        result = run_stage(tmp_path, "path", install, tmp_path / ".janitor")
        assert stage_frame(result.stdout) == {"ok": True, "stage": "path", "skipped": False}, (
            result.stdout + result.stderr
        )

    janitor = link_dir / "janitor"
    assert janitor.is_symlink()
    assert os.path.basename(os.readlink(janitor)) == "janitor"
    assert real_hermes.read_bytes() == b"#!/bin/sh\necho real hermes\n"
    assert not (link_dir / "hermes-agent").exists()
    assert not (link_dir / "hermes-acp").exists()


def _legacy_home(root):
    """A home holding the pre-app terminal install, with `janitor` linked into it."""
    home = root / ".janitor"
    legacy_bin = home / "janitor-core" / ".venv" / "bin"
    legacy_bin.mkdir(parents=True)
    (legacy_bin / "janitor").write_bytes(b"#!/bin/sh\necho janitor viejo\n")
    (home / "config.yaml").write_bytes(b"model:\n  default: mine\n")
    link_dir = root / ".local" / "bin"
    link_dir.mkdir(parents=True)
    (link_dir / "janitor").symlink_to(legacy_bin / "janitor")
    return home


@pytest.mark.parametrize("stage", ["path", "config"])
def test_stage_refuses_a_home_with_the_terminal_install(tmp_path, stage):
    """F1-22: a home with janitor-core is left byte for byte as it was."""
    install = fake_install_dir(tmp_path)
    home = _legacy_home(tmp_path)
    before = tree_snapshot(tmp_path)

    result = run_stage(tmp_path, stage, install, home)

    assert result.returncode != 0
    frame = stage_frame(result.stdout)
    assert frame is not None and frame["ok"] is False and frame["stage"] == stage, result.stdout
    reason = frame["reason"]
    assert str(home) in reason and "janitor-core" in reason and "no toqué nada" in reason, reason
    assert reason in result.stderr
    assert tree_snapshot(tmp_path) == before


def test_ensure_mode_refuses_a_home_with_the_terminal_install(tmp_path):
    """``--ensure`` installs packages: it stops at the same guard, before doing anything."""
    home = _legacy_home(tmp_path)
    before = tree_snapshot(tmp_path)

    result = run_install_sh(tmp_path, "--ensure", "node", "--hermes-home", str(home))

    assert result.returncode != 0
    assert "janitor-core" in result.stderr and "no toqué nada" in result.stderr
    assert tree_snapshot(tmp_path) == before


def test_stage_without_the_terminal_install_is_not_refused(tmp_path):
    install = fake_install_dir(tmp_path)
    home = tmp_path / ".janitor"
    (tmp_path / ".local" / "bin").mkdir(parents=True)

    result = run_stage(tmp_path, "path", install, home)

    assert stage_frame(result.stdout) == {"ok": True, "stage": "path", "skipped": False}, (
        result.stdout + result.stderr
    )
    assert "janitor-core" not in result.stdout + result.stderr


# ── optional installs: the base installs nothing it was not asked for (F1-26) ──

# Only the system dirs: the developer's ~/.local/bin may hold a real cua-driver,
# which the node-deps stage would otherwise find and run (`--version`, `manifest`).
_SYSTEM_PATH = "/usr/bin:/bin"


def _node_deps_run(tmp_path, *extra):
    """The node-deps stage with fake node/npm/uv/curl: each records its argv; curl fails."""
    install = fake_install_dir(tmp_path)  # no package.json, no ui-tui: npm installs nothing
    home = tmp_path / ".janitor"
    calls = tmp_path / "calls.log"
    record = f'#!/bin/sh\necho "$(basename "$0") $*" >> "{calls}"\n'
    bin_dir = tmp_path / "fakebin"
    write_fakes(bin_dir, {
        "node": record + 'echo v26.12.0\n',
        "npm": record + 'echo 10.9.0\n',
        "curl": record + "exit 22\n",
    })
    write_fakes(home / "bin", {"uv": record + 'echo "uv 0.0.0"\n'})
    path = f"{bin_dir}{os.pathsep}{_SYSTEM_PATH}"
    assert shutil.which("cua-driver", path=path) is None, "a cua-driver on the system PATH skews this test"
    before = set(os.listdir(tmp_path))
    result = run_stage(tmp_path, "node-deps", install, home, *extra, path=path)
    seen = calls.read_text(encoding="utf-8") if calls.exists() else ""
    return result, seen, set(os.listdir(tmp_path)) - before - {"calls.log"}


def test_node_deps_stage_does_not_install_computer_use_by_default(tmp_path):
    """cua-driver writes ~/.cua-driver (telemetry id), ~/.cursor and ~/.agents: never unasked."""
    result, seen, new_entries = _node_deps_run(tmp_path)

    assert stage_frame(result.stdout) == {"ok": True, "stage": "node-deps", "skipped": False}, (
        result.stdout + result.stderr
    )
    assert "curl" not in seen and "cua" not in seen, seen
    assert not new_entries, new_entries  # nothing new in HOME: no .cua-driver, .cursor, .agents
    assert "cua-driver" in result.stdout  # the user is told it was left out, in Spanish
    assert "Skipping" not in result.stdout


def test_node_deps_stage_does_not_install_the_browser_by_default(tmp_path):
    """The base ships no browser (decision 2.10): no Playwright, no Browser Use, and the user is told."""
    result, seen, _ = _node_deps_run(tmp_path)

    assert stage_frame(result.stdout)["ok"] is True, result.stdout + result.stderr
    assert "playwright" not in seen and "browser-use" not in seen, seen
    assert "la primera vez que Janitor navegue" in result.stdout
    assert "Browser tools will be unavailable" not in result.stdout


def test_with_browser_flag_installs_the_browser_use_cli(tmp_path):
    result, seen, _ = _node_deps_run(tmp_path, "--with-browser")

    assert any(line.startswith("uv ") and "browser-use" in line for line in seen.splitlines()), seen
    assert stage_frame(result.stdout)["ok"] is True, result.stdout + result.stderr


def test_with_computer_use_flag_runs_the_cua_driver_installer(tmp_path):
    result, seen, _ = _node_deps_run(tmp_path, "--with-computer-use")

    assert any(line.startswith("curl ") and "cua-driver" in line for line in seen.splitlines()), seen
    # A failed download stays non-fatal, as upstream designed it.
    assert stage_frame(result.stdout)["ok"] is True, result.stdout + result.stderr


# ── what the app shows under «Mostrar salida del instalador» ──────────────────

# Words of upstream's English messages and summary; none may survive in a stage
# the app runs. Paths are removed first (they may legitimately say anything).
_ENGLISH = re.compile(
    r"\b(Created|Setting up|ready|already|Skipping|Could not|found|installed|Installation|"
    r"Commands|Your files|Reload your shell|Start chatting|Update to latest|Note:)\b"
)
_PATHISH = re.compile(r"(~|/)[^\s:]*")


def _visible(stdout: str) -> list[str]:
    """Lines the installer itself prints: everything except the JSON frame and the
    `janitor.seed` lines (Python output, not part of install.sh)."""
    return [
        line for line in stdout.splitlines()
        if line.strip() and not line.startswith("{") and not line.lower().startswith("janitor ")
    ]


@pytest.mark.parametrize("stage", ["config", "path", "complete"])
def test_stage_output_is_spanish_and_never_says_hermes(tmp_path, stage):
    install = fake_install_dir(tmp_path)
    home = tmp_path / ".janitor"

    result = run_stage(tmp_path, stage, install, home)

    assert stage_frame(result.stdout)["ok"] is True, result.stdout + result.stderr
    lines = _visible(result.stdout + result.stderr)
    assert lines, result.stdout
    words = [_PATHISH.sub("", line) for line in lines]
    leaks = [w for w in words if "hermes" in w.lower() or _ENGLISH.search(w)]
    assert not leaks, leaks


def test_complete_stage_suggests_janitor_commands(tmp_path):
    install = fake_install_dir(tmp_path)
    result = run_stage(tmp_path, "complete", install, tmp_path / ".janitor")

    text = re.sub(r"\x1b\[[0-9;]*m", "", result.stdout)
    commands = re.findall(r"^\s+(janitor|hermes)\b", text, re.MULTILINE)
    assert commands and set(commands) == {"janitor"}, text
    assert "source ~/" not in text


def test_failed_stage_reason_is_spanish(tmp_path):
    """The app shows the frame's reason under a failed stage."""
    result = run_stage(tmp_path, "no-such-stage", fake_install_dir(tmp_path), tmp_path / ".janitor")

    frame = stage_frame(result.stdout)
    assert frame["ok"] is False and not re.search(r"\bexit code\b", frame["reason"]), frame
    assert str(frame["reason"]).split()[-1].isdigit(), frame
