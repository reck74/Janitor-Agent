"""Post-update phases of ``janitor update`` shared with ``hermes update``.

After a successful update upstream's ``_finish_pulled_update`` rebuilds
``web/``, writes the gateway's ``.update_exit_code`` under ``--gateway`` and
restarts the running gateway fleet onto the new code. The Janitor core calls
the same upstream helpers; these tests pin when it does (success only, never on
``--check`` or a failed run), that a missing helper is a warning and not a
failed update, and that a gateway served by ANOTHER checkout of the same home
(the pre-1.0 ``janitor-core/.venv`` next to the app's ``hermes-agent/venv``) is
never restarted. No real gateway is discovered, signalled or relaunched: the
restart seam is replaced where the core reads it.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

import janitor.update_core as juc
from tests.janitor.test_janitor_update_core import _make_side_effect, _stub_pipeline_helpers


@pytest.fixture
def update(monkeypatch, tmp_path):
    """A stubbed successful update whose post-update seams record their calls."""
    _stub_pipeline_helpers(monkeypatch, tmp_path)
    events: list = []
    monkeypatch.setattr(
        juc, "_write_gateway_update_exit_code", lambda ok: events.append(("exit_code", ok))
    )
    monkeypatch.setattr(
        juc,
        "_restart_gateway_fleet_after_update",
        lambda plan, gateway_mode: events.append(("restart", plan, gateway_mode))
        or SimpleNamespace(incomplete=False),
    )
    monkeypatch.setattr(juc, "_gateways_in_update_scope", lambda: [(4242, tmp_path)])

    def run(*, commit_count="3", **args):
        side_effect, recorded = _make_side_effect(commit_count=commit_count)
        monkeypatch.setattr(juc.subprocess, "run", side_effect)
        return juc.run_janitor_update(SimpleNamespace(**args)), recorded

    return SimpleNamespace(run=run, events=events, root=tmp_path)


def _restarts(events):
    return [e for e in events if e[0] == "restart"]


# ---------------------------------------------------------------------------
# When the fleet restart runs
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("gateway", [False, True])
def test_successful_pull_restarts_this_installs_gateways(update, gateway):
    rc, _ = update.run(gateway=gateway)

    assert rc == 0
    assert _restarts(update.events) == [("restart", None, gateway)]


def test_gateway_mode_writes_the_exit_code_before_the_restart(update):
    rc, _ = update.run(gateway=True)

    assert rc == 0
    assert update.events == [("exit_code", True), ("restart", None, True)]


def test_plain_update_never_writes_the_gateway_exit_code(update):
    update.run()

    assert [e for e in update.events if e[0] == "exit_code"] == []


@pytest.mark.parametrize(
    "breakage",
    ["fetch", "reset", "node_deps", "config_migration"],
)
def test_failed_update_restarts_nothing_and_reports_failure_to_the_gateway(
    update, monkeypatch, breakage
):
    if breakage == "node_deps":
        monkeypatch.setattr(juc, "_install_node_dependencies", lambda root: ["ui-tui npm (install)"])
    elif breakage == "config_migration":
        monkeypatch.setattr(juc, "_run_config_check_fresh", lambda: (33, 34))
        monkeypatch.setattr(juc, "_run_migrate_config_fresh", lambda **kw: {"warnings": []})
    side_effect, _ = _make_side_effect(
        fetch_fails=breakage == "fetch",
        ff_only_fails=breakage == "reset",
        reset_fails=breakage == "reset",
    )
    monkeypatch.setattr(juc.subprocess, "run", side_effect)

    rc = juc.run_janitor_update(SimpleNamespace(gateway=True))

    assert rc == 1
    assert _restarts(update.events) == []
    assert update.events == [("exit_code", False)]


def test_check_mode_restarts_nothing_and_writes_no_exit_code(update):
    rc, recorded = update.run(check=True, gateway=True)

    assert rc == 0
    assert update.events == []
    assert all("--ff-only" not in c for c in recorded)


def test_no_gateway_restart_flag_skips_the_restart(update, capsys):
    rc, _ = update.run(no_gateway_restart=True)

    assert rc == 0
    assert _restarts(update.events) == []
    assert "--no-gateway-restart" in capsys.readouterr().out
    assert juc.parse_update_args(["--no-gateway-restart"]).no_gateway_restart is True


@pytest.mark.parametrize("stale, restarted", [(False, False), (True, True)])
def test_already_current_restarts_only_a_fleet_still_on_stale_code(
    update, monkeypatch, stale, restarted
):
    """A previous run that pulled but failed afterwards leaves gateways on the
    old code; the rerun finds git current and must still catch them up."""
    monkeypatch.setattr(juc, "_fleet_runs_stale_code", lambda: stale)

    rc, _ = update.run(commit_count="0")

    assert rc == 0
    assert bool(_restarts(update.events)) is restarted


# ---------------------------------------------------------------------------
# Degraded venv: every upstream helper is optional
# ---------------------------------------------------------------------------


def test_unimportable_restart_helper_is_a_warning_not_a_failed_update(
    update, monkeypatch, capsys
):
    monkeypatch.setattr(juc, "_restart_gateway_fleet_after_update", None)
    real_try_import = juc._try_import
    monkeypatch.setattr(
        juc,
        "_try_import",
        lambda name: None if name == "_restart_gateway_fleet_after_update" else real_try_import(name),
    )

    rc, _ = update.run()

    assert rc == 0
    assert "Gateway restart helper unavailable" in capsys.readouterr().out


def test_unimportable_gateway_discovery_is_a_warning_not_a_failed_update(
    update, monkeypatch, capsys
):
    """The real discovery, with upstream's scoping module missing from the venv."""
    monkeypatch.setattr(juc, "_gateways_in_update_scope", _REAL_DISCOVERY)
    monkeypatch.setitem(sys.modules, "hermes_cli.update_fleet_scope", None)

    rc, _ = update.run()

    assert rc == 0
    assert _restarts(update.events) == []
    assert "Could not list running gateways" in capsys.readouterr().out


