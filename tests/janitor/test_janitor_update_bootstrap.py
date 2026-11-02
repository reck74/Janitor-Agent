"""Tests for the thin Janitor update bootstrap shell.

Per JANITOR FORK DIRECTIVE #13, ``janitor_update_bootstrap`` may ONLY print
its branding banner, parse its flags through the core, and delegate to
``janitor_update_core.run_janitor_update``. All update flow logic lives in
``janitor_update_core``. The git/stash/bytecode helpers previously defined
here have been removed and now live (and are tested) in
``tests/janitor/test_janitor_update_core.py``.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[2]


def _setup_py_root_modules() -> set[str]:
    spec = importlib.util.spec_from_file_location("_janitor_setup_py", REPO_ROOT / "setup.py")
    mod = importlib.util.module_from_spec(spec)
    saved = sys.argv
    sys.argv = ["setup.py", "--name"]
    try:
        try:
            spec.loader.exec_module(mod)
        except SystemExit:
            pass
    finally:
        sys.argv = saved
    return set(mod._root_py_modules())


def test_compat_aliases_are_packaged_for_pre_1_0_entrypoints():
    """Pre-1.0 console scripts import the root alias modules, so the
    distribution must ship them. Root single-file modules reach the editable
    install and the wheel through upstream's ``setup.py::_root_py_modules()``;
    the test interpreter is PM's test environment, which does not install the
    checkout, so the contract is read from that single source."""
    import janitor_update_bootstrap

    assert callable(janitor_update_bootstrap.run_update)
    assert {
        "janitor_cli", "janitor_update_core", "janitor_update_bootstrap", "janitor_version",
    } <= _setup_py_root_modules()


def test_update_intercept_runs_before_hermes_imports():
    """The early ``update`` intercept fires BEFORE the module-level
    ``from hermes_cli.config import DEFAULT_CONFIG`` line in ``janitor_cli``.

    Behavioral probe (no source reads): when ``sys.argv == ["janitor", "update"]``,
    importing ``janitor_cli`` must short-circuit to ``janitor_update_bootstrap.run_update``
    and ``sys.exit`` BEFORE control reaches the Hermes-import line. We verify
    by patching ``hermes_cli.config.DEFAULT_CONFIG`` so any attribute access
    raises; the intercept firing early means we observe ``SystemExit`` (not
    the sentinel access error).
    """
    import types

    sentinel_marker = "SENTINEL_ACCESSED"

    probe = (
        "import sys, types\n"
        "sys.argv = ['janitor', 'update']\n"
        # Pre-load hermes_cli.config and patch its DEFAULT_CONFIG so accessing
        # ``DEFAULT_CONFIG.setdefault(...)`` raises an obvious marker.
        "import hermes_cli.config as _cfg_mod\n"
        "class _Sentinel:\n"
        "    def setdefault(self, *a, **kw):\n"
        "        raise RuntimeError('" + sentinel_marker + "')\n"
        "    def __getattr__(self, name):\n"
        "        raise RuntimeError('" + sentinel_marker + "')\n"
        "_cfg_mod.DEFAULT_CONFIG = _Sentinel()\n"
        "# Stub run_update to sys.exit(42) so we can distinguish exit-via-intercept\n"
        "# from any other outcome.\n"
        "import sys as _sys\n"
        "import janitor_update_bootstrap as _jub\n"
        "_jub.run_update = lambda: _sys.exit(42)\n"
        "try:\n"
        "    import janitor_cli\n"
        "except SystemExit as exc:\n"
        "    print('SYSTEMEXIT_CODE=' + str(exc.code))\n"
        "except RuntimeError as exc:\n"
        "    print('RUNTIME_ERROR=' + str(exc))\n"
        "else:\n"
        "    print('NO_EXIT')\n"
    )
    r = subprocess.run(
        [sys.executable, "-c", probe],
        capture_output=True, text=True,
    )
    out = r.stdout
    assert sentinel_marker not in out, (
        f"early `update` intercept must fire before Hermes config DEFAULT_CONFIG "
        f"is touched, but the sentinel was observed: {out!r}"
    )
    assert "SYSTEMEXIT_CODE=42" in out, (
        f"early `update` intercept should sys.exit(42) via run_update(), got: {out!r}"
    )


def test_bootstrap_run_update_prints_branding(capsys):
    """``run_update()`` prints the Janitor branding banner before delegating."""
    import janitor_update_bootstrap as jub

    with patch.object(jub.janitor_update_core, "run_janitor_update",
                      return_value=0) as mock_delegate:
        rc = jub.run_update([])

    out = capsys.readouterr().out
    assert "THE JANITOR" in out
    assert rc == 0
    mock_delegate.assert_called_once()


def test_bootstrap_run_update_builds_default_namespace():
    """Without flags the bootstrap passes the core's contract keys with their
    defaults to ``run_janitor_update``.
    """
    import janitor_update_bootstrap as jub

    captured: dict = {}

    def fake_run(args):
        captured["args"] = args
        return 0

    with patch.object(jub.janitor_update_core, "run_janitor_update",
                      side_effect=fake_run):
        jub.run_update([])

    args = captured["args"]
    # Recognised attributes per the core's contract (all default False / None).
    assert args.check is False
    assert args.gateway is False
    assert args.backup is False
    assert args.no_backup is False
    assert args.branch is None


def test_bootstrap_run_update_delegates_to_janitor_update_core():
    """``run_update()`` delegates exactly once to ``janitor_update_core.run_janitor_update``."""
    import janitor_update_bootstrap as jub

    with patch.object(jub.janitor_update_core, "run_janitor_update",
                      return_value=0) as mock_delegate:
        rc = jub.run_update([])

    assert rc == 0
    assert mock_delegate.call_count == 1


def test_bootstrap_does_not_define_obsolete_helpers():
    """The bootstrap file no longer carries _git_cmd, _stash_local_changes_if_needed,
    _restore_stash, _clear_bytecode_cache. Those moved to janitor_update_core.
    """
    import janitor_update_bootstrap as jub

    for name in (
        "_git_cmd",
        "_stash_local_changes_if_needed",
        "_restore_stash",
        "_clear_bytecode_cache",
        "_stash_selector_for_ref",
    ):
        assert not hasattr(jub, name), (
            f"janitor_update_bootstrap must not define {name!r}; "
            f"that helper belongs in janitor_update_core"
        )


def _run_launcher_update(tmp_path, *update_args):
    """Run the real ``janitor update`` intercept with the core stubbed to
    report the namespace it received instead of updating anything."""
    probe = (
        "import json, sys\n"
        f"sys.argv = ['janitor', 'update', *{list(update_args)!r}]\n"
        "import janitor.update_core as core\n"
        "def fake_run(args):\n"
        "    print('ARGS=' + json.dumps(vars(args), sort_keys=True))\n"
        "    return 0\n"
        "core.run_janitor_update = fake_run\n"
        "import janitor.cli\n"
    )
    return subprocess.run(
        [sys.executable, "-c", probe],
        capture_output=True, text=True,
        env={**__import__("os").environ, "HOME": str(tmp_path)},
    )


def _received_args(result) -> dict:
    import json

    lines = [line for line in result.stdout.splitlines() if line.startswith("ARGS=")]
    assert len(lines) == 1, (result.stdout, result.stderr)
    return json.loads(lines[0][len("ARGS="):])


def test_launcher_update_forwards_check_flag_to_the_core(tmp_path):
    result = _run_launcher_update(tmp_path, "--check")

    assert result.returncode == 0, result.stderr
    assert _received_args(result)["check"] is True


def test_launcher_update_forwards_branch_and_backup_flags(tmp_path):
    result = _run_launcher_update(tmp_path, "--branch", "next", "--no-backup", "--gateway")

    assert result.returncode == 0, result.stderr
    args = _received_args(result)
    assert args["branch"] == "next"
    assert args["no_backup"] is True
    assert args["gateway"] is True
    assert args["check"] is False


def test_launcher_update_rejects_flags_the_core_does_not_implement(tmp_path):
    result = _run_launcher_update(tmp_path, "--plan")

    assert result.returncode == 2
    assert "ARGS=" not in result.stdout
    assert "--plan" in result.stderr
