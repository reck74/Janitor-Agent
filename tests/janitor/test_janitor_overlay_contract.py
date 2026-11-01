"""Contract for ``janitor/overlay.yaml``.

Each ``verify: test:<id>`` touchpoint has exactly one behavioral check in
``CHECKS`` below. After a ``chore(sync)`` merge these tell you which in-place
edit upstream overwrote, instead of a grep checklist in MERGE_GUIDE.md.
"""

from __future__ import annotations

import importlib.metadata
import re

import pytest

from janitor.home import REPO_ROOT
from janitor.overlay import glob_match, load_overlay, parse_overlay


def check_version():
    import hermes_cli

    assert re.search(r"\+janitor\.\d+$", hermes_cli.__version__), hermes_cli.__version__
    assert importlib.metadata.version("hermes-agent") == hermes_cli.__version__


def check_packaging():
    scripts = {ep.name: ep.value for ep in importlib.metadata.entry_points(group="console_scripts")}
    assert scripts.get("janitor") == "janitor.cli:main"
    assert scripts.get("hermes") == "hermes_cli.main:main"
    plugins = {ep.name: ep.value for ep in importlib.metadata.entry_points(group="hermes_agent.plugins")}
    assert plugins.get("janitor") == "janitor.plugin"
    assert callable(importlib.import_module("janitor.plugin").register)
    for alias, target in (
        ("janitor_cli", "janitor.cli"),
        ("janitor_update_core", "janitor.update_core"),
        ("janitor_update_bootstrap", "janitor.update_bootstrap"),
        ("janitor_version", "janitor.version"),
    ):
        assert importlib.import_module(alias) is importlib.import_module(target), alias


def check_banner(capsys=None):
    from hermes_cli import __version__
    from hermes_cli import _startup_fast
    from hermes_cli.banner import format_banner_version_label
    from janitor.version import display_version

    expected = f"THE JANITOR v{display_version(__version__)}"
    assert format_banner_version_label().startswith(expected)
    if capsys is not None:
        _startup_fast.print_fast_version_info()
        assert capsys.readouterr().out.startswith(expected)


def check_mcp_dashboard_endpoints():
    from hermes_cli.web_routers.mcp import router

    routes = {(m, r.path) for r in router.routes for m in getattr(r, "methods", ())}
    assert ("POST", "/api/mcp/servers/{name}/discover") in routes
    assert ("GET", "/api/mcp/servers/{name}/logs") in routes


CHECKS = {
    "version": check_version,
    "packaging": check_packaging,
    "banner": check_banner,
    "mcp-dashboard-endpoints": check_mcp_dashboard_endpoints,
}


@pytest.fixture(scope="module")
def overlay():
    return load_overlay()


def test_every_test_touchpoint_has_a_check_and_vice_versa(overlay):
    assert overlay.test_check_ids() == set(CHECKS)


@pytest.mark.parametrize("check_id", sorted(CHECKS))
def test_touchpoint_contract(check_id, capsys):
    check = CHECKS[check_id]
    if check is check_banner:
        check(capsys)
    else:
        check()


def _repo_files() -> list:
    return [
        p.relative_to(REPO_ROOT).as_posix()
        for p in REPO_ROOT.rglob("*")
        if p.is_file() and ".git" not in p.parts and "node_modules" not in p.parts
    ]


def test_every_declared_pattern_matches_a_real_file(overlay):
    """Stale declarations hide nothing but rot; drop them when a touchpoint goes away."""
    files = _repo_files()
    patterns = list(overlay.fork_paths) + [f for t in overlay.touchpoints for f in t.files]
    stale = [p for p in patterns if not any(glob_match(f, p) for f in files)]
    assert not stale, stale


def test_touchpoints_never_claim_fork_owned_paths(overlay):
    for touchpoint in overlay.touchpoints:
        for pattern in touchpoint.files:
            assert not any(glob_match(pattern, fp) for fp in overlay.fork_paths), (
                touchpoint.id,
                pattern,
            )


@pytest.mark.parametrize(
    ("path", "pattern", "expected"),
    [
        ("janitor/cli.py", "janitor/**", True),
        ("janitor/plugin/telegram.py", "janitor/**", True),
        ("janitorx/cli.py", "janitor/**", False),
        ("scripts/janitor-install.sh", "scripts/*janitor*", True),
        ("scripts/sub/janitor.sh", "scripts/*janitor*", False),
        (".github/workflows/tests.yml", ".github/workflows/*.yml", True),
        ("skills/janitor-core/SKILL.md", "skills/janitor-*/**", True),
        ("skills/devops/janitor-n8n/SKILL.md", "skills/janitor-*/**", False),
    ],
)
def test_glob_semantics(path, pattern, expected):
    assert glob_match(path, pattern) is expected


def test_undeclared_reports_only_unowned_paths():
    overlay = parse_overlay(
        {
            "schema": 1,
            "upstream": {"repo": "r", "base": "b"},
            "fork_paths": ["janitor/**"],
            "touchpoints": [
                {"id": "x", "files": ["cli.py"], "why": "w", "verify": "test:x", "merge": "reapply"}
            ],
        }
    )
    assert overlay.undeclared(["janitor/a.py", "cli.py", "agent/zombie.py"]) == ["agent/zombie.py"]
    assert overlay.owner_of("cli.py") == "x"
    assert overlay.owner_of("janitor/a.py") == "fork"


@pytest.mark.parametrize(
    "bad",
    [
        {"merge": "theirs"},
        {"verify": "grep:foo"},
        {"files": []},
    ],
)
def test_parse_rejects_invalid_touchpoints(bad):
    tp = {"id": "x", "files": ["a"], "why": "w", "verify": "test:x", "merge": "ours", **bad}
    with pytest.raises(ValueError):
        parse_overlay({"schema": 1, "upstream": {"repo": "r", "base": "b"}, "touchpoints": [tp]})


def test_overlay_check_cli_passes_on_this_tree():
    """The committed tree has no undeclared divergence from the declared base."""
    import subprocess
    import sys

    overlay = load_overlay()
    has_base = subprocess.run(
        ["git", "cat-file", "-e", f"{overlay.upstream_base}^{{commit}}"],
        cwd=REPO_ROOT,
        capture_output=True,
    ).returncode == 0
    if not has_base:
        pytest.skip("upstream base commit not in this clone (shallow checkout)")
    result = subprocess.run(
        [sys.executable, "-m", "janitor.overlay", "check"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
