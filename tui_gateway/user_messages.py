"""User-facing copy for gateway refusals and session-level failures.

One place for the sentences the TUI, Desktop and dashboard print verbatim, so the
"what happened / what to do" shape stays consistent and the slash commands cited
(`/model`, `/new`, `/sessions`, `/retry`) exist on EVERY client this gateway serves (TUI,
Desktop, dashboard) — no client-only forms (`/sessions new`, `/setup`) and no single-surface
gestures stated as fact (Ctrl+C is copy on Desktop). Lead phrases that clients pattern-match
on (``Session busy``) are part of the wire contract — keep them.
"""

from __future__ import annotations

import re
from typing import Any

# Provider-layer failure codes → (title, hint). Codes are ``agent.error_classifier.FailoverReason``
# values carried in ``error_surface.code``; anything unlisted falls back on the layer table.
_TURN_ERROR_CODE_COPY: dict[str, tuple[str, str]] = {
    "auth": ("The model provider rejected the API key", "Fix the key with /model, then /retry."),
    "auth_permanent": ("The model provider rejected the API key", "Fix the key with /model, then /retry."),
    "billing": ("The model provider reports no credit left", "Top up the account or switch with /model."),
    "billing_unverified": ("The model provider reports no credit left", "Top up the account or switch with /model."),
    "rate_limit": ("The model provider is rate-limiting requests", "Wait a moment, then /retry."),
    "upstream_rate_limit": ("The model provider is rate-limiting requests", "Wait a moment, then /retry."),
    "upstream_blocked": ("A firewall/CDN in front of the model provider blocked the request", "Set a User-Agent via the provider's extra_headers, or switch with /model."),
    "overloaded": ("The model provider is overloaded", "Wait a moment, then /retry."),
    "server_error": ("The model provider had an internal error", "Wait a moment, then /retry."),
    "timeout": ("The model provider did not answer in time", "Try /retry; if it keeps happening, switch with /model."),
    "context_overflow": ("The conversation is too long for this model", "Run /compress, then /retry."),
    "payload_too_large": ("The request was too large for this model", "Run /compress, then /retry."),
    "model_not_found": ("The model provider does not know this model", "Pick another model with /model."),
    "content_policy_blocked": ("The model provider refused this request (content policy)", "Rephrase and send again."),
    "provider_policy_blocked": ("The model provider refused this request (account policy)", "Switch with /model."),
    "format_error": ("The model provider rejected the request format", "Try /retry; if it persists, switch with /model."),
    "ssl_cert_verification": ("The connection to the model provider could not be verified (TLS)",
                              "Check the endpoint's certificate, then /retry."),
}

_TURN_ERROR_LAYER_COPY: dict[str, tuple[str, str]] = {
    "auth": ("The model provider rejected the credentials", "Fix them with /model, then /retry."),
    "billing": ("The model provider reports no credit left", "Top up the account or switch with /model."),
    "endpoint": ("Your custom model endpoint did not answer", "Check the endpoint is running, then /retry."),
    "streaming": ("The connection to the model provider dropped mid-reply", "Send /retry."),
    "disk": ("The disk is full, so Hermes could not save the turn", "Free some space, then /retry."),
    "gateway": ("Hermes hit an internal error while running this turn", "Send /retry; type /logs for the trace."),
    "provider": ("The model provider returned an error", "Send /retry, or switch with /model."),
}

_TURN_ERROR_DEFAULT = ("The request failed", "Send /retry, or switch with /model.")

_DETAIL_LIMIT = 400


# JANITOR: (touchpoint backend-user-copy) every sentence below is looked up in the i18n catalog
# under ``tui_gateway.*`` first; a catalog without the key (upstream's) keeps the English text.
def _catalog_text(key: str) -> str | None:
    from agent.i18n import t
    text = t(key)
    return None if text == key else text


def _copy(key: str, english: str, **fields: Any) -> str:
    text = _catalog_text(f"tui_gateway.{key}") or english
    return text.format(**fields) if fields else text


# Raw exception text shown after "Details:" that users hit on a normal path (first run without a key).
_DETAIL_COPY = (
    (re.compile(r"No usable credentials found for provider '(?P<provider>[^']+)'\. Set (?P<env>[^.]+)\."),
     "detail.missing_credentials"),
)


