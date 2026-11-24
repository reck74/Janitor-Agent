"""Safety proof for the janitor-file-organizer skill (F3-02, AGENTS.md directive #19).

Runs the real script in a subprocess on a throwaway HOME under ``tmp_path`` with a
fake ``sudo`` first on PATH. Moves never overwrite, never leave the folder, and
``undo`` restores the exact original tree.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import subprocess
import sys
import time
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
SKILL_DIR = REPO_ROOT / "janitor" / "skills" / "system" / "janitor-file-organizer"
SCRIPT = SKILL_DIR / "scripts" / "janitor_organize.py"


class Env:
    def __init__(self, tmp_path: Path):
        tmp_path = tmp_path.resolve()
        self.root = tmp_path
        self.home = tmp_path / "home"
        self.agent = self.home / ".janitor"
        self.folder = self.home / "Downloads"
        self.bin = tmp_path / "fakebin"
        self.plans = tmp_path / "plans"
        self.sudo_log = tmp_path / "sudo.log"
        for d in (self.home, self.agent, self.folder, self.bin, self.plans):
            d.mkdir(parents=True, exist_ok=True)
        self.sudo_log.write_text("")
        sudo = self.bin / "sudo"
        sudo.write_text(f'#!/bin/sh\necho "sudo $*" >> "{self.sudo_log}"\nexit 1\n')
        sudo.chmod(0o755)
        git = next((os.path.join(d, "git") for d in ("/usr/bin", "/bin")
                    if os.path.exists(os.path.join(d, "git"))), None)
        if git:
            (self.bin / "git").symlink_to(git)
        self.vars = {
            "HOME": str(self.home), "XDG_DATA_HOME": str(self.home / ".local" / "share"),
            "HERMES_HOME": str(self.agent), "PATH": str(self.bin), "LANG": "C.UTF-8",
            "TZ": "UTC", "GIT_CONFIG_NOSYSTEM": "1",
        }

    def run(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True,
                              text=True, env=self.vars, timeout=120, check=False)

    def plan(self, *extra: str) -> tuple[Path, str]:
        out = self.plans / f"organize-{len(list(self.plans.glob('*.json')))}.json"
        proc = self.run("plan", str(self.folder), "--out", str(out), *extra)
        assert proc.returncode == 0, proc.stderr
        return out, digest_of(proc.stdout)

    def digest(self, plan: Path) -> str:
        proc = self.run("summary", str(plan))
        assert proc.returncode == 0, proc.stderr
        return digest_of(proc.stdout)


def digest_of(stdout: str) -> str:
    m = re.search(r"^DIGEST: ([0-9a-f]+)$", stdout, re.M)
    assert m, stdout
    return m.group(1)


def listing(root: Path) -> dict:
    """Byte-level listing: every path with its kind, content hash and file mtime."""
    out = {}
    for dirpath, dirnames, filenames in os.walk(root):
        for name in dirnames + filenames:
            p = Path(dirpath) / name
            st = os.lstat(p)
            rel = str(p.relative_to(root))
            if stat.S_ISLNK(st.st_mode):
                out[rel] = ("link", os.readlink(p))
            elif stat.S_ISDIR(st.st_mode):
                out[rel] = ("dir",)
            else:
                out[rel] = ("file", st.st_mtime_ns, hashlib.sha256(p.read_bytes()).hexdigest())
    return out


def _journal(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def _w(path: Path, data: bytes, mtime: float | None = None) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    if mtime is not None:
        os.utime(path, (mtime, mtime))
    return path


@pytest.fixture
def env(tmp_path: Path) -> Env:
    e = Env(tmp_path)
    f = e.folder
    _w(f / "report.pdf", b"new report")
    _w(f / "Documentos" / "report.pdf", b"older report already filed")
    _w(f / "photo.JPG", b"jpeg")
    _w(f / "song.flac", b"flac")
    _w(f / "tool.AppImage", b"elf")
    _w(f / "pkg-1.0-1-x86_64.pkg.tar.zst", b"zst")
    _w(f / "backup.tar.gz", b"tgz")
    _w(f / "data.csv", b"a,b")
    _w(f / "copy-of-report.pdf", b"new report")
    _w(f / "movie.mkv.part", b"partial")
    _w(f / ".hidden", b"dot")
    _w(f / "mystery", b"???")
    (f / "link-out").symlink_to("/etc/hostname")
    _w(f / "sub" / "notes.txt", b"notes", mtime=time.time() - 400 * 86400)
    _w(f / "repo" / "readme.md", b"in a repo")
    (f / "repo" / ".git").mkdir()
    _w(f / ".config-ish" / "x.pdf", b"hidden dir")
    return e


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


def test_script_is_executable() -> None:
    assert os.access(SCRIPT, os.X_OK)


# --------------------------------------------------------------------------- plan


@pytest.mark.linux_only
def test_plan_modifies_nothing(env: Env) -> None:
    before = listing(env.root)
    plan, _ = env.plan("--recursive")
    after = listing(env.root)
    for rel in list(after):
        if rel.startswith("plans"):
            del after[rel]
    before = {k: v for k, v in before.items() if not k.startswith("plans")}
    assert after == before
    data = json.loads(plan.read_text())
    srcs = {Path(e["src"]).name for e in data["entries"]}
    assert "movie.mkv.part" not in srcs and ".hidden" not in srcs and "link-out" not in srcs
    dups = [set(map(lambda p: Path(p).name, g["paths"])) for g in data["duplicates"]]
    assert {"report.pdf", "copy-of-report.pdf"} in dups
    dst = {Path(e["src"]).name: Path(e["dst"]).relative_to(env.folder) for e in data["entries"]}
    assert dst["photo.JPG"] == Path("Imagenes/photo.JPG")
    assert dst["pkg-1.0-1-x86_64.pkg.tar.zst"].parts[0] == "Instaladores"
    assert dst["backup.tar.gz"].parts[0] == "Comprimidos"
    assert env.sudo_log.read_text() == ""


@pytest.mark.linux_only
def test_recursive_never_enters_repos_or_hidden_dirs(env: Env) -> None:
    plan, _ = env.plan("--recursive")
    srcs = {e["src"] for e in json.loads(plan.read_text())["entries"]}
    assert str(env.folder / "sub" / "notes.txt") in srcs
    assert not any(s.startswith(str(env.folder / "repo") + "/") for s in srcs)
    assert not any(s.startswith(str(env.folder / ".config-ish") + "/") for s in srcs)
    flat, _ = env.plan()
    flat_srcs = {e["src"] for e in json.loads(flat.read_text())["entries"]}
    assert all(Path(s).parent == env.folder for s in flat_srcs)


# --------------------------------------------------------------------------- apply / undo


@pytest.mark.linux_only
def test_apply_requires_plan_and_digest(env: Env) -> None:
    before = listing(env.folder)
    assert env.run("apply").returncode != 0
    assert env.run("apply", str(env.plans / "nope.json"), "--confirm", "x").returncode != 0
    plan, _ = env.plan()
    assert env.run("apply", str(plan)).returncode != 0
    _, digest = env.plan()
    wrong = env.run("apply", str(plan), "--confirm", "0" * 16)
    assert wrong.returncode == 2
    assert digest not in wrong.stdout + wrong.stderr, "the error must not hand out the digest"
    assert digest in env.run("summary", str(plan)).stdout
    assert listing(env.folder) == before


@pytest.mark.linux_only
def test_collisions_never_overwrite_and_undo_restores_exact_tree(env: Env) -> None:
    before = listing(env.folder)
    plan, digest = env.plan("--recursive")
    # a collision that appears AFTER planning must not overwrite either
    _w(env.folder / "Imagenes" / "photo.JPG", b"appeared later")
    before_with_late = listing(env.folder)
    proc = env.run("apply", str(plan), "--confirm", digest)
    assert proc.returncode == 0, proc.stderr
    assert (env.folder / "Documentos" / "report.pdf").read_bytes() == b"older report already filed"
    assert (env.folder / "Documentos" / "report (2).pdf").read_bytes() == b"new report"
    assert (env.folder / "Imagenes" / "photo.JPG").read_bytes() == b"appeared later"
    assert (env.folder / "Imagenes" / "photo (2).JPG").read_bytes() == b"jpeg"
    assert not (env.folder / "report.pdf").exists()
    undo = plan.with_name(plan.stem + ".undo.jsonl")
    assert undo.is_file()
    # applying the same plan twice is refused
    assert env.run("apply", str(plan), "--confirm", digest).returncode == 2
    proc = env.run("undo", str(undo))
    assert proc.returncode == 0, proc.stdout
    assert listing(env.folder) == before_with_late
    (env.folder / "Imagenes" / "photo.JPG").unlink()
    (env.folder / "Imagenes").rmdir()
    assert listing(env.folder) == before
    assert env.sudo_log.read_text() == ""


@pytest.mark.linux_only
def test_hand_edited_or_changed_entries_are_skipped(env: Env) -> None:
    outside = env.root / "outside"
    outside.mkdir()
    (env.folder / "escape").symlink_to(outside)
    (env.home / ".ssh").mkdir()
    plan, _ = env.plan()
    data = json.loads(plan.read_text())
    by_name = {Path(e["src"]).name: e for e in data["entries"]}
    by_name["photo.JPG"]["dst"] = str(outside / "photo.JPG")
    by_name["song.flac"]["dst"] = str(env.home / ".ssh" / "song.flac")
    by_name["data.csv"]["dst"] = str(env.folder / "escape" / "data.csv")
    by_name["mystery"]["dst"] = str(env.folder / ".." / "mystery")
    by_name["tool.AppImage"]["src"] = "/etc/hostname"
    plan.write_text(json.dumps(data))
    (env.folder / "backup.tar.gz").write_bytes(b"changed after plan")
    proc = env.run("apply", str(plan), "--confirm", env.digest(plan))
    assert proc.returncode == 0, proc.stderr
    for name in ("photo.JPG", "song.flac", "data.csv", "mystery", "backup.tar.gz"):
        assert (env.folder / name).exists(), name
    assert not any(outside.iterdir())
    assert not (env.home / ".ssh" / "song.flac").exists()
    assert (env.folder / "Documentos" / "report (2).pdf").exists(), "valid entries still apply"
    records = _journal(plan.with_name(plan.stem + ".undo.jsonl"))
    skipped = {Path(r["src"]).name for r in records if r.get("op") == "skip"}
    assert {"photo.JPG", "song.flac", "data.csv", "mystery", "backup.tar.gz",
            "hostname"} <= skipped

    data["roots"] = ["/"]
    plan.write_text(json.dumps(data))
    assert env.run("apply", str(plan), "--confirm", env.digest(plan)).returncode == 2


@pytest.mark.linux_only
def test_refuses_whole_home_and_agent_home(env: Env) -> None:
    assert env.run("plan", str(env.home), "--out", str(env.plans / "h.json")).returncode == 2
    assert env.run("plan", str(env.agent), "--out", str(env.plans / "a.json")).returncode == 2
    assert env.run("plan", "/etc", "--out", str(env.plans / "e.json")).returncode == 2


# --------------------------------------------------------------------------- crash safety

CRASH_DRIVER = """
import os, sys
sys.path.insert(0, sys.argv[1])
import janitor_fs_safety as fs
import janitor_organize as m
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
    real_append = fs.Journal.append
    def failing(self, record):
        calls[0] += 1
        if calls[0] >= n:
            raise fs.JournalError("disco lleno (simulado)")
        real_append(self, record)
    fs.Journal.append = failing
