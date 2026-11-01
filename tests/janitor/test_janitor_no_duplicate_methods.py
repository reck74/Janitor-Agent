"""Regression test for duplicate method definitions in core files.

CONTEXT
    The v2026.7.7.2 upstream sync (merge 83d4f8d62) introduced a duplicate
    ``_refresh_agent_cache_message_count`` definition in ``gateway/run.py``:
    the Janitor fork had an ``async def`` version (commits 3bc4a2ff7,
    aa4731598, b4cacba6a) and upstream also added a ``def`` (sync) version
    in a different location of the same file. The ``-X theirs`` merge
    strategy resolved textual conflicts in upstream's favor but left both
    non-conflicting additions in place.

    Python's "last definition wins" rule meant the sync version silently
    shadowed the async one. Callers still used ``await``, so every Telegram
    message crashed with::

        TypeError: object NoneType can't be used in 'await' expression

    The response was generated correctly (~1000 chars) but discarded in
    favor of the generic error message (91 chars).

    Directive #14's monkey-patch signature test does NOT cover this bug
    class — it only checks ``janitor_cli.py`` wrappers, not merge artifacts
    inside core files. This test fills that gap.

INVARIANT
    No class in a scanned core file may define the same method name twice.
    No scanned core file may define the same module-level function twice.
    The post-fix state of ``_refresh_agent_cache_message_count`` is locked:
    exactly one definition, and it MUST be ``async`` (callers await it).

    Module-level duplicates are the same bug class one scope up: the same
    v2026.7.7.2 merge left SIX duplicated top-level functions in ``cli.py``
    (``_reset_terminal_input_modes_on_exit``, ``_should_emit_cleanup_session_finalize``,
    ``_notify_session_finalize``, ``_emit_interrupted_session_end``,
    ``_finalize_single_query``, ``_notify_single_query_session_finalize``)
    and one in ``gateway/run.py`` (``_load_gateway_runtime_config``).
    Class-method scanning alone cannot see them.

See AGENTS.md directive #15 (POST-SYNC DUPLICATE METHOD AUDIT).
"""

import ast
import pathlib

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]

# Top-level core modules plus every Python package of the Hermes core.
# The v2026.8.13 audit found merge duplicates in cron/, tools/, agent/,
# hermes_cli/ and tui_gateway/ — a hand-picked file list missed all of them,
# so the scan now covers the whole core tree.
_SCANNED_TOP_LEVEL = [
    "run_agent.py",
    "cli.py",
    "model_tools.py",
    "toolsets.py",
    "hermes_state.py",
    "hermes_constants.py",
]
_SCANNED_PACKAGES = [
    "agent",
    "tools",
    "cron",
    "hermes_cli",
    "gateway",
    "tui_gateway",
    "plugins",
    "acp_adapter",
    "providers",
    "janitor",
]

# Duplicates that exist verbatim in the upstream tag the fork is based on.
# They are upstream's to fix; touching them in the fork would add merge
# surface. Keyed by (relative path, "Class.method" or "function").
_UPSTREAM_KNOWN_DUPLICATES = {
    ("tools/url_safety.py", "_Transport.__init__"),
    ("tui_gateway/server.py", "_content_display_text"),
    # v2026.9.24 PLUGIN-COMPAT blocks: the second module ``__getattr__`` saves
    # the first as ``_plugin_compat_prev_getattr`` and chains to it.
    ("hermes_cli/main.py", "__getattr__"),
    ("tools/mcp_tool.py", "__getattr__"),
    ("tools/skills_hub.py", "__getattr__"),
}

# ``_`` is the conventional name for decorator-registered RPC handlers
# (``@method("x") def _(...)``) — every definition is intentionally distinct.
_IGNORED_NAMES = {"_"}


def _iter_scanned_files():
    for name in _SCANNED_TOP_LEVEL:
        path = _REPO_ROOT / name
        if path.exists():
            yield path
    for package in _SCANNED_PACKAGES:
        root = _REPO_ROOT / package
        if not root.exists():
            continue
        for path in sorted(root.rglob("*.py")):
            rel = path.relative_to(_REPO_ROOT).as_posix()
            if "/tests/" in f"/{rel}" or path.name.startswith("test_"):
                continue
            if "node_modules" in path.parts:
                continue
            yield path


_SCANNED_FILES = list(_iter_scanned_files())


def _rel(path: pathlib.Path) -> str:
    return path.resolve().relative_to(_REPO_ROOT).as_posix()


