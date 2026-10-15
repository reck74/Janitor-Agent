"""Janitor Desktop distribution seams must never select the Hermes builder."""
import argparse
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from janitor_ext import desktop


def fixture_root(tmp_path):
    (tmp_path / 'janitor_ext').mkdir()
    (tmp_path / 'janitor_ext/release.json').write_text(json.dumps({'janitorVersion': '1.0.0'}))
    release = tmp_path / 'apps/desktop/release'
    release.mkdir(parents=True)
    return tmp_path, release


def publish_artifact(release):
    target = release / 'janitor-desktop-1.0.0-linux-x86_64.AppImage'
    target.write_text('fixture')
    target.chmod(0o755)
    return target


def test_janitor_artifact_selects_own_version_and_architecture(tmp_path, monkeypatch):
    root, release = fixture_root(tmp_path)
    monkeypatch.setattr(desktop.platform, 'machine', lambda: 'x86_64')
    (release / 'Hermes-1.0.0-linux-x86_64.AppImage').write_text('foreign')
    (release / 'janitor-desktop-99.0.0-linux-x86_64.AppImage').write_text('wrong version')
    assert desktop._artifact(root) is None
    target = publish_artifact(release)
    assert desktop._artifact(root) == target
    monkeypatch.setattr(desktop.platform, 'machine', lambda: 'aarch64')
    assert desktop._artifact(root) is None


def test_janitor_native_transaction_skips_source_desktop_build(monkeypatch):
    monkeypatch.delenv('_JANITOR_SKIP_DESKTOP_BUILD', raising=False)
    def forbidden(*args, **kwargs):
        raise AssertionError('AppImage worker must not build another Desktop product')
    monkeypatch.setattr(desktop, '_run_overlay', forbidden)
    desktop.build_desktop_product(Path('/no-runtime-mutation'), {'_JANITOR_SKIP_DESKTOP_BUILD': '1'}, forbidden)


def test_janitor_cli_skip_build_launches_appimage_without_preparing_dependencies(tmp_path, monkeypatch):
    root, release = fixture_root(tmp_path)
    target = publish_artifact(release)
    monkeypatch.setattr(desktop.sys, 'platform', 'linux')
    monkeypatch.setattr(desktop.platform, 'machine', lambda: 'x86_64')
    monkeypatch.setattr('janitor_ext.startup.janitor_home', lambda: tmp_path / 'profile')
    from hermes_cli import main_desktop
    monkeypatch.setattr(main_desktop, '_desktop_launch_env', lambda args: ({'HERMES_DESKTOP_CWD': args.cwd}, ['--disable-gpu']))
    monkeypatch.setattr(main_desktop, '_explicit_profile_args', lambda: ['--profile', 'alpha'])
    calls = []
    monkeypatch.setattr(desktop.subprocess, 'Popen', lambda command, **kwargs: calls.append((command, kwargs)))
    main = SimpleNamespace(PROJECT_ROOT=root)
    desktop.install_cli_adapter(main)
    main.cmd_gui(argparse.Namespace(skip_build=True, cwd=str(tmp_path / 'project')))
    assert calls[0][0] == [str(target), '--disable-gpu', '--profile', 'alpha']
    assert calls[0][1]['env']['JANITOR_HOME'] == str(tmp_path / 'profile')
    assert calls[0][1]['env']['HERMES_DESKTOP_CWD'] == str(tmp_path / 'project')
    assert calls[0][1]['start_new_session'] is True


def test_janitor_cli_build_only_serializes_prepare_and_own_builder(tmp_path, monkeypatch):
    root, release = fixture_root(tmp_path)
    monkeypatch.setattr(desktop.sys, 'platform', 'linux')
    monkeypatch.setattr(desktop.platform, 'machine', lambda: 'x86_64')
    from hermes_cli import source_build, desktop_build_lock
    order = []
    class Lock:
        def __init__(self, project_root):
            assert project_root == root
        def acquire(self, **kwargs):
            order.append('lock')
            return True
        def release(self):
            order.append('unlock')
    monkeypatch.setattr(desktop_build_lock, 'DesktopBuildLock', Lock)
    monkeypatch.setattr(source_build, 'source_build_env', lambda **kwargs: {'PATH': 'fixture'})
    monkeypatch.setattr(source_build, 'prepare_source_dependencies', lambda *args, **kwargs: order.append('prepare'))
    def build(project_root, script, **kwargs):
        assert script == 'apps/desktop/janitor/build.mjs'
        order.append('build')
        publish_artifact(release)
    monkeypatch.setattr(source_build, 'run_source_script', build)
    monkeypatch.setattr(desktop.subprocess, 'Popen', lambda *args, **kwargs: pytest.fail('build-only launched app'))
    main = SimpleNamespace(PROJECT_ROOT=root)
    desktop.install_cli_adapter(main)
    main.cmd_desktop(argparse.Namespace(build_only=True))
    assert order == ['lock', 'prepare', 'build', 'unlock']
