"""Updates the desktop app triggers go through Janitor's single update core.

The app applies an update by running ``scripts/desktop-update/posix.sh`` from
the installed checkout, which invokes ``<venv>/bin/<cli> update --yes
[--gateway] [--keep-stash] --branch B``. Directive #13 requires that to be
``janitor update`` (``janitor/update_core.py``), not upstream's ``hermes
update``. These tests pin the hand-off, the flags the core must accept, the
``--keep-stash`` contract on a real git checkout, and the venv the core
installs into (``hermes-agent/venv``, the app's layout).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

import janitor.update_core as juc
from tests.janitor.desktop_update_harness import run_posix_handoff


# ---------------------------------------------------------------------------
# posix.sh hand-off
# ---------------------------------------------------------------------------


@pytest.mark.linux_only
def test_handoff_forwards_branch_and_gateway_choice_to_janitor_update(tmp_path):
    seen = run_posix_handoff(tmp_path, "--branch", "next", "--no-gateway")

    assert seen["hermes"] == []
    assert len(seen["core"]) == 1
    args = seen["core"][0]
    assert args["branch"] == "next"
    assert args["gateway"] is False
    assert args["keep_stash"] is True
    assert seen["result"]["ok"] is True


@pytest.mark.linux_only
def test_handoff_without_janitor_script_still_runs_hermes_update(tmp_path):
    """A checkout whose venv has no `janitor` script keeps upstream behaviour."""
    seen = run_posix_handoff(tmp_path, with_janitor=False)

    assert seen["core"] == []
    assert len(seen["hermes"]) == 1
    assert seen["hermes"][0].split()[:2] == ["update", "--yes"]


# ---------------------------------------------------------------------------
# posix.sh after updating the engine from an AppImage (design 3.3)
# ---------------------------------------------------------------------------

# Records how it was launched, then stays up like an app that booted.
_FAKE_APPIMAGE = """#!/bin/bash
printf '%s\\n' "$PWD" "$@" > "$JANITOR_TEST_APPIMAGE_RECORD"
echo $$ > "$JANITOR_TEST_APPIMAGE_RECORD.pid"
exec sleep 30
"""


@pytest.fixture
def appimage(tmp_path):
    """A fake AppImage outside the checkout; killed after the test."""
    path = tmp_path / "Apps" / "Janitor.AppImage"
    path.parent.mkdir()
    path.write_text(_FAKE_APPIMAGE, encoding="utf-8")
    path.chmod(0o755)
    record = tmp_path / "appimage-launch.txt"
    yield path, record
    pid_file = Path(f"{record}.pid")
    if pid_file.exists():
        subprocess.run(["kill", pid_file.read_text(encoding="utf-8").strip()], check=False)


def _from_appimage(tmp_path, appimage_value: str, record: Path, *extra: str) -> dict:
    # The running binary lives in the AppImage's own mount, never under the checkout.
    mounted = tmp_path / ".mount_Janitor" / "janitor"
    return run_posix_handoff(
        tmp_path, "--relaunch-target", str(mounted), *extra,
        env={"APPIMAGE": appimage_value, "JANITOR_TEST_APPIMAGE_RECORD": str(record)},
    )


@pytest.mark.linux_only
def test_engine_update_from_an_appimage_reopens_that_appimage(tmp_path, appimage):
    path, record = appimage
    cwd = tmp_path / "launched-from"
    cwd.mkdir()

    seen = _from_appimage(tmp_path, str(path), record, "--relaunch-cwd", str(cwd), "--", "janitor://chat")

    assert record.read_text(encoding="utf-8").splitlines() == [str(cwd), "janitor://chat"]
    result = seen["result"]
    assert result["ok"] is True and result["manual"] is False, result
    # posix.sh does not know the app/engine contract: neutral, Spanish, points to the app's own check.
    assert "Janitor" in result["message"] and "descarga" in result["message"], result
    assert "hermes" not in result["message"].lower() and "AppImage/deb/rpm" not in result["message"], result


@pytest.mark.linux_only
def test_without_appimage_a_foreign_binary_keeps_the_skew_outcome(tmp_path, appimage):
    _, record = appimage
    mounted = tmp_path / "opt" / "janitor"

    seen = run_posix_handoff(
        tmp_path, "--relaunch-target", str(mounted), env={"JANITOR_TEST_APPIMAGE_RECORD": str(record)}
    )

    assert not record.exists()
    result = seen["result"]
    assert result["ok"] is True and result["manual"] is True, result
    assert "no se puede actualizar sola" in result["message"], result
    assert "AppImage/deb/rpm" not in result["message"], result


@pytest.mark.linux_only
@pytest.mark.parametrize("kind", ["not-executable", "relative", "directory"])
def test_an_untrustworthy_appimage_value_is_ignored(tmp_path, appimage, kind):
    path, record = appimage
    if kind == "not-executable":
        path.chmod(0o644)
        value = str(path)
    elif kind == "relative":
        # An executable with that relative name exists in the hand-off's cwd (the checkout).
        (tmp_path / "hermes-agent").mkdir()
        local = tmp_path / "hermes-agent" / "Janitor.AppImage"
        local.write_text(_FAKE_APPIMAGE, encoding="utf-8")
        local.chmod(0o755)
        value = "Janitor.AppImage"
    else:
        value = str(path.parent)

    seen = _from_appimage(tmp_path, value, record)

    assert not record.exists()
    result = seen["result"]
    assert result["ok"] is True and result["manual"] is True, result
    assert "no se puede actualizar sola" in result["message"], result
    assert "AppImage/deb/rpm" not in result["message"], result


@pytest.mark.linux_only
def test_an_appimage_that_dies_at_once_downgrades_to_reopen_by_hand(tmp_path, appimage):
    path, record = appimage
    path.write_text("#!/bin/bash\nexit 1\n", encoding="utf-8")

    seen = _from_appimage(tmp_path, str(path), record)

    result = seen["result"]
    assert result["ok"] is True and result["manual"] is True, result
    assert "Janitor" in result["message"] and "hermes" not in result["message"].lower(), result


def test_parser_accepts_every_flag_the_desktop_handoff_passes():
    args = juc.parse_update_args(["--yes", "--gateway", "--keep-stash", "--branch", "main"])

    assert (args.yes, args.gateway, args.keep_stash, args.branch) == (True, True, True, "main")
    assert juc.parse_update_args([]).keep_stash is False


# ---------------------------------------------------------------------------
# --keep-stash on a real checkout
# ---------------------------------------------------------------------------


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True
    ).stdout.strip()


@pytest.fixture
def checkout(tmp_path, monkeypatch):
    """A clone one commit behind its (local, bare) origin with a dirty file."""
    gitconfig = tmp_path / "gitconfig"
    gitconfig.write_text("", encoding="utf-8")
    for key, value in {
        "GIT_CONFIG_GLOBAL": str(gitconfig),
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@example.invalid",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@example.invalid",
    }.items():
        monkeypatch.setenv(key, value)

    origin = tmp_path / "origin.git"
    seed = tmp_path / "seed"
    _git(tmp_path, "init", "--bare", "-b", "main", str(origin))
    _git(tmp_path, "init", "-b", "main", str(seed))
    (seed / "tracked.txt").write_text("v1\n", encoding="utf-8")
    _git(seed, "add", ".")
    _git(seed, "commit", "-m", "one")
    _git(seed, "push", str(origin), "main")

    clone = tmp_path / "hermes-agent"
    _git(tmp_path, "clone", str(origin), str(clone))

    (seed / "new.txt").write_text("upstream\n", encoding="utf-8")
    _git(seed, "add", ".")
    _git(seed, "commit", "-m", "two")
    _git(seed, "push", str(origin), "main")

    (clone / "tracked.txt").write_text("local edit\n", encoding="utf-8")
    return clone


def _stub_everything_but_git(monkeypatch, root: Path, home: Path, parked: list):
    home.mkdir(exist_ok=True)
    monkeypatch.setattr(juc, "PROJECT_ROOT", root)
    monkeypatch.setattr(juc, "get_hermes_home", lambda: home)
    monkeypatch.setattr(juc, "_acquire_update_lock", lambda: (None, None))
    monkeypatch.setattr(juc, "_run_pre_update_backup", lambda args: None)
    monkeypatch.setattr(juc, "_install_hangup_protection", lambda gateway_mode=False: {})
    monkeypatch.setattr(juc, "_finalize_update_output", lambda state: None)
    monkeypatch.setattr(juc, "_discard_lockfile_churn", lambda git_cmd, cwd: None)
    monkeypatch.setattr(juc, "_normalize_managed_eol", lambda git_cmd, cwd: None)
    monkeypatch.setattr(juc, "_stash_local_changes_if_needed", lambda g, c: juc._local_stash(g, c))
    monkeypatch.setattr(
        juc, "_restore_stashed_changes", lambda g, c, ref, **kw: juc._local_restore_stash(g, c, ref)
    )
    monkeypatch.setattr(juc, "_park_stashed_changes", parked.append)
    monkeypatch.setattr(juc, "_capture_head_sha", lambda g, c: _git(c, "rev-parse", "HEAD"))
    monkeypatch.setattr(juc, "_validate_critical_files_syntax", lambda r: (True, None, None))
    monkeypatch.setattr(juc, "_invalidate_update_cache", lambda: None)
    monkeypatch.setattr(juc, "_clear_bytecode_cache", lambda r: 0)
    monkeypatch.setattr(juc, "_reload_helper_modules_after_pull", lambda: None)
    monkeypatch.setattr(juc, "_install_python_dependencies", lambda r: None)
    monkeypatch.setattr(juc, "_refresh_active_lazy_features", lambda: None)
    monkeypatch.setattr(juc, "_install_node_dependencies", lambda r: [])
    monkeypatch.setattr(juc, "_run_config_check_fresh", lambda: (1, 1))
    monkeypatch.setattr(juc, "_run_migrate_config_fresh", lambda **kw: {})
    monkeypatch.setattr(juc, "_print_update_completion", lambda message: None)
    monkeypatch.setattr(juc, "_build_web_ui", lambda *a, **kw: True)
    monkeypatch.setattr(juc, "_gateways_in_update_scope", lambda: [])
    monkeypatch.setattr(juc, "_fleet_runs_stale_code", lambda: False)


def test_keep_stash_updates_and_leaves_local_edits_parked(checkout, tmp_path, monkeypatch):
    parked: list = []
    _stub_everything_but_git(monkeypatch, checkout, tmp_path / "home", parked)

    rc = juc.run_janitor_update(juc.parse_update_args(["--yes", "--keep-stash", "--branch", "main"]))

    assert rc == 0
    assert _git(checkout, "rev-parse", "HEAD") == _git(checkout, "rev-parse", "origin/main")
    assert (checkout / "tracked.txt").read_text(encoding="utf-8") == "v1\n"
    stashes = _git(checkout, "stash", "list", "--format=%H").splitlines()
    assert parked == stashes and len(stashes) == 1


def test_without_keep_stash_local_edits_are_restored(checkout, tmp_path, monkeypatch):
    parked: list = []
    _stub_everything_but_git(monkeypatch, checkout, tmp_path / "home", parked)

    rc = juc.run_janitor_update(juc.parse_update_args(["--branch", "main"]))

    assert rc == 0
    assert _git(checkout, "rev-parse", "HEAD") == _git(checkout, "rev-parse", "origin/main")
    assert (checkout / "tracked.txt").read_text(encoding="utf-8") == "local edit\n"
    assert parked == []
    assert _git(checkout, "stash", "list") == ""


# ---------------------------------------------------------------------------
# Which venv the dependency install targets
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "dirs, expected",
    [
        (("venv",), "venv"),  # desktop app / install.sh: ~/.janitor/hermes-agent/venv
        (("venv", ".venv"), "venv"),
    ],
)
def test_uv_install_targets_the_checkouts_own_venv(tmp_path, monkeypatch, dirs, expected):
    for name in dirs:
        (tmp_path / name).mkdir()
    seen: dict = {}

    def fake_install(prefix, *, env=None, group="all"):
        seen["venv"] = env["VIRTUAL_ENV"]

    monkeypatch.setattr(juc, "_resolve_uv_bin", lambda pip_cmd: "/usr/bin/uv")
    monkeypatch.setattr(juc, "_is_termux_env", lambda *a: False)
    monkeypatch.setattr(juc, "_is_android_python", lambda: False)
    monkeypatch.setattr(juc, "_install_python_dependencies_with_optional_fallback", fake_install)

    juc._install_python_dependencies(tmp_path)

    assert seen["venv"] == str(tmp_path / expected)


@pytest.mark.parametrize("dirs", [(), (".venv",)])
def test_out_of_tree_venv_falls_back_to_the_running_interpreter(tmp_path, dirs):
    for name in dirs:
        (tmp_path / name).mkdir()
    assert juc._project_venv(tmp_path) == Path(sys.prefix)
