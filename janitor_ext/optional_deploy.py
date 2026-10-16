"""Run a Janitor service script with profile secrets, without shell evaluation."""
import os
import sys
from pathlib import Path


def main(argv=None):
    from janitor_ext.install import read_secrets
    args = sys.argv[1:] if argv is None else argv
    if not args:
        raise SystemExit("A Janitor skill deployment script is required")
    from janitor_ext.startup import janitor_home
    home = janitor_home().resolve()
    profile_root = home.parent.parent if home.parent.name == "profiles" else home
    roots = (Path(__file__).resolve().parents[1] / "skills", home / "skills", profile_root / "skills")
    script = Path(args[0]).expanduser().resolve()
    allowed = False
    for root in roots:
        if root.is_symlink():
            continue
        try:
            relative = script.relative_to(root.resolve())
        except ValueError:
            continue
        if (len(relative.parts) == 3 and relative.parts[0].startswith("janitor-")
                and relative.parts[1] == "scripts" and script.is_file()):
            allowed = True
            break
    if not allowed:
        raise SystemExit("Deployment must be a script inside a Janitor skill in the repository or selected profile")
    env = {**read_secrets(home / ".env"), **os.environ, "JANITOR_SERVICE_ENV": "1", "JANITOR_SERVICE_PYTHON": sys.executable, "JANITOR_CORE_ROOT": str(Path(__file__).resolve().parents[1]), "HERMES_HOME": str(home), "JANITOR_HOME": str(home)}
    os.execvpe("bash", ["bash", str(script), *args[1:]], env)


if __name__ == "__main__":
    main()
