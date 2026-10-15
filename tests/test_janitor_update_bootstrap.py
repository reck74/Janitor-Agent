"""The bootstrap is a branding/delegation shell, including exact argv forwarding."""
from unittest.mock import patch

import janitor_update_bootstrap as bootstrap


def test_bootstrap_forwards_update_arguments(capsys):
    argv = ["--check", "--branch", "maintenance", "--backup"]
    with patch.object(bootstrap.janitor_update_core, "run_janitor_update", return_value=7) as delegate:
        assert bootstrap.run_update(argv) == 7
    delegate.assert_called_once_with(argv)
    assert "THE JANITOR" in capsys.readouterr().out


def test_bootstrap_no_args_delegates_defaults():
    with patch.object(bootstrap.janitor_update_core, "run_janitor_update", return_value=0) as delegate:
        assert bootstrap.run_update() == 0
    delegate.assert_called_once_with(None)
