"""Janitor's policy adapter around Hermes's PM updater.

Both CLI entry points use this module. The upstream command keeps ownership of
backup, update locking, receipts, PM generations, rollback, stashes and fleet
restart. The fork only selects its own releases, forbids upstream synchronization,
and adds boot-critical Janitor modules to the syntax guard. Check mode never
imports the application or changes Git refs, configuration, dependencies or receipts.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager, ExitStack
import json
import os
from pathlib import Path
import py_compile
import re
import subprocess
import sys
import tempfile
import urllib.request

PROJECT_ROOT = Path(__file__).resolve().parent
_JANITOR_CRITICAL_FILES = (
    "janitor_cli.py", "janitor_update_core.py", "janitor_update_bootstrap.py",
    "janitor_version.py", "janitor_ext/__init__.py", "janitor_ext/startup.py",
    "janitor_ext/tips_es.py", "janitor_ext/version.py",
)
_validate_critical_files_syntax = None
_UPSTREAM_CMD_UPDATE = None
_GITHUB_ORIGIN = re.compile(
    r"^(?:https://github\.com/|git@github\.com:|ssh://git@github\.com/)"
    r"([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+?)(?:\.git)?/?$", re.IGNORECASE,
)
_STABLE_TAG = re.compile(r"v(?:0|[1-9][0-9]{0,2})\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)")


def parse_update_args(argv=None):
    parser = argparse.ArgumentParser(prog="janitor update", description="Update Janitor from its own releases")
    for flag in ("check", "plan", "gateway", "backup", "no-backup", "keep-stash", "switch-branch",
                 "force", "force-venv", "no-gateway-restart", "install-id", "list-venv-holders"):
        parser.add_argument(f"--{flag}", action="store_true")
    parser.add_argument("--yes", "-y", action="store_true")
    parser.add_argument("--branch", default=None)
    parser.add_argument("--channel", choices=("stable", "main"), default=None)
    parser.add_argument("--set-channel", choices=("stable", "main"), default=None)
    args = parser.parse_args([] if argv is None else argv)
    if args.check and args.set_channel:
        parser.error("--check cannot be combined with --set-channel")
    if args.branch and (args.branch.startswith("-") or any(c.isspace() for c in args.branch)):
        parser.error("invalid branch name")
    return args


def _git(root: Path, *args: str) -> subprocess.CompletedProcess:
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0", GIT_OPTIONAL_LOCKS="0", GIT_NO_LAZY_FETCH="1")
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=30,
                          stdin=subprocess.DEVNULL, env=env, check=False)


def _origin(root: Path) -> tuple[str, str | None]:
    result = _git(root, "config", "--get", "remote.origin.url")
    if result.returncode or not result.stdout.strip():
        raise ValueError("No origin remote configured for this Janitor installation")
    url = result.stdout.strip()
    match = _GITHUB_ORIGIN.fullmatch(url)
    repository = match[1] if match else None
    if repository and repository.lower() == "nousresearch/hermes-agent":
        raise ValueError("Janitor updates must use the Janitor fork as origin, not Hermes upstream")
    return url, repository


def _published_tag(repository: str) -> str:
    request = urllib.request.Request(
        f"https://api.github.com/repos/{repository}/releases/latest",
        headers={"Accept": "application/vnd.github+json", "User-Agent": "Janitor-Agent"},
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        release = json.load(response)
    tag = release.get("tag_name") if isinstance(release, dict) else None
    if not isinstance(release, dict) or release.get("draft") or release.get("prerelease") or not isinstance(tag, str) or not _STABLE_TAG.fullmatch(tag):
        raise ValueError("The fork has no valid published stable release")
    return tag


def _configured_channel(root: Path) -> str:
    """Read only a saved install subscription; never run config migration."""
    from janitor_ext.startup import janitor_home
    config = janitor_home() / "config.yaml"
    if not config.is_file():
        return "stable"
    text = config.read_text(encoding="utf-8-sig")
    if not re.search(r"^update\s*:", text, re.MULTILINE):
        return "stable"
    try:
        import hermes_yaml as yaml
    except ImportError as error:
        raise ValueError("Cannot read the saved update channel; use --channel stable or --channel main") from error
    try:
        payload = yaml.safe_load(text) or {}
    except yaml.YAMLError as error:
        raise ValueError("Cannot read the saved update channel: invalid config YAML") from error
    if not isinstance(payload, dict) or not isinstance(payload.get("update", {}), dict):
        raise ValueError("Update configuration must be a mapping")
    installs = payload.get("update", {}).get("installs", {})
    if not isinstance(installs, dict):
        raise ValueError("Update install subscriptions must be a mapping")
    records = installs.values()
    for record in records:
        if isinstance(record, dict) and str(record.get("path", "")) == str(root.resolve()):
            channel = record.get("channel", "stable")
            if channel not in ("stable", "main"):
                raise ValueError("Janitor supports its own stable releases or an explicit main subscription")
            return channel
    return "stable"


def _check_only(args, root: Path) -> int:
    """Use ls-remote and local reads; never fetch or invoke the mutating updater."""
    _, repository = _origin(root)
    branch = getattr(args, "branch", None)
    channel = getattr(args, "channel", None) or _configured_channel(root)
    if branch or channel == "main":
        branch = branch or "main"
        validity = _git(root, "check-ref-format", "--branch", branch)
        if validity.returncode:
            raise ValueError("Invalid update branch")
        refs = [f"refs/heads/{branch}"]
        label = f"origin/{branch}"
    else:
        if not repository:
            raise ValueError("Stable releases require a GitHub fork origin; use --branch for a local mirror")
        tag = _published_tag(repository)
        refs = [f"refs/tags/{tag}", f"refs/tags/{tag}^{{}}"]
        label = tag
    remote = _git(root, "ls-remote", "--exit-code", "origin", *refs)
    if remote.returncode:
        raise ValueError(f"Could not read {label}: {remote.stderr.strip() or 'remote ref unavailable'}")
    advertised = dict(line.split(None, 1)[::-1] for line in remote.stdout.splitlines() if line.strip())
    target = advertised.get(refs[-1]) or advertised.get(refs[0])
    if not target or not re.fullmatch(r"[0-9a-f]{40,64}", target):
        raise ValueError("Origin returned an invalid update commit")
    head = _git(root, "rev-parse", "HEAD")
    if head.returncode:
        raise ValueError("Cannot identify this Janitor checkout")
    current = head.stdout.strip()
    if current == target or _git(root, "merge-base", "--is-ancestor", target, current).returncode == 0:
        print(f"Janitor is up to date with {label}.")
    else:
        print(f"Janitor update available: {label} ({target[:12]}).")
        print("Run 'janitor update' to install.")
    return 0


def _validate_janitor_files_syntax(root):
    with tempfile.TemporaryDirectory(prefix="janitor-syntax-") as directory:
        for relative in _JANITOR_CRITICAL_FILES:
            source = Path(root) / relative
            if not source.exists():
                continue
            try:
                py_compile.compile(str(source), cfile=str(Path(directory) / relative.replace("/", "_")), doraise=True)
            except (py_compile.PyCompileError, OSError) as error:
                return False, str(source), str(error)
    return True, None, None


def _make_fork_syntax_validator(upstream):
    def validate(root):
        if upstream is not None:
            result = upstream(root)
            if not result[0]:
                return result
        return _validate_janitor_files_syntax(root)
    validate._janitor_fork_wrapper = True
    return validate


def _ensure_loaded():
    """Compatibility seam for the existing fork syntax-guard regression tests."""
    global _validate_critical_files_syntax
    if not getattr(_validate_critical_files_syntax, "_janitor_fork_wrapper", False):
        _validate_critical_files_syntax = _make_fork_syntax_validator(_validate_critical_files_syntax)


def install_update_adapter(main_module):
    global _UPSTREAM_CMD_UPDATE
    if not hasattr(main_module, "_janitor_original_cmd_update"):
        main_module._janitor_original_cmd_update = main_module.cmd_update
    _UPSTREAM_CMD_UPDATE = main_module._janitor_original_cmd_update


@contextmanager
def _replace(module, name, replacement):
    original = getattr(module, name)
    setattr(module, name, replacement)
    try:
        yield
    finally:
        setattr(module, name, original)


def _pinned_release_target(source_module, root: Path):
    """Resolve the native updater's admitted tag to the same published origin SHA."""
    tag = os.environ.get("_JANITOR_UPDATE_TARGET_TAG", "")
    if not _STABLE_TAG.fullmatch(tag):
        raise ValueError("Invalid native Janitor update tag; expected vX.Y.Z")
    _, repository = _origin(root)
    if not repository:
        raise ValueError("A pinned Janitor release requires its GitHub fork origin")
    base = f"https://api.github.com/repos/{repository}"
    release = source_module._json(f"{base}/releases/tags/{tag}")
    if not source_module._published(release, "stable") or release["tag_name"] != tag:
        raise ValueError(f"{tag} is not a published stable Janitor release")
    commit = source_module._json(f"{base}/commits/{tag}")
    sha = commit.get("sha") if isinstance(commit, dict) else None
    if not isinstance(sha, str) or not re.fullmatch(r"[0-9a-f]{40}", sha):
        raise ValueError("Published Janitor release has no valid commit")
    ref = f"refs/tags/{tag}"
    advertised = _git(root, "ls-remote", "--exit-code", "origin", ref, ref + "^{}")
    refs = dict((parts[1], parts[0]) for line in advertised.stdout.splitlines()
                if len(parts := line.split()) == 2)
    if advertised.returncode or refs.get(ref + "^{}", refs.get(ref)) != sha:
        raise ValueError(f"Origin tag {tag} does not match its published commit")
    return source_module.SourceTarget("stable", "stable", repository, commit=sha, version=tag[1:])


