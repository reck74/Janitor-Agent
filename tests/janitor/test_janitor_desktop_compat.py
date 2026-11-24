"""App↔engine contract file (F1-21a).

The desktop app bakes ``contract`` from ``janitor/desktop-compat.json`` at build
time and, at boot, reads the engine checkout's copy to decide whether it can
start the backend (``apps/desktop-janitor/brand/compat.mjs``). This pins the
engine side of that contract: the file ships with the ``janitor`` package and
keeps the shape the app parses. The value of ``contract`` is not frozen.
"""

import fnmatch
import json
import tomllib
from importlib.resources import files
from pathlib import Path
from urllib.parse import urlsplit

REPO_ROOT = Path(__file__).resolve().parents[2]
FORK_PREFIX = "/reck74/Janitor-Agent/"


def test_desktop_compat_file_ships_with_the_janitor_package():
    data = json.loads((files("janitor") / "desktop-compat.json").read_text(encoding="utf-8"))

    contract = data["contract"]
    assert isinstance(contract, int) and not isinstance(contract, bool) and contract >= 1

    url = urlsplit(data["release_url"])
    assert (url.scheme, url.netloc) == ("https", "github.com")
    assert url.path.startswith(FORK_PREFIX)

    pyproject = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    package_data = pyproject["tool"]["setuptools"]["package-data"]["janitor"]
    assert any(fnmatch.fnmatch("desktop-compat.json", pattern) for pattern in package_data)
