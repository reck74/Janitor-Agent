"""Build Janitor's shared upstream frontends without publishing global Hermes commands."""
from pathlib import Path


def main() -> int:
    from hermes_cli.source_build import source_build_env, prepare_source_dependencies, build_source_tui, build_source_web
    from janitor_ext.install import publish_commands
    import os
    root = Path(__file__).resolve().parents[1]
    env = source_build_env(explicit=True, verify=False)
    prepare_source_dependencies(root, ("ui-tui", "web"), env=env, explicit=True)
    build_source_tui(root, env=env)
    build_source_web(root, env=env)
    publish_commands(root, Path(os.environ["HERMES_HOME"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
