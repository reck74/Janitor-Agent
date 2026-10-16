"""Native shell selection for real Janitor skill script tests."""

import os
import sys
from pathlib import Path

import pytest

from pm.shell import bash


@pytest.fixture
def janitor_bash(monkeypatch):
    """Run Git Bash, including its child utilities, instead of the WSL launcher."""
    shell = bash()
    assert shell, "The skill shell tests require a working Bash installation"
    if os.name == "nt":
        binary = Path(shell).parent
        directories = [binary.parent / "usr" / "bin", binary]
        prefix = [str(path) for path in directories if path.is_dir()]
        monkeypatch.setenv("PATH", os.pathsep.join([*prefix, os.environ["PATH"]]))
    if "JANITOR_SERVICE_PYTHON" not in os.environ:
        monkeypatch.setenv("JANITOR_SERVICE_PYTHON", Path(sys.executable).as_posix())
    return shell
