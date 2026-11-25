"""Route the messaging ``/update`` command through ``janitor update`` (directive #13).

Upstream's handler spawns ``<python> -m hermes_cli.main update --gateway``: upstream's
update flow, which bypasses ``janitor.update_core``. There is no hook for the update
argv, so the plugin wraps ``gateway.slash_commands._spawn_detached_update`` and hands it
the launcher's argv instead; ``janitor.cli`` intercepts ``update`` before anything else
loads. Signature guarded by ``tests/janitor/test_janitor_monkeypatch_signatures.py``.

On Windows upstream's spawner ignores the argv it is given and always runs
``hermes_cli.main``, so there the wrapper does the spawn itself: upstream's own inline
helper (``_WINDOWS_UPDATE_HELPER``: output file + exit-code file) and detach flags, with
the launcher's argv as the command. The child also gets a UTF-8 stdout: the gateway
reads the output file as UTF-8, and the early ``update`` intercept prints before any
``hermes_cli`` import could repair a cp1252 stream.

``install()`` runs at plugin registration and again from the ``pre_gateway_dispatch`` hook:
registration can happen before ``gateway.run`` is imported (background discovery during CLI
startup), and the hook fires inside the gateway before any command is handled.
"""
from __future__ import annotations

import os
import sys


def janitor_update_argv() -> list[str]:
    """This install's launcher, by module: never a ``janitor`` found on PATH."""
    return [sys.executable, "-m", "janitor.cli"]


def windows_update_argv(helper: str, output_path, exit_code_path) -> list[str]:
    """Argv of the Windows ``/update`` spawn: upstream's ``helper`` running ``janitor update``."""
    return [sys.executable, "-c", helper, str(output_path), str(exit_code_path),
            *janitor_update_argv(), "update", "--gateway"]


def _spawn_windows_update(slash_commands, output_path, exit_code_path) -> None:
    import subprocess

    from hermes_cli._subprocess_compat import windows_detach_popen_kwargs

    env = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
    subprocess.Popen(
        windows_update_argv(slash_commands._WINDOWS_UPDATE_HELPER, output_path, exit_code_path),
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env, **windows_detach_popen_kwargs())


def install() -> bool:
    """Wrap the gateway's update spawner, once. Only acts in a gateway process: a CLI
    process never imports ``gateway.run`` and must not pay for it here."""
    if "gateway.run" not in sys.modules:
        return False

    import gateway.slash_commands as slash_commands

    original = slash_commands._spawn_detached_update
    if getattr(original, "_janitor_update", False):
        return True

    def _spawn_detached_update(hermes_cmd, output_path, exit_code_path) -> None:
        if sys.platform == "win32":
            _spawn_windows_update(slash_commands, output_path, exit_code_path)
            return
        original(janitor_update_argv(), output_path, exit_code_path)

    _spawn_detached_update._janitor_update = True
    _spawn_detached_update._janitor_original = original
    slash_commands._spawn_detached_update = _spawn_detached_update
    return True


def pre_gateway_dispatch(**_kwargs) -> None:
    """``pre_gateway_dispatch`` hook: make sure the wrapper is in place; never drops a message."""
    install()
    return None
