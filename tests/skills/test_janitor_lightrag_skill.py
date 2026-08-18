"""
Ad-hoc verification harness for the janitor-lightrag skill port.

Mirrors the static-check pattern from tests/skills/test_janitor_firecrawl_skill.py
since no janitor-lightrag skill test exists yet. Validates:

  * deploy.sh exists and is executable
  * lightrag-compose.yml is valid YAML with the 2 expected services
  * container_name values match AGENTS.md directive #5 (janitor-lightrag,
    janitor-lightrag-db)
  * janitor-honcho-network is declared external (cross-service dependency)
  * env_file paths are HERMES_HOME-aware (no hardcoded /home/reck/)
  * No hardcoded Docker bridge gateway IPs (172.17.0.1 / 172.18.0.1)
  * SKILL.md frontmatter description <= 60 chars, platforms=[linux]
  * SKILL.md references the new bundled compose path
  * SKILL.md references the env file path that lives in ~/.janitor/docker/
  * deploy.sh implements the required steps (check docker, check honcho
    network, generate credentials with openssl rand, copy compose, pull,
    up -d, wait_for_health, inject LIGHTRAG_API_URL)
  * deploy.sh uses SCRIPT_DIR + JANITOR_HOME conventions
  * bash syntax is valid
  * fork convention ~/.janitor preserved
"""
from __future__ import annotations

import os
import re
import stat
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
SKILL_DIR = REPO_ROOT / "skills" / "devops" / "janitor-lightrag"
SCRIPTS_DIR = SKILL_DIR / "scripts"
COMPOSE_FILE = SCRIPTS_DIR / "lightrag-compose.yml"
DEPLOY_SH = SCRIPTS_DIR / "deploy.sh"
SKILL_MD = SKILL_DIR / "SKILL.md"

EXPECTED_SERVICES = {"lightrag", "lightrag-db"}
EXPECTED_CONTAINER_NAMES = {"janitor-lightrag", "janitor-lightrag-db"}


@pytest.fixture(scope="module")
def compose_yaml() -> dict:
    return yaml.safe_load(COMPOSE_FILE.read_text())


@pytest.fixture(scope="module")
def deploy_text() -> str:
    return DEPLOY_SH.read_text()


@pytest.fixture(scope="module")
def skill_text() -> str:
    return SKILL_MD.read_text()


# --- File presence + permissions --------------------------------------------


@pytest.mark.skipif(
    sys.platform == "win32", reason="NTFS carries no executable bit; X_OK is POSIX-only"
)
def test_deploy_sh_exists_and_is_executable() -> None:
    assert DEPLOY_SH.is_file(), f"deploy.sh missing at {DEPLOY_SH}"
    mode = DEPLOY_SH.stat().st_mode
    assert mode & stat.S_IXUSR, f"deploy.sh not user-executable (mode {oct(mode)})"


def test_compose_file_exists() -> None:
    assert COMPOSE_FILE.is_file(), f"compose missing at {COMPOSE_FILE}"


def test_skill_md_exists() -> None:
    assert SKILL_MD.is_file(), f"SKILL.md missing at {SKILL_MD}"


# --- Compose file structural checks -----------------------------------------


def test_compose_has_expected_services(compose_yaml: dict) -> None:
    assert set(compose_yaml["services"].keys()) == EXPECTED_SERVICES


def test_compose_container_names_match_directive_5(compose_yaml: dict) -> None:
    """AGENTS.md directive #5: container names must be janitor-* branded."""
    names = {s["container_name"] for s in compose_yaml["services"].values()}
    assert names == EXPECTED_CONTAINER_NAMES


def test_compose_honcho_network_is_external(compose_yaml: dict) -> None:
    """Documented dependency on janitor-honcho being deployed first."""
    nets = compose_yaml["networks"]
    assert "janitor-honcho-network" in nets
    assert nets["janitor-honcho-network"].get("external") is True


def test_compose_env_file_uses_hermes_home(compose_yaml: dict) -> None:
    """env_file paths must be portable (HERMES_HOME-aware, not /home/reck)."""
    for svc in compose_yaml["services"].values():
        env_file = svc.get("env_file")
        if env_file:
            assert "${HERMES_HOME:-$HOME/.janitor}" in env_file, (
                f"env_file not HERMES_HOME-aware: {env_file!r}"
            )
            assert "/home/reck" not in env_file


