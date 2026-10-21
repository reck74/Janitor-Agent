"""Regression tests for janitor/cli.py monkey-patch signature compatibility.

CONTEXT
    janitor_cli.py monkey-patches several upstream functions at import time.
    When upstream changes a function's signature (adds/removes parameters),
    the Janitor wrapper can silently diverge. The `-X theirs` merge strategy
    adopts upstream's caller AND callee changes, but never touches
    janitor_cli.py (fork-only file), so the wrapper keeps its old signature
    and crashes at runtime.

    This happened in the v2026.7.7.2 sync: upstream PR #47846 added a
    ``context_length`` parameter to ``prompt_builder.load_soul_md`` and
    changed the call site in ``system_prompt.py:186`` to pass it. The
    Janitor wrapper ``_janitor_load_soul_md`` still had zero args, causing
    ``TypeError: _janitor_load_soul_md() takes 0 positional arguments but
    1 was given``. Fixed in PR #44; these tests prevent recurrence.

INVARIANT
    Each patched wrapper MUST accept every parameter the upstream original
    accepts. We verify two ways:

    1. Structural — inspect.signature(wrapper) >= inspect.signature(original)
    2. Behavioral — call the wrapper with representative upstream args

Since Janitor 1.0 the ``load_soul_md`` patch is gone: upstream already reads
``$HERMES_HOME/SOUL.md`` and the launcher points HERMES_HOME at ~/.janitor,
so the wrapper only bypassed upstream's injection scan and truncation. The
remaining patches (``hermes_cli.main.cmd_update`` and ``hermes_cli.tips``)
are applied inside ``janitor.cli.main()``, so the upstream originals are
still intact in the test process and can be compared directly.

See AGENTS.md directive #14 (MONKEY-PATCH SIGNATURE INVARIANTS).
"""

import inspect


def _missing_params(original, wrapper) -> set:
    original_params = inspect.signature(original).parameters
    wrapper_params = inspect.signature(wrapper).parameters
    if any(p.kind is p.VAR_KEYWORD for p in wrapper_params.values()):
        return set()
    return set(original_params) - set(wrapper_params)


class TestSoulMdServedByUpstream:
    """SOUL.md must come from upstream's loader reading the Janitor home."""

    def test_load_soul_md_is_not_patched(self):
        import janitor_cli  # noqa: F401
        from agent import prompt_builder

        assert prompt_builder.load_soul_md.__module__ == "agent.prompt_builder"

    def test_upstream_reads_soul_from_hermes_home(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HERMES_HOME", str(tmp_path))
        (tmp_path / "SOUL.md").write_text("Soy The Janitor.\n", encoding="utf-8")
        from agent import prompt_builder

        for ctx_len in (None, 200000):
            assert "Soy The Janitor." in prompt_builder.load_soul_md(ctx_len)


class TestCmdUpdateSignature:
    """hermes_cli.main.cmd_update — replaced by janitor.cli.main()."""

    def test_wrapper_signature_covers_original(self):
        import hermes_cli.main as hermes_main
        import janitor_cli

        assert hermes_main.cmd_update is not janitor_cli._janitor_cmd_update
        missing = _missing_params(hermes_main.cmd_update, janitor_cli._janitor_cmd_update)
        assert not missing, (
            f"upstream cmd_update now accepts {sorted(missing)} which "
            f"_janitor_cmd_update in janitor/cli.py does not."
        )


class TestTipsSignature:
    """hermes_cli.tips.get_random_tip / TIPS — replaced by janitor.cli.main()."""

    def test_wrapper_signature_covers_original(self):
        import hermes_cli.tips as hermes_tips
        from janitor.tips_es import get_janitor_tip

        missing = _missing_params(hermes_tips.get_random_tip, get_janitor_tip)
        assert not missing, (
            f"upstream get_random_tip now accepts {sorted(missing)} which "
            f"janitor.tips_es.get_janitor_tip does not."
        )

    def test_janitor_tips_match_upstream_shape(self):
        import hermes_cli.tips as hermes_tips
        from janitor.tips_es import JANITOR_TIPS, get_janitor_tip

        assert type(JANITOR_TIPS) is type(hermes_tips.TIPS)
        assert JANITOR_TIPS and all(isinstance(t, str) for t in JANITOR_TIPS)
        assert get_janitor_tip(exclude_recent=1) in JANITOR_TIPS


class TestArgparseInitSignature:
    """argparse.ArgumentParser.__init__ — patched globally."""

    def test_forwards_stdlib_args(self):
        """The wrapper uses ``*args, **kwargs`` so it forwards everything
        to the original. Verify stdlib's documented kwargs still work."""
        import argparse

        parser = argparse.ArgumentParser(
            prog="janitor-test",
            description="test",
            add_help=False,
        )
        assert parser.prog == "janitor-test"
        assert parser.description == "test"
