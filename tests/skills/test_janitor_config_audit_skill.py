"""
Tests for the janitor-config-audit skill.

Verifies:
  - SKILL.md frontmatter conforms to the hardline format
  - audit.py parses as valid Python
  - audit.py respects JANITOR_HOME env var instead of hardcoding ~/.janitor
  - diff logic correctly reports added, removed, and changed keys
  - apply mode creates backups and restores on malformed YAML
"""
from __future__ import annotations

import ast
import os
import re
import shutil
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

SKILL_DIR = Path(__file__).resolve().parents[2] / "skills" / "janitor-config-audit"


@pytest.fixture(scope="module")
def frontmatter() -> dict:
    src = (SKILL_DIR / "SKILL.md").read_text()
    m = re.search(r"^---\n(.*?)\n---", src, re.DOTALL)
    assert m, "SKILL.md missing YAML frontmatter"
    return yaml.safe_load(m.group(1))


@pytest.fixture
def tmp_janitor_home(tmp_path: Path) -> Path:
    home = tmp_path / ".janitor"
    home.mkdir()
    assets = home / "janitor-core" / "assets" / "janitor"
    assets.mkdir(parents=True)
    return home


@pytest.fixture
def audit_script_source() -> str:
    return (SKILL_DIR / "scripts" / "audit.py").read_text()


def test_skill_dir_exists() -> None:
    assert SKILL_DIR.is_dir(), f"missing skill dir: {SKILL_DIR}"


def test_skill_md_present() -> None:
    assert (SKILL_DIR / "SKILL.md").is_file()


def test_audit_script_present() -> None:
    assert (SKILL_DIR / "scripts" / "audit.py").is_file()


def test_description_under_60_chars(frontmatter) -> None:
    desc = frontmatter["description"]
    assert len(desc) <= 60, f"description is {len(desc)} chars (hardline ≤60): {desc!r}"


def test_name_matches_dir(frontmatter) -> None:
    assert frontmatter["name"] == "janitor-config-audit"


def test_license_present(frontmatter) -> None:
    assert frontmatter.get("license"), "license field is required"


def test_platforms_includes_common(frontmatter) -> None:
    platforms = frontmatter.get("platforms", [])
    assert set(platforms) >= {"linux", "macos"}


def test_script_is_valid_python(audit_script_source) -> None:
    ast.parse(audit_script_source)


def test_script_uses_janitor_home_env_var(audit_script_source) -> None:
    assert "JANITOR_HOME" in audit_script_source
    assert "os.environ" in audit_script_source


class TestDiffLogic:
    def _reload_and_run(self, tmp_janitor_home: Path, *extra_args: str) -> int:
        script = SKILL_DIR / "scripts" / "audit.py"
        with patch.dict(os.environ, {"JANITOR_HOME": str(tmp_janitor_home)}):
            if str(SKILL_DIR / "scripts") not in sys.path:
                sys.path.insert(0, str(SKILL_DIR / "scripts"))
            import importlib
            import audit as audit_mod
            importlib.reload(audit_mod)

            old_argv = sys.argv
            try:
                sys.argv = [str(script), *extra_args]
                audit_mod.main()
            except SystemExit as e:
                return e.code
            finally:
                sys.argv = old_argv
                if str(SKILL_DIR / "scripts") in sys.path:
                    sys.path.remove(str(SKILL_DIR / "scripts"))
                sys.modules.pop("audit", None)
        return 0

    def test_no_differences(self, tmp_janitor_home: Path, capsys) -> None:
        config = {"model": "gpt-4", "agent": {"max_iterations": 10}}
        active = tmp_janitor_home / "config.yaml"
        asset = tmp_janitor_home / "janitor-core" / "assets" / "janitor" / "config.yaml"
        active.write_text(yaml.safe_dump(config))
        asset.write_text(yaml.safe_dump(config))

        exit_code = self._reload_and_run(tmp_janitor_home, "config")
        captured = capsys.readouterr()
        assert "Sin diferencias" in captured.out or "OK" in captured.out
        assert exit_code == 0

    def test_detects_added_key(self, tmp_janitor_home: Path, capsys) -> None:
        active = tmp_janitor_home / "config.yaml"
        asset = tmp_janitor_home / "janitor-core" / "assets" / "janitor" / "config.yaml"
        active.write_text(yaml.safe_dump({"model": "gpt-4"}))
        asset.write_text(yaml.safe_dump({"model": "gpt-4", "new_key": "value"}))

        self._reload_and_run(tmp_janitor_home, "config")
        captured = capsys.readouterr()
        assert "new_key" in captured.out
        assert "+" in captured.out

    def test_detects_removed_key(self, tmp_janitor_home: Path, capsys) -> None:
        active = tmp_janitor_home / "config.yaml"
        asset = tmp_janitor_home / "janitor-core" / "assets" / "janitor" / "config.yaml"
        active.write_text(yaml.safe_dump({"model": "gpt-4", "old_key": "value"}))
        asset.write_text(yaml.safe_dump({"model": "gpt-4"}))

        self._reload_and_run(tmp_janitor_home, "config")
        captured = capsys.readouterr()
        assert "old_key" in captured.out
        assert "-" in captured.out

    def test_detects_changed_value(self, tmp_janitor_home: Path, capsys) -> None:
        active = tmp_janitor_home / "config.yaml"
        asset = tmp_janitor_home / "janitor-core" / "assets" / "janitor" / "config.yaml"
        active.write_text(yaml.safe_dump({"model": "gpt-3"}))
        asset.write_text(yaml.safe_dump({"model": "gpt-4"}))

        self._reload_and_run(tmp_janitor_home, "config")
        captured = capsys.readouterr()
        assert "~ model" in captured.out or "model" in captured.out
        assert "gpt-3" in captured.out
        assert "gpt-4" in captured.out

    def test_apply_creates_backup(self, tmp_janitor_home: Path, capsys) -> None:
        active = tmp_janitor_home / "config.yaml"
        asset = tmp_janitor_home / "janitor-core" / "assets" / "janitor" / "config.yaml"
        active.write_text(yaml.safe_dump({"model": "gpt-3"}))
        asset.write_text(yaml.safe_dump({"model": "gpt-4"}))

        self._reload_and_run(tmp_janitor_home, "--apply", "config")
        captured = capsys.readouterr()
        assert (tmp_janitor_home / "config.yaml.bak").exists()
        assert "Aplicando" in captured.out or "aplicado" in captured.out

        loaded = yaml.safe_load(active.read_text())
        assert loaded["model"] == "gpt-4"

    def test_apply_restores_on_bad_yaml(self, tmp_janitor_home: Path, capsys) -> None:
        active = tmp_janitor_home / "config.yaml"
        asset = tmp_janitor_home / "janitor-core" / "assets" / "janitor" / "config.yaml"
        active.write_text(yaml.safe_dump({"model": "gpt-3"}))
        asset.write_text("bad: yaml: : :")

        exit_code = self._reload_and_run(tmp_janitor_home, "--apply", "config")
        captured = capsys.readouterr()
        assert "RESTORED" in captured.out or "restaurado" in captured.out
        assert exit_code != 0

        loaded = yaml.safe_load(active.read_text())
        assert loaded["model"] == "gpt-3"
