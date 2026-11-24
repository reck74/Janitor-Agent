"""The release tag is derived from the version, never chosen freely (F1-21f)."""
from pathlib import Path

from janitor import release_channel
from janitor.version import display_version


def _pyproject(tmp_path: Path, version: str) -> Path:
    path = tmp_path / "pyproject.toml"
    path.write_text(f'[project]\nname = "x"\nversion = "{version}"\n', encoding="utf-8")
    return path


def test_only_the_tag_of_the_displayed_version_releases_a_tree(tmp_path):
    pyproject = _pyproject(tmp_path, "1.2.3+janitor.4")
    tag = "v" + display_version("1.2.3+janitor.4")

    assert release_channel.check_tag(tag, pyproject) is None
    for wrong in ("v1.2.3", "1.2.3-janitor.4", "v1.2.3+janitor.4", "v1.2.3-janitor.5"):
        problem = release_channel.check_tag(wrong, pyproject)
        assert problem and tag in problem, (wrong, problem)


def test_the_release_job_command_exits_nonzero_on_a_wrong_tag(capsys):
    """What the workflow runs, against this checkout's own pyproject.toml."""
    repo_pyproject = Path(release_channel.__file__).resolve().parent.parent / "pyproject.toml"
    good = release_channel.expected_tag(repo_pyproject)

    assert release_channel.main(["--check-tag", good]) == 0
    assert release_channel.main(["--check-tag", good + "-x"]) == 1
    assert "::error::" in capsys.readouterr().out
