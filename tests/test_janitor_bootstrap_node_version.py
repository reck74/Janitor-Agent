"""Node acquisition belongs to PM and its pin must satisfy every workspace engine.

The original regression installed Node20 below the application engine floor.
The modern contract follows pm/lock.json rather than freezing Node22 or nvm.
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

from packaging.specifiers import SpecifierSet
from packaging.version import Version
import pytest

ROOT = Path(__file__).resolve().parents[1]
BOOTSTRAP = ROOT / "scripts/bootstrap.sh"


def _satisfies(version, engines):
    """Evaluate the release-only caret and comparator forms declared by this repo."""
    selected = Version(version)
    for alternative in engines.split("||"):
        alternative = alternative.strip()
        if alternative.startswith("^"):
            minimum = Version(alternative[1:])
            upper = f"{minimum.major + 1}.0.0" if minimum.major else f"0.{minimum.minor + 1}.0"
            alternative = f">={minimum},<{upper}"
        if selected in SpecifierSet(alternative):
            return True
    return False


def test_pm_node_pin_satisfies_all_workspace_engines():
    root = json.loads((ROOT / "package.json").read_text())
    pin = json.loads((ROOT / "pm/lock.json").read_text())["packages"]["node"]["version"]
    manifests = [ROOT / "package.json"]
    for pattern in root["workspaces"]:
        manifests.extend(path / "package.json" for path in ROOT.glob(pattern))
    for path in manifests:
        manifest = json.loads(path.read_text())
        constraint = manifest.get("engines", {}).get("node")
        if constraint:
            assert _satisfies(pin, constraint), f"PM Node{pin} violates {path.relative_to(ROOT)}: {constraint}"


def test_engine_or_caret_ranges_reject_the_original_subfloor_regression():
    assert not _satisfies("20.19.0", "^22.22.0 || ^24.11.0 || >=26.0.0")
    assert _satisfies("22.22.0", "^22.22.0 || ^24.11.0 || >=26.0.0")
    assert not _satisfies("23.0.0", "^22.22.0 || ^24.11.0 || >=26.0.0")
    assert _satisfies("26.7.0", "^22.22.0 || ^24.11.0 || >=26.0.0")


@pytest.mark.skipif(sys.platform != "linux", reason="Linux bootstrap stage protocol")
def test_products_stage_uses_pm_without_global_node_uv_or_nvm(tmp_path):
    source = tmp_path / "source"; (source / "scripts").mkdir(parents=True)
    shutil.copy2(BOOTSTRAP, source / "scripts/bootstrap.sh")
    (source / "janitor_cli.py").write_text("# local bootstrap source marker\n")
    (source / "scripts/install.sh").write_text(f"bootstrap_python() {{ boot_py={str(sys.executable)!r}; }}\n")
    package = source / "hermes_cli"; package.mkdir(); (package / "__init__.py").touch()
    calls = tmp_path / "calls"
    (package / "_launchers.py").write_text(
        "import os\nfrom pathlib import Path\ndef ensure_install_launchers(root, target):\n"
        "    Path(os.environ['JANITOR_TEST_CALLS']).write_text(str(target)+'\\n')\n"
        "    return {'hermes': str(target / 'hermes')}\n")
    launcher = source / "scripts/janitor"
    launcher.write_text('#!/usr/bin/env bash\nprintf "%s\\n" "$*" >> "$JANITOR_TEST_CALLS"\n')
    launcher.chmod(0o755)
    binary = tmp_path / "bin"; binary.mkdir()
    # No global Node, npm, uv or nvm is visible; only shell primitives the wrapper needs.
    for name in ("bash", "dirname", "rm"):
        (binary / name).symlink_to(shutil.which(name))
    env = {"PATH": str(binary), "HOME": str(tmp_path / "home"), "JANITOR_TEST_CALLS": str(calls)}
    result = subprocess.run([str(binary / "bash"), str(source / "scripts/bootstrap.sh"), "--dir", str(source),
                             "--stage", "products", "--non-interactive", "--json"],
                            env=env, text=True, capture_output=True, check=False, timeout=20)
    assert result.returncode == 0, result.stdout + result.stderr
    assert calls.read_text().splitlines() == [str(source / ".hermes/bin"),
        "--run-module janitor_ext.install --publish-only", "--run-module janitor_ext.products"]
    assert json.loads(result.stdout.splitlines()[-1])["ok"] is True


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX bootstrap syntax")
def test_bootstrap_passes_bash_syntax_check():
    result = subprocess.run(["bash", "-n", str(BOOTSTRAP)], capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr

@pytest.mark.skipif(sys.platform == "win32", reason="POSIX bootstrap stage routing")
@pytest.mark.parametrize(("stage", "arguments", "resolves_release"), [
    ("repository", [], True),
    ("repository", ["--commit", "a" * 40], False),
    ("repository", ["--branch", "development"], False),
    ("config", [], False),
    ("config", ["--non-interactive", "--honcho-mode", "cloud"], False),
    ("setup", [], False),
    ("profile", [], False),
    ("complete", [], False),
    ("gateway", [], False),
])
def test_bootstrap_stage_routes_do_not_require_extglob(tmp_path, stage, arguments, resolves_release):
    source, env, calls, lookup = _stage_routing_fixture(tmp_path)
    result = subprocess.run(["bash", str(source / "scripts/bootstrap.sh"), "--dir", str(source),
                             "--stage", stage, "--json", *arguments],
                            env=env, text=True, capture_output=True, check=False, timeout=10)
    assert result.returncode == 0, result.stdout + result.stderr
    assert lookup.exists() is resolves_release
    assert calls.exists() is (stage != "gateway"), result.stdout + result.stderr
    if "--honcho-mode" in arguments:
        assert calls.read_text().strip() == "--non-interactive --honcho-mode cloud"
    if resolves_release:
        assert "--commit " + "a" * 40 in calls.read_text()
    assert json.loads(result.stdout.splitlines()[-1])["ok"] is True


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX bootstrap stage routing")
@pytest.mark.parametrize("failure", ["missing-release", "installer"])
def test_bootstrap_stage_routes_preserve_failures(tmp_path, failure):
    source, env, calls, _lookup = _stage_routing_fixture(tmp_path)
    env["JANITOR_TEST_STABLE"] = "missing" if failure == "missing-release" else "a" * 40
    env["JANITOR_TEST_INSTALL_EXIT"] = "17"
    result = subprocess.run(["bash", str(source / "scripts/bootstrap.sh"), "--dir", str(source),
                             "--stage", "repository", "--json"],
                            env=env, text=True, capture_output=True, check=False, timeout=10)
    assert result.returncode == (1 if failure == "missing-release" else 17), result.stdout + result.stderr
    if failure == "missing-release":
        assert not calls.exists()
        assert "stable v1.0.0 is unavailable" in result.stderr
    else:
        assert json.loads(result.stdout.splitlines()[-1])["ok"] is False


def _stage_routing_fixture(tmp_path):
    source = tmp_path / "source"
    scripts = source / "scripts"
    scripts.mkdir(parents=True)
    shutil.copy2(BOOTSTRAP, scripts / "bootstrap.sh")
    (source / "janitor_cli.py").write_text("# local installer marker\n")
    calls, lookup = tmp_path / "calls", tmp_path / "lookup"
    for name in ("install.sh", "janitor-install.sh", "janitor"):
        target = scripts / name
        target.write_text('#!/bin/sh\nprintf "%s\\n" "$*" >> "$JANITOR_TEST_CALLS"\n'
                          'exit "${JANITOR_TEST_INSTALL_EXIT:-0}"\n')
        target.chmod(0o755)
    binary = tmp_path / "bin"
    binary.mkdir()
    git = binary / "git"
    git.write_text('#!/bin/sh\nprintf "%s\\n" "$*" > "$JANITOR_TEST_LOOKUP"\n'
                   'printf "%s\\trefs/tags/v1.0.0\\n" "$JANITOR_TEST_STABLE"\n')
    git.chmod(0o755)
    home = tmp_path / "home"
    home.mkdir()
    env = {**os.environ, "PATH": str(binary) + os.pathsep + os.environ["PATH"],
           "HOME": str(home), "JANITOR_HOME": str(home / ".janitor"), "HERMES_HOME": str(home / ".janitor"),
           "JANITOR_TEST_CALLS": str(calls), "JANITOR_TEST_LOOKUP": str(lookup),
           "JANITOR_TEST_STABLE": "a" * 40, "JANITOR_TEST_INSTALL_EXIT": "0"}
    return source, env, calls, lookup