@contextmanager
def _fork_update_policy(main_module, update_module):
    """Scoped, reversible policy; all upstream safety mechanisms stay in place."""
    with ExitStack() as stack:
        stack.enter_context(_replace(main_module, "_sync_with_upstream_if_needed", lambda *a, **kw: False))
        stack.enter_context(_replace(update_module, "_push_synced_fork", lambda *a, **kw: None))
        validator = _make_fork_syntax_validator(update_module._validate_critical_files_syntax)
        stack.enter_context(_replace(update_module, "_validate_critical_files_syntax", validator))
        import hermes_cli.update_channel as channel_module
        original_default = channel_module.default_channel
        root = Path(main_module.PROJECT_ROOT).resolve()
        def fork_default(project_root=None):
            selected = Path(project_root).resolve() if project_root is not None else root
            return "stable" if selected == root else original_default(project_root)
        stack.enter_context(_replace(channel_module, "default_channel", fork_default))
        if os.environ.get("_JANITOR_UPDATE_TARGET_TAG"):
            import hermes_cli.source_releases as source_module
            target = _pinned_release_target(source_module, root)
            original_resolve = source_module.resolve_source_target
            def pinned_resolve(channel, git_cmd=None, cwd=None, **kwargs):
                if cwd is not None and Path(cwd).resolve() != root:
                    return original_resolve(channel, git_cmd, cwd, **kwargs)
                if channel != "stable":
                    raise ValueError("Native release updates require the stable Janitor channel")
                return target
            stack.enter_context(_replace(source_module, "resolve_source_target", pinned_resolve))
        yield


