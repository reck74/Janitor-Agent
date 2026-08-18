"""Task 16 A.7 fix: post-pull syntax guard must cover Janitor-fork files.

Upstream's ``_UPDATE_CRITICAL_FILES`` (hermes_cli/update_cmd.py) lists only
Hermes core files. The Janitor entry chain (janitor_cli -> janitor_update_
bootstrap -> janitor_update_core, plus janitor_version and the janitor_ext
package imported at startup) is equally boot-critical for the ``janitor``
command: a syntax error there bricks the CLI exactly like a broken
``hermes_cli/main.py``. The fork therefore wraps the upstream validator so
fork files are also py_compiled post-pull, with auto-rollback on failure.

These tests lock that invariant WITHOUT touching Hermes core: the wrapper
lives in ``janitor_update_core`` (JANITOR FORK DIRECTIVE #13) and is bound
into the module's lazy-helper seam.
"""
from pathlib import Path

import janitor_update_core as juc


def _write_clean_fork_files(root: Path) -> None:
    for rel in juc._JANITOR_CRITICAL_FILES:
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("x = 1\n", encoding="utf-8")


def test_janitor_critical_files_cover_the_entry_chain():
    """Every fork module on the `janitor` boot path is in the guard list."""
    required = {
        "janitor_cli.py",
        "janitor_update_core.py",
        "janitor_update_bootstrap.py",
        "janitor_version.py",
        "janitor_ext/__init__.py",
        "janitor_ext/tips_es.py",
    }
    assert required.issubset(set(juc._JANITOR_CRITICAL_FILES))


def test_fork_validator_catches_syntax_error_in_janitor_cli(tmp_path):
    """A.7 regression: broken janitor_cli.py must fail validation even when
    the upstream helper (which only knows Hermes files) reports success."""
    (tmp_path / "janitor_cli.py").write_text("def broken(: pass\n", encoding="utf-8")
    validator = juc._make_fork_syntax_validator(lambda root: (True, None, None))

    ok, failing_path, error = validator(tmp_path)

    assert ok is False
    assert failing_path == str(tmp_path / "janitor_cli.py")
    assert "SyntaxError" in (error or "")


def test_fork_validator_propagates_upstream_failure_unchanged(tmp_path):
    """Upstream failures short-circuit: wrapper never masks a Hermes break."""
    _write_clean_fork_files(tmp_path)
    upstream_result = (False, str(tmp_path / "cli.py"), "SyntaxError: boom")
    validator = juc._make_fork_syntax_validator(lambda root: upstream_result)

    assert validator(tmp_path) == upstream_result


def test_fork_validator_runs_when_upstream_helper_unavailable(tmp_path):
    """A.7 trace showed the helper resolves to None on some paths — the fork
    files must STILL be validated rather than silently skipped."""
    (tmp_path / "janitor_version.py").write_text("def broken(: pass\n", encoding="utf-8")
    validator = juc._make_fork_syntax_validator(None)

    ok, failing_path, error = validator(tmp_path)

    assert ok is False
    assert failing_path == str(tmp_path / "janitor_version.py")


def test_fork_validator_passes_clean_tree(tmp_path):
    _write_clean_fork_files(tmp_path)
    validator = juc._make_fork_syntax_validator(lambda root: (True, None, None))

    assert validator(tmp_path) == (True, None, None)


def test_fork_validator_skips_missing_files(tmp_path):
    """Empty tree (no fork files present) validates OK — mirrors upstream's
    missing-file policy so foreign checkouts don't false-positive."""
    validator = juc._make_fork_syntax_validator(lambda root: (True, None, None))

    assert validator(tmp_path) == (True, None, None)


def test_ensure_loaded_installs_fork_wrapper(monkeypatch):
    """After _ensure_loaded(), the module-level validator is ALWAYS the
    fork-aware wrapper — including when the upstream helper is None."""
    monkeypatch.setattr(juc, "_validate_critical_files_syntax", None)
    juc._ensure_loaded()

    validator = juc._validate_critical_files_syntax
    assert validator is not None
    assert getattr(validator, "_janitor_fork_wrapper", False) is True


def test_ensure_loaded_does_not_double_wrap(monkeypatch):
    """The wiring is idempotent across repeated _ensure_loaded() calls."""
    monkeypatch.setattr(juc, "_validate_critical_files_syntax", None)
    juc._ensure_loaded()
    first = juc._validate_critical_files_syntax

    juc._ensure_loaded()

    assert juc._validate_critical_files_syntax is first
