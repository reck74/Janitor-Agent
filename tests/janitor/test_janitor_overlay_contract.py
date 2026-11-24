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
    # The banner touchpoints import the version helper by its root name.
    assert importlib.import_module("janitor_version") is importlib.import_module("janitor.version")


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


def check_update_channel(monkeypatch, tmp_path):
    """Once the channel is applied, the passive probe of a local checkout asks
    for the release branch's tip, not main's."""
    from hermes_cli import banner
    from janitor.release_channel import RELEASE_BRANCH, apply_to_engine

    monkeypatch.setattr(banner, "_UPDATE_BRANCH", banner._UPDATE_BRANCH)
    apply_to_engine()
    asked: list[str] = []
    monkeypatch.setattr(banner, "_git_stdout", lambda args, **kw: (
        "https://github.com/example/janitor.git" if args[:2] == ["remote", "get-url"] else "a" * 40))
    monkeypatch.setattr(banner, "_github_branch_tip", lambda slug, branch: asked.append(branch) or "a" * 40)

    assert banner._check_via_local_git(tmp_path) == 0
    assert asked == [RELEASE_BRANCH]


def check_mcp_dashboard_endpoints():
    from hermes_cli.web_routers.mcp import router

    routes = {(m, r.path) for r in router.routes for m in getattr(r, "methods", ())}
    assert ("POST", "/api/mcp/servers/{name}/discover") in routes
    assert ("GET", "/api/mcp/servers/{name}/logs") in routes


def check_install_sh(tmp_path):
    """The config stage the desktop runs leaves a seeded Janitor home and a clean JSON frame."""
    import yaml

    from tests.janitor.install_sh_harness import fake_install_dir, run_stage, stage_frame

    home = tmp_path / ".janitor"
    result = run_stage(tmp_path, "config", fake_install_dir(tmp_path), home)
    assert stage_frame(result.stdout) == {"ok": True, "stage": "config", "skipped": False}, (
        result.stdout + result.stderr
    )
    assert "janitor" in yaml.safe_load((home / "config.yaml").read_text(encoding="utf-8"))["plugins"]["enabled"]
    assert (home / ".no-bundled-skills").is_file()


def check_desktop_update_posix(tmp_path):
    """The desktop's update hand-off drives `janitor update` with flags its parser accepts."""
    from tests.janitor.desktop_update_harness import run_posix_handoff

    seen = run_posix_handoff(tmp_path)
    assert seen["hermes"] == [], seen
    assert len(seen["core"]) == 1, seen
    args = seen["core"][0]
    assert args["keep_stash"] is True and args["yes"] is True and args["gateway"] is True, args
    assert args["branch"] == "main", args
    assert seen["result"]["ok"] is True, seen["result"]
    # The relaunch gate's message reaches the app verbatim (boot dialog / shim window): Spanish.
    import subprocess

    from tests.janitor.desktop_update_harness import handoff_env

    def gate(**env):
        out = subprocess.run(
            ["bash", str(REPO_ROOT / "scripts" / "desktop-update" / "posix.sh"), "--self-test-gate",
             "--install-root", str(tmp_path / "hermes-agent"), "--relaunch-target", str(foreign)],
            capture_output=True, text=True, check=True, env=handoff_env(tmp_path, **env),
        ).stdout.strip()
        return out.partition(":")[::2]

    foreign = tmp_path / "opt" / "janitor"
    decision, message = gate()
    assert decision == "skew" and "AppImage" in message, (decision, message)
    assert "Backend updated" not in message and "hermes" not in message.lower(), message
    # Run from an AppImage, the engine update reopens that AppImage; the app judges compatibility.
    appimage = tmp_path / "Janitor.AppImage"
    appimage.write_text("#!/bin/sh\n", encoding="utf-8")
    appimage.chmod(0o755)
    decision, message = gate(APPIMAGE=str(appimage))
    assert decision == "relaunch" and "Janitor" in message and "hermes" not in message.lower(), message


def check_desktop_update_ui(tmp_path):
    """The update window the user sees is served in Spanish and never names Hermes."""
    import subprocess
    import sys
    import time
    from html.parser import HTMLParser
    from urllib.request import urlopen

    shim = REPO_ROOT / "scripts" / "desktop-update"

    class Visible(HTMLParser):
        def __init__(self):
            super().__init__()
            self.lang, self.stack, self.text, self.labels = None, [], [], []

        def handle_starttag(self, tag, attrs):
            attrs = dict(attrs)
            self.lang = attrs.get("lang", self.lang) if tag == "html" else self.lang
            self.labels += [attrs["aria-label"]] if "aria-label" in attrs else []
            self.stack.append(tag)

        def handle_endtag(self, tag):
            if self.stack and self.stack[-1] == tag:
                self.stack.pop()

        def handle_data(self, data):
            if data.strip() and not {"script", "style"} & set(self.stack):
                self.text.append(data.strip())

    proc = subprocess.Popen(
        [sys.executable, str(shim / "serve-ui.py"), str(shim / "ui.html"),
         str(tmp_path / "status"), str(time.time())],
        stdout=subprocess.PIPE, text=True,
    )
    try:
        port = int(proc.stdout.readline().strip())
        with urlopen(f"http://127.0.0.1:{port}/", timeout=5) as response:
            page = response.read().decode("utf-8")
    finally:
        proc.kill()
        proc.wait(timeout=5)
    parsed = Visible()
    parsed.feed(page)
    visible = parsed.text + parsed.labels
    assert parsed.lang == "es", parsed.lang
    assert any("Janitor" in t for t in visible), visible
    assert not [t for t in visible if "hermes" in t.lower()], visible


