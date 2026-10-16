"""OAuth discovery wire conversion preserves persisted history and cache inputs."""
import copy
import json

import pytest

from agent.anthropic_discovery_aliases import map_discovery_history
from agent.anthropic_message_convert import convert_messages_to_anthropic


@pytest.mark.parametrize('stashed', [False, True])
def test_discovery_mapping_does_not_mutate_original_history(stashed):
    result = json.dumps({'tools': {'terminal': {}}, 'results': [{'matches': ['terminal']}]})
    tool = {'role': 'tool', 'tool_call_id': 'search1', 'content': result}
    if stashed:
        tool['content'] = ''
        tool['_anthropic_content_blocks'] = [{'type': 'text', 'text': result}]
    history = [
        {'role': 'assistant', 'content': '', 'tool_calls': [
            {'id': 'search1', 'type': 'function',
             'function': {'name': 'tool_search', 'arguments': '{}'}},
        ]},
        tool,
    ]
    original = copy.deepcopy(history)
    _, outbound = convert_messages_to_anthropic(history)
    map_discovery_history(outbound, lambda name: 'Terminal' if name == 'terminal' else name)
    content = outbound[-1]['content'][0]['content']
    text = content[0]['text'] if isinstance(content, list) else content
    mapped = json.loads(text)
    assert list(mapped['tools']) == ['Terminal']
    assert mapped['results'][0]['matches'] == ['Terminal']
    assert history == original
