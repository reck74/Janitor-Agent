"""Behaviour tests for the janitor-project-create skill (F3-05).

`plan` is read-only, `apply` writes only inside a new target and only what the plan
listed, network commands run only when selected, git identity is never invented and
`verify` reports honestly. Fake `git`/`uv`/`npm`/`pnpm`/`node`/`gh`/`sudo` binaries
record every invocation. The toolchain-gated tests at the end generate real projects
offline (no dependency downloads). Run with:
    scripts/run_tests.sh tests/janitor/test_janitor_project_create.py
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

# The git/npm toolchain is faked with POSIX shell scripts on PATH and the skill is Linux-only today
# (plan decision 2.7: Linux first). Windows and macOS get their own tests when supported.
pytestmark = pytest.mark.linux_only

REPO_ROOT = Path(__file__).resolve().parents[2]
SKILL_DIR = REPO_ROOT / "janitor" / "skills" / "projects" / "janitor-project-create"
SCRIPT = SKILL_DIR / "scripts" / "project_create.py"
PLACEHOLDER = re.compile(r"\{\{[A-Z][A-Z0-9_]*\}\}")
SHA_PIN = re.compile(r"^[\w.-]+/[\w./-]+@[0-9a-f]{40}$")

FAKE_TOOLS = {
    "git": """
case "$1" in
  --version) echo "git version 9.9.9" ;;
  config) [ -f "$FAKE_STATE/no-identity" ] && exit 1
          case "$3" in user.name) echo "Persona Prueba" ;; user.email) echo "prueba@example.invalid" ;; esac ;;
  init) /bin/mkdir -p .git ;;
  remote) exit 2 ;;
  rev-parse) echo 0000000000000000000000000000000000000000 ;;
esac
exit 0
""",
    "uv": """
case "$1" in
  --version) echo "uv 0.0.0" ;;
  python) echo /fake/python3.13 ;;
  run) if [ -f "$FAKE_STATE/uv-fails" ]; then echo "boom-lint: E999 fallo inventado"; exit 1; fi ;;
