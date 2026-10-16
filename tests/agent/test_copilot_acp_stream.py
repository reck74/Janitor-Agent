"""Incremental ACP delivery preserves context, tool envelopes and call ownership."""
import contextvars
import threading
from types import SimpleNamespace

import pytest

from agent.acp_openai_bridge import extract_tool_calls_from_text
from agent.copilot_acp_stream import stream_completion


def completion(text, reasoning=''):
    calls, text = extract_tool_calls_from_text(text)
    return SimpleNamespace(model='fixture', usage=None, choices=[SimpleNamespace(
        finish_reason='tool_calls' if calls else 'stop',
        message=SimpleNamespace(content=text, tool_calls=calls, reasoning=reasoning, reasoning_content=reasoning))])


def test_chunk_arrives_before_completion_and_context_is_preserved():
    profile = contextvars.ContextVar('fixture_profile', default='wrong')
    profile.set('correct')
    finish = threading.Event()
    seen = []

    def run(emit, cancelled):
        seen.append(profile.get())
        emit('text', 'early ')
        assert finish.wait(5), 'consumer did not observe the early chunk'
        emit('text', 'answer')
        return completion('early answer')

    stream = stream_completion(run)
    first = next(stream)
    assert first.choices[0].delta.content == 'early'
    finish.set()
    chunks = [first, *stream]
    assert ''.join(c.choices[0].delta.content or '' for c in chunks if c.choices) == 'early answer'
    assert seen == ['correct']


def test_split_tool_envelope_is_only_delivered_as_tool_delta():
    text = 'Checking. <tool_call>{"function":{"name":"read_file","arguments":{"path":"a"}}}</tool_call>'

    def run(emit, cancelled):
        for fragment in ('Checking. <too', 'l_call>{"function":{"name":"read_file",', '"arguments":{"path":"a"}}}</tool_call>'):
            emit('text', fragment)
        return completion(text)

    chunks = list(stream_completion(run))
    assert ''.join(c.choices[0].delta.content or '' for c in chunks if c.choices) == 'Checking.'
    calls = [call for c in chunks if c.choices for call in (c.choices[0].delta.tool_calls or [])]
    assert len(calls) == 1 and calls[0].function.name == 'read_file'


def test_closing_consumer_cancels_only_its_producer():
    stopped = threading.Event()

    def run(emit, cancelled):
        emit('text', 'early')
        try:
            assert cancelled.wait(5), 'producer cancellation was lost'
            return completion('early')
        finally:
            stopped.set()

    stream = stream_completion(run)
    next(stream)
    stream.close()
    assert stopped.wait(2)


def test_producer_failure_reaches_consumer():
    def run(emit, cancelled):
        emit('reasoning', 'working')
        raise RuntimeError('provider failed')

    stream = stream_completion(run)
    assert next(stream).choices[0].delta.reasoning_content == 'working'
    with pytest.raises(RuntimeError, match='provider failed'):
        next(stream)


@pytest.mark.parametrize('envelope', [
    '```json\n{"id":"read","type":"function","function":{"name":"read_file","arguments":"{}"}}\n```',
    '```xml\n<tool_call>{"function":{"name":"read_file","arguments":{}}}</tool_call>\n```',
])
def test_split_fence_matches_final_bridge_output_without_duplicate_prefix(envelope):
    text = 'Checking. ' + envelope

    def run(emit, cancelled):
        for fragment in ('Checking. `', envelope[1:5], envelope[5:]):
            emit('text', fragment)
        return completion(text)

    chunks = list(stream_completion(run))
    expected_calls, expected_text = extract_tool_calls_from_text(text)
    actual = ''.join(c.choices[0].delta.content or '' for c in chunks if c.choices)
    assert actual == expected_text
    assert actual.count('Checking.') == 1
    assert len([t for c in chunks if c.choices for t in (c.choices[0].delta.tool_calls or [])]) == len(expected_calls) == 1


def test_inconsistent_final_prefix_fails_instead_of_duplicating_output():
    def run(emit, cancelled):
        emit('text', 'already visible')
        return completion('inconsistent rewritten answer')

    stream = stream_completion(run)
    assert next(stream).choices[0].delta.content == 'already visible'
    with pytest.raises(RuntimeError, match='already-streamed prefix'):
        next(stream)
