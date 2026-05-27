"""Tests for the minimal Janitor update bootstrap helper."""

import subprocess
from pathlib import Path
import tomllib


def test_bootstrap_module_is_packaged_for_janitor_entrypoint():
    pyproject = tomllib.loads(Path("pyproject.toml").read_text())
    py_modules = pyproject["tool"]["setuptools"]["py-modules"]

    assert "janitor_update_bootstrap" in py_modules


def test_update_intercept_runs_before_hermes_imports():
    source = Path("janitor_cli.py").read_text()
    intercept = source.index('if len(sys.argv) > 1 and sys.argv[1] == "update":')
    hermes_config = source.index("from hermes_cli.config import DEFAULT_CONFIG")
    prompt_builder = source.index("from agent import prompt_builder")
    assert intercept < hermes_config
    assert intercept < prompt_builder


def test_stash_returns_none_on_clean_tree(tmp_path):
    import janitor_update_bootstrap as jub

    _init_git_repo(tmp_path)
    assert jub._stash_local_changes_if_needed(tmp_path) is None


def test_stash_includes_tracked_and_untracked_changes(tmp_path):
    import janitor_update_bootstrap as jub

    _init_git_repo(tmp_path)
    tracked = tmp_path / "file.txt"
    tracked.write_text("changed")
    untracked = tmp_path / "assets" / "janitor" / "SOUL.md"
    untracked.parent.mkdir(parents=True)
    untracked.write_text("local soul")

    stash_ref = jub._stash_local_changes_if_needed(tmp_path)
    assert stash_ref
    assert _status(tmp_path) == ""

    assert jub._restore_stash(tmp_path, stash_ref)
    status = _status(tmp_path)
    assert "file.txt" in status
    assert "assets/" in status
    assert untracked.exists()


def test_restore_stash_by_hash_when_not_top_of_stack(tmp_path):
    import janitor_update_bootstrap as jub

    _init_git_repo(tmp_path)
    (tmp_path / "first.txt").write_text("first")
    first_ref = jub._stash_local_changes_if_needed(tmp_path)

    (tmp_path / "second.txt").write_text("second")
    second_ref = jub._stash_local_changes_if_needed(tmp_path)

    assert first_ref and second_ref and first_ref != second_ref
    assert jub._restore_stash(tmp_path, first_ref)

    status = _status(tmp_path)
    assert "first.txt" in status
    assert "second.txt" not in status
    assert jub._stash_selector_for_ref(tmp_path, first_ref) is None
    assert jub._stash_selector_for_ref(tmp_path, second_ref) is not None


def test_restore_stash_returns_false_for_missing_ref(tmp_path):
    import janitor_update_bootstrap as jub

    _init_git_repo(tmp_path)
    assert not jub._restore_stash(tmp_path, "0" * 40)


def test_clear_bytecode_cache_removes_real_dirs_and_skips_symlink(tmp_path):
    import janitor_update_bootstrap as jub

    real_pycache = tmp_path / "pkg" / "__pycache__"
    real_pycache.mkdir(parents=True)
    external = tmp_path / "external"
    external.mkdir()
    symlink = tmp_path / "linked" / "__pycache__"
    symlink.parent.mkdir()
    symlink.symlink_to(external, target_is_directory=True)

    removed = jub._clear_bytecode_cache(tmp_path)

    assert removed == 1
    assert not real_pycache.exists()
    assert symlink.exists()
    assert external.exists()


def _init_git_repo(path: Path) -> None:
    subprocess.run(["git", "init"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=path, check=True, capture_output=True)
    (path / "file.txt").write_text("hello")
    subprocess.run(["git", "add", "."], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=path, check=True, capture_output=True)


def _status(path: Path) -> str:
    return subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=path,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
