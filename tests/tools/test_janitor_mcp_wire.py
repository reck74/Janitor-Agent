"""Preserve MCP metadata and isolate HTTP auth evidence at the transport boundary."""

import json
from types import SimpleNamespace

import pytest
from mcp.shared.message import ClientMessageMetadata, SessionMessage
from mcp.types import JSONRPCRequest
from pydantic import RootModel

from tools.mcp_tool_errors import MCPHTTPAuthenticationError, _is_auth_error
from tools.mcp_tool_wire import RequestMetadataStream, classify_http_auth_failure, without_empty_request_meta


@pytest.mark.parametrize('meta', [{}, None])
@pytest.mark.parametrize('wrapped', [False, True])
def test_empty_protocol_metadata_is_removed_without_touching_tool_arguments(meta, wrapped):
    params = {'name': 'probe', 'arguments': {'_meta': {}, 'value': 1}, '_meta': meta}
    request = JSONRPCRequest(jsonrpc='2.0', id=0, method='tools/call', params=params)
    message = RootModel[JSONRPCRequest](request) if wrapped else request
    metadata = ClientMessageMetadata(resumption_token='resume-canary')
    original = SessionMessage(message=message, metadata=metadata)
    copied = without_empty_request_meta(original)
    clean = getattr(copied.message, 'root', copied.message)
    assert clean.params == {'name': 'probe', 'arguments': {'_meta': {}, 'value': 1}}
    assert clean.id == request.id and copied.metadata is metadata
    assert request.params == params and copied is not original


@pytest.mark.parametrize('meta', [{'progressToken': 0}, {'traceparent': 'canary'}, {'vendor/key': {}}])
def test_meaningful_protocol_metadata_is_preserved(meta):
    request = JSONRPCRequest(jsonrpc='2.0', id=1, method='tools/list', params={'_meta': meta})
    original = SessionMessage(message=request)
    assert without_empty_request_meta(original) is original


@pytest.mark.asyncio
async def test_stream_adapter_delivers_request_and_preserves_close():
    import anyio
    send, receive = anyio.create_memory_object_stream(1)
    request = JSONRPCRequest(jsonrpc='2.0', id=1, method='tools/list', params={'_meta': {}})
    async with RequestMetadataStream(send) as stream:
        await stream.send(SessionMessage(message=request))
        assert (await receive.receive()).message.params == {}
    with pytest.raises(anyio.EndOfStream):
        await receive.receive()
    await receive.aclose()


class FoldedMCPError(RuntimeError):
    error = SimpleNamespace(code=-32603)


def folded_error():
    return FoldedMCPError('Server returned an error response')


@pytest.mark.asyncio
async def test_fresh_post_401_is_an_auth_error_without_exposing_response_secrets():
    server = SimpleNamespace(_http_rejection={})
    with pytest.raises(MCPHTTPAuthenticationError) as result:
        async with classify_http_auth_failure(server):
            server._http_rejection.update(status=401, method='POST', body='token=private', url='https://secret')
            raise folded_error()
    assert _is_auth_error(result.value)
    assert '401' in str(result.value) and 'private' not in str(result.value) and 'secret' not in str(result.value)


@pytest.mark.asyncio
@pytest.mark.parametrize('record', [{}, {'status': 400, 'method': 'POST'}, {'status': 401, 'method': 'GET'}])
async def test_unrelated_or_stale_http_rejections_do_not_change_error_type(record):
    server = SimpleNamespace(_http_rejection={'status': 401, 'method': 'POST'})
    error = folded_error()
    with pytest.raises(FoldedMCPError) as result:
        async with classify_http_auth_failure(server):
            server._http_rejection.update(record)
            raise error
    assert result.value is error


@pytest.mark.asyncio
async def test_auth_record_does_not_replace_a_non_mcp_error():
    server = SimpleNamespace(_http_rejection={})
    with pytest.raises(ValueError, match='parsing'):
        async with classify_http_auth_failure(server):
            server._http_rejection.update(status=401, method='POST')
            raise ValueError('parsing')


def test_uncacheable_image_notice_does_not_hide_structured_result():
    from tools.mcp_tool_handlers import _render_call_tool_result
    result = SimpleNamespace(content=[SimpleNamespace(type='image', mimeType='image/png', data='badb64!')],
                             structuredContent={'answer': 42}, isError=False, meta=None)
    rendered = json.loads(_render_call_tool_result(result, 'test'))
    assert 'image' in rendered['result']
    assert rendered['structuredContent'] == {'answer': 42}