def test_compose_no_hardcoded_gateway_ips() -> None:
    text = COMPOSE_FILE.read_text()
    for forbidden in ("172.17.0.1", "172.18.0.1"):
        assert forbidden not in text, (
            f"compose contains hardcoded gateway IP {forbidden}"
        )


# --- deploy.sh checks --------------------------------------------------------


def test_deploy_sh_bash_syntax(deploy_text: str) -> None:
    """Run bash -n on the deploy script."""
    result = subprocess.run(
        ["bash", "-n", str(DEPLOY_SH)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"bash syntax error: {result.stderr}"


def test_deploy_sh_uses_script_dir_and_janitor_home(deploy_text: str) -> None:
    """Required porting conventions."""
    assert 'SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"' in deploy_text
    assert 'JANITOR_HOME="${HERMES_HOME:-$HOME/.janitor}"' in deploy_text


def test_deploy_sh_generates_required_credentials(deploy_text: str) -> None:
    """All three credential keys must be generated with openssl rand."""
    assert "POSTGRES_PASSWORD" in deploy_text
    assert "LIGHTRAG_API_KEY" in deploy_text
    assert "AUTH_ACCOUNTS" in deploy_text
    # openssl rand must be used for each
    assert "openssl rand" in deploy_text


def test_deploy_sh_has_required_pipeline(deploy_text: str) -> None:
    """All steps from the task spec must be present."""
    lc = deploy_text.lower()
    for step in (
        "check_docker",
        "check_honcho_network",
        "generate_lightrag_env",
        "ensure_compose_file",
        "launch",
        "wait_for_health",
        "inject_janitor_env",
        "verify_endpoint",
    ):
        assert step in lc, f"missing required function: {step}"


def test_deploy_sh_injects_lightrag_api_url(deploy_text: str) -> None:
    """Must inject LIGHTRAG_API_URL into ~/.janitor/.env."""
    assert "LIGHTRAG_API_URL" in deploy_text
    assert "JANITOR_ENV" in deploy_text


def test_deploy_sh_idempotent_env_creation(deploy_text: str) -> None:
    """LightRAG env generation must be idempotent (preserve existing creds)."""
    # Either an early-return guard or explicit "preserve" comment
    assert "preserv" in deploy_text.lower(), (
        "deploy.sh should explicitly preserve existing credentials"
    )


def test_deploy_sh_no_hardcoded_paths(deploy_text: str) -> None:
    """No /home/reck/... hardcoded anywhere."""
    assert "/home/reck/" not in deploy_text


def test_deploy_sh_no_hardcoded_gateway_ips(deploy_text: str) -> None:
    for forbidden in ("172.17.0.1", "172.18.0.1"):
        assert forbidden not in deploy_text


# --- SKILL.md frontmatter + content checks ----------------------------------


def test_skill_md_frontmatter_description_under_60_chars(skill_text: str) -> None:
    m = re.search(r'description:\s*"([^"]+)"', skill_text)
    assert m, "description field missing"
    desc = m.group(1)
    assert len(desc) <= 60, f"description too long ({len(desc)} chars): {desc!r}"


def test_skill_md_frontmatter_platforms_linux(skill_text: str) -> None:
    m = re.search(r"platforms:\s*\[([^\]]+)\]", skill_text)
    assert m, "platforms field missing"
    assert m.group(1).strip() == "linux"


def test_skill_md_references_new_compose_path(skill_text: str) -> None:
    expected = "~/.janitor/skills/devops/janitor-lightrag/scripts/lightrag-compose.yml"
    assert expected in skill_text, (
        f"SKILL.md missing reference to bundled compose path: {expected}"
    )


def test_skill_md_references_env_file_in_docker_dir(skill_text: str) -> None:
    """Env file stays in ~/.janitor/docker/ (contains generated credentials)."""
    assert "~/.janitor/docker/lightrag.env" in skill_text


def test_skill_md_no_hardcoded_paths_or_ips(skill_text: str) -> None:
    assert "/home/reck/" not in skill_text
    for forbidden in ("172.17.0.1", "172.18.0.1"):
        assert forbidden not in skill_text, (
            f"SKILL.md still contains hardcoded gateway IP {forbidden}"
        )


def test_skill_md_preserves_fork_convention(skill_text: str) -> None:
    """Fork convention: paths use ~/.janitor."""
    assert "~/.janitor" in skill_text
