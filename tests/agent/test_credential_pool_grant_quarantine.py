"""A rejected OAuth grant cannot remove an independent login with the same source."""
import pytest
from agent.credential_pool import CredentialPool, PooledCredential


@pytest.mark.parametrize('token', ['rejected-grant', ''])
def test_quarantine_removes_only_owned_grant(monkeypatch, token):
    def row(identity, refresh):
        return PooledCredential(provider='openai-codex', id=identity, source='device_code',
                                auth_type='oauth', label=identity, priority=1, refresh_token=refresh, access_token='fixture')
    rejected = row('rejected', token)
    sibling = row('sibling', token)
    healthy = row('healthy', 'independent')
    pool = CredentialPool('openai-codex', [rejected, sibling, healthy])
    removed = []
    monkeypatch.setattr(pool, '_persist', lambda **kwargs: removed.extend(kwargs['removed_ids']))
    pool._quarantine_sources(rejected, {'device_code'})
    assert removed == (['rejected', 'sibling'] if token else ['rejected'])
    assert 'healthy' in [entry.id for entry in pool.entries()]
    assert healthy.refresh_token == 'independent'
