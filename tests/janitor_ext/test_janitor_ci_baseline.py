"""The approved sync baseline remains fail-closed and keeps the existing gates."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest

from janitor_ext import ci_baseline
from scripts.code_health import cli as health
from scripts.code_health.ruff_runner import pinned_version
from scripts.ci import check_blob_size as blobs

ROOT = Path(__file__).resolve().parents[2]


def git(repo, *args):
    return subprocess.run(
        ['git', *args], cwd=repo, check=True, capture_output=True, text=True,
        encoding='utf-8', timeout=30,
    ).stdout.strip()


def write(repo, path, content):
    target = repo / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content if isinstance(content, bytes) else content.encode('utf-8'))


def commit(repo, message):
    git(repo, 'add', '.')
    git(repo, 'commit', '-m', message)
    return git(repo, 'rev-parse', 'HEAD')


@dataclass
class History:
    repo: Path
    base: str
    engine: str
    head: str


@pytest.fixture
def history(tmp_path, monkeypatch):
    repo = tmp_path / 'repo'
    repo.mkdir()
    git(repo, 'init', '-b', 'fork')
    git(repo, 'config', 'user.email', 'fixture@example.invalid')
    git(repo, 'config', 'user.name', 'CI fixture')
    git(repo, 'config', 'core.autocrlf', 'false')
    git(repo, 'config', 'core.hooksPath', str(tmp_path / 'no-hooks'))
    write(repo, 'scripts/code_health/config.py', 'ENFORCEMENT = "blocking"\n')
    write(repo, 'scripts/ci/profile_scope_patterns.json',
          (ROOT / 'scripts/ci/profile_scope_patterns.json').read_bytes())
    write(repo, 'pyproject.toml', f'[dependency-groups]\ndev = ["ruff=={pinned_version(ROOT)}"]\n')
    common = commit(repo, 'common')
    write(repo, 'fork.txt', 'fork baseline\n')
    base = commit(repo, 'fork before sync')
    git(repo, 'checkout', '-b', 'engine', common)
    write(repo, 'engine.bin', b'\0' + b'e' * blobs.MAX_BYTES)
    engine = commit(repo, 'approved engine')
    git(repo, 'checkout', 'fork')
    git(repo, 'merge', '--no-ff', 'engine', '-m', 'sync approved engine')
    head = git(repo, 'rev-parse', 'HEAD')
    monkeypatch.setattr(ci_baseline, 'APPROVED_ENGINE', engine)
    return History(repo, base, engine, head)


def test_sync_selects_exact_engine_and_keeps_pr_switch(history):
    selected = ci_baseline.select_baseline(history.repo, history.base)
    assert selected.health_base == history.engine
    assert selected.pr_base == history.base
    assert selected.engine == history.engine


def test_post_sync_pr_uses_its_own_base(history):
    write(history.repo, 'next.txt', 'new change\n')
    commit(history.repo, 'next PR')
    assert ci_baseline.select_baseline(history.repo, history.head).health_base == history.head


def test_engine_must_be_present_and_ancestor(history, monkeypatch):
    monkeypatch.setattr(ci_baseline, 'APPROVED_ENGINE', '0' * 40)
    with pytest.raises(RuntimeError):
        ci_baseline.select_baseline(history.repo, history.base)
    monkeypatch.setattr(ci_baseline, 'APPROVED_ENGINE', history.engine)
    git(history.repo, 'checkout', '--detach', history.base)
    with pytest.raises(RuntimeError, match='ancestor'):
        ci_baseline.select_baseline(history.repo, history.base)


def test_pr_base_must_be_ancestor(history):
    git(history.repo, 'checkout', '-b', 'unrelated', history.base)
    write(history.repo, 'other.txt', 'not merged\n')
    unrelated = commit(history.repo, 'unmerged base')
    git(history.repo, 'checkout', 'fork')
    with pytest.raises(RuntimeError, match='ancestor'):
        ci_baseline.select_baseline(history.repo, unrelated)


def test_shallow_history_fails_closed(history, tmp_path):
    clone = tmp_path / 'shallow'
    git(tmp_path, 'clone', '--depth=1', history.repo.as_uri(), str(clone))
    with pytest.raises(RuntimeError, match='shallow'):
        ci_baseline.select_baseline(clone, 'HEAD')


def test_cli_cannot_select_a_different_engine(history):
    with pytest.raises(SystemExit) as error:
        ci_baseline.main(['health', '--base', history.base, '--engine', history.engine])
    assert error.value.code == 2


def test_identical_engine_blob_is_inherited_even_after_rename(history):
    git(history.repo, 'mv', 'engine.bin', 'renamed.bin')
    head = commit(history.repo, 'rename inherited content')
    selected = ci_baseline.select_baseline(history.repo, history.base)
    assert blobs.find_offenders(history.repo, history.base, head)
    assert ci_baseline.blob_offenders(history.repo, selected, head) == []


@pytest.mark.parametrize('path', ['engine.bin', 'new.bin', 'new.txt'])
def test_new_large_content_is_rejected_regardless_of_name(history, path):
    write(history.repo, path, (b'\0' if path.endswith('.bin') else b'') + b'x' * (blobs.MAX_BYTES + 1))
    head = commit(history.repo, 'new bytes')
    selected = ci_baseline.select_baseline(history.repo, history.base)
    assert [item.path for item in ci_baseline.blob_offenders(history.repo, selected, head)] == [path]


def test_one_changed_byte_in_engine_blob_is_not_inherited(history):
    content = bytearray((history.repo / 'engine.bin').read_bytes())
    content[-1] = ord('x')
    write(history.repo, 'engine.bin', bytes(content))
    selected = ci_baseline.select_baseline(history.repo, history.base)
    assert [item.path for item in ci_baseline.blob_offenders(history.repo, selected, None)] == ['engine.bin']


def test_untracked_large_file_and_existing_allowlist_rules_are_preserved(history):
    write(history.repo, 'untracked.bin', b'\0' + b'x' * blobs.MAX_BYTES)
    selected = ci_baseline.select_baseline(history.repo, history.base)
    assert [item.path for item in ci_baseline.blob_offenders(history.repo, selected, None)] == ['untracked.bin']
    write(history.repo, blobs.ALLOWLIST, 'untracked.bin\n')
    assert ci_baseline.blob_offenders(history.repo, selected, None) == []


def test_missing_ancestry_returns_error_without_running_health(history, monkeypatch, capsys):
    monkeypatch.setattr(ci_baseline, 'APPROVED_ENGINE', '0' * 40)
    assert ci_baseline.main(['health', '--base', history.base, '--repo', str(history.repo)]) == 2
    assert 'janitor CI baseline:' in capsys.readouterr().err


def test_health_keeps_rules_and_reads_enforcement_from_pr_base(history, capsys):
    # The judged tree cannot turn off the gate; the PR base owns ENFORCEMENT.
    write(history.repo, 'scripts/code_health/config.py', 'ENFORCEMENT = "off"\n')
    write(history.repo, 'unsafe.py', 'def bad():\n    return never_defined_name\n')
    commit(history.repo, 'head tries to disable check')
    assert ci_baseline.main(['health', '--base', history.base, '--repo', str(history.repo)]) == 1
    assert 'F821' in capsys.readouterr().out


def test_engine_enforcement_does_not_override_pr_base(history, capsys):
    git(history.repo, 'checkout', 'engine')
    write(history.repo, 'scripts/code_health/config.py', 'ENFORCEMENT = "off"\n')
    engine = commit(history.repo, 'engine enforcement off')
    git(history.repo, 'checkout', 'fork')
    git(history.repo, 'merge', 'engine', '-m', 'engine advance')
    write(history.repo, 'unsafe.py', 'def bad():\n    return never_defined_name\n')
    commit(history.repo, 'fork bug')
    # Pure fixture selection: no public CLI override exists for the real pin.
    from unittest.mock import patch
    with patch.object(ci_baseline, 'APPROVED_ENGINE', engine):
        assert ci_baseline.main(['health', '--base', history.base, '--repo', str(history.repo)]) == 1
    assert 'F821' in capsys.readouterr().out


def complexity(value):
    return 'def work(values):\n    result = 0\n' + ''.join(
        f'    if values[{i}]:\n        result += 1\n' for i in range(value - 1)
    ) + '    return result\n'


def test_approved_sync_cap_tradeoff_and_post_sync_ratchet(history, capsys, monkeypatch):
    git(history.repo, 'checkout', '-b', 'old-fork', history.base)
    write(history.repo, 'metric.py', complexity(25))
    old_base = commit(history.repo, 'old fork cap 25')
    git(history.repo, 'checkout', 'engine')
    write(history.repo, 'metric.py', complexity(30))
    engine = commit(history.repo, 'engine cap 30')
    git(history.repo, 'checkout', 'old-fork')
    # The merge conflict is resolved deliberately to the approved candidate, cap 28.
    subprocess.run(['git', 'merge', '--no-commit', 'engine'], cwd=history.repo,
                   capture_output=True, timeout=30, check=False)
    write(history.repo, 'metric.py', complexity(28))
    synced = commit(history.repo, 'sync resolved at 28')
    monkeypatch.setattr(ci_baseline, 'APPROVED_ENGINE', engine)
    assert health.run(history.repo, old_base, synced) == 1
    assert ci_baseline.main(['health', '--base', old_base, '--repo', str(history.repo)]) == 0
    write(history.repo, 'metric.py', complexity(29))
    commit(history.repo, 'post-sync regression')
    assert ci_baseline.main(['health', '--base', synced, '--repo', str(history.repo)]) == 1
    assert 'CC' in capsys.readouterr().out


@pytest.mark.parametrize(('mode', 'expected'), [('blocking', 1), ('advisory', 0), ('off', 0)])
def test_each_pr_base_enforcement_mode_is_preserved(history, mode, expected):
    git(history.repo, 'checkout', '-b', 'policy', history.base)
    write(history.repo, 'scripts/code_health/config.py', f'ENFORCEMENT = "{mode}"\n')
    write(history.repo, 'policy.txt', mode)
    policy_base = commit(history.repo, 'base enforcement policy')
    git(history.repo, 'merge', '--no-ff', 'engine', '-m', 'sync under base policy')
    write(history.repo, 'unsafe.py', 'def bad():\n    return never_defined_name\n')
    commit(history.repo, 'new finding')
    assert ci_baseline.main(['health', '--base', policy_base, '--repo', str(history.repo)]) == expected


def test_blob_cli_reports_new_violation_and_keeps_summary(history, tmp_path, monkeypatch):
    summary = tmp_path / 'summary.md'
    monkeypatch.setenv('GITHUB_STEP_SUMMARY', str(summary))
    args = ['blob-size', '--base', history.base, '--repo', str(history.repo)]
    assert ci_baseline.main(args) == 0
    write(history.repo, 'new.bin', b'\0' + b'n' * blobs.MAX_BYTES)
    assert ci_baseline.main(args) == 1
    assert '`new.bin`' in summary.read_text(encoding='utf-8')


def test_production_pin_and_workflow_entrypoints_are_fixed():
    from ruamel.yaml import YAML
    yaml = YAML(typ="safe")
    assert ci_baseline.APPROVED_ENGINE == 'd923a5eb487a17c0a68801bba9ef0f56c81040a8'
    for filename, job_name, gate in [
        ('lint.yml', 'code-health', 'health'),
        ('blob-size-check.yml', 'check-blob-size', 'blob-size'),
    ]:
        workflow = yaml.load((ROOT / '.github/workflows' / filename).read_text(encoding='utf-8'))
        steps = workflow['jobs'][job_name]['steps']
        checkout = next(step for step in steps if step.get('uses', '').startswith('actions/checkout@'))
        assert checkout['with']['fetch-depth'] == 0
        assert any(step.get('run', '').endswith(
            f'-m janitor_ext.ci_baseline {gate} --base HEAD^1'
        ) for step in steps)
