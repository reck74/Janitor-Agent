"""Who holds the SQLite write lock on state.db right now (Linux ``/proc/locks``).

The "database is locked for over Ns" failure names the victim but not the holder, and the
open-descriptor scan (``hermes_state_holders``) cannot tell a reader from the one writer: every
Hermes process has the DB open. SQLite's unix VFS takes ``fcntl`` byte-range locks whose offsets
encode the lock kind, and the kernel exports them with the owning pid, so the holder can be named
at the moment the deadline passes.
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from typing import Dict, List, Tuple

logger = logging.getLogger(__name__)

# sqlite/src/os_unix.c: UNIX_SHM_BASE = (22 + SQLITE_SHM_NLOCK) * 4 = 120; WAL lock i sits at BASE + i.
_SHM_LOCK_NAMES = {
    120: "WAL write",
    121: "WAL checkpoint",
    122: "WAL recover",
    128: "shm dead-man switch",
}
# Rollback-journal / exclusive locks on the main file live in the pending-byte page (1 GiB).
_PENDING_BYTE = 0x40000000
_MAIN_LOCK_NAMES = {
    _PENDING_BYTE: "PENDING",
    _PENDING_BYTE + 1: "RESERVED",
}


def _describe_range(sidecar: str, start: int, end: int) -> str:
    if sidecar == "-shm":
        if start in _SHM_LOCK_NAMES and end == start:
            return _SHM_LOCK_NAMES[start]
        if 123 <= start <= 127 and end == start:
            return f"WAL read slot {start - 123}"
        return f"shm bytes {start}-{end}"
    if start == end and start in _MAIN_LOCK_NAMES:
        return _MAIN_LOCK_NAMES[start]
    if start == _PENDING_BYTE + 2:
        return "SHARED range"
    return f"db bytes {start}-{end}"


def _write_lock_fields(line: str) -> tuple[int, tuple[int, int], int, int] | None:
    fields = line.split()
    # "N: POSIX ADVISORY WRITE <pid> MAJ:MIN:INO <start> <end|EOF>"; skip blocked waiters.
    if len(fields) < 8 or fields[1] == "->" or fields[3] != "WRITE":
        return None
    try:
        major, minor, inode = fields[5].split(":")
        key = (os.makedev(int(major, 16), int(minor, 16)), int(inode))
        start = int(fields[6])
        end = start if fields[7] == "EOF" else int(fields[7])
        return int(fields[4]), key, start, end
    except ValueError:
        return None


def parse_proc_locks(text: str, inodes: dict[tuple[int, int], str]) -> list[tuple[int, str, str]]:
    """``(pid, lock kind, sidecar)`` for every WRITE lock on one of ``inodes``.

    ``inodes`` maps ``(st_dev, st_ino)`` to ``""`` (main file), ``"-wal"`` or ``"-shm"``. Read locks
    are dropped: they never block a writer in WAL mode. An OFD lock is reported with pid ``-1``
    (the kernel does not export its owner).
    """
    found: list[tuple[int, str, str]] = []
    for line in text.splitlines():
        record = _write_lock_fields(line)
        if record is None:
            continue
        pid, key, start, end = record
        sidecar = inodes.get(key)
        if sidecar is not None:
            found.append((pid, _describe_range(sidecar, start, end), sidecar))
    return found


def _verified_fd_write_locks(pid: int, inodes: dict[tuple[int, int], str]) -> list[tuple[int, str, str]]:
    """Read locks only from FDs whose stat identity matches our SQLite generation.

    Btrfs exports its superblock device in /proc/locks but the subvolume device in stat().
    fdinfo attaches each lock to its descriptor, so equal inodes on other subvolumes cannot
    borrow an open descriptor for our file as proof. Never open the DB itself: closing it
    would release this process's POSIX locks on that file.
    """
    try:
        fds = os.listdir(f"/proc/{pid}/fd")
    except OSError:
        return []
    held: list[tuple[int, str, str]] = []
    for fd in fds:
        fd_path = f"/proc/{pid}/fd/{fd}"
        try:
            before = os.stat(fd_path)
            key = (before.st_dev, before.st_ino)
            sidecar = inodes.get(key)
            if sidecar is None:
                continue
            with open(f"/proc/{pid}/fdinfo/{fd}", encoding="ascii", errors="replace") as handle:
                info = handle.read()
            after = os.stat(fd_path)
        except OSError:
            continue
        if key != (after.st_dev, after.st_ino):
            continue  # descriptor closed/reused during the read
        for line in info.splitlines():
            if not line.startswith("lock:"):
                continue
            record = _write_lock_fields(line.removeprefix("lock:").lstrip())
            if record is None:
                continue
            owner, kernel_key, start, end = record
            if owner == pid and kernel_key[1] == before.st_ino:
                held.append((pid, _describe_range(sidecar, start, end), sidecar))
    return held


def _device_alias_write_locks(text: str, inodes: dict[tuple[int, int], str]) -> list[tuple[int, str, str]]:
    """Verify possible device aliases without treating an inode match alone as ownership."""
    watched_inodes = {inode for _, inode in inodes}
    candidates = set()
    for line in text.splitlines():
        record = _write_lock_fields(line)
        if record is not None:
            pid, key, _, _ = record
            if pid > 0 and key not in inodes and key[1] in watched_inodes:
                candidates.add(pid)
    return [entry for pid in sorted(candidates) for entry in _verified_fd_write_locks(pid, inodes)]


def state_db_write_lock_holders(db_path) -> list[str]:
    """Operator-facing lines naming the processes that hold a write-class lock on ``db_path``.

    Empty when nothing is held or the platform has no ``/proc/locks``.
    """
    if not sys.platform.startswith("linux"):
        return []
    base = os.path.realpath(os.fspath(db_path))
    inodes: dict[tuple[int, int], str] = {}
    for sidecar in ("", "-wal", "-shm"):
        try:
            st = os.stat(base + sidecar)
        except OSError:
            continue
        inodes[(st.st_dev, st.st_ino)] = sidecar
    # /proc/locks is host-wide and served over several read()s: lock churn in other processes
    # shifts it mid-read and can skip the holder. A skip rarely repeats, so union three passes.
    held: list[tuple[int, str, str]] = []
    for _ in range(3):
        try:
            with open("/proc/locks", encoding="ascii", errors="replace") as handle:
                text = handle.read()
        except OSError:
            return []
        entries = parse_proc_locks(text, inodes) + _device_alias_write_locks(text, inodes)
        held.extend(entry for entry in entries if entry not in held)
    from hermes_state_holders import describe_holder_pid

    lines = []
    for pid, kind, sidecar in held:
        who = describe_holder_pid(pid) if pid > 0 else "OFD lock, owner pid not exported by the kernel"
        lines.append(f"{who} holds {kind} lock on {Path(base + sidecar).name}")
    return lines


def log_write_lock_holders(db_path, patience_s: float) -> None:
    """One WARNING naming the write-lock holders at the moment a writer gave up waiting."""
    holders = state_db_write_lock_holders(db_path)
    if holders:
        detail = " | ".join(holders)
    else:
        detail = "no write-class lock held at the deadline (the holder released just before it)"
    logger.warning(
        "state.db write lock unavailable for %.0fs (%s): %s", patience_s, Path(db_path).name, detail
    )
