"""Janitor entrypoint, home/profile isolation and product-version contracts."""
from __future__ import annotations

import builtins
import json
import os
from pathlib import Path
import subprocess
import sys
import tomllib

import pytest

import janitor_cli
from janitor_ext.startup import janitor_home, prepare_environment

ROOT = Path(__file__).resolve().parents[1]


def test_packaging_registers_janitor_and_extension_package():
    data = tomllib.loads((ROOT / "pyproject.toml").read_text())
    assert data["project"]["scripts"]["janitor"] == "janitor_cli:main"
    assert "janitor_ext" in data["tool"]["setuptools"]["packages"]["find"]["include"]
    assert "release.json" in data["tool"]["setuptools"]["package-data"]["janitor_ext"]
    # Root modules use upstream's build-time discovery, not a drifting list.
    assert "py-modules" not in data["tool"]["setuptools"]


def test_default_home_is_janitor(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.delenv("HERMES_HOME", raising=False)
    monkeypatch.delenv("JANITOR_HOME", raising=False)
    assert janitor_home() == tmp_path / ".janitor"


def test_explicit_profile_home_is_preserved(tmp_path, monkeypatch):
    home = tmp_path / "profiles" / "work"
    monkeypatch.setenv("HERMES_HOME", str(home))
    monkeypatch.setenv("JANITOR_HOME", str(tmp_path / "other-root"))
    assert prepare_environment() == home
    assert os.environ["HERMES_HOME"] == str(home)


def test_profile_selected_before_update_intercept(tmp_path, monkeypatch):
    profile = tmp_path / "profiles" / "work"
    profile.mkdir(parents=True)
    (profile / "config.yaml").write_text("memory: {provider: honcho}\n")
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    monkeypatch.setattr(sys, "argv", ["janitor", "--profile", "Work", "update", "--check"])
    import janitor_update_bootstrap
    seen = []
    monkeypatch.setattr(janitor_update_bootstrap, "run_update", lambda argv: seen.append((argv, os.environ["HERMES_HOME"])) or 9)
    assert janitor_cli.main() == 9
    assert seen == [(["--check"], str(profile))]


def test_update_intercept_does_not_import_application(monkeypatch):
    import janitor_update_bootstrap
    original = builtins.__import__
    def guarded(name, *args, **kwargs):
        if name == "cli" or name == "run_agent" or name.startswith("hermes_cli"):
            pytest.fail(f"early update imported {name}")
        return original(name, *args, **kwargs)
    monkeypatch.setattr(builtins, "__import__", guarded)
    monkeypatch.setattr(sys, "argv", ["janitor", "update", "--check", "--backup"])
    seen = []
    monkeypatch.setattr(janitor_update_bootstrap, "run_update", lambda argv: seen.append(argv) or 0)
    assert janitor_cli.main() == 0
    assert seen == [["--check", "--backup"]]


def test_unknown_profile_does_not_fall_back_to_default(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    monkeypatch.setattr(sys, "argv", ["janitor", "-p", "missing", "--version"])
    assert janitor_cli.main() == 1
    assert "does not exist" in capsys.readouterr().err
    assert not (tmp_path / "profiles" / "missing").exists()


@pytest.mark.parametrize("module", ["janitor_cli", "acp_adapter.entry"])
def test_version_fast_path_is_independent_of_credentials(tmp_path, module):
    env = dict(os.environ, HERMES_HOME=str(tmp_path / "home"), HOME=str(tmp_path), USERPROFILE=str(tmp_path))
    for name in list(env):
        if name.endswith(("_API_KEY", "_TOKEN", "_SECRET", "_PASSWORD")):
            env.pop(name)
    result = subprocess.run([sys.executable, "-m", module, "--version"],
                            env=env, capture_output=True, text=True, timeout=15, check=False)
    assert result.returncode == 0, result.stderr
    metadata = json.loads((ROOT / "janitor_ext" / "release.json").read_text())
    assert f"THE JANITOR v{metadata['janitorVersion']}" in result.stdout  # AGENTS.md #12
    assert f"Hermes {metadata['upstreamVersion']}" in result.stdout
    assert metadata["upstreamRef"][:12] in result.stdout
    commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True,
                            text=True, timeout=15, check=True).stdout.strip()
    assert commit[:12] in result.stdout
    assert not (tmp_path / "home").exists()


def test_version_metadata_is_separate_from_engine_identity():
    from janitor_version import release_metadata, display_version
    data = release_metadata()
    assert data["janitorVersion"] != data["upstreamVersion"]
    assert display_version() == data["janitorVersion"]
    assert display_version("0.20.1+janitor.1") == "0.20.1-janitor.1"
    assert len(data["upstreamRef"]) == 40


def test_cli_wrapper_is_used_by_upstream_dispatch():
    janitor_cli._install_janitor_runtime()
    import cli
    assert cli.HermesCLI is janitor_cli.JanitorCLI
    assert cli.HermesCLI.__mro__[1].__name__ == "HermesCLI"
    instance = cli.HermesCLI.__new__(cli.HermesCLI)
    assert instance.force_skin is True
    assert instance.get_skin_name() == "sentry-janitor"


def test_honcho_repair_commands_do_not_invoke_runtime_gate(monkeypatch):
    import hermes_cli.main as main_module
    monkeypatch.setattr(janitor_cli, "_install_janitor_runtime", lambda: None)
    monkeypatch.setattr(janitor_cli, "_owasp_honcho_fail_safe", lambda: pytest.fail("repair command was blocked"))
    monkeypatch.setattr(sys, "argv", ["janitor", "honcho", "setup"])
    monkeypatch.setattr(main_module, "main", lambda: 0)
    assert janitor_cli.main() == 0


def test_source_stamp_and_fresh_child_keep_engine_compatibility(tmp_path, monkeypatch):
    from hermes_cli.source_stamp import write_source_stamp
    repo = tmp_path / "repo"
    (repo / "janitor_ext").mkdir(parents=True)
    metadata = json.loads((ROOT / "janitor_ext" / "release.json").read_text())
    (repo / "janitor_ext" / "release.json").write_text(json.dumps(metadata))
    (repo / "pyproject.toml").write_text('[tool.hermes.distribution]\nidentity-provider = "janitor_ext.version:distribution_identity"\n')
    for command in (["init", "-q"], ["config", "user.name", "Janitor Test"],
                    ["config", "user.email", "test@example.invalid"], ["add", "."],
                    ["commit", "-qm", "product release"], ["tag", "v" + metadata["janitorVersion"]]):
        subprocess.run(["git", *command], cwd=repo, capture_output=True, text=True, check=True)
    stamp = write_source_stamp(repo)
    assert stamp["baseVersion"] == metadata["upstreamVersion"]
    assert stamp["displayVersion"] == stamp["productVersion"] == metadata["janitorVersion"]
    assert stamp["upstreamRef"] == metadata["upstreamRef"]
    code = (
        "import json; from hermes_cli.source_stamp import write_source_stamp; "
        "from hermes_cli.version_info import get_version_info; "
        "from hermes_cli.plugins_manifest import requires_hermes_error; "
        "from pathlib import Path; import os; "
        "write_source_stamp(Path(os.environ['HERMES_INSTALL_ROOT'])); "
        "i=get_version_info(); print(json.dumps([i.base_version,i.display_version,i.product_version,"
        "requires_hermes_error({'requires_hermes':'>=0.22,<0.23'})]))"
    )
    env = dict(os.environ, HERMES_INSTALL_ROOT=str(repo), PYTHONPATH=str(ROOT))
    result = subprocess.run([sys.executable, "-c", code], cwd=tmp_path, env=env,
                            capture_output=True, text=True, timeout=20, check=False)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout.splitlines()[-1]) == [metadata["upstreamVersion"], metadata["janitorVersion"], metadata["janitorVersion"], None]


