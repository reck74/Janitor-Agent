"""The fork's fast CI gate and reusable workflow interfaces must remain executable."""

from pathlib import Path

import pytest
from ruamel.yaml import YAML

from janitor_ext.ci_contracts import janitor_test_files, workflow_interface_errors
from janitor_ext.fork_audit import fork_diff_violations

ROOT = Path(__file__).resolve().parent.parent


def _workflows():
    yaml = YAML(typ="safe")
    return {p.relative_to(ROOT).as_posix(): yaml.load(p.read_text(encoding="utf-8"))
            for p in (ROOT / ".github/workflows").iterdir() if p.suffix in {".yml", ".yaml"}}


def test_manifest_includes_all_janitor_tests_once():
    files = janitor_test_files(ROOT)
    assert files
    assert all("janitor" in Path(name).name or name in {
        "tests/hermes_cli/test_mcp_router_discover.py", "tests/hermes_cli/test_mcp_router_logs.py",
    } for name in files)


def test_reusable_workflow_interfaces_are_valid():
    assert not workflow_interface_errors(_workflows())


def test_workflow_expressions_do_not_embed_a_second_expression():
    import re

    def check(value, location):
        if isinstance(value, dict):
            for key, child in value.items():
                check(child, f"{location}.{key}")
        elif isinstance(value, list):
            for index, child in enumerate(value):
                check(child, f"{location}[{index}]")
        elif isinstance(value, str):
            for match in re.finditer(r"\$\{\{(.*?)\}\}", value, re.DOTALL):
                assert "${{" not in match.group(1), f"Nested Actions expression: {location}"

    for path, workflow in _workflows().items():
        check(workflow, path)


def test_windows_bundle_runners_resolve_architecture_and_configured_overrides():
    from tests.ci import _gha_expr as gha

    workflows = _workflows()
    targets = (
        ("desktop-bundle-smoke.yml", "windows", "arch"),
        ("install-e2e-windows-run.yml", "bundled-e2e", "bundle-arch"),
    )
    for filename, job, input_name in targets:
        expression = workflows[f".github/workflows/{filename}"]["jobs"][job]["runs-on"]
        for arch, key, fallback in (
            ("arm64", "JANITOR_WINDOWS_ARM_RUNNER", "windows-11-arm"),
            ("x64", "JANITOR_WINDOWS_RUNNER", "windows-latest"),
        ):
            for variables in ({}, {key: ""}, {key: f"janitor-custom-{arch}"}):
                context = {"inputs": {input_name: arch}, "vars": variables}
                assert gha.evaluate(expression, context) == (variables.get(key) or fallback)


def test_every_fork_python_gate_uses_one_manifest_runner():
    workflows = _workflows()
    for path, job in ((".github/workflows/tests.yml", "test"),
                      (".github/workflows/janitor-ci.yml", "python-tests"),
                      (".github/workflows/janitor-ci.yml", "os-compat"),
                      (".github/workflows/tests-os.yml", "os-tests")):
        commands = "\n".join(step.get("run", "") for step in workflows[path]["jobs"][job]["steps"])
        assert "scripts/run_janitor_tests.py" in commands
        assert "-m pytest" not in commands


def test_upstream_full_suite_is_gated_to_sync_or_dispatch():
    job = _workflows()[".github/workflows/tests.yml"]["jobs"]["upstream-sync-verify"]
    condition = job["if"]
    assert "workflow_dispatch" in condition and "push" in condition
    assert "chore(sync):" in condition and "fix(sync):" in condition and "upstream-sync-" in condition
    assert "pull_request" not in condition


def test_tui_bundle_and_tests_are_both_required():
    steps = _workflows()[".github/workflows/janitor-ci.yml"]["jobs"]["react-tests"]["steps"]
    commands = "\n".join(step.get("run", "") for step in steps)
    assert "npm run build --workspace ui-tui" in commands
    assert "npm run test --workspace ui-tui" in commands
    # The main bundle aliases Ink source; Vitest imports the generated module.
    # A clean checkout therefore needs both outputs before tests can collect.
    ink = commands.index("npm run build:ink --workspace ui-tui")
    assert ink < commands.index("npm run typecheck --workspace ui-tui")
    assert ink < commands.index("npm run test --workspace ui-tui")
    assert "npm run lint --workspace ui-tui" in commands


