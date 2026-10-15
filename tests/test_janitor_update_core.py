"""Fork update policy and real read-only Git checks around the upstream PM updater."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

import janitor_update_core as core


def git(root, *args):
    return subprocess.run(["git", "-c", "user.name=Janitor Test", "-c", "user.email=test@example.invalid", *args],
                          cwd=root, text=True, capture_output=True, check=True).stdout.strip()


@pytest.fixture
def checkout(tmp_path):
    remote, writer, local = (tmp_path / name for name in ("remote.git", "writer", "local"))
    remote.mkdir()
    git(remote, "init", "--bare", "--initial-branch=main")
    git(tmp_path, "clone", str(remote), str(writer))
    (writer / "janitor_cli.py").write_text("identity = 'janitor'\n")
    git(writer, "add", ".")
    git(writer, "commit", "-m", "initial")
    git(writer, "push", "origin", "main")
    git(tmp_path, "clone", str(remote), str(local))
    return remote, writer, local


def test_check_does_not_fetch_or_modify_checkout(checkout, monkeypatch, capsys):
    _, writer, local = checkout
    before = git(local, "rev-parse", "refs/remotes/origin/main")
    (local / "local-work.txt").write_text("preserve me\n")
    (writer / "change.txt").write_text("new release\n")
    git(writer, "add", ".")
    git(writer, "commit", "-m", "new")
    git(writer, "push", "origin", "main")
    monkeypatch.setattr(core, "PROJECT_ROOT", local)
    monkeypatch.delenv("HERMES_INSTALL_ROOT", raising=False)
    monkeypatch.setattr(core, "_run_upstream_update", lambda args: pytest.fail("check invoked the mutating updater"))
    assert core.run_janitor_update(["--check", "--branch", "main"]) == 0
    assert "update available" in capsys.readouterr().out
    assert git(local, "rev-parse", "refs/remotes/origin/main") == before
    assert git(local, "rev-parse", "HEAD") == before
    assert (local / "local-work.txt").read_text() == "preserve me\n"
    assert not git(local, "stash", "list")


def test_check_current_ref(checkout, monkeypatch, capsys):
    _, _, local = checkout
    monkeypatch.setattr(core, "PROJECT_ROOT", local)
    monkeypatch.delenv("HERMES_INSTALL_ROOT", raising=False)
    assert core.run_janitor_update(["--check", "--branch", "main"]) == 0
    assert "up to date" in capsys.readouterr().out


def test_check_reads_only_the_forks_published_release(monkeypatch, tmp_path, capsys):
    commands, repositories = [], []
    sha = "a" * 40
    def fake_git(root, *args):
        commands.append(args)
        outputs = {
            ("config", "--get", "remote.origin.url"): "https://github.com/reck74/Janitor-Agent.git\n",
            ("ls-remote", "--exit-code", "origin", "refs/tags/v1.0.0", "refs/tags/v1.0.0^{}"): sha + "\trefs/tags/v1.0.0^{}\n",
            ("rev-parse", "HEAD"): sha + "\n",
        }
        return SimpleNamespace(returncode=0, stdout=outputs[args], stderr="")
    monkeypatch.setattr(core, "_git", fake_git)
    monkeypatch.setattr(core, "_published_tag", lambda repository: repositories.append(repository) or "v1.0.0")
    assert core._check_only(core.parse_update_args(["--check"]), tmp_path) == 0
    assert repositories == ["reck74/Janitor-Agent"]
    assert all("fetch" not in command and "upstream" not in command for command in commands)
    assert "v1.0.0" in capsys.readouterr().out


@pytest.mark.parametrize("flags", [["--check", "--set-channel", "main"], ["--unknown"], ["--branch", "-invalid"]])
def test_invalid_arguments_fail_before_any_work(flags):
    with pytest.raises(SystemExit) as error:
        core.parse_update_args(flags)
    assert error.value.code == 2


def test_update_flags_are_preserved():
    args = core.parse_update_args(["--branch", "release", "--backup", "--gateway", "--keep-stash", "--yes"])
    assert (args.branch, args.backup, args.gateway, args.keep_stash, args.yes) == ("release", True, True, True, True)


@pytest.fixture
def upstream(monkeypatch, tmp_path):
    package = ModuleType("hermes_cli")
    package.__path__ = []
    main, update, channel = (ModuleType("hermes_cli." + name) for name in ("main", "update_cmd", "update_channel"))
    main.PROJECT_ROOT = tmp_path
    main._sync_with_upstream_if_needed = lambda *a, **kw: "original-sync"
    update._push_synced_fork = lambda *a, **kw: "original-push"
    update._validate_critical_files_syntax = lambda root: (True, None, None)
    channel.default_channel = lambda root=None: "main"
    for name, module in (("main", main), ("update_cmd", update), ("update_channel", channel)):
        setattr(package, name, module)
        monkeypatch.setitem(sys.modules, "hermes_cli." + name, module)
    monkeypatch.setitem(sys.modules, "hermes_cli", package)
    monkeypatch.setattr(core, "_origin", lambda root: ("fork", "reck74/Janitor-Agent"))
    monkeypatch.setattr(core, "_UPSTREAM_CMD_UPDATE", None)
    monkeypatch.setattr(core, "_retarget_to_owning_install", lambda root: None)
    return main, update, channel


def test_adapter_keeps_upstream_command_and_restores_policy(upstream):
    main, update, channel = upstream
    original = (main._sync_with_upstream_if_needed, update._push_synced_fork, update._validate_critical_files_syntax, channel.default_channel)
    seen = []
    def command(args):
        seen.append(args)
        assert main._sync_with_upstream_if_needed() is False
        assert update._push_synced_fork() is None
        assert channel.default_channel(main.PROJECT_ROOT) == "stable"
        assert update._validate_critical_files_syntax._janitor_fork_wrapper
        return 17
    main.cmd_update = command
    args = core.parse_update_args(["--keep-stash", "--backup"])
    assert core.run_janitor_update(args) == 17
    assert seen == [args]
    assert original == (main._sync_with_upstream_if_needed, update._push_synced_fork, update._validate_critical_files_syntax, channel.default_channel)


def test_adapter_preserves_upstream_receipt_failure_exit(upstream):
    main, update, channel = upstream
    original = update._validate_critical_files_syntax
    def command(args):
        raise SystemExit(23)
    main.cmd_update = command
    with pytest.raises(SystemExit) as error:
        core.run_janitor_update([])
    assert error.value.code == 23
    assert update._validate_critical_files_syntax is original
    assert channel.default_channel() == "main"


def test_official_origin_is_refused(checkout, monkeypatch):
    _, _, local = checkout
    git(local, "remote", "set-url", "origin", "https://github.com/NousResearch/hermes-agent.git")
    monkeypatch.setattr(core, "PROJECT_ROOT", local)
    monkeypatch.delenv("HERMES_INSTALL_ROOT", raising=False)
    assert core.run_janitor_update(["--check", "--branch", "main"]) == 1


def test_saved_main_subscription_is_honored(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    root = tmp_path / "checkout"
    (home / "config.yaml").write_text(f"update:\n  installs:\n    id:\n      path: {root}\n      channel: main\n")
    monkeypatch.setenv("HERMES_HOME", str(home))
    assert core._configured_channel(root) == "main"


def test_legacy_recovery_stash_blocks_update_without_losing_work(upstream, tmp_path, monkeypatch):
    main, _, _ = upstream
    home = tmp_path / "profile"
    home.mkdir()
    marker = home / "update-incomplete.json"
    contents = json.dumps({"stash_ref": "b" * 40, "failed_step": "node_deps", "timestamp": "2026-08-17T00:00:00Z"})
    marker.write_text(contents)
    monkeypatch.setenv("HERMES_HOME", str(home))
    main.cmd_update = lambda args: pytest.fail("legacy recovery was bypassed")
    assert core.run_janitor_update([]) == 1
    assert marker.read_text() == contents


def test_owning_install_relaunch_keeps_janitor_entry(monkeypatch, tmp_path):
    owner = tmp_path / "owner"
    owner.mkdir()
    (owner / "janitor_cli.py").write_text("pass\n")
    module = ModuleType("hermes_cli.update_owning_install")
    module.owning_install_root = lambda root: owner
    monkeypatch.setitem(sys.modules, "hermes_cli.update_owning_install", module)
    monkeypatch.setattr(sys, "argv", ["janitor", "update", "--backup"])
    seen = []
    monkeypatch.setattr(subprocess, "call", lambda argv, **kwargs: seen.append((argv, kwargs)) or 19)
    with pytest.raises(SystemExit) as error:
        core._retarget_to_owning_install(tmp_path)
    assert error.value.code == 19
    assert seen[0][0] == [sys.executable, str(owner / "janitor_cli.py"), "update", "--backup"]
    assert seen[0][1]["env"]["PYTHONPATH"] == str(owner)


def test_native_release_pin_uses_published_exact_tag(monkeypatch, tmp_path):
    from hermes_cli import source_releases
    sha = "a" * 40
    monkeypatch.setenv("_JANITOR_UPDATE_TARGET_TAG", "v1.2.3")
    monkeypatch.setattr(core, "_origin", lambda root: ("git@github.com:owner/janitor.git", "owner/janitor"))
    urls = []
    def response(url):
        urls.append(url)
        return {"draft": False, "prerelease": False, "tag_name": "v1.2.3"} if "/releases/tags/" in url else {"sha": sha}
    monkeypatch.setattr(source_releases, "_json", response)
    monkeypatch.setattr(core, "_git", lambda root, *args: subprocess.CompletedProcess(args, 0, f"{sha}\trefs/tags/v1.2.3\n", ""))
    target = core._pinned_release_target(source_releases, tmp_path)
    assert target.commit == sha and target.version == "1.2.3" and target.repository == "owner/janitor"
    assert all("latest" not in url for url in urls)


@pytest.mark.parametrize("tag", ["main", "v1.2.3-rc1", "--upload-pack=x", "v01.2.3"])
def test_native_release_pin_refuses_invalid_tags(monkeypatch, tmp_path, tag):
    monkeypatch.setenv("_JANITOR_UPDATE_TARGET_TAG", tag)
    with pytest.raises(ValueError, match="Invalid native"):
        core._pinned_release_target(None, tmp_path)


def test_native_release_pin_refuses_changed_tag(monkeypatch, tmp_path):
    from hermes_cli import source_releases
    monkeypatch.setenv("_JANITOR_UPDATE_TARGET_TAG", "v1.2.3")
    monkeypatch.setattr(core, "_origin", lambda root: ("git@github.com:owner/janitor.git", "owner/janitor"))
    monkeypatch.setattr(source_releases, "_json", lambda url: {"draft": False, "prerelease": False, "tag_name": "v1.2.3"} if "/releases/" in url else {"sha": "a" * 40})
    monkeypatch.setattr(core, "_git", lambda root, *args: subprocess.CompletedProcess(args, 0, f"{'b' * 40}\trefs/tags/v1.2.3\n", ""))
    with pytest.raises(ValueError, match="does not match"):
        core._pinned_release_target(source_releases, tmp_path)


def test_real_entry_check_leaves_profile_and_checkout_byte_identical(checkout, tmp_path):
    _, writer, local = checkout
    (writer / 'later').write_text('new upstream-independent fork commit\n')
    git(writer, 'add', '.'); git(writer, 'commit', '-m', 'next fork version'); git(writer, 'push', 'origin', 'main')
    home = tmp_path / 'home'; profile = home / 'profiles/work'; profile.mkdir(parents=True)
    (home / 'active_profile').write_text('work\n')
    (profile / 'config.yaml').write_text('memory: {provider: honcho}\n')
    (profile / '.env').write_text('MINIMAX_API_KEY="literal-only"\n')
    (local / 'local-work').write_text('preserve local changes\n')
    def snapshot(root):
        return {str(p.relative_to(root)): (p.read_bytes(), p.stat().st_mtime_ns)
                for p in root.rglob('*') if p.is_file()}
    before_home, before_git = snapshot(home), snapshot(local)
    root = Path(core.__file__).resolve().parent
    env = dict(os.environ, HERMES_HOME=str(home), JANITOR_HOME=str(home), HOME=str(tmp_path),
               HERMES_INSTALL_ROOT=str(local), PYTHONDONTWRITEBYTECODE='1', HERMES_DISABLE_LAZY_INSTALLS='1')
    result = subprocess.run([sys.executable, str(root / 'janitor_cli.py'), 'update', '--check', '--branch', 'main'],
                            env=env, capture_output=True, text=True, timeout=20, check=False)
    assert result.returncode == 0, result.stderr
    assert 'update available' in result.stdout
    assert snapshot(home) == before_home
    assert snapshot(local) == before_git
