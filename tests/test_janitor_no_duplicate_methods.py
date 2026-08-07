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

# Files scanned for duplicate method definitions within the same class.
# These are core files where the ``-X theirs`` merge strategy has
# historically left Janitor + upstream additions side-by-side.
_SCANNED_FILES = [
    pathlib.Path("gateway/run.py"),
    pathlib.Path("gateway/session.py"),
    pathlib.Path("run_agent.py"),
    pathlib.Path("cli.py"),
    pathlib.Path("plugins/platforms/telegram/adapter.py"),
    pathlib.Path("agent/tool_dispatch_helpers.py"),
]


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
    if "property" in decos or "cached_property" in decos:
        return True
    # @<something>.setter / .deleter / .getter
    for d in decos:
        if d.endswith((".setter", ".deleter", ".getter")):
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
        dups = _find_duplicates(pathlib.Path("gateway/run.py"))
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
                all_dups[str(path)] = dups
        assert not all_dups, (
            f"Duplicate method definitions found (last def wins in each):\n"
            + "\n".join(f"  {f}: {d}" for f, d in all_dups.items())
        )


def _find_duplicates(path: pathlib.Path):
    """Return ``{(class, method): [(lineno, is_async), ...]}`` for methods
    defined more than once in the same class."""
    source = path.read_text()
    tree = ast.parse(source)
    seen: dict[tuple[str, str], list[tuple[int, bool]]] = {}
    for class_name, method_name, lineno, is_async in _collect_class_methods(tree):
        key = (class_name, method_name)
        seen.setdefault(key, []).append((lineno, is_async))
    return {
        f"{cls}.{method}": locs
        for (cls, method), locs in seen.items()
        if len(locs) > 1
    }


def _collect_module_functions(tree: ast.Module):
    """Yield ``(function_name, lineno, is_async)`` for every function defined
    DIRECTLY at module top level (``tree.body``). Functions nested inside
    classes, ``if``/``try`` blocks or other functions are excluded — platform
    or import-fallback conditional definitions are intentional, and merge
    artifacts always appear as sequential top-level defs."""
    for child in tree.body:
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
            yield (
                child.name,
                child.lineno,
                isinstance(child, ast.AsyncFunctionDef),
            )


def _find_module_duplicates(path: pathlib.Path):
    """Return ``{function_name: [(lineno, is_async), ...]}`` for top-level
    functions defined more than once in the same file."""
    tree = ast.parse(path.read_text())
    seen: dict[str, list[tuple[int, bool]]] = {}
    for name, lineno, is_async in _collect_module_functions(tree):
        seen.setdefault(name, []).append((lineno, is_async))
    return {name: locs for name, locs in seen.items() if len(locs) > 1}


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
                all_dups[str(path)] = dups
        assert not all_dups, (
            f"Duplicate module-level function definitions found (last def wins):\n"
            + "\n".join(f"  {f}: {d}" for f, d in all_dups.items())
        )


class TestRefreshAgentCacheMessageCountRegression:
    """Targeted regression: the exact method that broke Telegram in
    v2026.7.7.2. Locks the post-fix state so the same bug class cannot
    silently return on a future sync."""

    def test_exactly_one_definition(self):
        """If a future merge re-introduces a duplicate, this fails before
        the duplicate can shadow the async version."""
        source = pathlib.Path("gateway/run.py").read_text()
        count = source.count("def _refresh_agent_cache_message_count(")
        assert count == 1, (
            f"Expected exactly 1 definition of _refresh_agent_cache_message_count, "
            f"found {count}. A duplicate means one silently shadows the other."
        )

    def test_definition_is_async(self):
        """Callers ``await`` this method (gateway/run.py:~12091, ~19951).
        If a sync version shadows the async one, ``await`` returns
        ``TypeError: object NoneType can't be used in 'await' expression``."""
        tree = ast.parse(pathlib.Path("gateway/run.py").read_text())
        defs = [
            n
            for n in ast.walk(tree)
            if isinstance(n, ast.AsyncFunctionDef)
            and n.name == "_refresh_agent_cache_message_count"
        ]
        assert len(defs) == 1, (
            f"Expected 1 async def, found {len(defs)}. "
            "Callers use `await` — the method must be a coroutine."
        )

    def test_no_sync_shadow(self):
        """No plain ``def _refresh_agent_cache_message_count`` may exist.
        If present, Python's last-definition-wins rule would let it shadow
        the async version even if the async def comes first."""
        tree = ast.parse(pathlib.Path("gateway/run.py").read_text())
        sync_defs = [
            n
            for n in ast.walk(tree)
            if isinstance(n, ast.FunctionDef)
            and not isinstance(n, ast.AsyncFunctionDef)
            and n.name == "_refresh_agent_cache_message_count"
        ]
        assert not sync_defs, (
            f"Found {len(sync_defs)} sync `def` at line(s) "
            f"{[d.lineno for d in sync_defs]} — would shadow the async version."
        )

    def test_callers_use_await(self):
        """Every call site of this method must use ``await``. If a caller
        drops ``await`` because it assumes a sync return, it breaks when
        the (correct) async version is active."""
        source = pathlib.Path("gateway/run.py").read_text()
        for lineno, line in enumerate(source.splitlines(), start=1):
            if "_refresh_agent_cache_message_count(" in line and "def " not in line:
                assert "await" in line, (
                    f"Line {lineno}: call without `await` — method is async: "
                    f"{line.strip()}"
                )
