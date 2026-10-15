"""API-key credential resolution; hermes_cli.auth remains the public and patchable facade."""

from __future__ import annotations

from typing import Any


def resolve_api_key_provider_credentials(provider_id: str, *, base_url: str | None = None) -> dict[str, Any]:
    """Resolve credentials, keeping an explicit endpoint terminal for URL discovery."""
    from hermes_cli.auth import (
        ACTUAL_LOCAL_NOAUTH_PLACEHOLDER, LMSTUDIO_NOAUTH_PLACEHOLDER, AuthError,
        _API_KEY_BASE_URL_RESOLVERS, _default_api_key_base_url, _nonempty_str,
        _provider_env_base_url, _registry_lookup, _resolve_api_key_provider_secret,
        is_actual_local_base_url,
    )

    pconfig = _registry_lookup(provider_id)
    if not pconfig or pconfig.auth_type != "api_key":
        raise AuthError(
            f"Provider '{provider_id}' is not an API-key provider.",
            provider=provider_id, code="invalid_provider")

    api_key, key_source = _resolve_api_key_provider_secret(provider_id, pconfig)
    # No-auth LM Studio: a placeholder so runtime / auxiliary_client see the local server as
    # configured. doctor still reports unconfigured because the status path uses the raw secret.
    if not api_key and provider_id == "lmstudio":
        api_key = LMSTUDIO_NOAUTH_PLACEHOLDER
        key_source = key_source or "default"

    env_url = _provider_env_base_url(pconfig)
    resolve_url = _API_KEY_BASE_URL_RESOLVERS.get(provider_id, _default_api_key_base_url)
    # A configured relay already owns the destination. Region auto-detection
    # must not send its credential to native hosts before using that relay.
    base_url = (base_url or "").strip() or resolve_url(api_key, pconfig.inference_base_url, env_url)
    # An API-key provider must never hand back an empty base URL (a set-but-empty
    # COPILOT_API_BASE_URL or similar env override otherwise wedges chat inference).
    if not _nonempty_str(base_url):
        base_url = pconfig.inference_base_url

    if not api_key and provider_id == "actual" and is_actual_local_base_url(base_url):
        api_key = ACTUAL_LOCAL_NOAUTH_PLACEHOLDER
        key_source = key_source or "local-offline"
    return {
        "provider": provider_id, "api_key": api_key, "base_url": base_url.rstrip("/"),
        "source": key_source or "default"}
