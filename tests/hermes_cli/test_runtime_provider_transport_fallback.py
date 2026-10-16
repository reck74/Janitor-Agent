"""Only credential/network failures may enter the configured resolution fallback chain."""
import httpx
import pytest
from hermes_cli import runtime_provider as rp


@pytest.mark.parametrize('error', [ConnectionRefusedError('fixture offline'), TimeoutError('fixture timeout'),
                                  httpx.ConnectError('fixture offline')])
def test_transport_error_uses_explicit_fallback_and_preserves_original_without_one(monkeypatch, error):
    calls = []
    def resolve(**kwargs):
        calls.append(kwargs['requested'])
        if kwargs['requested'] == 'nous':
            raise error
        return {'provider': 'custom', 'api_key': 'fixture', 'base_url': 'http://127.0.0.1:1/v1'}
    monkeypatch.setattr(rp, 'resolve_runtime_provider', resolve)
    config = {'fallback_providers': [{'provider': 'custom', 'model': 'fixture-model'}]}
    runtime, entry = rp.resolve_runtime_with_fallback(config, requested='nous')
    assert calls == ['nous', 'custom']
    assert runtime['provider'] == 'custom' and entry['model'] == 'fixture-model'
    with pytest.raises(type(error)) as caught:
        rp.resolve_runtime_with_fallback({}, requested='nous')
    assert caught.value is error


@pytest.mark.parametrize('error', [ValueError('unknown provider'), PermissionError('private file')])
def test_configuration_or_filesystem_errors_do_not_reroute(monkeypatch, error):
    calls = []
    def resolve(**kwargs):
        calls.append(kwargs['requested'])
        raise error
    monkeypatch.setattr(rp, 'resolve_runtime_provider', resolve)
    with pytest.raises(type(error)) as caught:
        rp.resolve_runtime_with_fallback({'fallback_providers': [{'provider': 'custom', 'model': 'fixture'}]}, requested='nous')
    assert caught.value is error
    assert calls == ['nous']
