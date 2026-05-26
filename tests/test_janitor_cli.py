"""Tests for Janitor CLI wrapper.

Verifies that the `janitor` command and JanitorCLI class exist and satisfy
the JANITOR FORK DIRECTIVES requirements.
"""

import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).parent.parent


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

    def test_janitor_command_available_in_path(self):
        """The `janitor` command must be available after installation."""
        python_exec = sys.executable
        result = subprocess.run(
            [python_exec, "-c", "from janitor_cli import main; main()"],
            capture_output=True,
            text=True,
            env={
                **subprocess.os.environ.copy(),
                "HERMES_QUIET": "1",
                "OPENAI_API_KEY": "test-key",
            },
        )
        assert result.returncode in (0, 2), (
            f"`janitor` command not found. Is the package installed? stderr: {result.stderr}"
        )

    def test_janitor_help_does_not_crash(self):
        """`janitor --help` must execute without errors (exit 0 or 2 for argparse)."""
        python_exec = sys.executable
        result = subprocess.run(
            [python_exec, "-c", "from janitor_cli import main; main()"],
            capture_output=True,
            text=True,
            env={
                **subprocess.os.environ.copy(),
                "HERMES_QUIET": "1",
                "OPENAI_API_KEY": "test-key",
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
