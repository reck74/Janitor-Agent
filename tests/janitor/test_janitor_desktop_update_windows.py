"""The desktop app's Windows update hand-off (touchpoint ``desktop-update-windows``, F6-06).

``scripts/desktop-update/windows.ps1`` must drive ``janitor update`` (directive
13), never upstream's ``hermes_cli.main update --force``. On the Windows lane of
``janitor-ci.yml`` (``os-compat``) the real script runs with Windows PowerShell
5.1 against a fake install whose ``venv\\Scripts\\python.exe`` is a compiled
recorder: the argv it receives is then parsed by the REAL Janitor parser
(``janitor.update_core.parse_update_args``), so a flag that parser rejects
(exit 2) fails here. Nothing is pulled or installed.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Optional

import pytest

from janitor.home import REPO_ROOT
from janitor.update_core import parse_update_args

WINDOWS_PS1 = REPO_ROOT / "scripts" / "desktop-update" / "windows.ps1"
_SEP = "\x1f"

_FAKE_PYTHON = r'''
using System;
using System.IO;

public static class FakePython {
    public static int Main(string[] args) {
        File.AppendAllText(Environment.GetEnvironmentVariable("JANITOR_FAKE_PY_LOG"),
            string.Join("\u001f", args) + Environment.NewLine);
        if (Array.IndexOf(args, "--help") >= 0) {
            Console.WriteLine("--keep-stash");
            return 0;
        }
        string code = (args.Length >= 3 && args[2] == "update")
            ? Environment.GetEnvironmentVariable("JANITOR_FAKE_UPDATE_EXIT") : null;
        return string.IsNullOrEmpty(code) ? 0 : int.Parse(code);
    }
}
'''


# --- every host: data invariant ---------------------------------------------


def test_windows_ps1_parses_the_same_in_ps51():
    """No BOM, and non-ASCII only inside full-line comments (upstream's own
    comments): PS 5.1 reads the file in the ANSI code page, where a UTF-8 byte in
    code or a string can become a stray quote."""
    raw = WINDOWS_PS1.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    offenders = [
        number
        for number, line in enumerate(raw.split(b"\n"), 1)
        if any(byte >= 0x80 for byte in line) and not line.lstrip().startswith(b"#")
    ]
    assert not offenders, f"non-ASCII outside comments on line(s) {offenders}"


# --- Windows: the real hand-off under Windows PowerShell 5.1 ------------------


def _powershell() -> str:
    exe = shutil.which("powershell")
    assert exe, "Windows updater tests require Windows PowerShell (powershell.exe)."
    return exe


def _compile_fake_python(output: Path) -> None:
    source = output.with_suffix(".cs")
    source.write_text(_FAKE_PYTHON, encoding="utf-8")
    script = output.with_name("compile-fake-python.ps1")
    script.write_text(
        "param([string]$Source, [string]$Output)\n"
        "Add-Type -Path $Source -OutputAssembly $Output -OutputType ConsoleApplication\n",
        encoding="utf-8",
    )
    subprocess.run(
        [_powershell(), "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script),
         "-Source", str(source), "-Output", str(output)],
        check=True, capture_output=True, timeout=120,
    )


def run_windows_handoff(
    tmp_path: Path, *extra: str, update_exit: int = 0, branch: Optional[str] = "stable", launcher: bool = True
) -> dict:
    """Run the hand-off on a fake Janitor checkout (``janitor\\cli.py``); return its exit,
    result file and the argv seen. ``branch=None`` omits -Branch; ``launcher=False``
    leaves the venv without janitor.exe (an incomplete install)."""
    home = tmp_path / "home"
    checkout = home / "hermes-agent"
    scripts = checkout / "venv" / "Scripts"
    scripts.mkdir(parents=True)
    (checkout / "janitor").mkdir()
    (checkout / "janitor" / "cli.py").write_text("", encoding="utf-8")
    fake = tmp_path / "fake-python.exe"
    _compile_fake_python(fake)
    shutil.copyfile(fake, scripts / "python.exe")
    if launcher:
        shutil.copyfile(fake, scripts / "janitor.exe")
    log = tmp_path / "argv.log"

    env = {k: v for k, v in os.environ.items() if not k.startswith("HERMES_")}
    env.update({"JANITOR_FAKE_PY_LOG": str(log), "JANITOR_FAKE_UPDATE_EXIT": str(update_exit)})
    proc = subprocess.run(
        [_powershell(), "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(WINDOWS_PS1),
         "-InstallRoot", str(checkout), *(["-Branch", branch] if branch else []), "-NoUi", *extra],
        cwd=tmp_path, env=env, capture_output=True, timeout=180, check=False,
    )
    output = proc.stdout.decode("utf-8", errors="replace") + proc.stderr.decode("utf-8", errors="replace")
    result_file = home / ".hermes-update-result.json"
    assert result_file.is_file(), output
    calls = [line.split(_SEP) for line in log.read_text(encoding="utf-8").splitlines()] if log.exists() else []
    return {
        "code": proc.returncode,
        "output": output,
        "result": json.loads(result_file.read_text(encoding="utf-8")),
        "calls": calls,
    }


def update_calls(seen: dict) -> list:
    return [call for call in seen["calls"] if call[:3] == ["-m", "janitor.cli", "update"]]


@pytest.mark.windows_only
def test_handoff_runs_janitor_update_with_flags_its_parser_accepts(tmp_path):
    seen = run_windows_handoff(tmp_path)
    assert seen["code"] == 0, seen["output"]
    assert not any("hermes_cli.main" in call for call in seen["calls"]), seen["calls"]
    assert not any("--force" in call or "-c" in call for call in seen["calls"]), seen["calls"]
    (update,) = update_calls(seen)
    args = parse_update_args(update[3:])
    assert args.yes and args.gateway and args.keep_stash and args.branch == "stable", update
    # Gateways come back through the launcher, after the update.
    assert seen["calls"][-1] == ["-m", "janitor.cli", "gateway", "start", "--all"], seen["calls"]
    assert seen["result"]["ok"] is True and seen["result"]["exit_code"] == 0, seen["result"]
    assert seen["result"]["message"] == "Actualización completa.", seen["result"]


@pytest.mark.windows_only
def test_remote_served_desktop_updates_without_gateway(tmp_path):
    seen = run_windows_handoff(tmp_path, "-NoGateway")
    assert seen["code"] == 0, seen["output"]
    (update,) = update_calls(seen)
    args = parse_update_args(update[3:])
    # No --gateway, and the gateways already running are left alone too.
    assert args.gateway is False and args.no_gateway_restart is True, update
    assert not any("gateway" in call[2:3] for call in seen["calls"]), seen["calls"]


@pytest.mark.windows_only
def test_lock_refusal_reads_as_another_update_in_progress(tmp_path):
    """Exit 2 from `janitor update` = another live update holds the lock: no retry, own message."""
    seen = run_windows_handoff(tmp_path, update_exit=2)
    assert seen["code"] == 2, seen["output"]
    assert len(update_calls(seen)) == 1, seen["calls"]
    result = seen["result"]
    assert result["ok"] is False and result["exit_code"] == 2, result
    assert "otra actualización de Janitor en curso" in result["message"], result


@pytest.mark.windows_only
def test_without_branch_the_engine_follows_its_channel(tmp_path):
    """The parameter's "main" default is upstream's: without -Branch no --branch is passed."""
    seen = run_windows_handoff(tmp_path, branch=None)
    assert seen["code"] == 0, seen["output"]
    (update,) = update_calls(seen)
    args = parse_update_args(update[3:])
    assert "--branch" not in update and args.branch is None, update


@pytest.mark.windows_only
def test_incomplete_janitor_install_never_runs_upstreams_updater(tmp_path):
    """No janitor.exe in the venv is still a Janitor checkout: janitor.cli, never hermes_cli.main --force."""
    seen = run_windows_handoff(tmp_path, launcher=False)
    assert seen["code"] == 0, seen["output"]
    assert not any("hermes_cli.main" in call or "--force" in call for call in seen["calls"]), seen["calls"]
    assert len(update_calls(seen)) == 1, seen["calls"]
