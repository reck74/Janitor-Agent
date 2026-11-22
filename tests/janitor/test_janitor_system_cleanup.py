"""Safety proof for the janitor-cleanup skill (F3-01, AGENTS.md directive #19).

Every behaviour test runs the real script in a subprocess against a throwaway HOME,
XDG_DATA_HOME and agent home under ``tmp_path``, with fake tool binaries (and a fake
``sudo``) first on PATH that only record their invocations. No real cache purge,
prune or trash-empty ever runs.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import re
import stat
import subprocess
import sys
import time
import urllib.parse
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
SYSTEM_SKILLS = REPO_ROOT / "janitor" / "skills" / "system"
SKILL_DIR = SYSTEM_SKILLS / "janitor-cleanup"
SCRIPT = SKILL_DIR / "scripts" / "janitor_cleanup.py"
SAFETY = SKILL_DIR / "scripts" / "janitor_fs_safety.py"
ORGANIZER_SAFETY = SYSTEM_SKILLS / "janitor-file-organizer" / "scripts" / "janitor_fs_safety.py"

OLD = time.time() - 400 * 86400


def _load_safety():
    spec = importlib.util.spec_from_file_location("cleanup_fs_safety", SAFETY)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


# --------------------------------------------------------------------------- fixtures


def _write(path: Path, data: bytes, mtime: float | None = None) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    if mtime is not None:
        os.utime(path, (mtime, mtime))
    return path


def _age_tree(path: Path, mtime: float) -> None:
    for dirpath, dirnames, filenames in os.walk(path):
        for name in filenames + dirnames:
            os.utime(os.path.join(dirpath, name), (mtime, mtime), follow_symlinks=False)
    os.utime(path, (mtime, mtime))


def _fake_tool(bindir: Path, name: str, log: Path, cases: dict[str, str]) -> None:
    lines = ["#!/bin/sh", f'echo "{name} $*" >> "{log}"', 'case "$*" in']
    for args, output in cases.items():
        lines.append(f'  "{args}") printf "%s\\n" \'{output}\' ;;')
    lines += ["esac", "exit 0", ""]
    path = bindir / name
    path.write_text("\n".join(lines))
    path.chmod(0o755)


class Env:
    def __init__(self, tmp_path: Path):
        tmp_path = tmp_path.resolve()
        self.root = tmp_path
        self.home = tmp_path / "home"
        self.agent = self.home / ".janitor"
        self.trash = self.home / ".local" / "share" / "Trash"
        self.bin = tmp_path / "fakebin"
        self.plans = tmp_path / "plans"
        self.logs = tmp_path / "logs"
        self.sysbin = tmp_path / "sysbin"
        self.log = self.logs / "tools.log"
        self.sudo_log = self.logs / "sudo.log"
        for d in (self.home, self.agent, self.bin, self.plans, self.logs, self.sysbin):
            d.mkdir(parents=True, exist_ok=True)
        # Hermetic PATH: fake tools plus only the real binaries the scripts may use
        # read-only (git) or to trash (gio). No real pip/npm/docker/pacman is reachable.
        for name in ("git", "gio"):
            for d in ("/usr/bin", "/bin"):
                if os.path.exists(os.path.join(d, name)):
                    (self.sysbin / name).symlink_to(os.path.join(d, name))
                    break
        self.log.write_text("")
        self.sudo_log.write_text("")
        sudo = self.bin / "sudo"
        sudo.write_text(f'#!/bin/sh\necho "sudo $*" >> "{self.sudo_log}"\nexit 1\n')
        sudo.chmod(0o755)
        self.vars = {
            "HOME": str(self.home),
            "XDG_DATA_HOME": str(self.home / ".local" / "share"),
            "HERMES_HOME": str(self.agent),
            "PATH": f"{self.bin}:{self.sysbin}",
            "LANG": "C.UTF-8",
            "TZ": "UTC",
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid",
            "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.invalid",
        }

    def run(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True,
                              text=True, env=self.vars, timeout=300, check=False)

    def git(self, cwd: Path, *args: str) -> None:
        subprocess.run(["git", *args], cwd=cwd, env=self.vars, check=True,
                       capture_output=True, timeout=60)

    def plan(self, *extra: str) -> tuple[Path, str]:
        out = self.plans / f"plan-{len(list(self.plans.iterdir()))}.json"
        proc = self.run("plan", "--out", str(out), *extra)
        assert proc.returncode == 0, proc.stderr
        return out, digest_of(proc.stdout)

    def summary_digest(self, plan: Path) -> str:
        proc = self.run("summary", str(plan))
        assert proc.returncode == 0, proc.stderr
        return digest_of(proc.stdout)

    def tool_calls(self) -> list[str]:
        return [ln for ln in self.log.read_text().splitlines() if ln.strip()]


def digest_of(stdout: str) -> str:
    m = re.search(r"^DIGEST: ([0-9a-f]+)$", stdout, re.M)
    assert m, stdout
    return m.group(1)


def snapshot(root: Path, exclude: tuple[Path, ...] = ()) -> dict:
    state = {}
    for dirpath, dirnames, filenames in os.walk(root):
        if any(Path(dirpath).is_relative_to(e) for e in exclude):
            continue
        for name in dirnames + filenames:
            p = Path(dirpath) / name
            rel = str(p.relative_to(root))
            st = os.lstat(p)
            if stat.S_ISLNK(st.st_mode):
                state[rel] = ("link", os.readlink(p))
            elif stat.S_ISDIR(st.st_mode):
                state[rel] = ("dir",)
            else:
                state[rel] = ("file", st.st_size, st.st_mtime_ns,
                              hashlib.sha256(p.read_bytes()).hexdigest())
    return state


@pytest.fixture
def env(tmp_path: Path) -> Env:
    return Env(tmp_path)


def _populate(env: Env) -> dict[str, Path]:
    """A home with something in every category plus protected bait."""
    h = env.home
    paths = {
        "old_cache": _write(h / ".cache" / "oldapp" / "blob.bin", os.urandom(2 * 1024 * 1024)),
        "fresh_cache": _write(h / ".cache" / "freshapp" / "blob.bin", os.urandom(2 * 1024 * 1024)),
        "thumb": _write(h / ".cache" / "thumbnails" / "large" / "a.png", os.urandom(1536 * 1024)),
        "log": _write(h / ".local" / "state" / "app" / "app.log", b"x" * 200_000, OLD),
        "download": _write(h / "Downloads" / "old.iso", os.urandom(3 * 1024 * 1024), OLD),
        "big": _write(h / "Videos" / "big.mkv", os.urandom(3 * 1024 * 1024)),
        "ssh": _write(h / ".ssh" / "id_ed25519", b"secret"),
        "agent_file": _write(env.agent / "state.db", os.urandom(2 * 1024 * 1024)),
    }
    _age_tree(h / ".cache" / "oldapp", OLD)
    dup = os.urandom(1536 * 1024)
    paths["dup1"] = _write(h / "Music" / "a.flac", dup)
    paths["dup2"] = _write(h / "Documents" / "a-copy.flac", dup)
    proj = h / "Projects" / "webapp"
    _write(proj / "package.json", b"{}")
    _write(proj / "node_modules" / "lib" / "index.js", os.urandom(300_000))
    _age_tree(proj, OLD)
    paths["node_modules"] = proj / "node_modules"
    pip_cache = h / ".cache" / "pip"
    _write(pip_cache / "http" / "blob", os.urandom(2 * 1024 * 1024))
    _fake_tool(env.bin, "pip", env.log, {"cache dir": str(pip_cache)})
    _fake_tool(env.bin, "docker", env.log, {
        "system df --format {{json .}}": (
            '{"Type":"Images","Reclaimable":"1GB (50%)"}\n'
            '{"Type":"Containers","Reclaimable":"20MB (10%)"}\n'
            '{"Type":"Local Volumes","Reclaimable":"3GB (90%)"}\n'
            '{"Type":"Build Cache","Reclaimable":"700MB"}'),
        "images --filter dangling=true --format {{.Size}}": "5MB",
    })
    return paths


def _journal(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def _entries(plan: Path) -> list[dict]:
    return json.loads(plan.read_text())["entries"]


def _by_path(plan: Path) -> dict[str, dict]:
    return {e["path"]: e for e in _entries(plan)}


# --------------------------------------------------------------------------- frontmatter


def test_skill_frontmatter_valid() -> None:
    text = (SKILL_DIR / "SKILL.md").read_text()
    m = re.search(r"^---\n(.*?)\n---", text, re.DOTALL)
    assert m, "SKILL.md missing YAML frontmatter"
    fm = yaml.safe_load(m.group(1))
    assert fm["name"] == SKILL_DIR.name
    desc = fm["description"]
    assert isinstance(desc, str) and len(desc) <= 60 and desc.endswith(".")
    assert fm["platforms"] == ["linux"]
    assert fm["author"] == "Janitor Agent" and fm["license"] == "MIT" and fm["version"]
    assert fm["metadata"]["hermes"]["tags"] and fm["metadata"]["hermes"]["category"]


def test_shared_safety_module_is_identical_in_both_skills() -> None:
    assert SAFETY.read_bytes() == ORGANIZER_SAFETY.read_bytes()


def test_script_is_executable() -> None:
    assert os.access(SCRIPT, os.X_OK)


# --------------------------------------------------------------------------- plan is read-only


@pytest.mark.linux_only
def test_plan_modifies_nothing_and_runs_no_tool_mutation(env: Env) -> None:
    _populate(env)
    before = snapshot(env.root, exclude=(env.plans, env.logs))
    plan, _ = env.plan("--large-mb", "2", "--dup-min-mb", "1")
    assert snapshot(env.root, exclude=(env.plans, env.logs)) == before
    calls = env.tool_calls()
    assert calls, "probes were expected"
    assert not any("purge" in c or "prune" in c or "clean" in c for c in calls), calls
    assert env.sudo_log.read_text() == ""
    cats = {e["category"] for e in _entries(plan)}
    assert {"user-cache", "thumbnails", "tool-cache", "docker", "build-artifacts",
            "large-files", "old-downloads", "duplicates", "logs"} <= cats


@pytest.mark.linux_only
def test_plan_classifies_risk_and_never_preselects_report_only(env: Env) -> None:
    p = _populate(env)
    plan, _ = env.plan("--large-mb", "2")
    entries = _entries(plan)
    for e in entries:
        assert e["risk"] in ("safe", "review")
        assert e["method"] in ("trash", "tool", "suggest")
        if e["report_only"] or e["method"] == "suggest" or e["risk"] == "review":
            assert not e["selected"], e
    by_path = _by_path(plan)
    assert str(p["fresh_cache"].parent) not in by_path, "recent cache must not be proposed"
    assert by_path[str(p["old_cache"].parent)]["selected"]
    dup_entries = [e for e in entries if e["category"] == "duplicates"]
    assert {e["path"] for e in dup_entries} == {str(p["dup1"]), str(p["dup2"])}
    assert all(not e["selected"] for e in dup_entries)
    vol_notes = [n for n in json.loads(plan.read_text())["notes"] if "volúmenes" in n]
    assert vol_notes, "Docker volumes must be reported as never touched"
    # selecting report-only items by category is refused; only explicit ids work
    env.run("select", str(plan), "--category", "duplicates")
    assert all(not e["selected"] for e in _entries(plan) if e["category"] == "duplicates")


@pytest.mark.linux_only
def test_protected_paths_never_planned(env: Env) -> None:
    p = _populate(env)
    plan, _ = env.plan("--large-mb", "1")
    planned = {e["path"] for e in _entries(plan)}
    for key in ("ssh", "agent_file"):
        assert not any(path == str(p[key]) or str(p[key]).startswith(path + "/")
                       for path in planned), key


# --------------------------------------------------------------------------- apply gate


@pytest.mark.linux_only
def test_apply_without_plan_or_digest_is_impossible(env: Env) -> None:
    _populate(env)
    before = snapshot(env.root, exclude=(env.plans, env.logs))
    assert env.run("apply").returncode != 0
    assert env.run("apply", "--confirm", "deadbeef").returncode != 0
    assert env.run("apply", str(env.plans / "missing.json"), "--confirm", "x").returncode != 0
    plan, digest = env.plan()
    assert env.run("apply", str(plan)).returncode != 0, "--confirm is mandatory"
    wrong = env.run("apply", str(plan), "--confirm", "0" * 16)
    assert wrong.returncode == 2
    # the error never hands out the valid digest; only plan/summary print it
    assert digest not in wrong.stdout + wrong.stderr
    assert digest in env.run("summary", str(plan)).stdout
    assert snapshot(env.root, exclude=(env.plans, env.logs)) == before
    assert not env.trash.exists()
    assert not any("purge" in c or "prune" in c for c in env.tool_calls())


@pytest.mark.linux_only
def test_apply_acts_only_on_selected_and_skips_changed(env: Env) -> None:
    p = _populate(env)
    plan, digest = env.plan("--categories", "user-cache,thumbnails,build-artifacts,old-downloads")
    by_path = _by_path(plan)
    assert by_path[str(p["thumb"].parents[1])]["selected"]
    # the thumbnail dir changes after planning -> must be skipped
    _write(p["thumb"].parent / "new.png", b"new")
    proc = env.run("apply", str(plan), "--confirm", digest)
    assert proc.returncode == 0, proc.stderr
    assert p["thumb"].exists(), "changed entry must be skipped"
    assert "cambió desde el plan" in proc.stdout
    assert not p["old_cache"].exists() and not p["node_modules"].exists()
    assert p["download"].exists(), "report-only entry was not selected"
    assert p["fresh_cache"].exists()
    trashed = sorted(x.name for x in (env.trash / "files").iterdir())
    assert trashed == ["node_modules", "oldapp"]
    # bytes still exist in the trash: nothing was unlinked
    assert (env.trash / "files" / "oldapp" / "blob.bin").stat().st_size == 2 * 1024 * 1024


@pytest.mark.linux_only
@pytest.mark.parametrize("backend", ["python", "auto"])
def test_trash_is_freedesktop_compliant_and_restorable(env: Env, backend: str) -> None:
    p = _populate(env)
    original_bytes = p["old_cache"].read_bytes()
    plan, digest = env.plan("--categories", "user-cache")
    proc = env.run("apply", str(plan), "--confirm", digest, "--trash-backend", backend)
    assert proc.returncode == 0, proc.stderr
    src = p["old_cache"].parent
    assert not src.exists()
    info = (env.trash / "info" / "oldapp.trashinfo").read_text()
    lines = info.splitlines()
    assert lines[0] == "[Trash Info]"
    fields = dict(ln.split("=", 1) for ln in lines[1:] if "=" in ln)
    assert urllib.parse.unquote(fields["Path"]) == str(src)
    assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d", fields["DeletionDate"])
    assert (env.trash / "files" / "oldapp" / "blob.bin").read_bytes() == original_bytes
    result = next(env.plans.glob("*.journal-*.jsonl"))
    proc = env.run("restore", str(result))
    assert proc.returncode == 0, proc.stdout
    assert p["old_cache"].read_bytes() == original_bytes
    assert not (env.trash / "info" / "oldapp.trashinfo").exists()
    assert not (env.trash / "files" / "oldapp").exists()


# --------------------------------------------------------------------------- hand-edited plans


@pytest.mark.linux_only
def test_hand_edited_plan_entries_are_refused(env: Env) -> None:
    fs = _load_safety()
    _populate(env)
    outside = _write(env.root / "outside" / "victim.txt", b"keep me")
    link = env.home / "escape"
    link.symlink_to(outside)
    ssh = env.home / ".ssh" / "id_ed25519"
    agent_file = env.agent / "state.db"
    repo = env.home / "work" / "repo"
    _write(repo / "tracked.txt", b"v1")
    env.git(repo, "init", "-q")
    env.git(repo, "add", ".")
    env.git(repo, "commit", "-qm", "init")
    (repo / "tracked.txt").write_bytes(b"v2 uncommitted")
    dirty = _write(repo / "scratch.bin", b"y" * 10)
    gitmeta = repo / ".git" / "config"
    system_file = Path("/etc/hostname") if Path("/etc/hostname").exists() else Path("/etc/passwd")

    plan, _ = env.plan("--categories", "thumbnails")
    data = json.loads(plan.read_text())
    for e in data["entries"]:
        e["selected"] = False
    targets = [outside, link, ssh, agent_file, dirty, gitmeta, system_file]
    for i, target in enumerate(targets, start=100):
        data["entries"].append({
            "id": i, "category": "user-cache", "path": str(target), "bytes": 1,
            "reason": "tampered", "risk": "safe", "method": "trash", "report_only": False,
            "selected": True, "fingerprint": fs.fingerprint(str(target)),
        })
    data["entries"].append({
        "id": 200, "category": "tool-cache", "path": "x", "bytes": 1, "reason": "tampered",
        "risk": "safe", "method": "tool", "report_only": False, "selected": True,
        "tool": "pip", "binary": str(env.bin / "pip"), "argv": ["cache", "purge", "--evil"],
        "command": "pip cache purge --evil"})
    data["entries"].append({
        "id": 201, "category": "pkg-cache", "path": "/var/cache", "bytes": 1,
        "reason": "tampered", "risk": "safe", "method": "suggest", "report_only": False,
        "selected": True, "command": "sudo rm -rf /var/cache", "privileged": True})
    plan.write_text(json.dumps(data))
    digest = env.summary_digest(plan)
    before = snapshot(env.root, exclude=(env.plans, env.logs))
    proc = env.run("apply", str(plan), "--confirm", digest)
    assert proc.returncode == 0, proc.stderr
    for target in targets:
        assert os.path.lexists(target), target
    assert outside.read_bytes() == b"keep me"
    assert not env.trash.exists() or not any((env.trash / "files").iterdir())
    assert snapshot(env.root, exclude=(env.plans, env.logs)) == before
    assert not any("purge" in c for c in env.tool_calls())
    assert env.sudo_log.read_text() == ""
    records = _journal(next(env.plans.glob("*.journal-*.jsonl")))
    skipped = {r["id"] for r in records if r.get("op") == "skip"}
    assert skipped >= set(range(100, 100 + len(targets))) | {200, 201}
    assert not any(r.get("op") in ("trash", "tool") for r in records)

    # widening the roots in the plan is refused outright
    data["roots"] = ["/"]
    plan.write_text(json.dumps(data))
    assert env.run("apply", str(plan), "--confirm", env.summary_digest(plan)).returncode == 2
    data["roots"] = [str(env.root / "outside")]
    plan.write_text(json.dumps(data))
    assert env.run("apply", str(plan), "--confirm", env.summary_digest(plan)).returncode == 2
    assert outside.read_bytes() == b"keep me"


# --------------------------------------------------------------------------- tools & sudo


@pytest.mark.linux_only
def test_tool_commands_run_only_on_apply_and_never_sudo(env: Env) -> None:
    _populate(env)
    plan, digest = env.plan("--categories", "tool-cache,docker,pkg-cache,trash-old,logs")
    entries = _entries(plan)
    pip = next(e for e in entries if e.get("tool") == "pip")
    assert pip["method"] == "tool" and pip["command"] == "pip cache purge" and pip["selected"]
    containers = next(e for e in entries if e.get("tool") == "docker-containers")
    assert containers["risk"] == "review" and not containers["selected"]
    for e in entries:
        if e["method"] == "suggest":
            assert not e["selected"]
    assert not any("purge" in c or "prune" in c for c in env.tool_calls())
    proc = env.run("apply", str(plan), "--confirm", digest)
    assert proc.returncode == 0, proc.stderr
    calls = env.tool_calls()
    assert calls.count("pip cache purge") == 1
    assert "docker image prune -f" in calls and "docker builder prune -f" in calls
    assert "docker container prune -f" not in calls, "review item was not selected"
    assert not any("volume" in c for c in calls)
    assert env.sudo_log.read_text() == ""


# --------------------------------------------------------------------------- git rules


@pytest.mark.linux_only
def test_build_artifacts_only_in_clean_pushed_repos(env: Env) -> None:
    remote = env.root / "remote.git"
    env.git(env.root, "init", "-q", "--bare", str(remote))

    def make(name: str) -> Path:
        proj = env.home / "Projects" / name
        _write(proj / "package.json", b"{}")
        _write(proj / ".gitignore", b"node_modules/\n")
        _write(proj / "node_modules" / "dep" / "index.js", b"z" * 50_000)
        env.git(proj, "init", "-q", "-b", "main")
        env.git(proj, "add", "package.json", ".gitignore")
        env.git(proj, "commit", "-qm", "init")
        return proj

    clean = make("clean")
    env.git(clean, "remote", "add", "origin", str(remote))
    env.git(clean, "push", "-q", "origin", "main")
    dirty = make("dirty")
    env.git(dirty, "remote", "add", "origin", str(remote))
    env.git(dirty, "push", "-q", "-f", "origin", "main:other")
    _write(dirty / "wip.txt", b"uncommitted")
    unpushed = make("unpushed")
    for proj in (clean, dirty, unpushed):
        _age_tree(proj, OLD)
    plan, digest = env.plan("--categories", "build-artifacts")
    planned = {e["path"] for e in _entries(plan)}
    assert str(clean / "node_modules") in planned
    assert str(dirty / "node_modules") not in planned
    assert str(unpushed / "node_modules") not in planned
    proc = env.run("apply", str(plan), "--confirm", digest)
    assert proc.returncode == 0, proc.stderr
    assert not (clean / "node_modules").exists()
    assert (dirty / "node_modules").exists() and (unpushed / "node_modules").exists()
    assert (env.trash / "files" / "node_modules" / "dep" / "index.js").exists()


# --------------------------------------------------------------------------- crash safety

CRASH_DRIVER = """
import os, sys
sys.path.insert(0, sys.argv[1])
import janitor_fs_safety as fs
import janitor_cleanup as m
target, mode, n = sys.argv[2], sys.argv[3], int(sys.argv[4])
calls = [0]
if target == "rename":
    real = fs.rename_noreplace
    def hooked(a, b):
        calls[0] += 1
        if calls[0] == n and mode == "before":
            os._exit(9)
        real(a, b)
        if calls[0] == n and mode == "after":
            os._exit(9)
    fs.rename_noreplace = hooked
