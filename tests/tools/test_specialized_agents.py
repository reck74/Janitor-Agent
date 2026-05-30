from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest


def _write_agent(root: Path, directory: str, yaml_text: str) -> Path:
    skill_dir = root / directory
    skill_dir.mkdir(parents=True)
    _ = (skill_dir / "agent.yaml").write_text(yaml_text, encoding="utf-8")
    return skill_dir


def test_get_agents_discovers_janitor_agent_skill_metadata(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tools import specialized_agents

    agent_dir = _write_agent(
        tmp_path,
        "janitor-code-review-agent",
        """
name: code-review
description: Reviews code changes.
systemPrompt: Review code carefully.
skills:
  - git-master
""".lstrip(),
    )
    _ = _write_agent(
        tmp_path,
        "janitor-security-agent",
        """
name: security
description: Finds security issues.
systemPrompt: Audit security.
""".lstrip(),
    )
    (tmp_path / "janitor-not-an-agent").mkdir()

    monkeypatch.setattr(specialized_agents, "SKILLS_DIR", tmp_path)

    assert specialized_agents.get_agents() == [
        {
            "name": "code-review",
            "description": "Reviews code changes.",
            "path": str(agent_dir),
        },
        {
            "name": "security",
            "description": "Finds security issues.",
            "path": str(tmp_path / "janitor-security-agent"),
        },
    ]


def test_load_agent_spec_returns_full_yaml_spec(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tools import specialized_agents

    agent_dir = _write_agent(
        tmp_path,
        "janitor-code-review-agent",
        """
name: code-review
description: Reviews code changes.
systemPrompt: |
  You are a code review agent.
skills:
  - git-master
model: gpt-4o
toolsets:
  - file
reasoningEffort: medium
""".lstrip(),
    )
    monkeypatch.setattr(specialized_agents, "SKILLS_DIR", tmp_path)

    spec = specialized_agents.load_agent_spec("code-review")

    assert spec == {
        "name": "code-review",
        "description": "Reviews code changes.",
        "systemPrompt": "You are a code review agent.\n",
        "skills": ["git-master"],
        "model": "gpt-4o",
        "toolsets": ["file"],
        "reasoningEffort": "medium",
        "path": str(agent_dir),
    }


def test_registry_handles_missing_and_malformed_agent_specs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tools import specialized_agents

    (tmp_path / "janitor-empty-agent").mkdir()
    _ = _write_agent(tmp_path, "janitor-broken-agent", "name: [unterminated")
    monkeypatch.setattr(specialized_agents, "SKILLS_DIR", tmp_path)

    assert specialized_agents.get_agents() == []
    assert specialized_agents.load_agent_spec("missing") is None
    assert specialized_agents.load_agent_spec("broken") is None


def test_get_agent_by_type_matches_basic_name_and_description(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tools import specialized_agents

    _ = _write_agent(
        tmp_path,
        "janitor-code-review-agent",
        """
name: code-review
description: Reviews code changes.
systemPrompt: Review code carefully.
""".lstrip(),
    )
    _ = _write_agent(
        tmp_path,
        "janitor-docs-agent",
        """
name: docs
description: Writes documentation.
systemPrompt: Document changes.
""".lstrip(),
    )
    monkeypatch.setattr(specialized_agents, "SKILLS_DIR", tmp_path)

    code_review = specialized_agents.get_agent_by_type("code review")
    docs = specialized_agents.get_agent_by_type("documentation")

    assert code_review is not None
    assert code_review["name"] == "code-review"
    assert docs is not None
    assert docs["name"] == "docs"
    assert specialized_agents.get_agent_by_type("unrelated") is None


def test_code_review_agent_registry_router_and_delegate_flow(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tools import agent_router, delegate_tool, specialized_agents

    agents = specialized_agents.get_agents()
    assert any(agent["name"] == "code-review" for agent in agents)

    spec = specialized_agents.load_agent_spec("code-review")
    assert spec is not None
    assert spec["name"] == "code-review"
    assert isinstance(spec.get("description"), str)
    assert spec["description"]
    assert isinstance(spec.get("systemPrompt"), str)
    assert spec["systemPrompt"]

    delegate_loader = cast(
        Callable[[str], dict[str, object] | None], getattr(delegate_tool, "load_agent_spec")
    )
    delegated_spec = delegate_loader("code-review")
    assert delegated_spec is not None
    assert delegated_spec["name"] == "code-review"

    def fake_call_llm(
        *,
        task: str,
        messages: list[dict[str, str]],
        temperature: int,
        max_tokens: int,
    ) -> SimpleNamespace:
        assert task == "agent_router"
        assert temperature == 0
        assert max_tokens == 20
        message_text = str(messages)
        classification = "generic" if "what is 2+2" in message_text else "code_review"
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content=classification),
                )
            ]
        )

    monkeypatch.setattr(agent_router, "call_llm", fake_call_llm)

    assert agent_router.classify("review my code") == "code_review"
    assert agent_router.should_delegate("review my code") is True
    assert agent_router.get_best_agent("review my code") == "code-review"
    assert agent_router.get_best_agent("what is 2+2") is None
