"""Google Vertex AI provider profile: Gemini via Google Cloud's OpenAI-compatible endpoint.

Auth is OAuth2 (service-account JSON or ADC), not a static key: ``agent/vertex_adapter.py``
mints ``(token, base_url)`` and the token is passed as ``api_key``. ``auth_type="vertex"``
keeps it out of the api_key provider path so a credentials-file path is never mistaken for a key.
"""

from copy import deepcopy
from typing import Any

from providers import register_provider
from providers.base import ProviderProfile


class VertexProfile(ProviderProfile):
    """Vertex AI — reuse Gemini's thinking_config translation for extra_body."""

    def prepare_api_kwargs(self, kwargs: dict[str, Any]) -> dict[str, Any]:
        """Bypass the lossy OpenAI schema translator using Google's native override.

        https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/migrate/openai/overview
        https://docs.cloud.google.com/gemini-enterprise-agent-platform/reference/rest/Shared.Types/FunctionDeclaration
        The SDK consumes the outer extra_body argument; the wire has one wrapper.
        """
        functions = [t["function"] for t in (kwargs.get("tools") or []) if t.get("type") == "function"]
        if not functions:
            return kwargs
        result = dict(kwargs)
        remaining = [t for t in kwargs["tools"] if t.get("type") != "function"]
        if remaining:
            result["tools"] = remaining
        else:
            result.pop("tools")
        extra = deepcopy(kwargs.get("extra_body", {}))
        google = extra.setdefault("extra_body", {}).setdefault("google", {})
        declarations = []
        for function in functions:
            declaration = {k: deepcopy(function[k]) for k in ("name", "description") if k in function}
            if "parameters" in function:
                declaration["parametersJsonSchema"] = deepcopy(function["parameters"])
            declarations.append(declaration)
        google["tools"] = [*google.get("tools", []), {"functionDeclarations": declarations}]
        result["extra_body"] = extra
        return result

    def build_extra_body(self, *, session_id: str | None = None, **context: Any) -> dict[str, Any]:
        """Emit ``extra_body.google.thinking_config`` like the ``gemini`` provider's OpenAI-compat subpath."""
        from agent.transports.chat_completions import _build_gemini_thinking_config, _snake_case_gemini_thinking_config

        raw = _build_gemini_thinking_config(context.get("model") or "", context.get("reasoning_config"))
        thinking_config = _snake_case_gemini_thinking_config(raw) if raw else None
        return {"extra_body": {"google": {"thinking_config": thinking_config}}} if thinking_config else {}


vertex = VertexProfile(
    name="vertex", aliases=("google-vertex", "vertex-ai", "gcp-vertex", "vertexai"), api_mode="chat_completions",
    env_vars=(),  # OAuth2 via service account / ADC — not a static key env var
    base_url="https://aiplatform.googleapis.com",  # real base_url computed at runtime
    auth_type="vertex", default_aux_model="google/gemini-3.6-flash",
    supports_model_listing=False,  # no /models route on the OpenAI-compat endpoint; setup ships a curated list
)

register_provider(vertex)