def _decorator_name(dec: ast.expr) -> str:
    """Extract a readable decorator name: ``property``, ``base_url.setter``,
    ``cached_property``, etc. Returns ``""`` if unparseable."""
    if isinstance(dec, ast.Name):
        return dec.id
    if isinstance(dec, ast.Attribute):
        parts = []
        cur = dec
        while isinstance(cur, ast.Attribute):
            parts.append(cur.attr)
            cur = cur.value
        if isinstance(cur, ast.Name):
            parts.append(cur.id)
        return ".".join(reversed(parts))
    return ""


def _is_property_accessor(node: ast.FunctionDef) -> bool:
    """True if this def is part of a property getter/setter/deleter pair
    (``@property``, ``@X.setter``, ``@X.deleter``, ``@cached_property``).
    These are intentional same-name pairs, NOT merge artifacts."""
    decos = {_decorator_name(d) for d in node.decorator_list}
    if decos & {"property", "cached_property", "functools.cached_property", "overload", "typing.overload"}:
        return True
    # @<something>.setter / .deleter / .getter, and @f.register (singledispatch)
    for d in decos:
        if d.endswith((".setter", ".deleter", ".getter", ".register")):
            return True
    return False


def _collect_class_methods(tree: ast.Module):
    """Yield ``(class_name, method_name, lineno, is_async)`` for every
    method defined directly inside a ClassDef, EXCLUDING property
    getter/setter/deleter accessors (those are intentional same-name pairs)."""
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        for child in node.body:
            if not isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if _is_property_accessor(child):
                continue
            yield (
                node.name,
                child.name,
                child.lineno,
                isinstance(child, ast.AsyncFunctionDef),
            )


class TestNoDuplicateMethods:
    """No class in any scanned core file may define the same method twice.

    A duplicate means the second definition silently shadows the first
    (Python "last definition wins"). After a ``-X theirs`` merge this
    happens when the fork and upstream both add a method with the same
    name in different parts of the file — the merge tool sees no textual
    conflict and leaves both in place.
    """

    def test_gateway_run_py_has_no_duplicate_methods(self):
        """gateway/run.py is the file where the v2026.7.7.2 sync left a
        duplicate ``_refresh_agent_cache_message_count``. This is the
        canary — if a duplicate reappears here, the same Telegram-crash
        class of bug is back."""
        dups = _find_duplicates(_REPO_ROOT / "gateway/run.py")
        assert not dups, (
            f"Duplicate method definitions in gateway/run.py (last def wins): {dups}"
        )

    def test_all_scanned_core_files_have_no_duplicate_methods(self):
        """Broad scan: every file in _SCANNED_FILES must be duplicate-free."""
        missing = [str(p) for p in _SCANNED_FILES if not p.exists()]
        assert not missing, f"Scanned files missing (update _SCANNED_FILES): {missing}"

        all_dups = {}
        for path in _SCANNED_FILES:
            dups = _find_duplicates(path)
            if dups:
                all_dups[_rel(path)] = dups
        assert not all_dups, (
            f"Duplicate method definitions found (last def wins in each):\n"
            + "\n".join(f"  {f}: {d}" for f, d in all_dups.items())
        )


def _find_duplicates(path: pathlib.Path):
    """Return ``{(class, method): [(lineno, is_async), ...]}`` for methods
    defined more than once in the same class."""
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    seen: dict[tuple[str, str], list[tuple[int, bool]]] = {}
    for class_name, method_name, lineno, is_async in _collect_class_methods(tree):
        if method_name in _IGNORED_NAMES:
            continue
        key = (class_name, method_name)
        seen.setdefault(key, []).append((lineno, is_async))
    rel = _rel(path)
    return {
        f"{cls}.{method}": locs
        for (cls, method), locs in seen.items()
        if len(locs) > 1 and (rel, f"{cls}.{method}") not in _UPSTREAM_KNOWN_DUPLICATES
    }


def _collect_module_functions(tree: ast.Module):
    """Yield ``(function_name, lineno, is_async)`` for every function defined
    DIRECTLY at module top level (``tree.body``). Functions nested inside
    classes, ``if``/``try`` blocks or other functions are excluded — platform
    or import-fallback conditional definitions are intentional, and merge
    artifacts always appear as sequential top-level defs."""
    for child in tree.body:
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if _is_property_accessor(child):
                continue
            yield (
                child.name,
                child.lineno,
                isinstance(child, ast.AsyncFunctionDef),
            )


