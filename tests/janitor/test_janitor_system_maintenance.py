"""Behaviour tests for the janitor-maintenance skill (F3-04).

The scheduled report depends on two things: the diff between two audit reports, and a
run script that stores state only under the profile home it is given. Run with:
    scripts/run_tests.sh tests/janitor/test_janitor_system_maintenance.py
"""
from __future__ import annotations

import importlib.util
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
SKILL_DIR = REPO_ROOT / "janitor" / "skills" / "system" / "janitor-maintenance"
SCRIPT = SKILL_DIR / "scripts" / "maintenance_run.py"


def _load_module():
    previous = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        spec = importlib.util.spec_from_file_location("janitor_maintenance_run", SCRIPT)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        sys.dont_write_bytecode = previous


mr = _load_module()


def _finding(fid: str, severity: str) -> dict:
    return {"id": fid, "probe": fid.split(":", 1)[0], "severity": severity, "area": "x",
            "title": fid, "evidence": "e", "suggested_fix": "f", "requires_privileges": False}


def _report(findings: list[dict], probes: dict[str, str], when: str = "2026-11-22T00:00:00+00:00") -> dict:
    return {"schema_version": 1, "generated_at": when, "probes": probes, "summary": {},
            "findings": findings, "skipped": []}


# --- frontmatter -----------------------------------------------------------------------------

def test_frontmatter_follows_authoring_standards():
    text = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
    fm = yaml.safe_load(re.match(r"^---\n(.*?)\n---\n", text, re.S).group(1))
    assert fm["name"] == SKILL_DIR.name
    assert len(fm["description"]) <= 60 and fm["description"].endswith(".")
    assert fm["platforms"] == ["linux"]
    assert fm["license"] and fm["author"] and fm["version"]
    assert fm["metadata"]["hermes"]["tags"] and fm["metadata"]["hermes"]["category"]


def test_default_audit_script_is_the_sibling_skill():
    assert mr.DEFAULT_AUDIT.is_file()
    assert mr.DEFAULT_AUDIT.parents[1].name == "janitor-system-health"


# --- diff ------------------------------------------------------------------------------------

def test_diff_classifies_every_transition():
    previous = _report([_finding("disk:space:/", "medium"), _finding("ssh:password-auth", "high"),
                        _finding("docker:reclaimable:images", "low"), _finding("updates:pending", "low"),
                        _finding("load:loadavg", "high"), _finding("kernel:info", "info")],
                       {"disk": "ok", "ssh": "ok", "docker": "ok", "updates": "ok", "load": "ok"})
    current = _report([_finding("disk:space:/", "critical"), _finding("load:loadavg", "medium"),
                       _finding("updates:pending", "low"), _finding("backups:none", "high"),
                       _finding("kernel:info", "info")],
                      {"disk": "ok", "ssh": "ok", "docker": "skipped", "updates": "ok", "load": "ok",
                       "backups": "ok"})
    d = mr.diff_reports(previous, current)
    ids = {k: [f["id"] for f in d[k]] for k in ("new", "worse", "improved", "still_open", "fixed",
                                                  "not_verified")}
    assert ids == {"new": ["backups:none"], "worse": ["disk:space:/"], "improved": ["load:loadavg"],
                   "still_open": ["updates:pending"], "fixed": ["ssh:password-auth"],
                   "not_verified": ["docker:reclaimable:images"]}
    assert d["worse"][0]["previous_severity"] == "medium"
    assert d["first_run"] is False
    assert d["counts"]["new"] == 1


def test_first_run_reports_everything_as_new_baseline():
    d = mr.diff_reports(None, _report([_finding("backups:none", "high")], {"backups": "ok"}))
    assert d["first_run"] is True and [f["id"] for f in d["new"]] == ["backups:none"]
    assert d["fixed"] == [] and d["not_verified"] == []


def test_state_dir_follows_the_profile_home():
    assert mr.resolve_state_dir(None, {"HERMES_HOME": "/srv/profiles/a"}) == Path(
        "/srv/profiles/a/janitor/system-health")
    assert mr.resolve_state_dir(None, {}) is None
    assert mr.resolve_state_dir("/x/y", {"HERMES_HOME": "/srv"}) == Path("/x/y")


# --- run script ------------------------------------------------------------------------------

FAKE_AUDIT = """import json, os, sys
print(open(os.environ["FAKE_REPORT"]).read())
"""


@pytest.fixture
def env(tmp_path: Path) -> dict:
    home = tmp_path / "profile"
    home.mkdir()
    e = dict(os.environ, HERMES_HOME=str(home), HOME=str(tmp_path / "user"))
    e.pop("HERMES_REAL_HOME", None)
    (tmp_path / "user").mkdir()
    return e


def _run(env: dict, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True,
                          env=env, timeout=300)


def test_rotation_and_diff_with_a_canned_audit(tmp_path, env):
    audit = tmp_path / "fake_audit.py"
    audit.write_text(FAKE_AUDIT)
    report = tmp_path / "report.json"
    state = Path(env["HERMES_HOME"]) / "janitor" / "system-health"
    env["FAKE_REPORT"] = str(report)

    report.write_text(json.dumps(_report([_finding("ssh:password-auth", "high")], {"ssh": "ok"}, "t1")))
    first = _run(env, "--audit-script", str(audit))
    assert first.returncode == 0, first.stderr
    assert json.loads(first.stdout)["first_run"] is True
    assert sorted(p.name for p in state.iterdir()) == ["last.json"]

    report.write_text(json.dumps(_report([], {"ssh": "ok"}, "t2")))
    second = json.loads(_run(env, "--audit-script", str(audit)).stdout)
    assert [f["id"] for f in second["fixed"]] == ["ssh:password-auth"]
    assert sorted(p.name for p in state.iterdir()) == ["last.json", "previous.json"]
    assert json.loads((state / "previous.json").read_text())["generated_at"] == "t1"

    report.write_text(json.dumps(_report([_finding("ssh:password-auth", "high")], {"ssh": "ok"}, "t3")))
    dry = json.loads(_run(env, "--audit-script", str(audit), "--no-save").stdout)
    assert [f["id"] for f in dry["new"]] == ["ssh:password-auth"] and dry["saved"] is False
    assert json.loads((state / "last.json").read_text())["generated_at"] == "t2"

    cmp = json.loads(_run(env, "--compare", str(state / "previous.json"), str(state / "last.json")).stdout)
    assert [f["id"] for f in cmp["fixed"]] == ["ssh:password-auth"]


def test_without_profile_home_it_refuses_instead_of_guessing(env):
    env.pop("HERMES_HOME")
    proc = _run(env, "--no-save")
    assert proc.returncode == 2
    assert "HERMES_HOME" in proc.stderr


@pytest.mark.linux_only
def test_real_audit_writes_only_the_state_dir(tmp_path, env):
    before = sorted(p.relative_to(tmp_path) for p in tmp_path.rglob("*"))
    proc = _run(env, "--skip", "home_usage,docker,updates")
    assert proc.returncode == 0, proc.stderr
    result = json.loads(proc.stdout)
    assert result["saved"] is True and result["first_run"] is True
    after = sorted(p.relative_to(tmp_path) for p in tmp_path.rglob("*"))
    created = {str(p) for p in set(after) - set(before)}
    assert created == {"profile/janitor", "profile/janitor/system-health",
                       "profile/janitor/system-health/last.json"}
