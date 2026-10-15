"""Assemble streamed tool arguments without guessing bytes lost in a dropped stream."""

import json
import logging
from types import SimpleNamespace

from agent.message_sanitization import _repair_tool_call_arguments
from agent.repetition_guard import is_repetition_dominated

logger = logging.getLogger("agent.chat_completion_helpers")


def assemble_tool_calls(tool_calls_acc, finish_reason):
    """Materialize accumulated tool calls; flag truncated/unrepairable args."""
    mock_tool_calls = []
    has_truncated_tool_args = False
    for idx in sorted(tool_calls_acc):
        tc = tool_calls_acc[idx]
        arguments = tc["function"]["arguments"]
        if arguments and arguments.strip():
            try:
                json.loads(arguments)
            except json.JSONDecodeError:
                # A dropped stream is never repaired: closing its prefix yields valid
                # JSON that silently lacks every key and digit not yet streamed.
                if finish_reason is None:
                    has_truncated_tool_args = True
                else:
                    # Repair before flagging (GLM via Ollama); "{}" = unrepairable.
                    repaired = _repair_tool_call_arguments(arguments, tc["function"]["name"] or "?")
                    if repaired != "{}":
                        arguments = repaired
                    else:
                        has_truncated_tool_args = True
            # Parseable JSON does not prove that a dropped stream completed its
            # action. Treat degenerate argument loops as partial calls too.
            # A provider-confirmed call may legitimately write repetitive data.
            if finish_reason is None and is_repetition_dominated(arguments):
                logger.warning(
                    "Tool call '%s' has repetition-dominated arguments without a "
                    "finish_reason; treating as a dropped tool call.", tc["function"]["name"] or "?")
                has_truncated_tool_args = True
        elif finish_reason is None:
            # Name arrived, zero arg bytes, no finish_reason: unflagged this
            # becomes a "stop" turn executing "{}" with no retry.
            has_truncated_tool_args = True
        mock_tool_calls.append(SimpleNamespace(
            id=tc["id"], type=tc["type"], extra_content=tc.get("extra_content"),
            function=SimpleNamespace(name=tc["function"]["name"], arguments=arguments,
                                     args_repaired=arguments != tc["function"]["arguments"],
                                     thought_signature=tc.get("thought_signature"))))
    return mock_tool_calls or None, has_truncated_tool_args