def _retarget_to_owning_install(project_root: Path) -> None:
    from hermes_cli.update_owning_install import owning_install_root
    owner = owning_install_root(project_root)
    if owner is None:
        return
    entry = owner / "janitor_cli.py"
    if not entry.is_file():
        raise ValueError(f"The interpreter belongs to {owner}, which has no Janitor entrypoint")
    env = dict(os.environ, PYTHONPATH=str(owner))
    code = subprocess.call([sys.executable, str(entry), *sys.argv[1:]], cwd=owner, env=env)  # health: allow HX006 -- foreground owner-process handoff preserves interactive prompts; the updater bounds its own network/build operations
    raise SystemExit(code)


def _check_legacy_recovery() -> None:
    """Do not strand a stash recorded by the pre-PM fork updater."""
    from janitor_ext.startup import janitor_home
    marker = janitor_home() / "update-incomplete.json"
    if not marker.is_file():
        return
    try:
        payload = json.loads(marker.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as error:
        raise ValueError(f"Cannot read legacy update recovery marker {marker}; repair it before updating") from error
    if not isinstance(payload, dict):
        raise ValueError(f"Invalid legacy recovery marker at {marker}")
    stash = payload.get("stash_ref")
    if stash:
        raise ValueError(
            f"Legacy update has a preserved stash ({stash}). Resolve it with git stash list / git stash apply, "
            f"then remove {marker}. The marker and stash have been left intact."
        )


def _run_upstream_update(args) -> int:
    import hermes_cli.main as main_module
    import hermes_cli.update_cmd as update_module
    _retarget_to_owning_install(Path(main_module.PROJECT_ROOT))
    install_update_adapter(main_module)
    _origin(Path(main_module.PROJECT_ROOT))
    _check_legacy_recovery()
    if os.environ.get("_JANITOR_UPDATE_TARGET_TAG"):
        if getattr(args, "branch", None) or getattr(args, "set_channel", None):
            raise ValueError("Native release pin cannot select a branch or change subscriptions")
        args.channel = "stable"
    # Stable source resolution already reads published releases from origin's
    # GitHub repository. Never subscribe the fork to the Nous/R2 release feed.
    with _fork_update_policy(main_module, update_module):
        result = _UPSTREAM_CMD_UPDATE(args)
    return result if isinstance(result, int) else 0


def run_janitor_update(args=None) -> int:
    """Shared entry for the bootstrap argv and the upstream argparse Namespace."""
    if args is None or isinstance(args, (list, tuple)):
        args = parse_update_args(args)
    if getattr(args, "check", False) and getattr(args, "set_channel", None):
        print("--check cannot change the update channel", file=sys.stderr)
        return 2
    for field in ("channel", "set_channel"):
        if getattr(args, field, None) not in (None, "stable", "main"):
            print("Janitor supports --channel stable or --channel main", file=sys.stderr)
            return 2
    try:
        if getattr(args, "check", False):
            root = Path(os.environ.get("HERMES_INSTALL_ROOT") or PROJECT_ROOT)
            return _check_only(args, root)
        return _run_upstream_update(args)
    except KeyboardInterrupt:
        print("Janitor update cancelled.", file=sys.stderr)
        return 130
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        print(f"Janitor update failed: {error}", file=sys.stderr)
        return 1
