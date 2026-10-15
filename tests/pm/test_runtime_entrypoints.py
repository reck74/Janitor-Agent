"""Bootstrap entrypoints must hand dependency operations to PM's own interpreter."""
import json
from types import SimpleNamespace

import pytest


def test_cli_dispatches_before_calling_engine(monkeypatch):
    from pm import cli, runtime

    calls = []
    monkeypatch.setattr(runtime, "is_runtime", lambda: False)
    monkeypatch.setattr(runtime, "run_cli", lambda argv: calls.append(argv) or 19)
    monkeypatch.setattr(cli, "cmd_install", lambda args: pytest.fail("caller imported the engine"))
    argv = ["install", "venv"]
    assert cli.main(argv) == 19
    assert calls == [argv]


def test_cli_runtime_executes_without_redispatch(monkeypatch):
    from pm import cli, runtime

    monkeypatch.setattr(runtime, "is_runtime", lambda: True)
    monkeypatch.setattr(runtime, "run_cli", lambda argv: pytest.fail("recursive PM dispatch"))
    monkeypatch.setattr(cli, "cmd_install", lambda args: 7 if args.names == ["venv"] else 1)
    assert cli.main(["install", "venv"]) == 7


def test_ci_dependency_phase_uses_isolated_runtime(tmp_path, monkeypatch):
    from pm import client
    from pm import paths
    from scripts.ci import setup_toolchain

    project = tmp_path / "source"
    project.mkdir()
    (project / "pyproject.toml").write_text('[project]\nname="ci-proof"\nversion="1"\n'
                                            '[dependency-groups]\ndev=[]\ntest=[]\n')
    monkeypatch.setattr(paths, "repo_root", lambda: project)
    monkeypatch.setattr(client, "is_runtime", lambda: False)
    calls = []

    def request(operation, arguments, **kwargs):
        calls.append((operation, arguments))
        return str(tmp_path / "test-environment/bin/python") if operation == "ensure_project_environment" else None

    monkeypatch.setattr(client, "_request", request)
    monkeypatch.setattr(setup_toolchain, "python3_alias", lambda _: None)
    monkeypatch.setattr(setup_toolchain, "file_commands", lambda *args: None)
    monkeypatch.setattr(setup_toolchain, "add_path", lambda *args: None)
    setup_toolchain.dependencies(SimpleNamespace(home=tmp_path, extras=[], test_environment=True, toolchain="all"))
    assert [operation for operation, _ in calls] == ["check_project_lock", "ensure_project_environment"]
    assert calls[0][1]["source"] == str(project)
    assert calls[1][1]["extras"] == []
    assert calls[1][1]["groups"] == ["dev", "test"]
    assert all(arguments["explicit"] for _, arguments in calls)


def test_store_root_reads_executing_trees_canonical_install_stamp(tmp_path, monkeypatch):
    from pm import environments, paths

    project = tmp_path / "source"
    project.mkdir()
    package = tmp_path / "package"
    package.mkdir()
    runtime = tmp_path / "packaged-tools"
    (package / "install-stamp.json").write_text(json.dumps({"runtimeDir": str(runtime)}))
    monkeypatch.setattr(paths, "repo_root", lambda: project)
    monkeypatch.setenv("HERMES_INSTALL_ROOT", str(package))
    monkeypatch.delenv("HERMES_RUNTIME_DIR", raising=False)

    assert environments.store_root(project) == runtime