def test_interface_validation_detects_both_original_ci_regressions():
    workflows = {
        "caller.yml": {"jobs": {"tests": {"uses": "./tests.yml", "with": {"slice_count": 12}},
                                 "scan": {"uses": "./scan.yml"}}},
        "tests.yml": {"on": {"workflow_call": None}},
        "scan.yml": {"on": {"workflow_call": {"inputs": {"mcp_catalog": {"required": True}}}}},
    }
    errors = workflow_interface_errors(workflows)
    assert any("undeclared input slice_count" in error for error in errors)
    assert any("missing required input mcp_catalog" in error for error in errors)


def test_merge_audit_rejects_core_renames_and_misplaced_skills():
    diff = '''diff --git a/cli.py b/cli.py
--- a/cli.py
+++ b/cli.py
@@ -1 +1 @@
-from hermes_cli import main
+from janitor_cli import main
diff --git a/skills/devops/janitor-example/SKILL.md b/skills/devops/janitor-example/SKILL.md
--- /dev/null
+++ b/skills/devops/janitor-example/SKILL.md
@@ -0,0 +1 @@
+name: janitor-example
'''
    errors = fork_diff_violations(diff)
    assert any("directive 1" in error for error in errors)
    assert any("directive 3" in error for error in errors)


def test_merge_audit_preserves_approved_banner_and_isolated_extensions():
    diff = '''diff --git a/hermes_cli/banner.py b/hermes_cli/banner.py
--- a/hermes_cli/banner.py
+++ b/hermes_cli/banner.py
@@ -1 +1 @@
-title = "Hermes Agent"
+title = "THE JANITOR"
diff --git a/janitor_ext/example.py b/janitor_ext/example.py
--- /dev/null
+++ b/janitor_ext/example.py
@@ -0,0 +1 @@
+from janitor_cli import main
'''
    assert not fork_diff_violations(diff)


def test_native_pr_gate_uses_manifest_and_acceptance_keeps_full_os_selection():
    from tests.ci import _gha_expr as gha
    workflows = _workflows()
    job = workflows[".github/workflows/tests-os.yml"]["jobs"]["os-tests"]
    fork = next(step for step in job["steps"] if "scripts/run_janitor_tests.py" in step.get("run", ""))
    upstream = next(step for step in job["steps"] if "scripts/ci/list_os_marked_tests.py" in step.get("run", ""))
    assert gha.condition(fork["if"], {"inputs": {"upstream_verify": False}})
    assert not gha.condition(upstream["if"], {"inputs": {"upstream_verify": False}})
    assert not gha.condition(fork["if"], {"inputs": {"upstream_verify": True}})
    assert gha.condition(upstream["if"], {"inputs": {"upstream_verify": True}})
    selector = workflows[".github/workflows/ci.yaml"]["jobs"]["tests-os"]["with"]["upstream_verify"]
    assert not gha.evaluate(selector, {"inputs": {}, "github": {"event_name": "pull_request"}})
    assert gha.evaluate(selector, {"inputs": {}, "github": {"event_name": "workflow_dispatch"}})


def test_actions_prefix_evaluator_keeps_case_insensitivity_and_scalar_coercion():
    from tests.ci import _gha_expr as gha
    assert gha.evaluate("startsWith('CHORE(sync): Hermes', 'chore(sync):')", {})
    assert not gha.evaluate("startsWith('docs: chore(sync): example', 'chore(sync):')", {})
    assert gha.evaluate("startsWith(42, '4')", {})
    assert not gha.evaluate("startsWith(null, 'chore(sync):')", {})



