"""The fork's ``scripts/install.ps1`` (touchpoint ``install-ps1``, task F6-05).

The desktop app on Windows downloads it and runs it with Windows PowerShell 5.1
stage by stage (``-Manifest``, then ``-Stage <name> -NonInteractive -Json``,
``apps/desktop/electron/bootstrap-runner.ts``). The behavioural tests run the
real script with ``powershell.exe`` on the Windows lane of ``janitor-ci.yml``
(``os-compat``) in its cheap modes only, against temp homes: nothing is
downloaded and the real home is never touched. Two data invariants hold on
every host: the file PS 5.1 parses is pure ASCII without a BOM, and its default
``-Branch`` is the release channel.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional

import pytest
import yaml

from janitor.home import ASSETS_ROOT, REPO_ROOT
from janitor.release_channel import RELEASE_BRANCH

INSTALL_PS1 = REPO_ROOT / "scripts" / "install.ps1"
LEGACY_REASON = "instalación antigua de Janitor"


# --- every host: data invariants -------------------------------------------


def test_install_ps1_is_pure_ascii_without_bom():
    """PS 5.1 reads a BOM-less .ps1 in the ANSI code page: one UTF-8 byte can
    decode into a stray quote and desync the parser. Spanish goes in as \\uXXXX."""
    raw = INSTALL_PS1.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    offenders = sorted({raw.count(b"\n", 0, i) + 1 for i, byte in enumerate(raw) if byte >= 0x80})
    assert not offenders, f"non-ASCII bytes on line(s) {offenders}"


def test_default_branch_is_the_release_channel():
    """The app passes -Branch, but a bare run must install tagged versions only (F1-28)."""
    text = INSTALL_PS1.read_bytes().decode("ascii")
    defaults = re.findall(r'^\s*\[string\]\$Branch\s*=\s*"([^"]*)"', text, flags=re.MULTILINE)
    assert defaults == [RELEASE_BRANCH], defaults


# --- Windows: the real script under Windows PowerShell 5.1 -------------------


def _powershell() -> str:
    exe = shutil.which("powershell")
    assert exe, "Windows installer tests require Windows PowerShell (powershell.exe)."
    return exe


def _env(home: Optional[Path]) -> dict:
    """The app's env: HERMES_HOME names the home (or is absent, for the defaults)."""
    env = {k: v for k, v in os.environ.items() if not k.startswith("HERMES_")}
    if home is not None:
        env["HERMES_HOME"] = str(home)
    return env


