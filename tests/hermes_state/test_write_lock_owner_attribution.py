"""Regression: a state.db write-lock timeout names the process holding the lock.

Before, ``database is locked (another Hermes process held the state.db write lock for over 60s)``
identified the victim only; every Hermes process has the DB open, so the descriptor scan could not
single out the writer. ``/proc/locks`` can.
"""

import io
import os
import sqlite3
import subprocess
import sys
import textwrap
import time

import pytest

from hermes_state_lockowners import parse_proc_locks, state_db_write_lock_holders


def test_parse_proc_locks_keeps_only_write_locks_on_our_inodes_and_decodes_the_wal_write_byte():
    inodes = {(os.makedev(0x103, 0x02), 4194737): "-shm", (os.makedev(0x103, 0x02), 4228330): ""}
    text = textwrap.dedent("""\
        1: POSIX  ADVISORY  WRITE 594094 103:02:4194737 120 120
        2: POSIX  ADVISORY  READ 594094 103:02:4194737 125 125
        3: POSIX  ADVISORY  READ 99493 103:02:4194737 128 128
        4: OFDLCK ADVISORY  WRITE -1 103:02:4228330 1073741825 1073741825
        5: POSIX  ADVISORY  WRITE 4242 103:02:99999 120 120
        6: -> POSIX  ADVISORY  WRITE 777 103:02:4194737 120 120
    """)
    assert parse_proc_locks(text, inodes) == [
        (594094, "WAL write", "-shm"),
        (-1, "RESERVED", ""),
    ]


@pytest.mark.platforms("linux")
def test_holder_skipped_by_one_proc_locks_pass_is_still_named(tmp_path, monkeypatch):
    """/proc/locks is served over several read()s, so churn elsewhere can skip an entry in one pass."""
    import hermes_state_lockowners

    db = tmp_path / "state.db"
    db.write_bytes(b"")
    st = os.stat(db)
    held = (f"1: POSIX  ADVISORY  WRITE {os.getpid()} "
            f"{os.major(st.st_dev):02x}:{os.minor(st.st_dev):02x}:{st.st_ino} 1073741825 1073741825\n")
    passes = iter(["", held, ""])
    monkeypatch.setattr(hermes_state_lockowners, "open", lambda *a, **k: io.StringIO(next(passes)), raising=False)
    lines = state_db_write_lock_holders(db)
    assert len(lines) == 1 and f"PID {os.getpid()} " in lines[0] and "RESERVED" in lines[0], lines


@pytest.mark.platforms("linux")
def test_live_writer_in_another_process_is_named_by_pid(tmp_path):
    db = tmp_path / "state.db"
    conn = sqlite3.connect(db)
    conn.execute("PRAGMA journal_mode=wal")
    conn.execute("CREATE TABLE t(x)")
    conn.commit()
    conn.close()

    holder = subprocess.Popen(
        [sys.executable, "-c", textwrap.dedent(f"""
            import sqlite3, sys, time
            c = sqlite3.connect({str(db)!r}, isolation_level=None)
            c.execute("BEGIN IMMEDIATE")
            c.execute("INSERT INTO t VALUES (1)")
            print("held", flush=True)
            time.sleep(30)
        """)],
        stdout=subprocess.PIPE, text=True,
    )
    try:
        assert holder.stdout.readline().strip() == "held"
        deadline = time.monotonic() + 5
        lines = []
        while time.monotonic() < deadline:
            lines = state_db_write_lock_holders(db)
            if lines:
                break
            time.sleep(0.05)
        assert any(f"PID {holder.pid} " in line and "WAL write" in line for line in lines), lines
    finally:
        holder.kill()
        holder.wait()
    assert state_db_write_lock_holders(db) == []


