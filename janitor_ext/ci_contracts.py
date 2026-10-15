"""Pure validation shared by the fork test runner and CI contract tests."""

from __future__ import annotations

from pathlib import Path, PurePosixPath


def janitor_test_files(root: Path) -> list[str]:
    manifest = root / ".github" / "janitor-tests.txt"
    files = [line.strip() for line in manifest.read_text(encoding="utf-8").splitlines()
             if line.strip() and not line.lstrip().startswith("#")]
    if not files or len(files) != len(set(files)):
        raise ValueError("Janitor test manifest must be nonempty and contain no duplicates")
    for name in files:
        path = PurePosixPath(name)
        if path.is_absolute() or ".." in path.parts or path.parts[0] != "tests" or path.suffix != ".py":
            raise ValueError(f"Invalid Janitor test path: {name}")
        if not (root / name).is_file():
            raise ValueError(f"Missing Janitor test file: {name}")
    missing = {p.relative_to(root).as_posix() for p in (root / "tests").rglob("test_*janitor*.py")} - set(files)
    if missing:
        raise ValueError(f"Janitor tests absent from the PR gate: {sorted(missing)}")
    return files


def workflow_interface_errors(workflows: dict) -> list[str]:
    errors = []
    for path, workflow in workflows.items():
        for job_name, job in (workflow.get("jobs") or {}).items():
            uses = job.get("uses", "")
            if not uses.startswith("./"):
                continue
            target = uses[2:]
            if target not in workflows:
                errors.append(f"{path}:{job_name}: missing workflow {target}")
                continue
            events = workflows[target].get("on") or {}
            if not isinstance(events, dict) or "workflow_call" not in events:
                errors.append(f"{path}:{job_name}: {target} does not support workflow_call")
                continue
            inputs = (events["workflow_call"] or {}).get("inputs") or {}
            provided = job.get("with") or {}
            for name in provided.keys() - inputs.keys():
                errors.append(f"{path}:{job_name}: undeclared input {name}")
            for name, declaration in inputs.items():
                if declaration.get("required") is True and "default" not in declaration and name not in provided:
                    errors.append(f"{path}:{job_name}: missing required input {name}")
    return errors
