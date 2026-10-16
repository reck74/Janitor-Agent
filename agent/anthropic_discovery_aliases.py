"""OAuth wire aliases in discovery references, never in arbitrary tool arguments."""
from __future__ import annotations

import json
from typing import Any, Callable


def map_discovery_arguments(name: str, arguments: Any, rename: Callable[[str], str]) -> Any:
    if not isinstance(arguments, dict):
        return arguments
    mapped = dict(arguments)
    if name == "tool_describe" and isinstance(mapped.get("names"), list):
        mapped["names"] = [rename(value) if isinstance(value, str) else value for value in mapped["names"]]
    elif name == "tool_call":
        if isinstance(mapped.get("name"), str):
            mapped["name"] = rename(mapped["name"])
        if isinstance(mapped.get("calls"), list):
            mapped["calls"] = [map_discovery_arguments(name, call, rename) for call in mapped["calls"]]
    return mapped


def _map_result_text(text: str, rename: Callable[[str], str]) -> str:
    try:
        payload = json.loads(text)
    except (TypeError, ValueError):
        return text
    if not isinstance(payload, dict):
        return text
    for key in ("tools", "errors"):
        if isinstance(payload.get(key), dict):
            payload[key] = {rename(name): value for name, value in payload[key].items()}
    for key in ("not_found", "undescribed"):
        if isinstance(payload.get(key), list):
            payload[key] = [rename(name) if isinstance(name, str) else name for name in payload[key]]
    if isinstance(payload.get("results"), list):
        for result in payload["results"]:
            if isinstance(result, dict) and isinstance(result.get("matches"), list):
                result["matches"] = [rename(name) if isinstance(name, str) else name for name in result["matches"]]
    return json.dumps(payload, ensure_ascii=False)


def map_discovery_history(messages: list[dict], rename: Callable[[str], str]) -> None:
    """Mutate only the already-copied outbound history; original signed blocks stay stored."""
    discovery_ids = set()
    for message in messages:
        for block in message.get("content") if isinstance(message.get("content"), list) else []:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "tool_use":
                name = block.get("name")
                if name in ("tool_search", "tool_describe"):
                    discovery_ids.add(block.get("id"))
                block["input"] = map_discovery_arguments(name, block.get("input"), rename)
            elif block.get("type") == "tool_result" and block.get("tool_use_id") in discovery_ids:
                content = block.get("content")
                if isinstance(content, str):
                    block["content"] = _map_result_text(content, rename)
                elif isinstance(content, list):
                    # The converter may shallow-copy stashed multimodal blocks.
                    # Replace text dictionaries; never mutate stored transcript objects.
                    block["content"] = [
                        {**part, "text": _map_result_text(part.get("text"), rename)}
                        if isinstance(part, dict) and part.get("type") == "text" else part
                        for part in content
                    ]
