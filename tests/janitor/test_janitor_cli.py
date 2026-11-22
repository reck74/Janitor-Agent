"""Tests for Janitor CLI wrapper.

Verifies that the `janitor` command and JanitorCLI class exist and satisfy
the JANITOR FORK DIRECTIVES requirements.
"""

import os
import subprocess
import sys
from importlib.metadata import entry_points
from pathlib import Path

import pytest

from tests.janitor.legacy_home import launcher_env

PROJECT_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module", autouse=True)
def _launcher_import_uses_a_temp_home(tmp_path_factory):
    """Importing janitor.cli seeds and initializes ``~/.janitor``: keep the
    in-process import off the real home."""
    patch = pytest.MonkeyPatch()
    patch.setenv("HOME", str(tmp_path_factory.mktemp("home")))
    yield
    patch.undo()


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
        """The `janitor` console script must exist in installed metadata.

        Given the package is installed, When console_scripts entry points are
        read, Then `janitor` is present and dispatches to `janitor.cli:main`.
        scripts/janitor-install.sh relies on this to put `janitor` on PATH;
        importing janitor.cli.main directly does not prove registration.
        """
        console_scripts = entry_points(group="console_scripts")
        janitor = {ep.name: ep.value for ep in console_scripts}.get("janitor")

        assert janitor is not None, (
            "`janitor` console script missing from installed metadata; "
            "[project.scripts] in pyproject.toml must declare it"
        )
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

    def test_hermes_home_is_overridden_to_janitor(self, tmp_path):
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
            env={**os.environ, "HOME": str(tmp_path), "HERMES_HOME": str(tmp_path / ".hermes")},
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
        """hermes_cli.__version__ carries the PEP 440 local segment."""
        import re
        import tomllib

        from hermes_cli import __version__

        assert re.fullmatch(r"\d+\.\d+\.\d+\+janitor\.\d+", __version__), __version__
        pyproject = tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        assert pyproject["project"]["version"] == __version__

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
        """The canonical __version__ round-trips through display_version to the display form."""
        from hermes_cli import __version__
        from janitor_version import display_version

        assert display_version(__version__) == __version__.replace("+janitor.", "-janitor.")

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
        from hermes_cli import __version__
        from janitor_version import display_version

        combined = result.stdout + result.stderr
        assert f"THE JANITOR v{display_version(__version__)}" in combined
        assert __version__ not in combined


class TestLauncherProfiles:
    """The desktop runs ``python -m janitor.cli [--profile P] serve`` with
    HERMES_HOME set to the root home; gateway services pin HERMES_HOME to a
    profile dir. Both must land on the profile, with only its own secrets."""

    @staticmethod
    def _homes(tmp_path):
        from janitor.seed import ensure_home

        root = tmp_path / ".janitor"
        ensure_home(root)
        (root / ".env").write_text("JANITOR_TEST_ROOT_SECRET=root\n", encoding="utf-8")
        profile = root / "profiles" / "coder"
        profile.mkdir(parents=True)
        (profile / "config.yaml").write_text("display:\n  language: en\n", encoding="utf-8")
        (profile / ".env").write_text("JANITOR_TEST_PROFILE_SECRET=coder\n", encoding="utf-8")
        return root, profile

    @staticmethod
    def _resolved(tmp_path, hermes_home, *argv):
        code = (
            "import os, sys; sys.argv = ['janitor', *sys.argv[1:]]; import janitor.cli; "
            "print(os.environ['HERMES_HOME']); "
            "print(os.environ.get('JANITOR_TEST_ROOT_SECRET', '-')); "
            "print(os.environ.get('JANITOR_TEST_PROFILE_SECRET', '-'))"
        )
        env = launcher_env(tmp_path)
        env["HERMES_HOME"] = str(hermes_home)
        result = subprocess.run(
            [sys.executable, "-c", code, *argv],
            capture_output=True, text=True, env=env, cwd=str(tmp_path), timeout=180,
        )
        assert result.returncode == 0, result.stderr
        return result.stdout.strip().splitlines()[-3:]

    def test_desktop_profile_flag_gets_the_profile_home_and_no_root_secrets(self, tmp_path):
        root, profile = self._homes(tmp_path)
        assert self._resolved(tmp_path, root, "--profile", "coder", "serve") == [str(profile), "-", "coder"]

    def test_profile_pinned_hermes_home_is_kept(self, tmp_path):
        root, profile = self._homes(tmp_path)
        assert self._resolved(tmp_path, profile, "serve") == [str(profile), "-", "coder"]

    def test_root_home_without_profile_stays_on_the_root(self, tmp_path):
        root, _ = self._homes(tmp_path)
        assert self._resolved(tmp_path, root, "serve") == [str(root), "root", "-"]

    def test_foreign_hermes_home_is_replaced_by_the_janitor_home(self, tmp_path):
        root, _ = self._homes(tmp_path)
        assert self._resolved(tmp_path, tmp_path / ".hermes", "serve")[0] == str(root)