def test_without_the_upstream_writer_the_exit_code_still_reaches_the_gateway(
    update, monkeypatch
):
    monkeypatch.setattr(juc, "_write_gateway_update_exit_code", None)
    real_try_import = juc._try_import
    monkeypatch.setattr(
        juc,
        "_try_import",
        lambda name: None if name == "_write_gateway_update_exit_code" else real_try_import(name),
    )

    rc, _ = update.run(gateway=True)

    assert rc == 0
    assert (update.root / ".update_exit_code").read_text(encoding="utf-8") == "0"


# ---------------------------------------------------------------------------
# web/ rebuild
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("has_web", [True, False])
def test_web_ui_is_rebuilt_only_when_the_checkout_has_web(update, monkeypatch, has_web):
    if has_web:
        (update.root / "web").mkdir()
    built: list = []
    monkeypatch.setattr(juc, "_build_web_ui", lambda web_dir, **kw: built.append(web_dir) or True)

    rc, _ = update.run()

    assert rc == 0
    assert built == ([update.root / "web"] if has_web else [])


def test_web_build_helper_missing_or_failing_never_fails_the_update(
    update, monkeypatch, capsys
):
    (update.root / "web").mkdir()

    def broken_build(web_dir, **kw):
        raise RuntimeError("npm exploded")

    monkeypatch.setattr(juc, "_build_web_ui", broken_build)
    rc, _ = update.run()

    assert rc == 0
    assert "Web UI not rebuilt: npm exploded" in capsys.readouterr().out
    assert _restarts(update.events), "a broken web build must not skip the gateway restart"


# ---------------------------------------------------------------------------
# Restart scoping: home (upstream) + checkout (Janitor)
# ---------------------------------------------------------------------------

_REAL_DISCOVERY = juc._gateways_in_update_scope


def _checkout(path: Path) -> Path:
    (path / "hermes_cli").mkdir(parents=True)
    (path / "hermes_cli" / "main.py").write_text("", encoding="utf-8")
    return path


def _gateway_state(home: Path, pid: int, checkout: Path) -> None:
    home.mkdir(parents=True, exist_ok=True)
    (home / "gateway_state.json").write_text(
        json.dumps({
            "pid": pid,
            "kind": "hermes-gateway",
            "argv": [str(checkout / "hermes_cli" / "main.py"), "gateway", "run"],
            "gateway_state": "running",
        }),
        encoding="utf-8",
    )


