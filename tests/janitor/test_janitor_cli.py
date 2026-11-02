"""Tests for Janitor CLI wrapper.

Verifies that the `janitor` command and JanitorCLI class exist and satisfy
the JANITOR FORK DIRECTIVES requirements.
"""

import subprocess
import sys
from pathlib import Path

from tests.janitor.checkout_metadata import declared_entry_points


PROJECT_ROOT = Path(__file__).resolve().parents[2]


class TestJanitorCLIExists:
    """Test that JanitorCLI is properly defined and importable."""

    def test_janitorcli_class_exists(self):
        """JanitorCLI must be importable from janitor_cli module."""
        import janitor_cli

        assert hasattr(janitor_cli, "JanitorCLI"), (
            "JanitorCLI class not found in janitor_cli module"
        )

    def test_janitorcli_inherits_from_hermescli(self):
        """JanitorCLI must inherit from HermesCLI per CLI WRAPPER directive."""
        import janitor_cli
        from cli import HermesCLI

        assert issubclass(janitor_cli.JanitorCLI, HermesCLI), (
            "JanitorCLI must inherit from HermesCLI"
        )

    def test_janitorcli_has_skin_force_property(self):
        """JanitorCLI must expose a mechanism to force the Janitor skin."""
        import janitor_cli

        assert (
            hasattr(janitor_cli.JanitorCLI, "force_skin")
            or hasattr(janitor_cli.JanitorCLI, "get_skin_name")
            or "skin" in dir(janitor_cli.JanitorCLI)
        ), "JanitorCLI must have skin forcing capability"

    def test_janitor_module_has_main_function(self):
        """janitor_cli must expose a main() function for pyproject entry point."""
        import janitor_cli

        assert hasattr(janitor_cli, "main"), "janitor_cli must expose a main() function"