esac
exit 0
""",
    "node": 'echo "v99.0.0"\nexit 0\n',
    "npm": 'echo "11.0.0"\nexit 0\n',
    "pnpm": 'echo "12.0.0"\nexit 0\n',
    "gh": 'echo "gh version 0.0.0"\nexit 0\n',
    "sudo": "exit 1\n",
}

COMBOS = [
    pytest.param({"type": "python", "license": "MIT"}, id="python-mit"),
    pytest.param({"type": "node", "kind": "cli", "package-manager": "npm", "license": "Apache-2.0"},
                 id="node-cli-npm-apache"),
    pytest.param({"type": "node", "kind": "service", "package-manager": "pnpm", "license": "none"},
                 id="node-service-pnpm-none"),
    pytest.param({"type": "ops", "license": "MIT"}, id="ops-mit"),
]


def _frontmatter(skill_md: Path) -> dict:
    m = re.match(r"^---\n(.*?)\n---\n", skill_md.read_text(encoding="utf-8"), re.S)
    assert m, f"{skill_md} has no YAML frontmatter"
    return yaml.safe_load(m.group(1))


def _snapshot(root: Path, exclude: tuple[Path, ...] = ()) -> dict:
    out = {}
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if Path(dirpath, d) not in exclude]
        for name in dirnames + filenames:
            p = Path(dirpath) / name
            if p in exclude:
                continue
            st = p.lstat()
            out[str(p.relative_to(root))] = (st.st_size, st.st_mtime_ns, st.st_mode)
    return out


class Sandbox:
    """Temp HOME with a git identity, a fake bin dir and dirs for work and plans."""

    def __init__(self, root: Path, fake: bool = True):
        self.root = root
        self.home = root / "home"
        self.state = root / "fake-state"
        self.bin = root / "fake-bin"
        self.work = root / "work"
        self.plans = root / "plans"
        for d in (self.home, self.state, self.bin, self.work, self.plans, root / "xdg", root / "hermes"):
            d.mkdir(parents=True, exist_ok=True)
        (self.home / ".gitconfig").write_text(
            "[user]\n\tname = Persona Prueba\n\temail = prueba@example.invalid\n"
            "[init]\n\tdefaultBranch = otra\n[commit]\n\tgpgsign = false\n")
        for name, body in FAKE_TOOLS.items():
            path = self.bin / name
            path.write_text(f'#!/bin/sh\nprintf \'%s\\n\' "$*" >> "$FAKE_STATE/{name}.log"\n{body}')
            path.chmod(0o755)
        env = {k: v for k, v in os.environ.items()
               if not k.startswith(("GIT_", "UV_", "npm_config_", "pnpm_config_"))}
        env.update(HOME=str(self.home), XDG_CONFIG_HOME=str(root / "xdg"), GIT_CONFIG_NOSYSTEM="1",
                   HERMES_HOME=str(root / "hermes"), FAKE_STATE=str(self.state), LC_ALL="C.UTF-8")
        env.pop("HERMES_REAL_HOME", None)
        if fake:
            env["PATH"] = str(self.bin)
        self.env = env

    def run(self, *args: str, path: str | None = None) -> subprocess.CompletedProcess:
        env = dict(self.env) if path is None else dict(self.env, PATH=path)
        return subprocess.run([sys.executable, "-B", str(SCRIPT), *args], capture_output=True,
                              text=True, env=env, timeout=600, cwd=self.root)

    def calls(self, tool: str) -> list[str]:
        log = self.state / f"{tool}.log"
        return log.read_text().splitlines() if log.exists() else []

    def plan(self, name: str = "inventario-red", target: Path | None = None, **opts) -> tuple[subprocess.CompletedProcess, Path, Path]:
        target = target or self.work / name
        out = self.plans / f"{name}.json"
        opts = {"type": "python", "license": "MIT", **opts}
        args = ["plan", "--name", name, "--target", str(target), "--output", str(out),
                "--problem", "Inventaría los equipos de la red y detecta cambios",
                "--users", "El equipo de infraestructura de la oficina"]
        for key, value in opts.items():
            if value is True:
                args.append(f"--{key}")
            elif value is not None:
                args += [f"--{key}", str(value)]
        return self.run(*args), out, target


@pytest.fixture
def box(tmp_path: Path) -> Sandbox:
    return Sandbox(tmp_path)


def _generate(box: Sandbox, **opts) -> tuple[dict, Path, Path]:
    proc, plan_path, target = box.plan(**opts)
    assert proc.returncode == 0, proc.stderr
    applied = box.run("apply", str(plan_path), "--confirmed")
    assert applied.returncode == 0, applied.stderr + applied.stdout
    return json.loads(plan_path.read_text()), plan_path, target


# --- skill shape -------------------------------------------------------------------------------

def test_frontmatter_follows_authoring_standards():
    fm = _frontmatter(SKILL_DIR / "SKILL.md")
    assert fm["name"] == SKILL_DIR.name
    assert len(fm["description"]) <= 60 and fm["description"].endswith(".")
    assert fm["platforms"] == ["linux"]
    assert fm["license"] and fm["author"] and fm["version"]
    hermes = fm["metadata"]["hermes"]
    assert hermes["tags"] and hermes["category"]
    for related in hermes["related_skills"]:
        assert list(REPO_ROOT.glob(f"skills/*/{related}/SKILL.md")), related


def test_script_is_executable():
    assert SCRIPT.stat().st_mode & stat.S_IXUSR


# --- plan ---------------------------------------------------------------------------------------

@pytest.mark.parametrize("opts", COMBOS)
def test_plan_writes_nothing_in_target_and_lists_every_file(box, opts):
    before = _snapshot(box.work)
    proc, plan_path, target = box.plan(**opts)
    assert proc.returncode == 0, proc.stderr
    assert _snapshot(box.work) == before and not target.exists()
    plan = json.loads(plan_path.read_text())
    assert plan["files"], "a plan must list files"
    for f in plan["files"]:
        assert f["purpose"].strip()
        assert f"  {f['path']}" in proc.stdout
    for cmd in plan["commands"]:
        assert " ".join(cmd["argv"]) in proc.stdout
    assert ("LICENSE" in {f["path"] for f in plan["files"]}) == (opts["license"] != "none")


def test_plan_leaves_an_existing_empty_target_empty(box):
    target = box.work / "vacio"
    target.mkdir()
    proc, _, _ = box.plan(name="vacio", target=target)
    assert proc.returncode == 0, proc.stderr
    assert list(target.iterdir()) == []


# --- apply: tree, placeholders, CI ---------------------------------------------------------------

@pytest.mark.parametrize("opts", COMBOS)
def test_apply_creates_exactly_the_planned_tree_and_nothing_outside(box, opts):
    proc, plan_path, target = box.plan(**opts)
    assert proc.returncode == 0, proc.stderr
    plan = json.loads(plan_path.read_text())
    outside_before = _snapshot(box.root, exclude=(target, box.state))
    outside_before.pop("work")  # the parent gains exactly one entry, checked below

    applied = box.run("apply", str(plan_path), "--confirmed")

    assert applied.returncode == 0, applied.stderr
    outside_after = _snapshot(box.root, exclude=(target, box.state))
    outside_after.pop("work")
    assert outside_after == outside_before
    assert [p.name for p in box.work.iterdir()] == [target.name]
    expected = {f["path"] for f in plan["files"]}
    expected |= {str(p) for f in plan["files"] for p in Path(f["path"]).parents if str(p) != "."}
    expected |= {c.rstrip("/") for cmd in plan["commands"]
                 if cmd["selected"] and cmd["phase"] != "publish" for c in cmd["creates"]}
    assert set(_snapshot(target)) == expected
    for f in plan["files"]:
        data = (target / f["path"]).read_bytes()
        assert hashlib.sha256(data).hexdigest() == f["sha256"]
        assert stat.S_IMODE((target / f["path"]).stat().st_mode) == f["mode"]


@pytest.mark.parametrize("opts", COMBOS)
def test_generated_files_have_no_placeholders_and_ci_is_sha_pinned(box, opts):
    plan, _, target = _generate(box, **opts)
    for f in plan["files"]:
        text = (target / f["path"]).read_text(encoding="utf-8")
        assert not PLACEHOLDER.search(text), f"{f['path']}: {PLACEHOLDER.search(text).group(0)}"
    workflow_text = (target / ".github" / "workflows" / "ci.yml").read_text()
    workflow = yaml.safe_load(workflow_text)
    uses = [s["uses"] for job in workflow["jobs"].values() for s in job["steps"] if "uses" in s]
    assert uses
    for ref in uses:
        assert SHA_PIN.match(ref), ref
    for line in workflow_text.splitlines():
        if "uses:" in line:
            assert re.search(r"# v\d", line), line
    ignored = (target / ".gitignore").read_text().splitlines()
    assert ".env" in ignored and ".env.*" in ignored


def test_generated_manifests_parse_and_pin_dev_dependencies(box):
    import tomllib

    _, _, py = _generate(box, name="paquete-py", type="python")
    project = tomllib.loads((py / "pyproject.toml").read_text())
    for spec in project["dependency-groups"]["dev"]:
        assert ">=" in spec and "<" in spec, spec
    for spec in project["build-system"]["requires"]:
        assert ">=" in spec and "<" in spec, spec
    _, _, node = _generate(box, name="servicio-ts", type="node", kind="service")
    pkg = json.loads((node / "package.json").read_text())
    for name, version in pkg["devDependencies"].items():
        assert re.fullmatch(r"\d+\.\d+\.\d+", version), (name, version)


# --- apply: refusals ------------------------------------------------------------------------------

def test_non_empty_target_is_refused_by_plan_and_apply(box):
    target = box.work / "ocupado"
    target.mkdir()
    (target / "importante.txt").write_text("no tocar")
    proc, plan_path, _ = box.plan(name="ocupado", target=target)
    assert proc.returncode == 2 and "no está vacío" in proc.stderr
    assert not plan_path.exists()

    target2 = box.work / "luego-ocupado"
    proc, plan_path, _ = box.plan(name="luego-ocupado", target=target2)
    assert proc.returncode == 0, proc.stderr
    target2.mkdir()
    (target2 / "nuevo.txt").write_text("apareció después del plan")
    applied = box.run("apply", str(plan_path), "--confirmed")
    assert applied.returncode == 2
    assert sorted(p.name for p in target2.iterdir()) == ["nuevo.txt"]
    assert (target / "importante.txt").read_text() == "no tocar"


def test_apply_requires_confirmation(box):
    proc, plan_path, target = box.plan()
    assert proc.returncode == 0
    applied = box.run("apply", str(plan_path))
    assert applied.returncode == 2 and "--confirmed" in applied.stderr
    assert not target.exists()


@pytest.mark.parametrize("evil", ["../evil", "{abs}/evil", "src/../../evil", ".git/hooks/pre-commit"])
def test_hand_edited_plan_with_path_outside_target_is_refused(box, evil):
    proc, plan_path, target = box.plan()
    assert proc.returncode == 0
    plan = json.loads(plan_path.read_text())
    plan["files"][0]["path"] = evil.format(abs=box.root)
    plan_path.write_text(json.dumps(plan))
    before = _snapshot(box.root, exclude=(box.state,))

    applied = box.run("apply", str(plan_path), "--confirmed")

    assert applied.returncode == 2 and "RECHAZADO" in applied.stderr
    assert _snapshot(box.root, exclude=(box.state,)) == before
    assert not target.exists()


def test_symlinked_target_is_refused(box):
    proc, plan_path, target = box.plan()
    assert proc.returncode == 0
    elsewhere = box.root / "elsewhere"
    elsewhere.mkdir()
    target.symlink_to(elsewhere, target_is_directory=True)

    applied = box.run("apply", str(plan_path), "--confirmed")

    assert applied.returncode == 2 and "enlace simbólico" in applied.stderr
    assert list(elsewhere.iterdir()) == []


def test_hand_edited_command_is_refused(box):
    proc, plan_path, target = box.plan()
    assert proc.returncode == 0
    plan = json.loads(plan_path.read_text())
    commit = next(c for c in plan["commands"] if c["id"] == "git-commit")
    commit["argv"] = ["sudo", "rm", "-rf", "/"]
    plan_path.write_text(json.dumps(plan))

    applied = box.run("apply", str(plan_path), "--confirmed")

    assert applied.returncode == 2 and "modificado" in applied.stderr
    assert not target.exists()
    assert box.calls("sudo") == []


# --- network gating -------------------------------------------------------------------------------

def _network_calls(box: Sandbox) -> list[str]:
    calls = [f"uv {c}" for c in box.calls("uv") if not c.startswith(("--version", "python find"))]
    calls += [f"npm {c}" for c in box.calls("npm") if c != "--version"]
    calls += [f"pnpm {c}" for c in box.calls("pnpm") if c != "--version"]
    calls += [f"gh {c}" for c in box.calls("gh") if c != "--version"]
    calls += [f"git {c}" for c in box.calls("git") if c.startswith(("push", "remote add", "fetch", "clone"))]
    return calls


@pytest.mark.parametrize("opts", COMBOS)
def test_no_network_command_runs_unless_selected(box, opts):
    _generate(box, remote="dueno/inventario-red", **opts)
    assert _network_calls(box) == []
    assert box.calls("sudo") == []
    assert any(c.startswith("commit") for c in box.calls("git"))


def test_selected_install_runs_only_the_planned_command(box):
    _generate(box, install=True)
    assert _network_calls(box) == ["uv sync"]
    _generate(box, name="cli-pnpm", type="node", kind="cli", **{"package-manager": "pnpm"}, install=True)
    assert _network_calls(box) == ["uv sync", "pnpm install"]
    assert box.calls("sudo") == []


def test_publish_is_separate_and_needs_its_own_confirmation(box):
    _, plan_path, _ = _generate(box, remote="dueno/inventario-red")
    refused = box.run("publish", str(plan_path))
    assert refused.returncode == 2 and _network_calls(box) == []

    published = box.run("publish", str(plan_path), "--confirmed")

    assert published.returncode == 0, published.stderr
    assert [c for c in box.calls("gh") if c != "--version"] == [
        "repo create dueno/inventario-red --private --source . --remote origin"]
    assert "push --set-upstream origin main" in box.calls("git")
    assert box.calls("sudo") == []


def test_publish_without_remote_in_plan_is_refused(box):
    _, plan_path, _ = _generate(box)
    proc = box.run("publish", str(plan_path), "--confirmed")
    assert proc.returncode == 2 and "remoto" in proc.stderr
    assert _network_calls(box) == []


# --- git identity -----------------------------------------------------------------------------------

def test_plan_without_git_identity_stops_with_clear_message(box):
    (box.state / "no-identity").touch()
    proc, plan_path, target = box.plan()
    assert proc.returncode == 2
    assert "identidad" in proc.stderr and "git config --global user.name" in proc.stderr
    assert not plan_path.exists() and not target.exists()


def test_apply_without_git_identity_writes_nothing_and_never_commits(box):
    proc, plan_path, target = box.plan()
    assert proc.returncode == 0
    (box.state / "no-identity").touch()

    applied = box.run("apply", str(plan_path), "--confirmed")

    assert applied.returncode == 2 and "identidad" in applied.stderr
    assert not target.exists()
    assert not any(c.startswith(("commit", "init", "-c")) for c in box.calls("git"))


# --- verify ---------------------------------------------------------------------------------------

def test_verify_reports_missing_toolchain_as_not_verified(box):
    _, plan_path, target = _generate(box)
    only_git = box.root / "only-git"
    only_git.mkdir()
    (only_git / "git").symlink_to(box.bin / "git")

    proc = box.run("verify", str(plan_path), path=str(only_git))

    assert proc.returncode == 3, proc.stderr
    report = json.loads(proc.stdout)
    assert report["overall"] == "unverified"
    assert {s["status"] for s in report["steps"]} == {"not_verified"}
    assert all("uv" in s["reason"] for s in report["steps"])


def test_verify_without_installed_dependencies_never_downloads(box):
    _, plan_path, _ = _generate(box)
    proc = box.run("verify", str(plan_path))
    assert proc.returncode == 3
    report = json.loads(proc.stdout)
    assert all("uv sync" in s["reason"] for s in report["steps"])
    assert _network_calls(box) == []


def test_verify_failure_reports_real_output_tail(box):
    _, plan_path, target = _generate(box)
    (target / "uv.lock").write_text("")
    (target / ".venv").mkdir()
    (box.state / "uv-fails").touch()

    proc = box.run("verify", str(plan_path))

    assert proc.returncode == 1
    report = json.loads(proc.stdout)
    assert report["overall"] == "failed"
    assert all(s["status"] == "fail" and "boom-lint" in s["output_tail"] for s in report["steps"])


# --- real toolchain, offline ------------------------------------------------------------------------

def _has(*tools: str) -> bool:
    return all(any(Path(d, t).is_file() and os.access(Path(d, t), os.X_OK)
                   for d in os.environ.get("PATH", "").split(os.pathsep) if d) for t in tools)


@pytest.fixture
def real_box(tmp_path: Path) -> Sandbox:
    return Sandbox(tmp_path, fake=False)


def _git(target: Path, env: dict, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=target, env=env, capture_output=True, text=True,
                          check=True).stdout.strip()


def _assert_real_first_commit(box: Sandbox, target: Path) -> None:
    assert _git(target, box.env, "rev-parse", "--abbrev-ref", "HEAD") == "main"
    assert _git(target, box.env, "rev-list", "--count", "HEAD") == "1"
    assert _git(target, box.env, "log", "-1", "--format=%an <%ae>") == "Persona Prueba <prueba@example.invalid>"
    assert _git(target, box.env, "status", "--porcelain") == ""
    (target / ".env").write_text("TOKEN=no-debe-entrar\n")
    assert _git(target, box.env, "check-ignore", ".env") == ".env"


@pytest.mark.skipif(not _has("git", "make", "bash"), reason="needs git, make and bash")
def test_real_ops_project_builds_and_its_tests_pass(real_box):
    _, plan_path, target = _generate(real_box, name="rotar-backups", type="ops")
    _assert_real_first_commit(real_box, target)

    proc = real_box.run("verify", str(plan_path))

    report = json.loads(proc.stdout)
    steps = {s["id"]: s for s in report["steps"]}
    assert steps["test"]["status"] == "pass", steps["test"]
    if _has("shellcheck"):
        assert steps["lint"]["status"] == "pass", steps["lint"]
        assert report["overall"] == "passed" and proc.returncode == 0
    else:
        assert steps["lint"]["status"] == "not_verified" and "shellcheck" in steps["lint"]["reason"]
        assert report["overall"] == "unverified" and proc.returncode == 3


@pytest.mark.skipif(not _has("git", "uv"), reason="needs git and uv")
def test_real_python_project_is_committed_and_flagged_unverified_offline(real_box):
    _, plan_path, target = _generate(real_box, name="paquete-real", type="python")
    _assert_real_first_commit(real_box, target)
    proc = real_box.run("verify", str(plan_path))
    report = json.loads(proc.stdout)
    assert proc.returncode == 3 and report["overall"] == "unverified"
    assert not (target / ".venv").exists()


@pytest.mark.skipif(not _has("git", "node", "npm"), reason="needs git, node and npm")
def test_real_node_project_is_committed_and_flagged_unverified_offline(real_box):
    _, plan_path, target = _generate(real_box, name="servicio-real", type="node", kind="service",
                                     **{"package-manager": "npm"})
    _assert_real_first_commit(real_box, target)
    proc = real_box.run("verify", str(plan_path))
    report = json.loads(proc.stdout)
    assert proc.returncode == 3 and report["overall"] == "unverified"
    assert not (target / "node_modules").exists()
