"""Small transport probes run inside the Honcho server, never printing credentials."""
from __future__ import annotations

import json
import os
from pathlib import Path
import tomllib
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def _request(label, url, payload, headers, opener):
    try:
        request = Request(url, data=json.dumps(payload).encode(), headers={"Content-Type": "application/json", **headers})
        with opener(request, timeout=45) as response:
            if not 200 <= response.status < 300:
                raise RuntimeError(f"{label} probe failed (HTTP {response.status})")
            return json.load(response)
    except HTTPError as error:
        raise RuntimeError(f"{label} probe failed (HTTP {error.code}); verify the configured credential and access") from None
    except (URLError, OSError):
        raise RuntimeError(f"{label} probe failed (network unavailable)") from None
    except (ValueError, KeyError, TypeError):
        raise RuntimeError(f"{label} probe returned an invalid response") from None


def probe_transports(config: dict, env=None, *, opener=None) -> None:
    env = os.environ if env is None else env
    opener = urlopen if opener is None else opener
    embedding = config.get("embedding", {})
    model = embedding.get("model_config", {})
    if model.get("transport") != "openai":
        raise RuntimeError("Configured Honcho embedding transport needs an explicit supported readiness probe")
    key = env.get("LLM_OPENAI_API_KEY", "")
    if not key:
        raise RuntimeError("OpenAI embedding credential is missing inside the Honcho server")
    base = model.get("overrides", {}).get("base_url", "https://api.openai.com/v1").rstrip("/")
    result = _request("OpenAI embeddings", base + "/embeddings",
                      {"model": model.get("model", "text-embedding-3-small"), "input": "Janitor readiness",
                       "dimensions": int(embedding.get("VECTOR_DIMENSIONS", 1536))},
                      {"Authorization": "Bearer " + key}, opener)
    try:
        vector = result["data"][0]["embedding"]
        if not isinstance(vector, list) or len(vector) != int(embedding.get("VECTOR_DIMENSIONS", 1536)):
            raise ValueError("dimension mismatch")
    except (KeyError, IndexError, TypeError, ValueError):
        raise RuntimeError("OpenAI embedding probe returned an invalid vector or dimension") from None
    reasoning = config.get("deriver", {}).get("model_config", {})
    if reasoning.get("transport") != "anthropic":
        raise RuntimeError("Configured Honcho reasoning transport needs an explicit supported readiness probe")
    key = env.get("LLM_ANTHROPIC_API_KEY", "")
    if not key:
        raise RuntimeError("MiniMax reasoning credential is missing inside the Honcho server")
    base = reasoning.get("overrides", {}).get("base_url", "https://api.minimax.io/anthropic").rstrip("/")
    result = _request("MiniMax reasoning", base + "/v1/messages",
                      {"model": reasoning.get("model", "MiniMax-M2.7"), "max_tokens": 512,
                       "messages": [{"role": "user", "content": "Reply with only OK."}]},
                      {"x-api-key": key, "anthropic-version": "2023-06-01"}, opener)
    if (not isinstance(result, dict) or result.get("stop_reason") != "end_turn"
            or not any(isinstance(block, dict) and block.get("type") == "text" and str(block.get("text", "")).strip()
                       for block in result.get("content", []))):
        raise RuntimeError("MiniMax reasoning probe did not finish with generated text")


def main() -> int:
    try:
        with Path("/app/config.toml").open("rb") as handle:
            config = tomllib.load(handle)
        probe_transports(config)
        print("Honcho embeddings and reasoning transport probes passed.")
        return 0
    except Exception as error:
        # RuntimeErrors above are curated; never render arbitrary network/config exception text.
        detail = str(error) if isinstance(error, RuntimeError) else "invalid server configuration or transport response"
        print(f"Honcho readiness failed: {detail}", file=__import__("sys").stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
