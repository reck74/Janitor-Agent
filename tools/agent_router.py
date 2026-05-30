"""LLM-based task classification and routing for specialized agents.

Provides functions to classify a task description and determine whether
it should be delegated to a specialized subagent based on LLM analysis.

Classification types: code_review, debugging, refactoring, writing, generic
"""

from __future__ import annotations

import logging
from typing import Optional

from agent.auxiliary_client import call_llm

from tools.specialized_agents import get_agents, get_agent_by_type

logger = logging.getLogger(__name__)

# Task types that the LLM can classify into
TASK_TYPES = ("code_review", "debugging", "refactoring", "writing", "generic")

# Prompt template for task classification
_CLASSIFICATION_PROMPT = """You are a task classification system. Given a task description, classify it into exactly one of these types:

- code_review: Reviewing code, pull requests, commits, or code quality analysis
- debugging: Fixing bugs, investigating errors, troubleshooting issues
- refactoring: Improving code structure, renaming, reorganizing, optimizing
- writing: Creating documentation, writing content, generating text
- generic: Any task that doesn't fit the above categories

Task: {task_description}

Respond with ONLY the classification type in lowercase, no extra text.
""".strip()


def _build_messages(task_description: str) -> list[dict[str, str]]:
    """Build messages for the classification LLM call."""
    return [
        {"role": "user", "content": _CLASSIFICATION_PROMPT.format(task_description=task_description)}
    ]


def classify(task_description: str) -> Optional[str]:
    """Classify a task description using LLM.

    Args:
        task_description: The natural language description of the task.

    Returns:
        One of: "code_review", "debugging", "refactoring", "writing", "generic",
        or None if classification fails.
    """
    if not task_description or not task_description.strip():
        return None

    try:
        response = call_llm(
            task="agent_router",
            messages=_build_messages(task_description),
            temperature=0,
            max_tokens=20,
        )
        content = (response.choices[0].message.content or "").strip().lower()

        # Validate the response is one of the known types
        if content in TASK_TYPES:
            return content

        # If the response doesn't match exactly, check if it starts with a valid type
        for task_type in TASK_TYPES:
            if content.startswith(task_type):
                return task_type

        logger.debug("Agent router: unexpected classification response '%s', returning None", content)
        return None

    except Exception as e:
        logger.debug("Agent router: LLM classification failed (%s), returning None", e)
        return None


def should_delegate(task_description: str) -> bool:
    """Decide if a task should be delegated to a specialized agent.

    Args:
        task_description: The natural language description of the task.

    Returns:
        True if the task should be delegated to a specialized agent,
        False if it should be handled directly (fallback to generic delegate).
    """
    if not task_description or not task_description.strip():
        return False

    task_type = classify(task_description)
    if task_type is None:
        return False

    # Generic tasks don't need specialized delegation
    if task_type == "generic":
        return False

    # Check if there's a matching agent for this task type
    agent = get_agent_by_type(task_type)
    return agent is not None


def get_best_agent(task_description: str) -> Optional[str]:
    """Return the best matching specialized agent name for a task.

    Args:
        task_description: The natural language description of the task.

    Returns:
        The agent name (e.g., "code-review") if a specialized agent matches,
        None if no match found (triggering fallback to generic delegate).
    """
    if not task_description or not task_description.strip():
        return None

    task_type = classify(task_description)
    if task_type is None:
        return None

    # Generic tasks don't have specialized agents
    if task_type == "generic":
        return None

    agent = get_agent_by_type(task_type)
    if agent is None:
        return None

    return agent.get("name")