def run_install_ps1(cwd: Path, home: Optional[Path], *args: str, timeout: int = 120) -> subprocess.CompletedProcess:
    result = subprocess.run(
        [_powershell(), "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(INSTALL_PS1), *args],
        cwd=cwd,
        env=_env(home),
        capture_output=True,
        timeout=timeout,
        check=False,
    )
    result.stdout = result.stdout.decode("utf-8", errors="replace")
    result.stderr = result.stderr.decode("utf-8", errors="replace")
    return result


def _dot_source(cwd: Path, script: str, env: dict) -> dict:
    """Load the installer's functions (its dot-source early return) and run ``script``,
    which must end by writing one JSON line."""
    ps1 = str(INSTALL_PS1).replace("'", "''")
    result = subprocess.run(
        [_powershell(), "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", f". '{ps1}'\n{script}"],
        cwd=cwd,
        env=env,
        capture_output=True,
        timeout=60,
        check=False,
    )
    out = result.stdout.decode("utf-8", errors="replace")
    assert result.returncode == 0, out + result.stderr.decode("utf-8", errors="replace")
    return json.loads([line for line in out.splitlines() if line.strip()][-1])


def last_json(stdout: str) -> Optional[dict]:
    for line in reversed([l for l in stdout.splitlines() if l.strip()]):
        try:
            parsed = json.loads(line)
        except ValueError:
            continue
        if isinstance(parsed, dict):
            return parsed
    return None


def legacy_home(tmp_path: Path) -> Path:
    home = tmp_path / ".janitor"
    (home / "janitor-core").mkdir(parents=True)
    return home


def assert_legacy_refusal(result: subprocess.CompletedProcess, stage: Optional[str]) -> None:
    """The {ok:false} frame the app reads carries the Spanish reason."""
    output = result.stdout + result.stderr
    assert result.returncode == 1, output
    frame = last_json(result.stdout)
    assert frame is not None, output
    assert frame["ok"] is False and frame["stage"] == stage, frame
    assert "janitor-core" in frame["reason"] and LEGACY_REASON in frame["reason"], frame


@pytest.mark.windows_only
def test_manifest_is_json_and_writes_nothing(tmp_path):
    home = tmp_path / ".janitor"
    install = tmp_path / "install"
    result = run_install_ps1(tmp_path, home, "-Manifest", "-InstallDir", str(install))
    assert result.returncode == 0, result.stdout + result.stderr
    stages = last_json(result.stdout)["stages"]
    names = [stage["name"] for stage in stages]
    assert {"repository", "venv", "dependencies", "path", "config-templates"} <= set(names), names
    titles = {stage["name"]: stage["title"] for stage in stages}
    assert "Hermes" not in titles["repository"] and "Hermes" not in titles["path"], titles
    assert not home.exists() and not install.exists()


@pytest.mark.windows_only
@pytest.mark.parametrize("stage", ["repository", "config-templates"])
def test_every_stage_refuses_a_legacy_home(tmp_path, stage):
    home = legacy_home(tmp_path)
    install = tmp_path / "install"
    result = run_install_ps1(tmp_path, home, "-Stage", stage, "-NonInteractive", "-Json", "-InstallDir", str(install))
    assert_legacy_refusal(result, stage)
    assert not install.exists()
    assert [p.name for p in home.iterdir()] == ["janitor-core"]


@pytest.mark.windows_only
def test_full_run_refuses_a_legacy_home(tmp_path):
    home = legacy_home(tmp_path)
    install = tmp_path / "install"
    result = run_install_ps1(tmp_path, home, "-NonInteractive", "-Json", "-InstallDir", str(install))
    output = result.stdout + result.stderr
    assert result.returncode == 1, output
    frame = last_json(result.stdout)
    assert frame is not None and frame["ok"] is False and LEGACY_REASON in frame["reason"], output
    assert not install.exists()
    assert [p.name for p in home.iterdir()] == ["janitor-core"]


@pytest.mark.windows_only
def test_ensure_refuses_a_legacy_home(tmp_path):
    """-Ensure (dep_ensure.py) installs packages: same guard, exit 1."""
    home = legacy_home(tmp_path)
    result = run_install_ps1(tmp_path, home, "-Ensure", "node")
    output = result.stdout + result.stderr
    assert result.returncode == 1, output
    assert "janitor-core" in output, output


@pytest.mark.windows_only
def test_defaults_install_the_fork_into_dot_janitor(tmp_path):
    """No HERMES_HOME, no flags: the fork, ~/.janitor, the release channel, no browser, no Computer Use."""
    got = _dot_source(
        tmp_path,
        "@{ branch = $Branch; home = $HermesHome; install = $InstallDir; profile = $env:USERPROFILE;"
        " https = $RepoUrlHttps; ssh = $RepoUrlSsh; browser = [bool]$WithBrowser;"
        " computerUse = [bool]$WithComputerUse } | ConvertTo-Json -Compress",
        _env(None),
    )
    assert got["branch"] == RELEASE_BRANCH
    expected_home = got["profile"].rstrip("\\") + "\\.janitor"
    assert got["home"].lower() == expected_home.lower(), got
    assert got["install"].lower() == (expected_home + "\\hermes-agent").lower(), got
    assert got["https"] == "https://github.com/reck74/Janitor-Agent.git"
    assert got["ssh"] == "git@github.com:reck74/Janitor-Agent.git"
    assert got["browser"] is False and got["computerUse"] is False


@pytest.mark.windows_only
def test_path_stage_launcher_is_janitor_only(tmp_path):
    """Only `janitor` is staged on PATH, and a venv without janitor.exe is an error."""
    root = tmp_path / "root"
    scripts = root / "venv" / "Scripts"
    scripts.mkdir(parents=True)
    for name in ("janitor.exe", "hermes.exe", "hermes-acp.exe"):
        (scripts / name).write_bytes(b"MZ")
    bare = tmp_path / "bare"
    (bare / "venv" / "Scripts").mkdir(parents=True)
    (bare / "venv" / "Scripts" / "hermes.exe").write_bytes(b"MZ")

    def q(path: Path) -> str:
        return str(path).replace("'", "''")

    got = _dot_source(
        tmp_path,
        f"Install-HermesCommandLaunchers -Root '{q(root)}' -Destination '{q(tmp_path / 'bin')}' | Out-Null\n"
        "$staged = (@(Get-ChildItem -LiteralPath '" + q(tmp_path / "bin") + "' | ForEach-Object { $_.Name }) | Sort-Object) -join ','\n"
        "$refused = $null\n"
        f"try {{ Install-HermesCommandLaunchers -Root '{q(bare)}' -Destination '{q(tmp_path / 'bin2')}' | Out-Null }}"
        " catch { $refused = \"$_\" }\n"
        "@{ staged = $staged; refused = $refused } | ConvertTo-Json -Compress",
        _env(tmp_path / ".janitor"),
    )
    assert got["staged"] == "janitor.exe", got
    assert got["refused"] and "janitor.exe" in got["refused"], got
    assert not (tmp_path / "bin2").exists()


def _link_venv(install: Path) -> Path:
    """``install\\venv`` as a junction to the venv running this test, so the stage's
    ``venv\\Scripts\\python.exe -m janitor.seed`` is a real interpreter with this checkout."""
    if sys.prefix == sys.base_prefix:
        pytest.skip("needs to run from a virtualenv")
    install.mkdir(parents=True)
    link = install / "venv"
    subprocess.run(["cmd", "/c", "mklink", "/J", str(link), sys.prefix], check=True, capture_output=True)
    return link


def run_config_stage(tmp_path: Path, home_setup=None) -> tuple[subprocess.CompletedProcess, Path]:
    """The config-templates stage the app runs, on a fresh home with a real venv.
    ``home_setup(home)`` prepares the home first."""
    home = tmp_path / ".janitor"
    if home_setup is not None:
        home_setup(home)
    install = tmp_path / "install"
    link = _link_venv(install)
    try:
        result = run_install_ps1(tmp_path, home, "-Stage", "config-templates", "-NonInteractive", "-Json",
                                 "-InstallDir", str(install))
    finally:
        os.rmdir(link)  # removes the junction only, never the venv behind it
    return result, home


@pytest.mark.windows_only
def test_config_stage_seeds_a_janitor_home_without_upstream_skills(tmp_path):
    result, home = run_config_stage(tmp_path)
    output = result.stdout + result.stderr
    assert result.returncode == 0, output
    frame = last_json(result.stdout)
    assert frame and frame["stage"] == "config-templates" and frame["ok"] is True, output
    config = yaml.safe_load((home / "config.yaml").read_text(encoding="utf-8"))
    assert "janitor" in config["plugins"]["enabled"], config
    soul = (home / "SOUL.md").read_text(encoding="utf-8").replace("\r\n", "\n").strip()
    assert soul == (ASSETS_ROOT / "SOUL.md").read_text(encoding="utf-8").replace("\r\n", "\n").strip()
    assert (home / ".no-bundled-skills").is_file()
    assert not any((home / "skills").iterdir()), "upstream's bundled skills must not be synced"


def assert_stage_failed(result: subprocess.CompletedProcess, stage: str, *phrases: str) -> None:
    output = result.stdout + result.stderr
    assert result.returncode == 1, output
    frame = last_json(result.stdout)
    assert frame is not None and frame["stage"] == stage and frame["ok"] is False, output
    for phrase in phrases:
        assert phrase in frame["reason"], frame


@pytest.mark.windows_only
def test_config_stage_fails_without_the_venv_python(tmp_path):
    """An unseeded home would keep upstream's SOUL.md: the stage reports the failure."""
    home = tmp_path / ".janitor"
    result = run_install_ps1(tmp_path, home, "-Stage", "config-templates", "-NonInteractive", "-Json",
                             "-InstallDir", str(tmp_path / "install"))
    assert_stage_failed(result, "config-templates", "home de Janitor", "python.exe")


@pytest.mark.windows_only
def test_config_stage_fails_when_the_seed_fails(tmp_path):
    """A file where the seed needs the skins directory makes janitor.seed exit non-zero."""
    def block_skins(home: Path) -> None:
        home.mkdir(parents=True)
        (home / "skins").write_text("not a directory", encoding="utf-8")

    result, _home = run_config_stage(tmp_path, block_skins)
    assert_stage_failed(result, "config-templates", "janitor.seed")


@pytest.mark.windows_only
def test_origin_check_accepts_only_the_fork(tmp_path):
    urls = {
        "https://github.com/reck74/Janitor-Agent.git": True,
        "https://github.com/reck74/janitor-agent": True,
        "git@github.com:reck74/Janitor-Agent.git": True,
        "ssh://git@github.com/reck74/Janitor-Agent.git": True,
        "HTTPS://GITHUB.COM/RECK74/JANITOR-AGENT/": True,
        "https://github.com/NousResearch/hermes-agent.git": False,
        "https://github.com/someone/reck74-janitor-agent.git": False,
        "": False,
    }
    script = "@(" + ", ".join("'" + u.replace("'", "''") + "'" for u in urls) + ") | ForEach-Object {"
    script += " if (Test-JanitorOrigin $_) { 'Y' } else { 'N' } } | Out-String | ForEach-Object {"
    script += " @{ got = ($_ -replace '\\s', '') } | ConvertTo-Json -Compress }"
    got = _dot_source(tmp_path, script, _env(tmp_path / ".janitor"))
    assert got["got"] == "".join("Y" if ok else "N" for ok in urls.values()), got


@pytest.mark.windows_only
def test_repository_stage_refuses_a_checkout_of_another_repo(tmp_path):
    """An existing checkout whose origin is not the fork is never stashed, fetched or reset."""
    install = tmp_path / "install"
    install.mkdir()

    def git(*args: str) -> str:
        return subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", *args], cwd=install,
                              check=True, capture_output=True, text=True).stdout.strip()

    git("init", "-q", "-b", "main")
    (install / "README.md").write_text("hermes\n", encoding="utf-8")
    git("add", "README.md")
    git("commit", "-q", "-m", "init")
    git("remote", "add", "origin", "https://github.com/NousResearch/hermes-agent.git")
    (install / "local-edit.txt").write_text("mine\n", encoding="utf-8")
    head = git("rev-parse", "HEAD")

    result = run_install_ps1(tmp_path, tmp_path / ".janitor", "-Stage", "repository", "-NonInteractive", "-Json",
                             "-InstallDir", str(install))
    assert_stage_failed(result, "repository", "reck74/Janitor-Agent", "NousResearch/hermes-agent")
    assert git("rev-parse", "HEAD") == head
    assert git("stash", "list") == ""
    assert (install / "local-edit.txt").is_file()
