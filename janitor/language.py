"""Janitor output-language instruction (``janitor.language_instruction``)."""

from __future__ import annotations

import logging
from typing import Any, Mapping, Optional

logger = logging.getLogger(__name__)


def get_language_instruction(config: Optional[Mapping[str, Any]] = None) -> str:
    """Return the configured ``janitor.language_instruction``, or ``""``."""
    try:
        if config is None:
            from hermes_cli.config import load_config

            config = load_config()
        janitor_config = config.get("janitor") or {}
        instruction = janitor_config.get("language_instruction", "")
        if isinstance(instruction, str):
            return instruction.strip()
    except Exception as exc:
        logger.debug("Could not read janitor.language_instruction: %s", exc)
    return ""


def language_prompt_section(_session_info: Mapping[str, Any]) -> str:
    """System prompt section renderer; evaluated once per new session."""
    return get_language_instruction()
