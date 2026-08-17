"""Tests for the thin Janitor update bootstrap shell.

Per JANITOR FORK DIRECTIVE #13, ``janitor_update_bootstrap`` may ONLY print
its branding banner, build the default namespace, and delegate to
``janitor_update_core.run_janitor_update``. All update flow logic lives in
``janitor_update_core``. The git/stash/bytecode helpers previously defined
here have been removed and now live (and are tested) in
``tests/test_janitor_update_core.py``.
"""

from __future__ import annotations

import tomllib
from pathlib import Path
from unittest.mock import patch


def test_bootstrap_module_is_packaged_for_janitor_entrypoint():
    """The bootstrap module is listed in pyproject's py-modules."""
    pyproject = tomllib.loads(Path("pyproject.toml").read_text())
    py_modules = pyproject["tool"]["setuptools"]["py-modules"]

    assert "janitor_update_bootstrap" in py_modules


def test_update_intercept_runs_before_hermes_imports():
    """The early ``update`` intercept fires before any Hermes import in janitor_cli.py."""
    source = Path("janitor_cli.py").read_text()
    intercept = source.index('if len(sys.argv) > 1 and sys.argv[1] == "update":')
    hermes_config = source.index("from hermes_cli.config import DEFAULT_CONFIG")
    prompt_builder = source.index("from agent import prompt_builder")
    assert intercept < hermes_config
    assert intercept < prompt_builder


def test_bootstrap_run_update_prints_branding(capsys):
    """``run_update()`` prints the Janitor branding banner before delegating."""
    import janitor_update_bootstrap as jub

    with patch.object(jub.janitor_update_core, "run_janitor_update",
                      return_value=0) as mock_delegate:
        rc = jub.run_update()

    out = capsys.readouterr().out
    assert "THE JANITOR" in out
    assert rc == 0
    mock_delegate.assert_called_once()


def test_bootstrap_run_update_builds_default_namespace():
    """The bootstrap builds a default argparse.Namespace with the contract keys
    ``janitor_update_core`` recognises and passes it to ``run_janitor_update``.
    """
    import janitor_update_bootstrap as jub

    captured: dict = {}

    def fake_run(args):
        captured["args"] = args
        return 0

    with patch.object(jub.janitor_update_core, "run_janitor_update",
                      side_effect=fake_run):
        jub.run_update()

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
        rc = jub.run_update()

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