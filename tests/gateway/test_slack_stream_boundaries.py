"""The newly opened message must not split a word across Slack bubbles (#124219)."""
import pytest
from plugins.platforms.slack.stream_text import continuation_offset, stream_relation


@pytest.mark.parametrize("text,sent,continuation", [
    ("Hello world", "Hello wo", "world"),
    ("Hello world", "Hello ", "world"),
    ("Hello world", "Hello", " world"),
    ("onetoken", "onet", "onetoken"),
    ("line\nword", "line\nwo", "word"),
    ("Hello world", "Hello world", ""),
])
def test_reopened_message_starts_at_word_boundary(text, sent, continuation):
    assert text[continuation_offset(text, sent):] == continuation
    # Ordinary in-stream appends stay exact, without repeating words.
    kind, delta = stream_relation(sent, text)
    assert sent + delta == text
    assert kind == ("extends" if delta else "equal")
