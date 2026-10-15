"""Janitor language guard helpers."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def get_janitor_language_instruction(agent: Any) -> str:
    """Return the configured Janitor language instruction, if any."""
    try:
        config = getattr(agent, "_config", None)
        if config is None:
            from hermes_cli.config import load_config

            config = load_config()
        janitor_config = config.get("janitor", {})
        instruction = janitor_config.get("language_instruction", "")
        if isinstance(instruction, str):
            return instruction.strip()
    except Exception as exc:
        logger.debug("Could not read janitor.language_instruction: %s", exc)
    return ""