@pytest.mark.platforms("linux")
@pytest.mark.parametrize("fd_device,fd_inode,fd_lock,expected", [
    (31, 73, "1: POSIX ADVISORY WRITE 4242 00:1d:73 120 120", True),
    (32, 73, "1: POSIX ADVISORY WRITE 4242 00:1d:73 120 120", False),
    (31, 74, "1: POSIX ADVISORY WRITE 4242 00:1d:73 120 120", False),
    (31, 73, "", False),
    (31, 73, "1: POSIX ADVISORY READ 4242 00:1d:73 120 120", False),
    (31, 73, "1: POSIX ADVISORY WRITE 9999 00:1d:73 120 120", False),
])
def test_device_alias_requires_exact_file_identity_and_its_fd_lock(
    tmp_path, monkeypatch, fd_device, fd_inode, fd_lock, expected,
):
    """Btrfs subvolume st_dev differs from /proc/locks; inode alone is not authority."""
    from types import SimpleNamespace
    import hermes_state_holders
    import hermes_state_lockowners as owners

    db = tmp_path / "state.db"
    child_fd = "/proc/4242/fd/9"
    lock = "1: POSIX ADVISORY WRITE 4242 00:1d:73 120 120\n"
    real_stat = os.stat

    def stat(path, *args, **kwargs):
        if str(path) == str(db) + "-shm":
            return SimpleNamespace(st_dev=os.makedev(0, 31), st_ino=73)
        if str(path) == child_fd:
            return SimpleNamespace(st_dev=os.makedev(0, fd_device), st_ino=fd_inode)
        return real_stat(path, *args, **kwargs)

    def opened(path, *args, **kwargs):
        if str(path) == "/proc/locks":
            return io.StringIO(lock)
        if str(path) == "/proc/4242/fdinfo/9":
            return io.StringIO("pos: 0\nino: 73\n" + ("lock: " + fd_lock if fd_lock else ""))
        raise AssertionError(f"unexpected open: {path}")

    monkeypatch.setattr(owners.os, "stat", stat)
    monkeypatch.setattr(owners.os, "listdir", lambda path: ["9"] if str(path) == "/proc/4242/fd" else [])
    monkeypatch.setattr(owners, "open", opened, raising=False)
    monkeypatch.setattr(hermes_state_holders, "describe_holder_pid", lambda pid: f"PID {pid} (fixture)")
    lines = owners.state_db_write_lock_holders(db)
    assert lines == (["PID 4242 (fixture) holds WAL write lock on state.db-shm"] if expected else [])


@pytest.mark.platforms("linux")
def test_device_alias_does_not_borrow_another_descriptor_lock(tmp_path, monkeypatch):
    """A process may read our file and write another subvolume's equal inode."""
    from types import SimpleNamespace
    import hermes_state_lockowners as owners

    db = tmp_path / "state.db"
    real_stat = os.stat

    def stat(path, *args, **kwargs):
        path = str(path)
        if path in (str(db) + "-shm", "/proc/4242/fd/8"):
            return SimpleNamespace(st_dev=os.makedev(0, 31), st_ino=73)
        if path == "/proc/4242/fd/9":
            return SimpleNamespace(st_dev=os.makedev(0, 32), st_ino=73)
        return real_stat(path, *args, **kwargs)

    def opened(path, *args, **kwargs):
        if str(path) == "/proc/locks":
            return io.StringIO("1: POSIX ADVISORY WRITE 4242 00:1d:73 120 120\n")
        if str(path) == "/proc/4242/fdinfo/8":
            return io.StringIO("pos: 0\nino: 73\n")
        raise AssertionError(f"unverified descriptor must not be read: {path}")

    monkeypatch.setattr(owners.os, "stat", stat)
    monkeypatch.setattr(owners.os, "listdir", lambda path: ["8", "9"])
    monkeypatch.setattr(owners, "open", opened, raising=False)
    assert owners.state_db_write_lock_holders(db) == []


@pytest.mark.platforms("linux")
@pytest.mark.parametrize("failure", ["listdir", "stat", "fdinfo", "reused_fd"])
def test_device_alias_inaccessible_or_reused_descriptor_is_not_attributed(tmp_path, monkeypatch, failure):
    from types import SimpleNamespace
    import hermes_state_lockowners as owners

    db = tmp_path / "state.db"
    real_stat = os.stat
    reads = 0

    def stat(path, *args, **kwargs):
        nonlocal reads
        if str(path) == str(db) + "-shm":
            return SimpleNamespace(st_dev=os.makedev(0, 31), st_ino=73)
        if str(path) == "/proc/4242/fd/9":
            if failure == "stat":
                raise PermissionError("fd hidden")
            reads += 1
            return SimpleNamespace(st_dev=os.makedev(0, 31), st_ino=74 if failure == "reused_fd" and reads > 1 else 73)
        return real_stat(path, *args, **kwargs)

    def listdir(path):
        if failure == "listdir":
            raise PermissionError("process hidden")
        return ["9"]

    def opened(path, *args, **kwargs):
        if str(path) == "/proc/locks":
            return io.StringIO("1: POSIX ADVISORY WRITE 4242 00:1d:73 120 120\n")
        if str(path) == "/proc/4242/fdinfo/9":
            if failure == "fdinfo":
                raise PermissionError("lock hidden")
            return io.StringIO("lock: 1: POSIX ADVISORY WRITE 4242 00:1d:73 120 120\n")
        raise AssertionError(f"unexpected open: {path}")

    monkeypatch.setattr(owners.os, "stat", stat)
    monkeypatch.setattr(owners.os, "listdir", listdir)
    monkeypatch.setattr(owners, "open", opened, raising=False)
    assert owners.state_db_write_lock_holders(db) == []
