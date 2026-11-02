"""The checkout's packaging metadata, independent of whether it is installed.

PM's test environment carries the locked dependencies but never installs the
checkout (``pm.operations.ensure_project_environment`` passes
``no_install_project``), while PM's runtime environment installs it from the
same ``pyproject.toml``. Tests read that declaration, and tests that exercise
real entry-point discovery install it as a ``dist-info`` first.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def declared_project() -> dict:
    return tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]


def declared_entry_points() -> dict[str, dict[str, str]]:
    project = declared_project()
    return {"console_scripts": dict(project.get("scripts", {})), **project.get("entry-points", {})}


def install_checkout_metadata(site: Path) -> Path:
    """Write the checkout's distribution metadata under ``site``, the way an install does."""
    project = declared_project()
    dist = site / f"{project['name'].replace('-', '_')}-{project['version']}.dist-info"
    dist.mkdir(parents=True, exist_ok=True)
    (dist / "METADATA").write_text(
        f"Metadata-Version: 2.1\nName: {project['name']}\nVersion: {project['version']}\n",
        encoding="utf-8",
    )
    sections = []
    for group, entries in declared_entry_points().items():
        sections.append(f"[{group}]\n" + "".join(f"{name} = {value}\n" for name, value in entries.items()))
    (dist / "entry_points.txt").write_text("\n".join(sections), encoding="utf-8")
    return dist
