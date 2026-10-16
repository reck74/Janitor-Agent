"""Import-light Janitor home selection, before Hermes caches profile paths."""
from __future__ import annotations

import os
import re
from pathlib import Path
from collections.abc import Mapping, Sequence


def janitor_home(env: Mapping[str, str] | None = None) -> Path:
    if env is None:
        from hermes_constants import get_hermes_home_override
        override = get_hermes_home_override()
        if override:
            return Path(override).expanduser().absolute()
    values = os.environ if env is None else env
    chosen = values.get("HERMES_HOME", "").strip() or values.get("JANITOR_HOME", "").strip()
    return Path(os.path.expandvars(chosen)).expanduser().absolute() if chosen else Path.home() / ".janitor"


def profile_selection(argv: Sequence[str]) -> tuple[str | None, list[str]]:
    """Consume only leading profile selectors; subcommand arguments remain intact."""
    remaining = list(argv)
    profile = None
    while remaining:
        token = remaining[0]
        if token in ("--profile", "-p"):
            if len(remaining) < 2:
                raise ValueError(f"{token} requires a profile name")
            profile, remaining = remaining[1], remaining[2:]
        elif token.startswith("--profile="):
            profile, remaining = token.partition("=")[2], remaining[1:]
        else:
            break
    if profile is not None:
        profile = profile.strip().lower()
        if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,63}", profile):
            raise ValueError("Invalid profile name; use letters, numbers, '-' or '_' (maximum 64)")
    return profile, remaining


def prepare_environment(argv: Sequence[str] = ()) -> Path:
    home = janitor_home()
    root = home.parent.parent if home.parent.name == "profiles" else home
    profile, command = profile_selection(argv)
    # Match upstream's sticky selection for import-light update/version paths too.
    # An explicit profile-shaped home is already bound and must remain so.
    early = command[:1] == ["update"] or command in (["--version"], ["version"])
    if early and profile is None and home.parent.name != "profiles":
        try:
            saved = (root / "active_profile").read_text(encoding="utf-8-sig").strip()
        except (OSError, UnicodeError):
            saved = ""
        if saved and saved != "default":
            profile, _ = profile_selection(["--profile", saved])
    if profile is not None:
        home = root if profile == "default" else root / "profiles" / profile
        if profile != "default" and not (home / "config.yaml").is_file():
            raise ValueError(f"Profile {profile!r} does not exist; run 'janitor profile create {profile}'")
    os.environ["HERMES_HOME"] = str(home)
    os.environ.setdefault("HERMES_SKIN", "sentry-janitor")  # health: allow HX002 -- internal bridge to the upstream skin loader for bundled Janitor identity; explicit user skin selection wins
    return home
