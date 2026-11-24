"""What ``janitor update`` tells the user and when it calls the run a failure.

Covers the core's own outcomes (F1-21d, ``docs/janitor/plans/actualizacion-diseno.md``
sections 3.2, 3.4, 3.5 and 5):

* the output is Spanish on every path (it is also streamed into the chat during
  a messaging ``/update``), with upstream's ``hermes update`` refusal replaced;
* a pull that raises the app/engine contract ends with the fork's release URL;
* a base dependency still missing after the install fails the run and keeps
  the "dependencies pending" flag, so the next run reinstalls;
* a gateway still on pre-update code after the restart fails the run (exit 1)
  with the exact command that restarts it;
* the pending flag resumes an interrupted update and is cleared only when the
  tree is back where it started.

Git, the gateway fleet and the installers are stubbed where the core reads them;
the dependency probe runs for real against a temporary ``pyproject.toml``.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

import janitor.update_core as juc
from tests.janitor.test_janitor_update_core import (  # noqa: F401 — fixture
    _make_side_effect,
    _stub_pipeline_helpers,
    foreign_update_holder,
)


FORK_RELEASES = "https://github.com/reck74/Janitor-Agent/releases/latest"


@pytest.fixture
def pipeline(monkeypatch, tmp_path):
    """A stubbed update whose git side effect can be wrapped per test."""
    _stub_pipeline_helpers(monkeypatch, tmp_path)
    events: list = []
    monkeypatch.setattr(juc, "_write_gateway_update_exit_code", lambda ok: events.append(("exit_code", ok)))
    monkeypatch.setattr(
        juc, "_restart_gateway_fleet_after_update",
        lambda plan, gateway_mode: events.append(("restart",)) or SimpleNamespace(incomplete=False),
    )
    monkeypatch.setattr(juc, "_gateways_in_update_scope", lambda: [(4242, tmp_path)])

    def run(*, wrap=None, side_effect_kwargs=None, **args):
        side_effect, recorded = _make_side_effect(**(side_effect_kwargs or {}))
        monkeypatch.setattr(juc.subprocess, "run", wrap(side_effect) if wrap else side_effect)
        return juc.run_janitor_update(SimpleNamespace(**args))

    return SimpleNamespace(run=run, root=tmp_path, events=events)


def _pending_flag(root: Path) -> Path:
    return root / ".git" / "janitor-update-deps-pending"


# ---------------------------------------------------------------------------
# Spanish on every path
# ---------------------------------------------------------------------------

# Phrases the core printed before F1-21d, and common English function words:
# none may survive in what the user reads. Commands in backticks and paths are
# not prose and are stripped first.
_OLD_PHRASES = (
    "Fetching", "Already up to date", "Updating Python dependencies", "updated successfully",
    "Update complete", "Restart Janitor", "Pulling updates", "post-pull", "Repairing Node",
    "config migration", "Another Hermes update", "Gateway restart", "Update cancelled",
)
_ENGLISH_WORDS = re.compile(
    r"\b(the|and|of|to|is|not|failed|could|cannot|already|updating|fetching|pulling|running|"
    r"skipped|skipping|unavailable|please|successfully|manually|restarting|available)\b",
    re.IGNORECASE,
)


def _english_lines(output: str) -> list[str]:
    offending = []
    for line in output.splitlines():
        if line.strip().startswith(juc._DETAIL_PREFIX):
            continue  # git's own words, labelled as such
        prose = re.sub(r"`[^`]*`", "", line)
        prose = " ".join(tok for tok in prose.split() if "/" not in tok and "\\" not in tok)  # drop paths, either separator
        if _ENGLISH_WORDS.search(prose) or any(p in line for p in _OLD_PHRASES):
            offending.append(line)
    return offending


def _scenarios(monkeypatch, pipeline):
    """(name, callable) pairs covering success, every failure class and the notices."""

    def stale_fleet():
        monkeypatch.setattr(
            juc, "_stale_gateways_after_restart",
            lambda outcome: [{"profile": "default", "pid": 4242, "state": "stale"}],
        )
        return pipeline.run()

    def missing_deps():
        monkeypatch.setattr(juc, "_missing_required_dependencies", lambda root: ["httpx"])
        return pipeline.run()

    def node_failure():
        monkeypatch.setattr(juc, "_install_node_dependencies", lambda root: ["ui-tui npm (install)"])
        return pipeline.run()

    def config_failure():
        monkeypatch.setattr(juc, "_run_config_check_fresh", lambda: (33, 34))
        monkeypatch.setattr(juc, "_run_migrate_config_fresh", lambda **kw: {"warnings": []})
        return pipeline.run()

    def lock_refused():
        holder = SimpleNamespace(pid=31337, age_seconds=125)
        monkeypatch.setattr(juc, "_acquire_update_lock", lambda: (None, juc._describe_update_holder(holder)))
        return pipeline.run(gateway=True)

    def foreign_gateway():
        monkeypatch.setattr(juc, "_gateways_in_update_scope", lambda: [(77, None)])
        return pipeline.run()

    def interrupted():
        def boom(root):
            raise KeyboardInterrupt
        monkeypatch.setattr(juc, "_install_node_dependencies", boom)
        return pipeline.run()

    return [
        ("pulled", lambda: pipeline.run()),
        ("already current", lambda: pipeline.run(side_effect_kwargs={"commit_count": "0"})),
        ("diverged", lambda: pipeline.run(side_effect_kwargs={"ff_only_fails": True})),
        ("reset fails", lambda: pipeline.run(side_effect_kwargs={"ff_only_fails": True, "reset_fails": True})),
        ("network", lambda: pipeline.run(side_effect_kwargs={
            "fetch_fails": True, "fetch_stderr": "fatal: Could not resolve host: github.com"})),
        ("auth", lambda: pipeline.run(side_effect_kwargs={
            "fetch_fails": True, "fetch_stderr": "fatal: Authentication failed for 'x'"})),
        ("fetch other", lambda: pipeline.run(side_effect_kwargs={
            "fetch_fails": True, "fetch_stderr": "fatal: the remote end hung up unexpectedly"})),
        ("branch switch", lambda: pipeline.run(side_effect_kwargs={"current_branch": "HEAD"})),
        ("check behind", lambda: pipeline.run(check=True, side_effect_kwargs={"commit_count": "5"})),
        ("check current", lambda: pipeline.run(check=True, side_effect_kwargs={"commit_count": "0"})),
        ("unsupported flag", lambda: pipeline.run(plan=True)),
        ("no restart flag", lambda: pipeline.run(no_gateway_restart=True)),
        ("stale fleet", stale_fleet),
        ("missing deps", missing_deps),
        ("node failure", node_failure),
        ("config failure", config_failure),
        ("lock refused", lock_refused),
        ("foreign gateway", foreign_gateway),
        ("interrupted", interrupted),
    ]


def test_no_path_of_the_update_speaks_english(monkeypatch, pipeline, capsys):
    names = [name for name, _ in _scenarios(monkeypatch, pipeline)]
    assert len(names) == len(set(names))
    for name in names:
        # Each scenario's breakage is undone before the next one runs.
        with monkeypatch.context() as m:
            run = dict(_scenarios(m, pipeline))[name]
            run()
        out = capsys.readouterr().out
        assert out.strip(), name
        assert _english_lines(out) == [], name


def test_a_failed_run_says_what_to_do_next(monkeypatch, pipeline, capsys):
    """Every ``✗`` outcome of a mutating run names the command to run next."""
    for kwargs in ({"fetch_fails": True}, {"ff_only_fails": True, "reset_fails": True}):
        assert pipeline.run(side_effect_kwargs=kwargs) == 1
        assert "`janitor update`" in capsys.readouterr().out, kwargs


# ---------------------------------------------------------------------------
# Lock refusal (design 3.4)
# ---------------------------------------------------------------------------


def test_lock_refusal_under_gateway_is_spanish_and_writes_no_exit_code(
    monkeypatch, tmp_path, capsys, foreign_update_holder
):
    _marker, holder_pid = foreign_update_holder
    _stub_pipeline_helpers(monkeypatch, tmp_path)
    written: list = []
    monkeypatch.setattr(juc, "_write_gateway_update_exit_code", written.append)
    side_effect, recorded = _make_side_effect()
    monkeypatch.setattr(juc.subprocess, "run", side_effect)

    rc = juc.run_janitor_update(SimpleNamespace(gateway=True))

    out = capsys.readouterr().out
    assert rc == juc._UPDATE_EXIT_CONCURRENT
    assert written == [] and not (tmp_path / ".update_exit_code").exists()
    assert recorded == []
    assert str(holder_pid) in out and "hermes" not in out.lower()
    assert _english_lines(out) == []


@pytest.mark.parametrize("age, minutes", [(30, None), (125, 2), (1199, 19)])
def test_refusal_reports_the_running_update_age_in_whole_minutes(age, minutes):
    text = juc._describe_update_holder(SimpleNamespace(pid=9, age_seconds=age))
    if minutes is None:
        assert re.search(rf"\b{age} s\b", text)
    else:
        assert re.search(rf"\b{minutes} min\b", text)


# ---------------------------------------------------------------------------
# App/engine contract notice (design 3.2)
# ---------------------------------------------------------------------------


def _write_compat(root: Path, payload) -> None:
    path = root / "janitor" / "desktop-compat.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload) if not isinstance(payload, str) else payload, encoding="utf-8")


def _pull_writes_compat(root: Path, payload):
    """Wrap the git side effect so the pull lands ``payload`` in the checkout."""
    def wrap(side_effect):
        def run(cmd, **kwargs):
            if "--ff-only" in [str(c) for c in cmd] and payload is not None:
                _write_compat(root, payload)
            return side_effect(cmd, **kwargs)
        return run
    return wrap


def _last_line(out: str) -> str:
    return [line for line in out.splitlines() if line.strip()][-1]


def test_a_raised_contract_ends_the_update_with_the_fork_release_url(pipeline, capsys):
    _write_compat(pipeline.root, {"contract": 1, "release_url": FORK_RELEASES})

    rc = pipeline.run(wrap=_pull_writes_compat(pipeline.root, {"contract": 2, "release_url": FORK_RELEASES}))

    out = capsys.readouterr().out
    assert rc == 0, "the notice never changes the exit code"
    assert FORK_RELEASES in _last_line(out)
    assert juc._SUCCESS_LINE in out and out.index(juc._SUCCESS_LINE) < out.index(FORK_RELEASES)


@pytest.mark.parametrize(
    "before, after",
    [
        ({"contract": 2}, {"contract": 2}),
        ({"contract": 3}, {"contract": 2}),
        (None, {"contract": 5}),  # engine predates the contract: nothing to compare
        ({"contract": 1}, None),  # pull did not touch the file
        ({"contract": 1}, "not json"),
    ],
)
def test_no_notice_unless_the_contract_rose(pipeline, capsys, before, after):
    if before is not None:
        _write_compat(pipeline.root, before)

    rc = pipeline.run(wrap=_pull_writes_compat(pipeline.root, after))

    assert rc == 0
    assert "releases" not in capsys.readouterr().out


def test_no_notice_when_already_current(pipeline, capsys):
    _write_compat(pipeline.root, {"contract": 9})

    assert pipeline.run(side_effect_kwargs={"commit_count": "0"}) == 0
    assert "releases" not in capsys.readouterr().out


@pytest.mark.parametrize(
    "url", ["https://evil.example/releases", "http://github.com/reck74/Janitor-Agent/releases",
            "https://github.com/NousResearch/hermes-agent/releases/latest", 42, None],
)
def test_a_release_url_outside_the_fork_is_replaced_by_the_fork_url(pipeline, capsys, url):
    _write_compat(pipeline.root, {"contract": 1})

    rc = pipeline.run(wrap=_pull_writes_compat(pipeline.root, {"contract": 2, "release_url": url}))

    out = capsys.readouterr().out
    assert rc == 0
    assert FORK_RELEASES in _last_line(out)
    if isinstance(url, str):
        assert url not in out


# ---------------------------------------------------------------------------
# Base dependencies (defect: partial install looked like success)
# ---------------------------------------------------------------------------


def _pyproject(root: Path, deps: list[str], extras: dict | None = None) -> None:
    lines = ["[project]", 'name = "probe"', 'version = "1.0+janitor.1"', "dependencies = ["]
    lines += [f"    {json.dumps(d)}," for d in deps]
    lines.append("]")
    if extras:
        lines.append("[project.optional-dependencies]")
        lines += [f"{k} = {json.dumps(v)}" for k, v in extras.items()]
    (root / "pyproject.toml").write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_probe_reports_only_absent_base_dependencies_that_apply_here(tmp_path):
    """Real probe in the real target interpreter: an installed base dependency
    passes, an absent one is reported, a marker that does not apply and an
    absent optional extra are not."""
    _pyproject(
        tmp_path,
        ["pytest>=7", "janitor-no-such-dist-f121d>=1", "janitor-other-absent ; python_version < '3'"],
        extras={"all": ["janitor-absent-extra-f121d"]},
    )

    assert juc._missing_required_dependencies(tmp_path) == ["janitor-no-such-dist-f121d"]


def test_probe_without_a_readable_pyproject_is_indeterminate_not_a_failure(tmp_path, capsys):
    assert juc._missing_required_dependencies(tmp_path) is None
    assert juc._verify_required_dependencies(tmp_path) is True
    assert "⚠" in capsys.readouterr().out


def test_probe_through_a_broken_interpreter_counts_as_missing(tmp_path, monkeypatch):
    _pyproject(tmp_path, ["pytest"])
    monkeypatch.setattr(juc, "_dependency_target_python", lambda root: tmp_path / "no-python")

    missing = juc._missing_required_dependencies(tmp_path)

    assert missing and str(tmp_path / "no-python") in missing[0]


@pytest.mark.parametrize("commit_count", ["3", "0"])
def test_missing_base_dependency_fails_and_keeps_the_pending_flag(pipeline, monkeypatch, capsys, commit_count):
    if commit_count == "0":  # resumed run of an interrupted update
        _pending_flag(pipeline.root).write_text("x", encoding="utf-8")
    monkeypatch.setattr(juc, "_missing_required_dependencies", lambda root: ["httpx"])
    receipts: list = []
    monkeypatch.setattr(juc, "_print_update_completion", receipts.append)
    catalog: list = []
    monkeypatch.setattr(juc, "_reapply_skill_catalog", lambda: catalog.append(1))

    rc = pipeline.run(gateway=True, side_effect_kwargs={"commit_count": commit_count})

    out = capsys.readouterr().out
    assert rc == 1
    assert _pending_flag(pipeline.root).exists(), "the next run must reinstall"
    assert receipts == [] and catalog == []
    assert juc._SUCCESS_LINE not in out
    assert "httpx" in out and "`janitor update`" in out
    assert ("exit_code", False) in pipeline.events and ("exit_code", True) not in pipeline.events
    marker = json.loads((pipeline.root / "update-incomplete.json").read_text(encoding="utf-8"))
    assert marker["failed_step"] == "python_deps"


def test_python_deps_marker_carries_the_stash_to_the_next_run(pipeline, monkeypatch):
    monkeypatch.setattr(juc, "_missing_required_dependencies", lambda root: ["httpx"])
    monkeypatch.setattr(juc, "_stash_local_changes_if_needed", lambda *a, **kw: "stash-ref-1")
    restored: list = []
    monkeypatch.setattr(juc, "_restore_stashed_changes", lambda *a, **kw: restored.append(a[2]) or True)

    assert pipeline.run() == 1
    assert restored == [], "a failed run does not re-apply the stash"
    assert juc._read_persisted_marker() == "stash-ref-1"


# ---------------------------------------------------------------------------
# Fleet still on old code (design 3.5)
# ---------------------------------------------------------------------------


def test_a_gateway_left_on_old_code_fails_with_the_command_to_restart_it(pipeline, monkeypatch, capsys):
    monkeypatch.setattr(
        juc, "_stale_gateways_after_restart",
        lambda outcome: [
            {"profile": "default", "pid": 4242, "state": "stale"},
            {"profile": "investigador", "pid": 4343, "state": "stale"},
        ],
    )

    rc = pipeline.run(gateway=True)

    out = capsys.readouterr().out
    assert rc == 1
    assert "janitor gateway restart" in out
    assert "janitor -p investigador gateway restart" in out
    assert juc._SUCCESS_LINE not in out
    exit_codes = [e[1] for e in pipeline.events if e[0] == "exit_code"]
    assert exit_codes[-1] is False, "the gateway's result file must not stay at success"


def test_a_healthy_restart_keeps_the_update_successful(pipeline, capsys):
    assert pipeline.run() == 0
    assert juc._SUCCESS_LINE in capsys.readouterr().out


def test_no_restart_means_nothing_to_verify(pipeline, monkeypatch):
    probes: list = []
    monkeypatch.setattr(juc, "_stale_gateways_after_restart", lambda outcome: probes.append(outcome) or [])
    monkeypatch.setattr(juc, "_gateways_in_update_scope", lambda: [])

    assert pipeline.run() == 0
    assert probes == []


def test_stale_probe_keeps_only_stale_rows_and_waits_when_gateways_were_restarted(monkeypatch):
    import hermes_cli.update_cmd_fleet as fleet

    calls: list = []
    rows = [
        {"profile": "default", "pid": 1, "state": "current"},
        {"profile": "a", "pid": 2, "state": "stale"},
        {"profile": "b", "pid": 3, "state": "restart_pending"},
        {"profile": "c", "pid": 4, "state": "down"},
    ]
    monkeypatch.setattr(fleet, "_collect_fleet_snapshot", lambda restart, expected: calls.append(expected) or rows)

    restarted = SimpleNamespace(restarted_services=["janitor-gateway"], killed_pids=set(), relaunched_profiles=[])
    idle = SimpleNamespace(restarted_services=[], killed_pids=set(), relaunched_profiles=[])

    assert juc._stale_gateways_after_restart(restarted) == [rows[1]]
    assert juc._stale_gateways_after_restart(idle) == [rows[1]]
    assert calls == [True, False]


def test_stale_probe_failure_is_a_warning_not_a_failed_update(monkeypatch, capsys):
    import hermes_cli.update_cmd_fleet as fleet

    def broken(restart, expected):
        raise RuntimeError("probe exploded")

    monkeypatch.setattr(fleet, "_collect_fleet_snapshot", broken)

    assert juc._stale_gateways_after_restart(SimpleNamespace()) == []
    assert "probe exploded" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# Resuming an interrupted update (deps-pending flag)
# ---------------------------------------------------------------------------


def _record_tail(monkeypatch) -> list:
    calls: list = []
    monkeypatch.setattr(juc, "_install_python_dependencies", lambda root: calls.append("deps"))
    monkeypatch.setattr(juc, "_reapply_skill_catalog", lambda: calls.append("catalog"))
    return calls


def test_flag_on_a_current_tree_reinstalls_dependencies_and_catalog_then_clears(pipeline, monkeypatch):
    _pending_flag(pipeline.root).write_text("x", encoding="utf-8")
    calls = _record_tail(monkeypatch)

    rc = pipeline.run(side_effect_kwargs={"commit_count": "0"})

    assert rc == 0
    assert calls == ["deps", "catalog"]
    assert not _pending_flag(pipeline.root).exists()


def test_current_tree_without_flag_installs_nothing(pipeline, monkeypatch):
    calls = _record_tail(monkeypatch)

    assert pipeline.run(side_effect_kwargs={"commit_count": "0"}) == 0
    assert calls == []


def test_failed_pull_back_at_the_start_clears_the_flag(pipeline, monkeypatch):
    calls = _record_tail(monkeypatch)

    rc = pipeline.run(side_effect_kwargs={"ff_only_fails": True, "reset_fails": True})

    assert rc == 1
    assert calls == []
    assert not _pending_flag(pipeline.root).exists()


def _head_moves(side_effect):
    """``git rev-parse HEAD`` answers the pre-pull SHA once, then a new one."""
    answers = iter(["aaa111\n"])

    def run(cmd, **kwargs):
        argv = [str(c) for c in cmd]
        if argv[-2:] == ["rev-parse", "HEAD"]:
            return SimpleNamespace(returncode=0, stdout=next(answers, "bbb222\n"), stderr="")
        return side_effect(cmd, **kwargs)

    return run


def test_failed_pull_that_left_new_code_keeps_the_flag(monkeypatch, tmp_path):
    """Syntax rollback that could not reset: the tree is not where it started."""
    from tests.janitor.test_janitor_update_core import _stub_helpers

    _stub_pipeline_helpers(monkeypatch, tmp_path)
    _stub_helpers(monkeypatch, tmp_path, syntax_break_in="janitor/cli.py")
    monkeypatch.setattr(juc, "get_hermes_home", lambda: tmp_path)
    side_effect, _ = _make_side_effect(reset_fails=True)
    monkeypatch.setattr(juc.subprocess, "run", _head_moves(side_effect))

    rc = juc.run_janitor_update(SimpleNamespace())

    assert rc == 1
    assert _pending_flag(tmp_path).exists()