def test_runner_env_and_argument_slices_cover_the_suite_once(monkeypatch):
    """Exercise the real parser: consuming the env must not erase the chosen slice."""
    import importlib.util
    import sys
    from concurrent import futures

    spec = importlib.util.spec_from_file_location("janitor_runner_slice_probe", ROOT / "scripts/run_tests_parallel.py")
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    files = sorted((ROOT / "tests").rglob("test_*.py"))
    selected = []
    real_slice = runner._slice_files

    class BeforeWorkers(Exception):
        pass

    def capture_slice(files, index, count, durations, repo):
        result = real_slice(files, index, count, durations, repo)
        selected.append(set(result))
        return result

    def stop_before_workers(*args, **kwargs):
        raise BeforeWorkers

    monkeypatch.setattr(runner, "_select_files", lambda *args: (files, []))
    monkeypatch.setattr(runner, "_approximately_count_tests", lambda *args: dict.fromkeys(files, 1))
    monkeypatch.setattr(runner, "_load_durations", lambda *args: {})
    monkeypatch.setattr(runner, "_slice_files", capture_slice)
    monkeypatch.setattr(futures, "ThreadPoolExecutor", stop_before_workers)
    # The runner imports the executor directly on current upstream.
    if hasattr(runner, "ThreadPoolExecutor"):
        monkeypatch.setattr(runner, "ThreadPoolExecutor", stop_before_workers)
    for channel in ("environment", "argument"):
        selected.clear()
        for index in range(1, 7):
            argv = ["run_tests_parallel.py", "--jobs", "1"]
            if channel == "environment":
                monkeypatch.setenv("HERMES_TEST_SLICE", f"{index}/6")
            else:
                # Explicit CLI choice wins over inherited CI environment.
                monkeypatch.setenv("HERMES_TEST_SLICE", "1/2")
                argv += ["--slice", f"{index}/6"]
            monkeypatch.setattr(sys, "argv", argv)
            try:
                runner.main()
            except BeforeWorkers:
                pass
            assert "HERMES_TEST_SLICE" not in runner.os.environ
        assert len(selected) == 6, f"{channel}: the selected slice was lost before execution"
        assert set.union(*selected) == set(files)
        assert sum(map(len, selected)) == len(files), f"{channel}: slices overlap"
        assert all(selected), f"{channel}: empty shard in nonempty suite"


def test_merge_audit_is_independent_of_git_diff_prefix_preferences(tmp_path, monkeypatch, capsys):
    import importlib.util
    import subprocess
    import sys

    def git(*args):
        return subprocess.check_output(["git", *args], cwd=tmp_path, text=True)

    git("init", "-q")
    git("config", "user.name", "Janitor audit fixture")
    git("config", "user.email", "audit@example.invalid")
    git("config", "diff.mnemonicPrefix", "true")
    git("config", "color.ui", "always")
    (tmp_path / "cli.py").write_text("from hermes_cli import main\n")
    git("add", "cli.py")
    git("-c", "core.hooksPath=/dev/null", "commit", "-qm", "base")
    base = git("rev-parse", "HEAD").strip()
    (tmp_path / "cli.py").write_text("from janitor_cli import main\n")
    git("add", "cli.py")
    git("-c", "core.hooksPath=/dev/null", "commit", "-qm", "violation")
    spec = importlib.util.spec_from_file_location("janitor_merge_audit_probe", ROOT / "scripts/audit_janitor_merge.py")
    audit = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(audit)
    monkeypatch.setattr(audit, "ROOT", tmp_path)
    monkeypatch.setattr(sys, "argv", ["audit_janitor_merge.py", "--base", base])
    assert audit.main() == 1
    assert "directive 1" in capsys.readouterr().err



def test_website_audit_exception_is_scoped_and_expires():
    from copy import deepcopy
    from datetime import date
    from scripts.ci.janitor_website_audit import audit_errors

    url = "https://github.com/advisories/GHSA-vfj7-8cjw-p6xm"
    report = {
        "metadata": {"vulnerabilities": {"high": 2}},
        "vulnerabilities": {
            "builder": {"severity": "high", "via": ["braces"]},
            "braces": {"severity": "high", "via": [{"name": "braces", "url": url}],
                       "nodes": ["node_modules/braces"]},
        },
    }
    policy = {"exceptions": [{"advisory": url, "package": "braces", "version": "3.0.3", "expires": "2026-10-29"}]}
    lock = {"packages": {"node_modules/braces": {"version": "3.0.3"}}}
    assert audit_errors(report, policy, lock, date(2026, 10, 15)) == []
    assert audit_errors(report, policy, lock, date(2026, 10, 30))
    changed = deepcopy(report)
    changed["vulnerabilities"]["braces"]["via"].append({"name": "braces", "url": "https://example.invalid/new-advisory"})
    assert audit_errors(changed, policy, lock, date(2026, 10, 15))
    changed = deepcopy(lock)
    changed["packages"]["node_modules/braces"]["version"] = "3.0.2"
    assert audit_errors(report, policy, changed, date(2026, 10, 15))
    assert audit_errors({"error": {"code": "ENETUNREACH"}}, policy, lock, date(2026, 10, 15))