def test_sticky_profile_applies_to_import_light_update(tmp_path, monkeypatch):
    profile = tmp_path / 'profiles/work'; profile.mkdir(parents=True)
    (profile / 'config.yaml').write_text('memory: {provider: honcho}\n')
    (tmp_path / 'active_profile').write_text('work\n')
    monkeypatch.setenv('HERMES_HOME', str(tmp_path))
    assert prepare_environment(['update', '--check']) == profile


def test_gateway_profile_selection_remains_upstream_owned(tmp_path, monkeypatch):
    profile = tmp_path / 'profiles/work'; profile.mkdir(parents=True)
    (profile / 'config.yaml').write_text('memory: {provider: honcho}\n')
    (tmp_path / 'active_profile').write_text('work\n')
    monkeypatch.setenv('HERMES_HOME', str(tmp_path))
    monkeypatch.setenv('HERMES_GATEWAY_EXTERNAL_SUPERVISOR', '1')
    # Stable main has supervisor/SSH-specific exceptions to sticky selection.
    assert prepare_environment(['gateway', 'run']) == tmp_path


def test_shell_launcher_preserves_explicit_home_and_profile_flags(tmp_path):
    from pm.shell import bash
    shell = bash()
    assert shell is not None, 'The PM Bash toolchain must be available'
    root = tmp_path / 'source'; (root / 'scripts').mkdir(parents=True)
    launcher = root / 'scripts/janitor'; launcher.write_text((ROOT / 'scripts/janitor').read_text(), newline='\n'); launcher.chmod(0o755)
    backend = root / '.hermes/bin/hermes'; backend.parent.mkdir(parents=True)
    backend.write_text('#!/bin/sh\nprintf "%s\n" "$HERMES_HOME" "$@"\n', newline='\n'); backend.chmod(0o755)
    profile = tmp_path / 'custom/profiles/work'
    env = dict(os.environ, HERMES_HOME=str(profile), JANITOR_HOME=str(tmp_path / 'default'))
    result = subprocess.run([shell, launcher.as_posix(), '--profile', 'work', 'config', 'path'], env=env,
                            capture_output=True, text=True, timeout=10, check=False)
    assert result.returncode == 0
    assert result.stdout.splitlines() == [str(profile), '--run-module', 'janitor_cli', '--profile', 'work', 'config', 'path']