class TestLauncherCatalog:
    """Every start reconciles the served home's skills with the catalog (F2-01)."""

    @staticmethod
    def _run(tmp_path, *argv):
        env = launcher_env(tmp_path)
        env["HERMES_HOME"] = str(tmp_path / ".janitor")
        result = subprocess.run(
            [sys.executable, "-c", "import sys; sys.argv = ['janitor', *sys.argv[1:]]; import janitor.cli", *argv],
            capture_output=True, text=True, env=env, cwd=str(tmp_path), timeout=180,
        )
        assert result.returncode == 0, result.stderr
        return result

    @staticmethod
    def _blank_dirs(home):
        import yaml

        path = home / "config.yaml"
        config = yaml.safe_load(path.read_text(encoding="utf-8"))
        config["skills"]["external_dirs"] = []
        path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
        return path.read_bytes()

    @staticmethod
    def _dirs(home):
        import yaml

        return yaml.safe_load((home / "config.yaml").read_text(encoding="utf-8"))["skills"]["external_dirs"]

    def test_profile_flag_applies_the_catalog_to_the_profile_home_only(self, tmp_path, monkeypatch):
        from janitor.profile_templates import create_from_template
        from janitor.seed import ensure_home

        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        root = tmp_path / ".janitor"
        monkeypatch.setenv("HERMES_HOME", str(root))
        ensure_home(root)
        profile = create_from_template("investigador", home_root=root).path
        expected = self._dirs(profile)
        root_before = self._blank_dirs(root)
        self._blank_dirs(profile)

        self._run(tmp_path, "--profile", "investigador", "serve")

        assert self._dirs(profile) == expected
        assert (root / "config.yaml").read_bytes() == root_before

    def test_existing_style_home_is_untouched(self, tmp_path):
        root = tmp_path / ".janitor"
        root.mkdir()
        legacy = ("# mine\nplugins:\n  enabled: [janitor]\nskills:\n"
                  "  external_dirs:\n  - ${JANITOR_SKILLS_ROOT}\n")
        (root / "config.yaml").write_text(legacy, encoding="utf-8")

        self._run(tmp_path, "serve")

        assert (root / "config.yaml").read_text(encoding="utf-8") == legacy

    def test_broken_catalog_input_never_stops_the_launcher(self, tmp_path):
        root = tmp_path / ".janitor"
        root.mkdir()
        broken = "janitor:\n  template: main\n  skills: {not: a-list}\n"
        (root / "config.yaml").write_text(broken, encoding="utf-8")

        self._run(tmp_path, "serve")  # returncode 0 asserted inside

        assert (root / "config.yaml").read_text(encoding="utf-8") == broken


@pytest.mark.parametrize(
    ("current", "expected"),
    [
        (None, ".janitor"),
        ("", ".janitor"),
        ("~/.hermes", ".janitor"),
        ("~/.hermes/profiles/coder", ".janitor"),
        ("~/.janitor", ".janitor"),
        ("~/.janitor/profiles/coder", ".janitor/profiles/coder"),
        ("~/elsewhere/profiles/coder", ".janitor"),
    ],
)
def test_resolve_hermes_home(tmp_path, monkeypatch, current, expected):
    from janitor.home import resolve_hermes_home

    monkeypatch.setenv("HOME", str(tmp_path))
    assert resolve_hermes_home(current) == tmp_path / expected
