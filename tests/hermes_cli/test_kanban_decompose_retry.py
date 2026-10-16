"""Automatic decomposition spends a durable bounded budget; humans can retry."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from hermes_cli import kanban_db as kb, kanban_db_connect as kbc
from hermes_cli import kanban_decompose as decomp
from hermes_cli import kanban_decompose_retry as retry


@pytest.fixture
def card(tmp_path, monkeypatch):
    home = tmp_path / '.hermes'
    home.mkdir()
    monkeypatch.setenv('HERMES_HOME', str(home))
    monkeypatch.setattr(Path, 'home', lambda: tmp_path)
    kb.init_db()
    with kbc.connect_closing() as conn:
        return kb.create_task(conn, title='rough idea', triage=True)


def test_budget_survives_new_connections_and_cools_down(card, monkeypatch):
    clock = [1000]
    monkeypatch.setattr(retry.time, 'time', lambda: clock[0])
    for attempt in range(retry.MAX_AUTO_ATTEMPTS):
        assert retry.reserve_attempt(card) == ''
        assert retry.reserve_attempt(card)
        clock[0] += retry.RETRY_DELAY_SECONDS * 2 ** attempt
    clock[0] += 100000
    assert 'budget exhausted' in retry.reserve_attempt(card)
    with kbc.connect_closing() as conn:
        assert kb.get_task(conn, card).status == 'triage'
        count = conn.execute("SELECT count(*) FROM task_events WHERE task_id=? AND kind='auto_decompose_attempted'", (card,)).fetchone()[0]
        assert count == retry.MAX_AUTO_ATTEMPTS
        conn.execute('UPDATE tasks SET body=? WHERE id=?', ('new instructions', card))
        conn.commit()
    assert retry.reserve_attempt(card) == ''


def test_concurrent_dispatchers_reserve_only_one_call(card):
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(retry.reserve_attempt, [card, card]))
    assert results.count('') == 1
    assert any('cooling down' in reason for reason in results)


def test_manual_decompose_can_retry_after_automatic_budget(card, monkeypatch):
    clock = [1000]
    monkeypatch.setattr(retry.time, 'time', lambda: clock[0])
    for _ in range(retry.MAX_AUTO_ATTEMPTS):
        assert retry.reserve_attempt(card) == ''
        clock[0] += 1000
    calls = []
    def aux(*args, **kwargs):
        calls.append(args)
        return '{"fanout":false,"title":"repaired task","body":"accepted instructions"}', ''
    monkeypatch.setattr(decomp, '_call_aux', aux)
    assert not decomp.decompose_task(card, automatic=True).ok
    assert calls == []
    assert decomp.decompose_task(card).ok
    assert len(calls) == 1
