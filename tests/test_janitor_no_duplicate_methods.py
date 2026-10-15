"""Directive #15: detect merge shadows across the extracted core modules.

The July sync left async/sync duplicates and broke every Telegram turn.
AST inspection is intentional for this structural fork invariant. Scan the
facades and their extracted modules; never silently drop a renamed file.
"""

import ast
from functools import cache
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REQUIRED_FILES = ("gateway/run.py", "gateway/run_agent_cache.py", "gateway/run_turn.py",
                  "gateway/session.py", "run_agent.py", "cli.py",
                  "plugins/platforms/telegram/adapter.py", "cron/jobs.py")
CORE_DIRS = ("agent", "gateway", "hermes_cli", "tui_gateway", "tools", "providers", "plugins/platforms", "cron", "janitor_ext", "acp_adapter")
# Concrete wrappers around HandlerRegistry.method / server.method in the
# extracted JSON-RPC modules; unlike plain decorators they retain each body.
RPC_REGISTRARS = {"method", "_controller_method", "_projects_handler", "_projects_method",
                  "_room_method", "_profile_handler", "_session_method", "_pet_method",
                  "_rpc", "_scoped_rpc", "_mcp_rpc"}


@cache
def _tree(path):
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _scanned_files():
    missing = [name for name in REQUIRED_FILES if not (ROOT / name).is_file()]
    assert not missing, f"Core entry/refactor files missing; audit their replacements: {missing}"
    files = {ROOT / name for name in REQUIRED_FILES}
    for directory in CORE_DIRS:
        files.update((ROOT / directory).rglob("*.py"))
    files.update(ROOT.glob("*.py"))
    return sorted(files)


def _decorator_name(node):
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = _decorator_name(node.value)
        return f"{base}.{node.attr}" if base else node.attr
    return ""


def _declarations(body):
    for child in body:
        if not isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        decorators = {_decorator_name(d) for d in child.decorator_list}
        # Overload declarations and property accessors do not replace the
        # runtime getter/body. Two getters or ordinary methods still fail.
        if decorators & {"overload", "typing.overload"}:
            continue
        if any(name.endswith((".setter", ".deleter", ".getter")) for name in decorators):
            continue
        yield child


def _duplicate_declarations(body):
    seen = {}
    for node in _declarations(body):
        key = node.name
        # JSON-RPC handlers deliberately use `_`; the decorator stores each
        # callable by route before the next definition binds that local name.
        # Audit the registered route, so a duplicate route still fails.
        if node.name == "_":
            for decorator in node.decorator_list:
                if (isinstance(decorator, ast.Call) and _decorator_name(decorator.func) in RPC_REGISTRARS
                        and len(decorator.args) >= 1 and isinstance(decorator.args[0], ast.Constant)
                        and isinstance(decorator.args[0].value, str)):
                    route = decorator.args[0].value
                    if _decorator_name(decorator.func) == "_mcp_rpc":
                        route = f"mcp.servers.{route}"
                    key = f"@method({route!r})"
                    break
        seen.setdefault(key, []).append(node.lineno)
    return {name: lines for name, lines in seen.items() if len(lines) > 1}


def _class_duplicates(tree):
    result = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            duplicates = _duplicate_declarations(node.body)
            if duplicates:
                # Distinct homonymous nested classes are independent scopes.
                result[f"{node.name} (line {node.lineno})"] = duplicates
    return result


def test_no_core_class_or_module_function_is_silently_shadowed():
    failures = {}
    for path in _scanned_files():
        tree = _tree(path)
        classes = _class_duplicates(tree)
        functions = _duplicate_declarations(tree.body)
        if classes or functions:
            failures[path.relative_to(ROOT).as_posix()] = {"classes": classes, "functions": functions}
    assert not failures, f"Duplicate runtime definitions (last definition wins): {failures}"


def test_cache_refresh_has_exactly_one_async_definition_and_awaited_callers():
    target = "_refresh_agent_cache_message_count"
    definitions, callers = [], []
    for path in _scanned_files():
        if not path.is_relative_to(ROOT / "gateway"):
            continue
        tree = _tree(path)
        parents = {child: parent for parent in ast.walk(tree) for child in ast.iter_child_nodes(parent)}
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == target:
                definitions.append((path, node))
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == target:
                callers.append((path, node, parents.get(node)))
    assert len(definitions) == 1, f"Expected one cache refresh definition, got {definitions}"
    assert isinstance(definitions[0][1], ast.AsyncFunctionDef), "Cache refresh callers await a coroutine"
    assert callers, "Cache-refresh audit found no callers; audit the new calling path"
    assert all(isinstance(parent, ast.Await) for _, _, parent in callers), [
        f"{path.relative_to(ROOT)}:{node.lineno}" for path, node, parent in callers
        if not isinstance(parent, ast.Await)]


def test_structural_audit_accepts_properties_and_independent_class_scopes():
    tree = ast.parse('''
class Sample:
    @property
    def value(self): return 1
    @value.setter
    def value(self, value): pass

def factory_one():
    class Worker:
        def run(self): pass

def factory_two():
    class Worker:
        def run(self): pass
''')
    assert not _class_duplicates(tree)
    assert not _duplicate_declarations(tree.body)


def test_structural_audit_rejects_sync_shadow_and_repeated_property_getter():
    tree = ast.parse('''
class Worker:
    async def run(self): pass
    def run(self): pass
    @property
    def value(self): return 1
    @property
    def value(self): return 2

def action(): pass
def action(): pass
''')
    duplicates = next(iter(_class_duplicates(tree).values()))
    assert set(duplicates) == {"run", "value"}
    assert "action" in _duplicate_declarations(tree.body)


def test_rpc_handlers_are_audited_by_registered_route():
    distinct = ast.parse('''
@method("session.list")
def _(rid, params): pass
@method("session.get")
def _(rid, params): pass
''')
    assert not _duplicate_declarations(distinct.body)
    same = ast.parse('''
@method("session.get")
def _(rid, params): pass
@method("session.get")
def _(rid, params): pass
''')
    assert _duplicate_declarations(same.body)
    assert _duplicate_declarations(ast.parse("def _(): pass\ndef _(): pass").body)
