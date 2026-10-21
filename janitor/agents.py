"""Discovery helpers for Janitor specialized agents."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import cast

import yaml

from janitor.home import SKILLS_ROOT

logger = logging.getLogger(__name__)
SKILLS_DIR = SKILLS_ROOT / "agents"
_AGENT_DIR_PATTERN = "janitor-*-agent"


AgentSpec = dict[str, object]


def _read_agent_spec(agent_dir: Path) -> AgentSpec | None:
    spec_path = agent_dir / "agent.yaml"
    if not spec_path.exists():
        return None

    try:
        loaded = cast(object, yaml.safe_load(spec_path.read_text(encoding="utf-8")))
    except (OSError, UnicodeDecodeError, yaml.YAMLError) as exc:
        logger.debug("Skipping specialized agent at %s: %s", spec_path, exc)
        return None

    if not isinstance(loaded, dict):
        return None

    raw_spec = cast("dict[object, object]", loaded)
    return {str(key): value for key, value in raw_spec.items()}


def _iter_agent_dirs() -> list[Path]:
    if not SKILLS_DIR.exists():
        return []
    try:
        return sorted(path for path in SKILLS_DIR.glob(_AGENT_DIR_PATTERN) if path.is_dir())
    except OSError as exc:
        logger.debug("Could not scan specialized agents in %s: %s", SKILLS_DIR, exc)
        return []


def get_agents() -> list[dict[str, str]]:
    """Return discovered Janitor specialized agent metadata."""
    agents: list[dict[str, str]] = []

    for agent_dir in _iter_agent_dirs():
        spec = _read_agent_spec(agent_dir)
        if not spec:
            continue

        name = spec.get("name")
        description = spec.get("description")
        if not isinstance(name, str) or not isinstance(description, str):
            continue

        agents.append(
            {
                "name": name,
                "description": description,
                "path": str(agent_dir),
            }
        )

    return agents


def load_agent_spec(agent_name: str) -> AgentSpec | None:
    """Load the full ``agent.yaml`` spec for a discovered agent."""
    wanted = (agent_name or "").strip()
    if not wanted:
        return None

    for agent_dir in _iter_agent_dirs():
        spec = _read_agent_spec(agent_dir)
        if not spec:
            continue

        name = spec.get("name")
        if name != wanted and agent_dir.name != wanted:
            continue

        spec = dict(spec)
        spec["path"] = str(agent_dir)
        return spec

    return None


def get_agent_by_type(task_type: str) -> dict[str, str] | None:
    """Return a basic metadata match for a task type.

    This intentionally stays simple; higher-level routers can use LLM
    classification before calling ``load_agent_spec``.
    """
    query = (task_type or "").strip().lower()
    if not query:
        return None

    query_terms = {term for term in query.replace("-", " ").replace("_", " ").split() if term}
    for agent in get_agents():
        haystack = f"{agent.get('name', '')} {agent.get('description', '')}".lower().replace("-", " ")
        if query in haystack or any(term in haystack for term in query_terms):
            return agent

    return None


def setup_parser(parser) -> None:
    sub = parser.add_subparsers(dest="agents_action")
    sub.add_parser("list", help="List Janitor specialized agents")
    show = sub.add_parser("show", help="Print the agent.yaml spec of one agent")
    show.add_argument("name")


def handle(args, out=print) -> int:
    action = getattr(args, "agents_action", None) or "list"
    if action == "list":
        for agent in get_agents():
            out(f"{agent['name']:<28} {agent['description']}")
        return 0
    spec = load_agent_spec(args.name)
    if spec is None:
        out(f"error: unknown agent {args.name!r}")
        return 1
    out(yaml.safe_dump(spec, sort_keys=False, allow_unicode=True).rstrip())
    return 0