def _localized_detail(detail: str) -> str:
    for pattern, key in _DETAIL_COPY:
        if (match := pattern.fullmatch(detail)) and (text := _catalog_text(f"tui_gateway.{key}")):
            return text.format(**match.groupdict())
    return detail


def _turn_copy(surface: dict) -> tuple[str, str]:
    code, layer = str(surface.get("code") or ""), str(surface.get("layer") or "")
    key, (title, hint) = (f"code.{code}", _TURN_ERROR_CODE_COPY[code]) if code in _TURN_ERROR_CODE_COPY \
        else (f"layer.{layer}", _TURN_ERROR_LAYER_COPY[layer]) if layer in _TURN_ERROR_LAYER_COPY \
        else ("default", _TURN_ERROR_DEFAULT)
    return _copy(f"turn_error.{key}.title", title), _copy(f"turn_error.{key}.hint", hint)


def _identity(surface: dict | None) -> str:
    provider = str((surface or {}).get("provider") or "").strip()
    return f" ({provider})" if provider else ""


def turn_error_title(surface: dict | None) -> str:
    """Plain title for a failed turn, picked from ``error_surface`` code then layer."""
    surface = surface if isinstance(surface, dict) else {}
    title, _ = _turn_copy(surface)
    return f"{title}{_identity(surface)}"


def turn_error_hint(surface: dict | None, recoverable: bool = True) -> str:
    surface = surface if isinstance(surface, dict) else {}
    _, hint = _turn_copy(surface)
    return hint if recoverable else hint.replace(
        _copy("turn_error.retry_step", "Send /retry"), _copy("turn_error.switch_step", "Pick another model with /model"))


def turn_error_text(error: Any, surface: dict | None = None, *, recoverable: bool = True) -> str:
    """The assistant-slot text for a turn that produced no reply: title, what it means for the
    user, the raw provider detail on its own dimmed-able line, and the next step."""
    detail = _localized_detail(" ".join(str(error or "").split()))
    if len(detail) > _DETAIL_LIMIT:
        detail = detail[:_DETAIL_LIMIT - 1] + "…"
    lines = [_copy("turn_error.not_answered", "{title}. Your message was not answered.", title=turn_error_title(surface))]
    if detail:
        lines.append(_copy("details", "Details: {detail}", detail=detail))
    lines.append(turn_error_hint(surface, recoverable))
    return "\n".join(lines)


def busy_message(command: str) -> str:
    """4009 refusal for a history-mutating command while a reply is streaming. There is no
    ``/interrupt`` slash command on any client: Desktop has a Stop button, the terminal TUI uses
    Ctrl+C — name both without assuming which one the reader has."""
    return (f"session busy — Hermes is still replying. Stop the current reply first (Stop button, "
            f"or Ctrl+C in a terminal), then run /{command.lstrip('/')}.")


def agent_init_failed_message(exc: Any) -> str:
    return _copy("agent_init_failed",
                 "Hermes could not start the assistant for this session. Details: {exc}. "
                 "Check the model and provider with /model, or run `hermes setup` in a terminal to reconfigure.",
                 exc=exc, detail=_localized_detail(" ".join(str(exc).split())).rstrip("."))


AGENT_STILL_STARTING = (
    "Hermes is still starting this session (loading tools), so this command could not run yet. "
    "Wait for the status bar to show ready and try again.")

# A deferred build that finished WITHOUT attaching an agent (its session record was replaced or
# closed while it ran) leaves ``agent_ready`` set and ``agent`` None; this is the recorded cause.
AGENT_BUILD_ABANDONED = "agent build aborted: the session record was replaced before the build finished"
# Turn refusal when the record still has no agent at admission time (reason unknown).
AGENT_MISSING_FOR_TURN = (
    "Hermes could not start the assistant for this session, so your message was not run. "
    "Reopen the session (or start a new one with /new) and send it again.")


def resume_failed_message(exc: Any) -> str:
    return (f"Could not reopen that session (its transcript could not be read). Details: {exc}. "
            "Start a new session (/new), or pick another from /sessions.")