def _find_module_duplicates(path: pathlib.Path):
    """Return ``{function_name: [(lineno, is_async), ...]}`` for top-level
    functions defined more than once in the same file."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    seen: dict[str, list[tuple[int, bool]]] = {}
    for name, lineno, is_async in _collect_module_functions(tree):
        if name in _IGNORED_NAMES:
            continue
        seen.setdefault(name, []).append((lineno, is_async))
    rel = _rel(path)
    return {
        name: locs
        for name, locs in seen.items()
        if len(locs) > 1 and (rel, name) not in _UPSTREAM_KNOWN_DUPLICATES
    }


class TestNoDuplicateModuleLevelFunctions:
    """No scanned core file may define the same module-level function twice.

    The v2026.7.7.2 merge left six duplicated top-level functions in
    ``cli.py`` and one (``_load_gateway_runtime_config``) in
    ``gateway/run.py`` — identical copies the class-method scan cannot see.
    Today the copies are byte-identical (benign); the danger is the NEXT
    sync editing only one copy and silently shadowing the other, exactly
    how the Telegram crash started."""

    def test_all_scanned_core_files_have_no_duplicate_module_functions(self):
        """Broad scan: every file in _SCANNED_FILES must be free of
        duplicate top-level function definitions."""
        missing = [str(p) for p in _SCANNED_FILES if not p.exists()]
        assert not missing, f"Scanned files missing (update _SCANNED_FILES): {missing}"

        all_dups = {}
        for path in _SCANNED_FILES:
            dups = _find_module_duplicates(path)
            if dups:
                all_dups[_rel(path)] = dups
        assert not all_dups, (
            f"Duplicate module-level function definitions found (last def wins):\n"
            + "\n".join(f"  {f}: {d}" for f, d in all_dups.items())
        )


def _gateway_sources():
    """``(rel_path, source)`` for every gateway module. Since v2026.9.24 the
    method lives in the ``gateway/run_agent_cache.py`` mixin and its callers
    are spread across ``GatewayRunner``'s other mixins, so the lock covers the
    whole package: a second definition in ANY mixin shadows the first via MRO.
    """
    for path in sorted((_REPO_ROOT / "gateway").rglob("*.py")):
        yield _rel(path), path.read_text(encoding="utf-8")


def _refresh_defs(kind):
    return [
        (rel, n.lineno)
        for rel, source in _gateway_sources()
        for n in ast.walk(ast.parse(source))
        if type(n) is kind and n.name == "_refresh_agent_cache_message_count"
    ]


class TestRefreshAgentCacheMessageCountRegression:
    """Targeted regression: the exact method that broke Telegram in
    v2026.7.7.2. Locks the post-fix state so the same bug class cannot
    silently return on a future sync."""

    def test_exactly_one_definition(self):
        """If a future merge re-introduces a duplicate, this fails before
        the duplicate can shadow the async version."""
        defs = _refresh_defs(ast.AsyncFunctionDef) + _refresh_defs(ast.FunctionDef)
        assert len(defs) == 1, (
            f"Expected exactly 1 definition of _refresh_agent_cache_message_count "
            f"in gateway/, found {defs}. A duplicate means one silently shadows the other."
        )

    def test_definition_is_async(self):
        """Callers ``await`` this method. If a sync version shadows the async
        one, ``await`` returns ``TypeError: object NoneType can't be used in
        'await' expression``."""
        defs = _refresh_defs(ast.AsyncFunctionDef)
        assert len(defs) == 1, (
            f"Expected 1 async def in gateway/, found {defs}. "
            "Callers use `await` — the method must be a coroutine."
        )

    def test_no_sync_shadow(self):
        """No plain ``def _refresh_agent_cache_message_count`` may exist.
        If present, Python's last-definition-wins rule (or the mixin MRO)
        would let it shadow the async version."""
        sync_defs = _refresh_defs(ast.FunctionDef)
        assert not sync_defs, f"Sync `def` found at {sync_defs} — would shadow the async version."

    def test_resolved_method_is_a_coroutine(self):
        """What ``GatewayRunner`` actually resolves through its mixins."""
        import inspect

        from gateway.run import GatewayRunner

        assert inspect.iscoroutinefunction(GatewayRunner._refresh_agent_cache_message_count)

    def test_callers_use_await(self):
        """Every call site of this method must use ``await``. If a caller
        drops ``await`` because it assumes a sync return, it breaks when
        the (correct) async version is active."""
        calls = 0
        for rel, source in _gateway_sources():
            for lineno, line in enumerate(source.splitlines(), start=1):
                if "_refresh_agent_cache_message_count(" in line and "def " not in line:
                    calls += 1
                    assert "await" in line, (
                        f"{rel}:{lineno}: call without `await` — method is async: "
                        f"{line.strip()}"
                    )
        assert calls, "No call sites found — the cache refresh is no longer wired in."
