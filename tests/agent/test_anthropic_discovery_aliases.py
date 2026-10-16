"""Discovery alias references round-trip without rewriting argument data or stored history."""
import copy
import json
from types import SimpleNamespace

from agent.anthropic_discovery_aliases import map_discovery_arguments, map_discovery_history
from agent.transports.anthropic import AnthropicTransport


def test_discovery_references_are_resolved_but_user_data_is_unchanged(monkeypatch):
    from tools.registry import registry
    monkeypatch.setattr(registry, 'get_entry', lambda name: None)
    arguments = {'names': ['chat_history_lookup', 'context_notes']}
    response = SimpleNamespace(content=[SimpleNamespace(type='tool_use', id='a',
                               name='mcp__tool_describe', input=arguments)], stop_reason='tool_use')
    call = AnthropicTransport().normalize_response(response, strip_tool_prefix=True).tool_calls[0]
    assert call.name == 'tool_describe'
    assert json.loads(call.arguments)['names'] == ['session_search', 'memory']
    assert arguments['names'] == ['chat_history_lookup', 'context_notes']
    data = {'name': 'chat_history_lookup', 'arguments': {'text': 'chat_history_lookup'}}
    mapped = map_discovery_arguments('tool_call', data, lambda name: 'session_search')
    assert mapped['name'] == 'session_search'
    assert mapped['arguments'] == data['arguments']
    assert map_discovery_arguments('write_file', data, lambda name: 'bad') == data


def test_outbound_discovery_names_do_not_rewrite_schema_literals():
    original = [{'role': 'assistant', 'content': [{'type': 'tool_use', 'name': 'tool_describe',
                 'id': 'a', 'input': {'names': ['session_search']}}]},
                {'role': 'user', 'content': [{'type': 'tool_result', 'tool_use_id': 'a',
                 'content': json.dumps({'tools': {'session_search': {'parameters': {
                     'properties': {'name': {'enum': ['session_search']}}}}}})}]}]
    snapshot = copy.deepcopy(original)
    wire = copy.deepcopy(original)
    rename = lambda name: {'session_search': 'chat_history_lookup'}.get(name, name)
    map_discovery_history(wire, rename)
    assert original == snapshot
    assert wire[0]['content'][0]['input']['names'] == ['chat_history_lookup']
    payload = json.loads(wire[1]['content'][0]['content'])
    assert payload['tools']['chat_history_lookup']['parameters']['properties']['name']['enum'] == ['session_search']


def test_search_match_names_and_catalog_keys_stay_consistent():
    payload = {"results": [{"query": "session_search", "matches": ["session_search", "read_file"]}],
               "tools": {"session_search": {"description": "session_search is user data"}, "read_file": {}}}
    wire = [{"content": [{"type": "tool_use", "name": "tool_search", "id": "s", "input": {"query": "session_search"}}]},
            {"content": [{"type": "tool_result", "tool_use_id": "s", "content": json.dumps(payload)}]}]
    map_discovery_history(wire, lambda name: {"session_search": "chat_history_lookup"}.get(name, name))
    result = json.loads(wire[1]["content"][0]["content"])
    assert result["results"][0]["matches"] == list(result["tools"])
    assert result["results"][0]["query"] == "session_search"
    assert result["tools"]["chat_history_lookup"]["description"] == "session_search is user data"