@pytest.mark.parametrize("distribution", ["nix", "docker"])
def test_packaged_runtime_uses_explicit_stamp_without_tool_downloads(tmp_path, monkeypatch, distribution):
    from pm import runtime, paths

    monkeypatch.setattr("pm._uv._toolchain", lambda **kw: pytest.fail("packaged PM tried to download tools"))
    project = tmp_path / "app"
    project.mkdir()
    monkeypatch.setattr(paths, "repo_root", lambda: project)
    install_root = tmp_path / "package"
    install_root.mkdir()
    monkeypatch.setenv("HERMES_INSTALL_ROOT", str(install_root))
    pm = install_root / "pm-runtime"
    site = pm / "site-packages"
    site.mkdir(parents=True)
    python = install_root / "python"
    python.touch()
    (pm / "pm-runtime.json").write_text(json.dumps({"python": str(python), "sitePackages": str(site)}))
    stamp = {"distribution": distribution, "pmRuntime": str(pm)}
    (install_root / "install-stamp.json").write_text(json.dumps(stamp))
    command = runtime.runtime_command(project / "worker.py", ["argument"])
    assert command[:4] == [str(python), "-I", "-S", "-B"]
    assert str(site) in command
    assert command[-2:] == [str(project / "worker.py"), "argument"]
    (pm / "pm-runtime.json").unlink()
    from pm.package import InstallError
    with pytest.raises(InstallError, match="PM runtime"):
        runtime.runtime_command(project / "worker.py")


@pytest.mark.parametrize("record", ["valid", "missing", "relative", "other-checkout", "deleted"])
def test_generation_install_owner_requires_its_recorded_checkout(tmp_path, monkeypatch, record):
    from pm import environments, paths

    owner = tmp_path / "checkout"
    owner.mkdir()
    state = tmp_path / "home" / "installs" / environments.install_key(owner)
    generated = state / "environments" / ("a" * 32) / "workspace"
    generated.mkdir(parents=True)
    inputs = state / "inputs"
    inputs.mkdir()
    value = str(owner)
    if record == "relative":
        value = "checkout"
    elif record == "other-checkout":
        other = tmp_path / "other"
        other.mkdir()
        value = str(other)
    elif record == "deleted":
        owner.rmdir()
    if record != "missing":
        (inputs / ".project-root").write_text(value, encoding="utf-8")
    monkeypatch.setattr(paths, "repo_root", lambda: generated)
    monkeypatch.delenv("HERMES_INSTALL_ROOT", raising=False)

    assert paths.install_root() == (owner if record == "valid" else generated)
    assert paths.repo_root() == generated, "ownership must not replace executing source"
    expected = owner if record == "valid" else generated
    assert paths.install_stamp_path(generated) == expected / "install-stamp.json"


@pytest.mark.parametrize("entrypoint", ["hermes", "janitor"])
def test_workspace_version_reports_owner_without_importing_live_checkout(tmp_path, entrypoint):
    import os
    from pathlib import Path
    import subprocess
    import sys

    from pm import environments, workspace

    owner = Path(__file__).resolve().parents[2]
    state = tmp_path / "installs" / environments.install_key(owner)
    generated = state / "environments" / ("b" * 32) / "workspace"
    generated.parent.mkdir(parents=True)
    workspace._generate_pyproject([], generated, source=owner)
    environments.record_activation_inputs(state / "inputs", {}, owner, test_environment=False)
    env = dict(os.environ)
    env.pop("HERMES_INSTALL_ROOT", None)
    code = (
        "import sys; sys.path.insert(0, sys.argv[1]); "
        "from pm.paths import repo_root; print('Executing source:', repo_root()); "
    )
    if entrypoint == "hermes":
        code += ("from hermes_cli._startup_fast import print_fast_version_info; "
                 "print_fast_version_info(check_updates=False)")
    else:
        code += "sys.argv=['janitor', '--version']; import janitor_cli; sys.exit(janitor_cli.main())"
    cp = subprocess.run([sys.executable, "-I", "-c", code, str(generated)],
                        cwd=tmp_path, env=env, text=True, capture_output=True,
                        timeout=60, check=False)
    assert cp.returncode == 0, cp.stderr
    assert f"Install directory: {owner}" in cp.stdout
    if entrypoint == "hermes":
        assert "Install method: git" in cp.stdout
    assert f"Executing source: {generated}" in cp.stdout