def test_real_cli_profile_dispatch_and_honcho_gate_are_isolated(tmp_path):
    work = tmp_path / 'profiles/work'; work.mkdir(parents=True)
    config = 'memory: {provider: honcho}\nmodel: {provider: minimax, default: MiniMax-M2.7}\n'
    (tmp_path / 'config.yaml').write_text(config)
    (work / 'config.yaml').write_text(config)
    (tmp_path / 'active_profile').write_text('work\n')
    env = dict(os.environ, HERMES_HOME=str(tmp_path), JANITOR_HOME=str(tmp_path), HOME=str(tmp_path), USERPROFILE=str(tmp_path),
               HERMES_DISABLE_LAZY_INSTALLS='1', PYTHONPATH=str(ROOT), PYTEST_CURRENT_TEST='janitor-entry-contract')
    for name in list(env):
        if name.endswith(('_API_KEY', '_TOKEN', '_SECRET', '_PASSWORD')): env.pop(name)
    def invoke(*args):
        return subprocess.run([sys.executable, str(ROOT / 'janitor_cli.py'), *args], env=env,
                              capture_output=True, text=True, timeout=20, check=False)
    result = invoke('--profile', 'work', 'config', 'path')
    assert result.returncode == 0, result.stderr
    assert str(work / 'config.yaml') in result.stdout
    result = invoke('config', 'path')
    assert result.returncode == 0 and str(work / 'config.yaml') in result.stdout
    assert invoke('--help').returncode == 0
    assert invoke('--profile', 'work', 'setup', '--help').returncode == 0
    result = invoke('--profile', 'work', 'chat', '-q', 'hello')
    assert result.returncode == 1
    assert 'Honcho memory plugin is missing' in result.stderr
