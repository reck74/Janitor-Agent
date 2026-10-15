"""Deterministic checks for the fork rules on changes introduced by a merge/PR."""

from __future__ import annotations

import re

_CORE_FILES = {"cli.py", "run_agent.py", "model_tools.py", "toolsets.py", "hermes_constants.py",
               "hermes_state.py", "hermes_logging.py"}
_CORE_DIRS = ("agent/", "gateway/", "hermes_cli/", "tools/", "tui_gateway/")
_BANNER_EXCEPTIONS = {"hermes_cli/main.py", "hermes_cli/banner.py"}


def fork_diff_violations(diff: str) -> list[str]:
    """Reject direct Hermes→Janitor replacements and misplaced newly added skills.

    Compare complete changed lines rather than the presence of the word
    Janitor: legitimate isolated imports and existing branding are allowed.
    CLI welcome/version banner exceptions are required by directive #12.
    """
    violations = []
    path = ""
    removed = []
    added = []

    def inspect_hunk():
        if not path:
            return
        if path in _CORE_FILES or path.startswith(_CORE_DIRS):
            for old in removed:
                for new in added:
                    if path in _BANNER_EXCEPTIONS and "THE JANITOR" in new:
                        continue
                    old_text, new_text = old.lower().strip(), new.lower().strip()
                    if "hermes" in old_text and old_text.replace("hermes", "janitor") == new_text:
                        violations.append(f"{path}: core Hermes name replaced with Janitor (directive 1)")
        if path.endswith("/SKILL.md") and any(re.match(r"name:\s*['\"]?janitor-", line) for line in added):
            if not re.match(r"skills/janitor-[^/]+/SKILL\.md$", path):
                violations.append(f"{path}: Janitor skill must live under skills/janitor-* (directive 3)")
        if path.startswith("ui-tui/src/components/"):
            if any(re.search(r'''["'](?:THE JANITOR|Janitor Agent|Janitor)["']''', line) for line in added):
                violations.append(f"{path}: use the injected skin for Janitor branding (directive 4)")

    for line in diff.splitlines():
        if line.startswith("diff --git "):
            inspect_hunk()
            path = ""
            removed, added = [], []
        elif line.startswith("+++ b/"):
            path = line[6:]
        elif line.startswith("@@"):
            inspect_hunk()
            removed, added = [], []
        elif line.startswith("-") and not line.startswith("---"):
            removed.append(line[1:])
        elif line.startswith("+") and not line.startswith("+++"):
            added.append(line[1:])
    inspect_hunk()
    return sorted(set(violations))