sys.exit(m.main(sys.argv[5:]))
"""


def _crash_apply(env: Env, plan: Path, digest: str, target: str, mode: str,
                 n: int) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-c", CRASH_DRIVER, str(SCRIPT.parent), target, mode, str(n),
         "apply", str(plan), "--confirm", digest],
        capture_output=True, text=True, env=env.vars, timeout=120, check=False)


@pytest.mark.linux_only
@pytest.mark.parametrize("mode", ["after", "before"])
def test_killed_apply_is_fully_undoable(env: Env, mode: str) -> None:
    before = listing(env.folder)
    plan, digest = env.plan("--recursive")
    proc = _crash_apply(env, plan, digest, "rename", mode, 3)
    assert proc.returncode == 9, proc.stderr
    assert listing(env.folder) != before, "some moves happened before the kill"
    undo = plan.with_name(plan.stem + ".undo.jsonl")
    records = _journal(undo)
    outcomes = {r["seq"] for r in records if r.get("state") in ("done", "failed")}
    hanging = [r for r in records if r.get("state") == "pending" and r["seq"] not in outcomes]
    assert len(hanging) == 1 and hanging[0]["op"] == "move"
    src_there = Path(hanging[0]["src"]).exists()
    assert src_there == (mode == "before")
    proc = env.run("undo", str(undo))
    assert proc.returncode == 0, proc.stdout
    assert listing(env.folder) == before
    # undo is idempotent
    assert env.run("undo", str(undo)).returncode == 0
    assert listing(env.folder) == before


@pytest.mark.linux_only
def test_journal_failure_stops_apply_before_the_next_move(env: Env) -> None:
    before = listing(env.folder)
    plan, digest = env.plan()
    proc = _crash_apply(env, plan, digest, "append", "", 6)
    assert proc.returncode == 1
    assert "DETENIDO" in proc.stderr
    undo = plan.with_name(plan.stem + ".undo.jsonl")
    records = _journal(undo)
    journaled = {r["src"] for r in records if r.get("op") == "move"}
    for rel, kind in before.items():
        p = env.folder / rel
        if kind[0] == "file" and not os.path.lexists(p):
            assert str(p) in journaled, f"{rel} moved without a journal record"
    assert env.run("undo", str(undo)).returncode == 0
    assert listing(env.folder) == before


@pytest.mark.linux_only
def test_unwritable_journal_moves_nothing(env: Env) -> None:
    before = listing(env.folder)
    plan, digest = env.plan()
    env.plans.chmod(0o555)
    try:
        proc = env.run("apply", str(plan), "--confirm", digest)
    finally:
        env.plans.chmod(0o755)
    assert proc.returncode == 1
    assert listing(env.folder) == before


@pytest.mark.linux_only
def test_undo_never_overwrites_a_reoccupied_original_path(env: Env) -> None:
    plan, digest = env.plan()
    assert env.run("apply", str(plan), "--confirm", digest).returncode == 0
    _w(env.folder / "photo.JPG", b"new file the user saved later")
    proc = env.run("undo", str(plan.with_name(plan.stem + ".undo.jsonl")))
    assert proc.returncode == 1
    assert "ocupada" in proc.stdout
    assert (env.folder / "photo.JPG").read_bytes() == b"new file the user saved later"
    assert (env.folder / "Imagenes" / "photo.JPG").read_bytes() == b"jpeg"
    assert (env.folder / "report.pdf").read_bytes() == b"new report", "others restored"