class TestJanitorCommand:
    """Test that the `janitor` command is registered and executable."""

    def test_janitor_console_script_is_registered(self):
        """Every install registers the `janitor` console script, dispatching to
        `janitor.cli:main`. scripts/janitor-install.sh relies on this to put
        `janitor` on PATH; importing janitor.cli.main directly does not prove
        registration. The test interpreter does not install the checkout, so
        the registration is read from the declaration every install uses.
        """
        janitor = declared_entry_points()["console_scripts"].get("janitor")

        assert janitor is not None, "[project.scripts] in pyproject.toml must declare `janitor`"
        assert janitor == "janitor.cli:main", (
            f"`janitor` must dispatch to janitor.cli:main, got {janitor!r}"
        )

    def test_pre_1_0_console_script_target_still_runs(self):
        """Installs from before 1.0 keep a script that imports janitor_cli:main
        until their venv is reinstalled; the alias must be the real module."""
        import janitor.cli
        import janitor_cli

        assert janitor_cli is janitor.cli
        assert janitor_cli.main is janitor.cli.main

    def test_hermes_home_is_overridden_to_janitor(self):
        """HERMES_HOME must be set to ~/.janitor before any hermes imports.

        Uses subprocess to isolate from pytest fixture interference (monkeypatch,
        xdist worker cache). In-process import would hit the module singleton
        cache, making this test flaky in CI with pytest-xdist.
        """
        result = subprocess.run(
            [sys.executable, "-c",
             "import os; import janitor_cli; "
             "assert os.environ['HERMES_HOME'].endswith('.janitor'), "
             "f\"HERMES_HOME was not set to ~/.janitor: {os.environ['HERMES_HOME']}\""],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, (
            f"HERMES_HOME not set to ~/.janitor in subprocess. "
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )

    def test_janitor_command_available_in_path(self, tmp_path):
        """The `janitor` command must be available after installation."""
        python_exec = sys.executable
        result = subprocess.run(
            [python_exec, "-c",
             "import sys; sys.argv = ['janitor', '--version']; "
             "from janitor_cli import main; main()"],
            capture_output=True,
            text=True,
            env={
                **subprocess.os.environ.copy(),
                "HERMES_QUIET": "1",
                "OPENAI_API_KEY": "test-key",
                "HONCHO_API_KEY": "test-key",
                # Override HOME so the dotenv loader finds no .env to clobber
                # the HONCHO_API_KEY we just set with an empty value. The
                # production OWASP guard itself is unchanged — it sees a
                # non-empty HONCHO_API_KEY and returns early.
                "HOME": str(tmp_path),
            },
        )
        assert result.returncode in (0, 2), (
            f"`janitor` command not found. Is the package installed? stderr: {result.stderr}"
        )

    def test_janitor_help_does_not_crash(self, tmp_path):
        """`janitor --help` must execute without errors (exit 0 or 2 for argparse)."""
        python_exec = sys.executable
        result = subprocess.run(
            [python_exec, "-c",
             "import sys; sys.argv = ['janitor', '--help']; "
             "from janitor_cli import main; main()"],
            capture_output=True,
            text=True,
            env={
                **subprocess.os.environ.copy(),
                "HERMES_QUIET": "1",
                "OPENAI_API_KEY": "test-key",
                "HONCHO_API_KEY": "test-key",
                # Override HOME so the dotenv loader finds no .env to clobber
                # the HONCHO_API_KEY we just set with an empty value. The
                # production OWASP guard itself is unchanged — it sees a
                # non-empty HONCHO_API_KEY and returns early.
                "HOME": str(tmp_path),
            },
        )
        assert result.returncode in (0, 2), (
            f"janitor --help failed with code {result.returncode}. stderr: {result.stderr}"
        )


class TestJanitorCLIBranding:
    """Test that JanitorCLI forces Janitor visual identity."""

    def test_janitorcli_returns_janitor_skin_name(self):
        """JanitorCLI.get_skin_name() must return 'sentry-janitor'."""
        import janitor_cli

        jcli = janitor_cli.JanitorCLI.__new__(janitor_cli.JanitorCLI)
        assert jcli.get_skin_name() == "sentry-janitor", (
            "JanitorCLI must return 'sentry-janitor' from get_skin_name()"
        )

    def test_janitorcli_force_skin_is_true(self):
        """JanitorCLI.force_skin property must be True."""
        import janitor_cli

        jcli = janitor_cli.JanitorCLI.__new__(janitor_cli.JanitorCLI)
        assert jcli.force_skin is True, "JanitorCLI.force_skin must be True"


class TestOWASPFailSafe:
    """Test OWASP fail-safe for Honcho memory integration."""

    def test_owasp_blocked_when_honcho_configured_but_no_env_vars(
        self, tmp_path, monkeypatch
    ):
        """Must exit with code 1 when memory.provider=honcho and no HONCHO_API_KEY."""
        monkeypatch.delenv("HONCHO_API_KEY", raising=False)
        monkeypatch.delenv("HONCHO_BASE_URL", raising=False)
        config_file = tmp_path / "config.yaml"
        config_file.write_text("memory:\n  provider: honcho\n")
        import janitor_cli

        ok, msg = janitor_cli._owasp_honcho_fail_safe_for_test(str(tmp_path))
        assert not ok, f"OWASP check should have blocked but passed. msg: {msg}"
        assert "HONCHO_API_KEY" in msg

    def test_owasp_allows_when_honcho_key_set(self, tmp_path, monkeypatch):
        """Must NOT block when HONCHO_API_KEY is set even if memory.provider=honcho."""
        monkeypatch.setenv("HONCHO_API_KEY", "test-key-from-env")
        import janitor_cli

        ok, msg = janitor_cli._owasp_honcho_fail_safe_for_test(str(tmp_path))
        assert ok, f"OWASP should allow when HONCHO_API_KEY is set: {msg}"

    def test_owasp_allows_when_honcho_base_url_set(self, tmp_path, monkeypatch):
        """Must NOT block when HONCHO_BASE_URL is set (local Honcho instance)."""
        monkeypatch.setenv("HONCHO_BASE_URL", "http://localhost:1973")
        import janitor_cli

        ok, msg = janitor_cli._owasp_honcho_fail_safe_for_test(str(tmp_path))
        assert ok, f"OWASP should allow when HONCHO_BASE_URL is set: {msg}"

    def test_owasp_allows_when_memory_provider_not_honcho(self, tmp_path, monkeypatch):
        """Must NOT block when memory.provider is something other than honcho."""
        config_file = tmp_path / "config.yaml"
        config_file.write_text("memory:\n  provider: mem0\n")
        import janitor_cli

        ok, msg = janitor_cli._owasp_honcho_fail_safe_for_test(str(tmp_path))
        assert ok, f"OWASP should allow when provider is not honcho: {msg}"


class TestJanitorVersionDisplay:
    """Behavior: Janitor shows ``<hermes>-janitor.N`` in banner and --version."""

    def test_canonical_version_is_pep440_local(self):
        """The running identity is pyproject's ``<hermes>+janitor.N``."""
        import re
        import tomllib

        from hermes_cli.version_info import _reset_version_info_cache, get_version_info

        _reset_version_info_cache()
        declared = tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
        assert re.fullmatch(r"\d+\.\d+\.\d+\+janitor\.\d+", declared), declared
        assert get_version_info().base_version == declared

    def test_fork_release_tags_do_not_become_the_hermes_version(self, tmp_path, monkeypatch):
        """A reachable ``v1.0.0`` Janitor release tag must not read as Hermes 1.0.0."""
        import subprocess

        from hermes_cli.version_info import _reset_version_info_cache, get_version_info

        def git(*args):
            subprocess.run(
                ["git", "-c", "user.email=t@example.invalid", "-c", "user.name=t", *args],
                cwd=tmp_path, check=True, capture_output=True,
            )

        git("init", "-q")
        (tmp_path / "pyproject.toml").write_text(
            '[project]\nname = "hermes-agent"\nversion = "0.22.5+janitor.3"\n', encoding="utf-8"
        )
        git("add", "pyproject.toml")
        git("commit", "-qm", "release")
        git("tag", "v1.0.0")
        git("tag", "v0.22.5")
        monkeypatch.setattr("hermes_cli.version_info._resolve_stamp_file", lambda: None)
        monkeypatch.setattr("hermes_cli.version_info._resolve_repo_dir", lambda: tmp_path)
        _reset_version_info_cache()
        try:
            info = get_version_info()
        finally:
            _reset_version_info_cache()

        assert info.base_version == info.derived_version == "0.22.5+janitor.3"

    def test_display_version_replaces_plus_with_hyphen(self):
        """janitor_version.display_version converts + to - in the local segment."""
        from janitor_version import display_version

        assert display_version("0.20.1+janitor.1") == "0.20.1-janitor.1"

    def test_display_version_is_pure(self):
        """display_version depends only on its argument."""
        from janitor_version import display_version

        assert display_version("1.2.3+local.5") == "1.2.3-local.5"
        assert display_version("1.2.3") == "1.2.3"

    def test_module_canonical_matches_helper_output(self):
        """The running version round-trips through display_version to the display form."""
        from hermes_cli.version_info import get_version_info
        from janitor_version import display_version

        version = get_version_info().derived_version
        assert display_version(version) == version.replace("+janitor.", "-janitor.")

    def test_subprocess_janitor_version_uses_display_form(self, tmp_path):
        """The real module entry point honors --version without entering chat."""
        import subprocess
        import sys

        result = subprocess.run(
            [sys.executable, "-m", "janitor_cli", "--version"],
            capture_output=True,
            text=True,
            env={
                **subprocess.os.environ.copy(),
                "HERMES_QUIET": "1",
                "OPENAI_API_KEY": "test-key",
                "HONCHO_API_KEY": "test-key",
                # Override HOME so the dotenv loader finds no .env to clobber
                # the HONCHO_API_KEY we just set with an empty value. The
                # production OWASP guard itself is unchanged — it sees a
                # non-empty HONCHO_API_KEY and returns early.
                "HOME": str(tmp_path),
            },
        )
        from hermes_cli.version_info import get_version_info
        from janitor_version import display_version

        version = get_version_info().derived_version
        combined = result.stdout + result.stderr
        assert f"THE JANITOR v{display_version(version)}" in combined
        assert version not in combined
