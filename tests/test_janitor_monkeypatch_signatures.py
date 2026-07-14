"""Regression tests for janitor_cli.py monkey-patch signature compatibility.

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

See AGENTS.md directive #14 (MONKEY-PATCH SIGNATURE INVARIANTS).
"""

import inspect


class TestLoadSoulMdSignature:
    """prompt_builder.load_soul_md — the patch that broke in v2026.7.7.2."""

    def test_wrapper_is_installed(self):
        """Importing janitor_cli must replace prompt_builder.load_soul_md
        with the Janitor wrapper. If this silently fails, every other test
        in this file is meaningless."""
        import janitor_cli
        from agent import prompt_builder

        assert prompt_builder.load_soul_md is janitor_cli._janitor_load_soul_md

    def test_accepts_context_length_positionally(self):
        """agent/system_prompt.py calls ``load_soul_md(_ctx_len)`` where
        _ctx_len is ``Optional[int]``. The wrapper must accept it."""
        from agent import prompt_builder

        for ctx_len in (None, 200000, 8000):
            prompt_builder.load_soul_md(ctx_len)

    def test_accepts_no_args(self):
        """Backward compatibility: some callers may invoke with no args."""
        from agent import prompt_builder

        prompt_builder.load_soul_md()

    def test_wrapper_signature_covers_original(self):
        """The wrapper's parameter set must be a superset of the original's.

        ``_original_load_soul_md`` is captured at import time from the
        CURRENT upstream ``prompt_builder.load_soul_md``, so if upstream
        adds a parameter and the sync adopts it, this comparison will fail
        until the wrapper is updated to match."""
        import janitor_cli

        original = janitor_cli._original_load_soul_md
        original_params = set(inspect.signature(original).parameters.keys())

        wrapper = janitor_cli._janitor_load_soul_md
        wrapper_params = set(inspect.signature(wrapper).parameters.keys())

        missing = original_params - wrapper_params
        assert not missing, (
            f"_janitor_load_soul_md accepts {sorted(wrapper_params)} but "
            f"upstream load_soul_md now accepts {sorted(original_params)}. "
            f"Missing parameters: {sorted(missing)}. Update the wrapper "
            f"signature in janitor_cli.py to match upstream."
        )


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