def check_backend_user_copy(tmp_path):
    """user_messages reads the catalog: Janitor's overlay gives Spanish, upstream's keeps English."""
    import os

    from agent.i18n import reset_language_cache
    from janitor import locales
    from tui_gateway.user_messages import agent_init_failed_message, turn_error_text

    home = os.environ["HERMES_HOME"]
    os.makedirs(home, exist_ok=True)
    with open(os.path.join(home, "config.yaml"), "w", encoding="utf-8") as f:
        f.write("display:\n  language: es\n")
    saved = os.environ.pop(locales.ENV_VAR, None)
    exc = RuntimeError("No usable credentials found for provider 'minimax'. Set MINIMAX_API_KEY.")
    try:
        reset_language_cache()
        assert agent_init_failed_message(exc).startswith("Hermes could not start the assistant")
        os.environ[locales.ENV_VAR] = str(locales.build(tmp_path / "locales"))
        reset_language_cache()
        text = agent_init_failed_message(exc)
        assert text.startswith("Janitor no pudo iniciar el asistente") and "`janitor setup`" in text, text
        assert "Configura MINIMAX_API_KEY" in text, text
        assert turn_error_text("x").startswith("La petición falló."), turn_error_text("x")
    finally:
        os.environ.pop(locales.ENV_VAR, None)
        if saved is not None:
            os.environ[locales.ENV_VAR] = saved
        reset_language_cache()


def check_runtime_copy(tmp_path):
    """English literals with no upstream key ask the catalog: Janitor's gives Spanish, upstream's English."""
    import os

    from agent.i18n import reset_language_cache, t_default
    from hermes_cli.commands import COMMAND_REGISTRY, localized_description
    from janitor import locales

    home = os.environ["HERMES_HOME"]
    os.makedirs(home, exist_ok=True)
    with open(os.path.join(home, "config.yaml"), "w", encoding="utf-8") as f:
        f.write("display:\n  language: es\n")
    saved = os.environ.pop(locales.ENV_VAR, None)
    update = next(c for c in COMMAND_REGISTRY if c.name == "update")
    try:
        reset_language_cache()
        assert localized_description(update) == update.description
        assert t_default("runtime_copy.gateway.restarted", "Back {x}.", x=1) == "Back 1."
        os.environ[locales.ENV_VAR] = str(locales.build(tmp_path / "locales"))
        reset_language_cache()
        assert localized_description(update) == "Actualiza Janitor a la última versión"
        assert t_default("runtime_copy.gateway.restarted", "x").startswith("♻ Gateway reiniciado")
    finally:
        os.environ.pop(locales.ENV_VAR, None)
        if saved is not None:
            os.environ[locales.ENV_VAR] = saved
        reset_language_cache()


def check_update_single_flight(tmp_path):
    """A /update in flight, from any entry point, makes the next one stand down; leftovers never block."""
    import os
    import time

    from gateway.slash_commands import _update_already_running

    pending, claimed, lock = (tmp_path / ".update_pending.json", tmp_path / ".update_pending.claimed.json",
                              tmp_path / "lock")
    assert not _update_already_running(pending, lock_path=lock)
    pending.write_text("{}", encoding="utf-8")
    assert _update_already_running(pending, lock_path=lock)  # spawned, lock not taken yet
    pending.replace(claimed)
    assert _update_already_running(pending, lock_path=lock)  # finished, its watcher is still delivering
    an_hour_ago = time.time() - 3600
    os.utime(claimed, (an_hour_ago, an_hour_ago))
    assert not _update_already_running(pending, lock_path=lock)  # a crashed run's leftover never blocks
    claimed.unlink()
    lock.write_text(f"{os.getpid()}\n{time.time()}\n", encoding="utf-8")
    assert _update_already_running(pending, lock_path=lock)  # the app or a terminal is updating


CHECKS = {
    "backend-user-copy": check_backend_user_copy,
    "runtime-copy": check_runtime_copy,
    "update-single-flight": check_update_single_flight,
    "version": check_version,
    "packaging": check_packaging,
    "banner": check_banner,
    "update-channel": check_update_channel,
    "mcp-dashboard-endpoints": check_mcp_dashboard_endpoints,
    "install-sh": check_install_sh,
    "desktop-update-posix": check_desktop_update_posix,
    "desktop-update-ui": check_desktop_update_ui,
}

# Checks that drive a POSIX shell script run on Linux only (directive #11 lanes).
_LINUX_ONLY_CHECKS = {"install-sh", "desktop-update-posix"}


@pytest.fixture(scope="module")
def overlay():
    return load_overlay()


def test_every_test_touchpoint_has_a_check_and_vice_versa(overlay):
    assert overlay.test_check_ids() == set(CHECKS)


@pytest.mark.parametrize(
    "check_id",
    [
        pytest.param(cid, marks=pytest.mark.linux_only) if cid in _LINUX_ONLY_CHECKS else cid
        for cid in sorted(CHECKS)
    ],
)
def test_touchpoint_contract(check_id, capsys, tmp_path, monkeypatch):
    check = CHECKS[check_id]
    if check is check_banner:
        check(capsys)
    elif check is check_update_channel:
        check(monkeypatch, tmp_path)
    elif check in (check_install_sh, check_desktop_update_posix, check_desktop_update_ui, check_backend_user_copy,
                   check_runtime_copy, check_update_single_flight):
        check(tmp_path)
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
        ("scripts/janitor-sync-verify.sh", "scripts/*janitor*", True),
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