else:
    real_put = fs.Trash.put
    def hooked_put(self, path):
        calls[0] += 1
        rec = real_put(self, path)
        if calls[0] == n:
            os._exit(9)
        return rec
    fs.Trash.put = hooked_put
sys.exit(m.main(sys.argv[5:]))
"""


def _crash_apply(env: Env, plan: Path, digest: str, target: str, mode: str, n: int,
                 backend: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-c", CRASH_DRIVER, str(SCRIPT.parent), target, mode, str(n),
         "apply", str(plan), "--confirm", digest, "--trash-backend", backend],
        capture_output=True, text=True, env=env.vars, timeout=300, check=False)


def _cache_dirs(env: Env, count: int, *, with_trash: bool = True) -> list[Path]:
    if with_trash:  # so snapshots compare user data, not the trash skeleton
        for sub in ("files", "info"):
            (env.trash / sub).mkdir(parents=True, exist_ok=True)
    dirs = []
    for i in range(count):
        d = env.home / ".cache" / f"stale{i}"
        _write(d / "blob.bin", os.urandom(1100 * 1024))
        _age_tree(d, OLD)
        dirs.append(d)
    return dirs


@pytest.mark.linux_only
@pytest.mark.parametrize("backend", ["python", "auto"])
def test_killed_apply_leaves_every_trashed_item_restorable(env: Env, backend: str) -> None:
    dirs = _cache_dirs(env, 3)
    before = snapshot(env.home, exclude=(env.trash,))
    plan, digest = env.plan("--categories", "user-cache")
    proc = _crash_apply(env, plan, digest, "put", "after", 2, backend)
    assert proc.returncode == 9, proc.stderr
    gone = [d for d in dirs if not d.exists()]
    assert len(gone) == 2, "two items reached the trash before the kill"
    journal = next(env.plans.glob("*.journal-*.jsonl"))
    records = _journal(journal)
    done = {r["seq"] for r in records if r.get("state") == "done"}
    pending = [r for r in records if r.get("state") == "pending"]
    assert len(pending) == 2 and len(done) == 1, "the 2nd item has no done record"
    proc = env.run("restore", str(journal))
    assert proc.returncode == 0, proc.stdout
    assert snapshot(env.home, exclude=(env.trash,)) == before
    assert not any((env.trash / "files").iterdir()) and not any((env.trash / "info").iterdir())


@pytest.mark.linux_only
def test_killed_between_trashinfo_and_move_restores_cleanly(env: Env) -> None:
    dirs = _cache_dirs(env, 2)
    before = snapshot(env.home, exclude=(env.trash,))
    plan, digest = env.plan("--categories", "user-cache")
    proc = _crash_apply(env, plan, digest, "rename", "before", 2, "python")
    assert proc.returncode == 9, proc.stderr
    assert sum(not d.exists() for d in dirs) == 1
    journal = next(env.plans.glob("*.journal-*.jsonl"))
    proc = env.run("restore", str(journal))
    assert proc.returncode == 0, proc.stdout
    assert "no llegó a moverse" in proc.stdout
    assert snapshot(env.home, exclude=(env.trash,)) == before
    assert not any((env.trash / "files").iterdir()) and not any((env.trash / "info").iterdir())


@pytest.mark.linux_only
def test_unwritable_journal_stops_apply_before_anything(env: Env) -> None:
    _cache_dirs(env, 2, with_trash=False)
    plan, digest = env.plan("--categories", "user-cache")
    before = snapshot(env.home)
    env.plans.chmod(0o555)
    try:
        proc = env.run("apply", str(plan), "--confirm", digest)
    finally:
        env.plans.chmod(0o755)
    assert proc.returncode == 1
    assert snapshot(env.home) == before
    assert not env.trash.exists()