@pytest.fixture
def fleet(tmp_path, monkeypatch):
    """Three gateways on one host, seen through upstream's discovery and scoping.

    * 101 — this home, served by this checkout (``hermes-agent``);
    * 102 — this home's profile ``old``, served by the pre-1.0 ``janitor-core``;
    * 103 — another home entirely.
    """
    import hermes_cli.dashboard_procs as dashboard_procs
    import hermes_cli.gateway as gateway_cli

    ours = _checkout(tmp_path / "janitor" / "hermes-agent")
    legacy = _checkout(tmp_path / "janitor" / "janitor-core")
    home = tmp_path / "janitor"
    other_home = tmp_path / "elsewhere"
    homes = {101: home, 102: home / "profiles" / "old", 103: other_home}
    _gateway_state(homes[101], 101, ours)
    _gateway_state(homes[102], 102, legacy)
    _gateway_state(homes[103], 103, ours)

    monkeypatch.setenv("HERMES_HOME", str(home))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setattr(juc, "PROJECT_ROOT", ours)
    monkeypatch.setattr(juc, "get_hermes_home", lambda: home)
    live = {"pids": [101, 102, 103]}
    monkeypatch.setattr(
        gateway_cli, "find_gateway_pids",
        lambda exclude_pids=None, all_profiles=False: list(live["pids"]),
    )
    monkeypatch.setattr(gateway_cli, "find_profile_gateway_processes", lambda *a, **kw: [])
    monkeypatch.setattr(dashboard_procs, "_hermes_home_for_pid", lambda pid: str(homes[pid]))
    restarted: list = []
    monkeypatch.setattr(
        juc,
        "_restart_gateway_fleet_after_update",
        lambda plan, gateway_mode: restarted.append(gateway_mode) or SimpleNamespace(incomplete=False),
    )
    return SimpleNamespace(ours=ours.resolve(), legacy=legacy.resolve(), live=live, restarted=restarted)


def test_discovery_keeps_upstream_home_scope_and_reads_each_gateways_checkout(fleet):
    rows = dict(juc._gateways_in_update_scope())

    assert 103 not in rows, "a gateway of another home is out of the update's scope"
    assert rows == {101: fleet.ours, 102: fleet.legacy}


def test_a_gateway_served_by_another_checkout_is_never_restarted(fleet, capsys):
    juc._restart_gateways_after_update(gateway_mode=True)

    out = capsys.readouterr().out
    assert fleet.restarted == []
    assert "PID 102" in out and str(fleet.legacy) in out
    assert "PID 103" not in out


def test_gateways_of_this_checkout_only_are_restarted(fleet):
    fleet.live["pids"] = [101, 103]

    juc._restart_gateways_after_update(gateway_mode=False)

    assert fleet.restarted == [False]


def test_no_running_gateway_of_this_home_restarts_nothing(fleet):
    fleet.live["pids"] = [103]

    juc._restart_gateways_after_update(gateway_mode=False)

    assert fleet.restarted == []


# ---------------------------------------------------------------------------
# npm resolution without hermes_cli
# ---------------------------------------------------------------------------


def _fake_npm(directory: Path, log: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    npm = directory / "npm"
    npm.write_text(f'#!/bin/sh\necho "$@" >> "{log}"\n', encoding="utf-8")
    npm.chmod(0o755)
    return npm


@pytest.fixture
def tui_without_resolver(tmp_path, monkeypatch):
    ui_tui = tmp_path / "ui-tui"
    ui_tui.mkdir()
    (ui_tui / "package.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(juc, "_resolve_node_runtime_npm", None)
    monkeypatch.setattr(juc, "_tui_install_context", lambda d: None)
    return ui_tui


@pytest.mark.linux_only
def test_tui_build_uses_the_node_runtime_lookup_when_the_resolver_is_missing(
    tui_without_resolver, tmp_path, monkeypatch
):
    import hermes_constants

    log = tmp_path / "npm.log"
    npm = _fake_npm(tmp_path / "managed-node", log)
    monkeypatch.setattr(
        hermes_constants, "find_node_executable", lambda cmd: str(npm) if cmd == "npm" else None
    )

    assert juc._build_tui(tui_without_resolver) == []
    assert log.read_text(encoding="utf-8").split() == ["run", "build"]


@pytest.mark.linux_only
def test_tui_build_finds_npm_on_path_when_hermes_constants_is_unimportable(
    tui_without_resolver, tmp_path, monkeypatch
):
    log = tmp_path / "npm.log"
    bin_dir = tmp_path / "bin"
    _fake_npm(bin_dir, log)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}")
    monkeypatch.setitem(sys.modules, "hermes_constants", None)

    assert juc._build_tui(tui_without_resolver) == []
    assert log.read_text(encoding="utf-8").split() == ["run", "build"]


def test_tui_build_reports_missing_npm_when_nothing_resolves(tui_without_resolver, monkeypatch):
    monkeypatch.setitem(sys.modules, "hermes_constants", None)
    monkeypatch.setitem(sys.modules, "hermes_platform.resolver", None)

    assert juc._build_tui(tui_without_resolver) == ["ui-tui npm (npm not found)"]
