"""Minimal bootstrap helper for `janitor update`.

Zero heavy imports — only stdlib + subprocess.
Designed to be importable even when the virtual environment is partially
broken, so `janitor update` can self-repair before the full CLI stack loads.

Per JANITOR FORK DIRECTIVES:
- ZERO-RENAMING: Does not rename 'hermes' in the core.
- CLI WRAPPER: Helper lives in a separate file, not inline in janitor_cli.py.
- SKILLS AISLADOS: No core Hermes skills are touched.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


def _git_cmd() -> list[str]:
    """Return the git command list, with Windows atomic-append workaround."""
    base = ["git"]
    if sys.platform == "win32":
        base = ["git", "-c", "windows.appendAtomically=false"]
    return base


def _stash_local_changes_if_needed(cwd: Path) -> str | None:
    """Stash local changes (including untracked) before update."""
    status = subprocess.run(
        _git_cmd() + ["status", "--porcelain"],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=True,
    )
    if not status.stdout.strip():
        return None

    # Interrupted merges leave unmerged index entries that make `git stash` fail;
    # `git reset` clears those index markers while preserving working-tree edits.
    unmerged = subprocess.run(
        _git_cmd() + ["ls-files", "--unmerged"],
        cwd=cwd,
        capture_output=True,
        text=True,
    )
    if unmerged.stdout.strip():
        print("  → Clearing unmerged index entries from a previous conflict...")
        subprocess.run(_git_cmd() + ["reset"], cwd=cwd, capture_output=True)

    stash_name = datetime.now(timezone.utc).strftime(
        "janitor-update-autostash-%Y%m%d-%H%M%S"
    )
    print("  → Local changes detected — stashing before update...")
    subprocess.run(
        _git_cmd() + ["stash", "push", "--include-untracked", "-m", stash_name],
        cwd=cwd,
        check=True,
    )
    return subprocess.run(
        _git_cmd() + ["rev-parse", "--verify", "refs/stash"],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()


def _stash_selector_for_ref(cwd: Path, stash_ref: str) -> str | None:
    result = subprocess.run(
        _git_cmd() + ["stash", "list", "--format=%H%x00%gd"],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=True,
    )
    for line in result.stdout.splitlines():
        if "\x00" not in line:
            continue
        commit_hash, selector = line.split("\x00", 1)
        if commit_hash == stash_ref:
            return selector
    return None


def _restore_stash(cwd: Path, stash_ref: str | None) -> bool:
    """Apply and drop the saved stash by commit hash."""
    if not stash_ref:
        return True

    selector = _stash_selector_for_ref(cwd, stash_ref)
    if not selector:
        print(f"  ⚠ Could not find autostash {stash_ref}; run `git stash list` manually.")
        return False

    print("  → Restoring local changes from stash...")
    apply_result = subprocess.run(_git_cmd() + ["stash", "apply", selector], cwd=cwd)
    if apply_result.returncode != 0:
        print(f"  ⚠ Failed to apply autostash {selector}; resolve manually with `git stash apply {selector}`.")
        return False

    subprocess.run(_git_cmd() + ["stash", "drop", selector], cwd=cwd, check=True)
    return True


def _clear_bytecode_cache(project_root: Path) -> int:
    """Remove stale __pycache__ directories without following symlinks."""
    removed = 0
    root = project_root.resolve()
    for pycache in project_root.rglob("__pycache__"):
        if pycache.is_symlink() or not pycache.is_dir():
            continue
        try:
            pycache.resolve().relative_to(root)
        except ValueError:
            print(f"  ⚠ Skipping __pycache__ outside project: {pycache}")
            continue
        shutil.rmtree(pycache)
        removed += 1
    return removed


def _update_python_dependencies(janitor_root: Path) -> None:
    print("  → Updating dependencies (uv)...")
    uv_bin = shutil.which("uv")
    if uv_bin:
        subprocess.run(
            [uv_bin, "pip", "install", "--python", sys.prefix, "-e", ".[all]"],
            cwd=janitor_root,
            check=True,
        )
        return

    print("  ⚠ uv not found — falling back to pip")
    subprocess.run(
        [sys.executable, "-m", "pip", "install", "-e", ".[all]"],
        cwd=janitor_root,
        check=True,
    )


def _build_tui(janitor_root: Path) -> None:
    print("  → Compiling TUI components...")
    ui_tui_dir = janitor_root / "ui-tui"
    subprocess.run(["npm", "install"], cwd=ui_tui_dir, check=True)
    subprocess.run(["npm", "run", "build"], cwd=ui_tui_dir, check=True)


def run_update() -> int:
    """Run the minimal update cycle and return a process exit code."""
    print("\n🔥 THE JANITOR: Initiating tactical update...\n")
    janitor_root = Path(__file__).parent.resolve()
    stash_ref: str | None = None

    try:
        os.chdir(janitor_root)

        if not (janitor_root / ".git").exists():
            print("✗ Not a git repository. Please reinstall.")
            return 1

        stash_ref = _stash_local_changes_if_needed(janitor_root)

        print("  → Syncing incinerator protocols (git pull)...")
        subprocess.run(
            _git_cmd() + ["pull", "--ff-only", "origin", "main"],
            cwd=janitor_root,
            check=True,
        )

        _update_python_dependencies(janitor_root)
        _build_tui(janitor_root)

        removed = _clear_bytecode_cache(janitor_root)
        if removed:
            print(
                f"  ✓ Cleared {removed} stale __pycache__ "
                f"director{'y' if removed == 1 else 'ies'}"
            )

        if not _restore_stash(janitor_root, stash_ref):
            return 1

        print("\n✅ Janitor updated successfully. Garbage collected.\n")
        return 0
    except subprocess.CalledProcessError as e:
        print(f"\n❌ Update failed at step: {e.cmd}\n")
        if stash_ref:
            _restore_stash(janitor_root, stash_ref)
        return 1
    except KeyboardInterrupt:
        print("\n✗ Update cancelled.\n")
        if stash_ref:
            _restore_stash(janitor_root, stash_ref)
        return 130


if __name__ == "__main__":
    sys.exit(run_update())