def test_janitor_desktop_candidate_requires_its_build_and_full_acceptance():
    workflow = _workflows()[".github/workflows/janitor-desktop-linux.yml"]
    jobs = workflow["jobs"]
    build = "\n".join(step.get("run", "") for step in jobs["linux"]["steps"])
    assert "apps/desktop/janitor/build.mjs" in build
    assert "janitor-artifacts.mjs" in build and "janitor-smoke.mjs" in build
    acceptance = jobs["acceptance"]["with"]
    assert acceptance["upstream_verify"] is True
    assert acceptance["e2e"] is True and acceptance["e2e_upgrade"] is True
    assert acceptance["strict_acceptance"] == "1"
    candidate = jobs["candidate"]
    assert {"linux", "acceptance"} <= set(candidate["needs"])
    assert "workflow_dispatch" in candidate["if"] and "publish_candidate" in candidate["if"]
    commands = "\n".join(step.get("run", "") for step in candidate["steps"])
    assert "--prerelease" in commands and "re.fullmatch" in commands
    assert "--target \"$GITHUB_SHA\"" in commands
    assert "sourceDirty" in commands and "sha256sum --check" in commands


def _janitor_manifest_runner():
    import importlib.util
    spec = importlib.util.spec_from_file_location("janitor_manifest_runner_probe", ROOT / "scripts/run_janitor_tests.py")
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    return runner


@pytest.mark.platforms("windows")
def test_manifest_runner_uses_pm_git_bash_instead_of_windows_wsl_stub(tmp_path, monkeypatch):
    import json
    import subprocess
    from pm import shell

    staged = tmp_path / "tools/git-test/usr/bin/bash.exe"
    staged.parent.mkdir(parents=True)
    staged.write_text("synthetic Windows binary", encoding="utf-8")
    facts = tmp_path / "facts.json"
    facts.write_text(json.dumps({"schema": 1, "packages": {"git": {"entry": "git-test"}}}), encoding="utf-8")
    monkeypatch.setattr(shell.paths, "facts_path", lambda: facts)
    monkeypatch.setattr(shell.paths, "store_root", lambda: tmp_path / "tools")
    monkeypatch.setattr(shell.shutil, "which", lambda name: r"C:\Windows\System32\bash.exe")
    probes = []

    def start(argv, **kwargs):
        probes.append(argv)
        return subprocess.CompletedProcess(argv, 0)

    monkeypatch.setattr(shell.subprocess, "run", start)
    runner = _janitor_manifest_runner()
    monkeypatch.setattr(runner, "janitor_test_files", lambda root: ["tests/test_janitor_cli.py"])
    calls = []
    monkeypatch.setattr(runner.subprocess, "call", lambda argv, **kwargs: calls.append(argv) or 23)
    assert runner.main(["-j", "2", "--file-retries", "0"]) == 23
    assert probes and probes[0][0] == str(staged)
    assert calls == [[str(staged), str(ROOT / "scripts/run_tests.sh"), "tests/test_janitor_cli.py",
                      "-j", "2", "--file-retries", "0"]]


@pytest.mark.platforms("windows")
def test_manifest_runner_reports_unavailable_bash_but_keeps_list_accessible(tmp_path, monkeypatch, capsys):
    from pm import shell

    monkeypatch.setattr(shell, "_staged_bash", lambda: None)
    for name in ("ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA"):
        monkeypatch.setenv(name, str(tmp_path))
    monkeypatch.delenv("HERMES_GIT_BASH_PATH", raising=False)
    monkeypatch.setattr(shell.shutil, "which", lambda name: r"C:\Windows\System32\bash.exe")
    runner = _janitor_manifest_runner()
    monkeypatch.setattr(runner, "janitor_test_files", lambda root: ["tests/test_janitor_cli.py"])
    calls = []
    monkeypatch.setattr(runner.subprocess, "call", lambda *args, **kwargs: calls.append(args) or 0)
    assert runner.main([]) == 2
    assert "Bash" in capsys.readouterr().err
    assert not calls
    assert runner.main(["--list"]) == 0
    assert capsys.readouterr().out.strip() == "tests/test_janitor_cli.py"
