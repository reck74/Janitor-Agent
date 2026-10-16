"""Real OpenAI SDK serialization and independent Vertex native-schema boundary tests."""
from copy import deepcopy
import json

import httpx
from openai import OpenAI
import pytest
from jsonschema import Draft202012Validator

from agent.transports.chat_completions import ChatCompletionsTransport
from providers import get_provider_profile
from tests.fakes.providers.vertex import _check_tools, _check_native_tools

SCHEMA = {"type": "object", "properties": {"notify": {"anyOf": [
    {"type": "boolean"}, {"type": "array", "items": {"type": "string"}},
]}}, "required": ["notify"]}
TOOLS = [{"type": "function", "function": {"name": "watch", "description": "Watch", "parameters": SCHEMA}}]


@pytest.mark.parametrize("choice", ["auto", "none", {"type": "function", "function": {"name": "watch"}}])
def test_real_sdk_wire_preserves_union_and_tool_choice(choice):
    profile = get_provider_profile("vertex")
    source = deepcopy(TOOLS)
    kwargs = ChatCompletionsTransport().build_kwargs(
        "google/gemini-3-flash-preview", [{"role": "user", "content": "Watch"}], source,
        provider_profile=profile, request_overrides={"tool_choice": choice},
    )
    captured = []

    def respond(request):
        captured.append(json.loads(request.content))
        return httpx.Response(200, json={"id": "test", "object": "chat.completion", "created": 1,
            "model": "google/gemini-3-flash-preview", "choices": [{"index": 0,
            "message": {"role": "assistant", "content": "OK"}, "finish_reason": "stop"}]})

    with OpenAI(api_key="test", http_client=httpx.Client(transport=httpx.MockTransport(respond))) as client:
        client.chat.completions.create(**kwargs)
    body = captured[0]
    assert "tools" not in body
    assert "extra_body" not in body["extra_body"]
    assert body["tool_choice"] == choice
    schema = body["extra_body"]["google"]["tools"][0]["functionDeclarations"][0]["parametersJsonSchema"]
    assert schema == SCHEMA
    assert _check_native_tools(body) is None
    validator = Draft202012Validator(schema)
    assert validator.is_valid({"notify": True})
    assert validator.is_valid({"notify": ["ready"]})
    assert not validator.is_valid({"notify": [42]})
    assert source == TOOLS


def test_compat_translator_still_rejects_union_and_native_validates_errors():
    assert "schema type should be ARRAY" in _check_tools(TOOLS)
    profile = get_provider_profile("vertex")
    projected = profile.prepare_api_kwargs({"tools": deepcopy(TOOLS)})
    body = projected["extra_body"]  # SDK merges this into the request body.
    declaration = body["extra_body"]["google"]["tools"][0]["functionDeclarations"][0]
    declaration["parametersJsonSchema"]["properties"]["notify"] = {"type": "invalid"}
    assert "Invalid parametersJsonSchema" in _check_native_tools(body)


def test_projection_preserves_existing_native_tools_and_does_not_mutate_inputs():
    profile = get_provider_profile("vertex")
    kwargs = {"tools": deepcopy(TOOLS), "extra_body": {"extra_body": {"google": {
        "tools": [{"googleSearch": {}}], "thinking_config": {"thinking_level": "high"},
    }}}}
    original = deepcopy(kwargs)
    result = profile.prepare_api_kwargs(kwargs)
    assert kwargs == original
    google = result["extra_body"]["extra_body"]["google"]
    assert google["tools"][0] == {"googleSearch": {}}
    assert google["thinking_config"] == {"thinking_level": "high"}
    assert profile.prepare_api_kwargs({"model": "no-tools"}) == {"model": "no-tools"}


def test_parameter_free_native_declaration_is_valid():
    assert _check_native_tools({"extra_body": {"google": {"tools": [
        {"functionDeclarations": [{"name": "ping"}]},
    ]}}}) is None
