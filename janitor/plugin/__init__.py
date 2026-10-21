"""Janitor Hermes plugin.

Registered through the ``hermes_agent.plugins`` entry point (pyproject) and
activated by ``plugins.enabled: [janitor]`` in ``~/.janitor/config.yaml``.
Everything Janitor adds at runtime goes through the public plugin surface
here instead of edits to core files.
"""

from __future__ import annotations

from typing import Any


def register(ctx: Any) -> None:
    from janitor.language import language_prompt_section
    from janitor.plugin import telegram

    ctx.register_hook("pre_gateway_dispatch", telegram.pre_gateway_dispatch)
    ctx.register_system_prompt_section("janitor.language", language_prompt_section)
