"""The real system-prompt skill index of a Janitor home, for behaviour tests.

Drives ``agent.prompt_builder.build_skills_system_prompt`` against ``home`` the
way the agent does (essential-skill sync first), so tests compare what the
model would actually see, not config values.
"""

from __future__ import annotations

import re
from pathlib import Path

ESSENTIAL = "hermes-agent"


def skill_index(home: Path, monkeypatch) -> set:
    """Skill names in the ``<available_skills>`` block of ``home``'s system prompt."""
    from agent import skill_utils
    from agent.prompt_builder import build_skills_system_prompt, clear_skills_system_prompt_cache
    from tools.skills_sync import sync_skills

    monkeypatch.setenv("HERMES_HOME", str(home))
    skill_utils._external_dirs_cache_clear()
    clear_skills_system_prompt_cache()
    sync_skills(quiet=True)
    prompt = build_skills_system_prompt()
    block = prompt.split("<available_skills>", 1)[1].split("</available_skills>", 1)[0]
    return set(re.findall(r"^\s+- ([^:\s]+):", block, re.M))
