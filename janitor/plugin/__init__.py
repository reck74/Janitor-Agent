"""Janitor Hermes plugin.

Registered through the ``hermes_agent.plugins`` entry point (pyproject) and
activated by ``plugins.enabled: [janitor]`` in ``~/.janitor/config.yaml``.
Everything Janitor adds at runtime goes through the public plugin surface
here instead of edits to core files.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def _export_message_catalogs() -> None:
    """Janitor's backend catalogs for a process the launcher did not start.

    A gateway service or ``python -m hermes_cli.main ...`` loads this plugin
    but never ran the launcher's export, so ``t()`` would read upstream's
    catalogs. Runs at plugin discovery, which a gateway reaches while loading
    its config (``gateway.config_loader.load_yaml_layer``), before any message.
    """
    try:
        from janitor.locales import ensure_exported

        ensure_exported()
    except Exception as exc:  # noqa: BLE001 — upstream's catalogs are a working fallback
        logger.warning("Janitor message catalogs unavailable, using upstream's: %s", exc)


def _use_janitor_tips() -> None:
    """Janitor's Spanish tip corpus in every process the plugin runs in, not only the
    launcher's: a gateway (service, or handed off by the launcher) shows one on ``/reset``
    (``gateway/slash_commands_session.py``). Same patch as ``janitor.cli.main()``;
    signature guarded by ``tests/janitor/test_janitor_monkeypatch_signatures.py``."""
    import hermes_cli.tips as tips

    from janitor.tips_es import JANITOR_TIPS, get_janitor_tip

    tips.TIPS = JANITOR_TIPS
    tips.get_random_tip = get_janitor_tip


def _route_gateway_update() -> None:
    """``/update`` from a messaging platform runs ``janitor update`` (directive #13)."""
    try:
        from janitor.plugin import gateway_update

        gateway_update.install()
    except Exception as exc:  # noqa: BLE001 — the gateway must still start; /update then runs upstream's flow
        logger.warning("Janitor could not route /update through `janitor update`: %s", exc)


def register(ctx: Any) -> None:
    _export_message_catalogs()
    _use_janitor_tips()
    _route_gateway_update()

    from janitor import profile_templates, services
    from janitor.language import language_prompt_section
    from janitor.plugin import gateway_update, telegram

    ctx.register_hook("pre_gateway_dispatch", telegram.pre_gateway_dispatch)
    ctx.register_hook("pre_gateway_dispatch", gateway_update.pre_gateway_dispatch)
    ctx.register_system_prompt_section("janitor.language", language_prompt_section)
    ctx.register_cli_command(
        "services",
        "Manage Janitor self-hosted services (honcho, firecrawl, n8n, ...)",
        services.setup_parser,
        handler_fn=services.handle,
        description="Deploy, inspect, stop and remove Janitor Docker services. "
        "Volumes are never deleted.",
    )
    ctx.register_cli_command(
        "plantillas",
        "Crea agentes especialistas (perfiles) desde plantillas Janitor",
        profile_templates.setup_parser,
        handler_fn=profile_templates.handle,
        description="Lista las plantillas de agente especialista y crea un perfil "
        "nuevo desde una de ellas, sin memoria compartida.",
    )
