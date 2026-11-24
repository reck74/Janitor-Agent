"""Behaviour tests for the janitor-system-health skill (F3-03).

The audit script must be read-only, survive missing tools, and keep its logic in pure
functions that classify data passed in. Run with:
    scripts/run_tests.sh tests/janitor/test_janitor_system_health.py
"""
from __future__ import annotations

import importlib.util
import json
import os
import re
import stat
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
SKILL_DIR = REPO_ROOT / "janitor" / "skills" / "system" / "janitor-system-health"
SCRIPT = SKILL_DIR / "scripts" / "system_health.py"
SEVERITIES = {"critical", "high", "medium", "low", "info"}
FINDING_FIELDS = {"id", "probe", "severity", "area", "title", "evidence", "suggested_fix",
                  "requires_privileges"}


def _load_module():
    previous = sys.dont_write_bytecode
    sys.dont_write_bytecode = True  # never drop __pycache__ into the skill tree
    try:
        spec = importlib.util.spec_from_file_location("janitor_system_health", SCRIPT)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        sys.dont_write_bytecode = previous


sh = _load_module()


def _frontmatter(skill_md: Path) -> dict:
    text = skill_md.read_text(encoding="utf-8")
    m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    assert m, f"{skill_md} has no YAML frontmatter"
    return yaml.safe_load(m.group(1))


def _assert_valid_report(doc: dict) -> None:
    assert doc["schema_version"] == sh.SCHEMA_VERSION
    assert set(doc["summary"]) == SEVERITIES
    assert sum(doc["summary"].values()) == len(doc["findings"])
    for f in doc["findings"]:
        assert FINDING_FIELDS <= set(f), f
        assert f["severity"] in SEVERITIES
        assert f["id"].startswith(f["probe"] + ":")
        assert f["probe"] in doc["probes"]
        assert isinstance(f["requires_privileges"], bool)
        assert f["title"] and f["suggested_fix"]
    ranks = [sh.SEVERITY_RANK[f["severity"]] for f in doc["findings"]]
    assert ranks == sorted(ranks), "findings must be ordered most severe first"
    for s in doc["skipped"]:
        assert s["probe"] and s["reason"]
    assert set(doc["probes"].values()) <= {"ok", "skipped", "error"}


def _run(env: dict, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True,
                          env=env, timeout=300)


def _snapshot(root: Path) -> dict:
    out = {}
    for dirpath, dirnames, filenames in os.walk(root):
        for name in dirnames + filenames:
            p = Path(dirpath) / name
            st = p.lstat()
            out[str(p.relative_to(root))] = (st.st_size, st.st_mtime_ns, st.st_mode)
    return out


@pytest.fixture
def fake_home(tmp_path: Path) -> Path:
    home = tmp_path / "home"
    (home / ".ssh").mkdir(parents=True)
    (home / ".ssh").chmod(0o700)
    key = home / ".ssh" / "id_test"
    key.write_text("-----BEGIN OPENSSH PRIVATE KEY-----\nAAAA\n-----END OPENSSH PRIVATE KEY-----\n")
    key.chmod(0o644)  # deliberately too open
    (home / ".ssh" / "id_test.pub").write_text("ssh-ed25519 AAAA test\n")
    (home / ".config" / "app").mkdir(parents=True)
    (home / ".config" / "app" / "settings.ini").write_text("x=1\n")
    (home / ".cache" / "thing").mkdir(parents=True)
    (home / ".cache" / "thing" / "blob").write_bytes(b"0" * 4096)
    (home / ".bashrc").write_text("export X=1\n")
    return home


# --- frontmatter -----------------------------------------------------------------------------

def test_frontmatter_follows_authoring_standards():
    fm = _frontmatter(SKILL_DIR / "SKILL.md")
    assert fm["name"] == SKILL_DIR.name
    assert len(fm["description"]) <= 60 and fm["description"].endswith(".")
    assert fm["platforms"] == ["linux"]
    assert fm["license"] and fm["author"] and fm["version"]
    hermes = fm["metadata"]["hermes"]
    assert hermes["tags"] and hermes["category"]


@pytest.mark.linux_only  # the executable bit does not exist on Windows
def test_script_is_executable():
    assert SCRIPT.stat().st_mode & stat.S_IXUSR


# --- end to end on this host -------------------------------------------------------------------

@pytest.mark.linux_only
def test_full_audit_emits_valid_report_without_writes_or_sudo(tmp_path, fake_home):
    fake_bin = tmp_path / "fakebin"
    fake_bin.mkdir()
    record = tmp_path / "sudo-calls"
    sudo = fake_bin / "sudo"
    sudo.write_text(f"#!/bin/sh\necho \"$@\" >> '{record}'\nexit 1\n")
    sudo.chmod(0o755)
    env = dict(os.environ, HOME=str(fake_home), PATH=f"{fake_bin}{os.pathsep}{os.environ.get('PATH', '')}")
    env.pop("HERMES_REAL_HOME", None)
    before = _snapshot(tmp_path)
    out = tmp_path / "out" / "report.json"

    proc = _run(env, "--home-budget", "5", "--output", str(out))

    assert proc.returncode == 0, proc.stderr
    doc = json.loads(proc.stdout)
    _assert_valid_report(doc)
    assert "error" not in doc["probes"].values(), doc["skipped"]
    assert json.loads(out.read_text()) == doc
    assert not record.exists(), f"sudo was invoked: {record.read_text()}"
    after = _snapshot(tmp_path)
    created = set(after) - set(before)
    assert created == {"out", "out/report.json"}, created
    assert {k: v for k, v in after.items() if k in before} == before
    ids = {f["id"] for f in doc["findings"]}
    assert "permissions:private_key:~/.ssh/id_test" in ids


@pytest.mark.linux_only
def test_missing_tools_are_skipped_not_fatal(tmp_path, fake_home):
    empty_bin = tmp_path / "bin"
    empty_bin.mkdir()
    env = dict(os.environ, HOME=str(fake_home), PATH=str(empty_bin))
    env.pop("HERMES_REAL_HOME", None)

    proc = _run(env, "--home-budget", "2")

    assert proc.returncode == 0, proc.stderr
    doc = json.loads(proc.stdout)
    _assert_valid_report(doc)
    skipped = {s["probe"] for s in doc["skipped"]}
    for probe in ("disk", "systemd_units", "listening_ports", "docker", "smart", "updates", "time_sync"):
        assert probe in skipped, probe
        assert doc["probes"][probe] == "skipped"
    assert "error" not in doc["probes"].values(), doc["skipped"]
    assert doc["probes"]["memory"] == "ok"  # /proc needs no tool


def test_unknown_probe_is_a_usage_error():
    proc = _run(dict(os.environ), "--only", "nope")
    assert proc.returncode != 0


# --- pure classifiers ------------------------------------------------------------------------

DF = """Filesystem     Type  1024-blocks      Used Available Capacity Mounted on
/dev/mapper/root btrfs  1000000    960000     40000      96% /
/dev/mapper/root btrfs  1000000    960000     40000      96% /home
tmpfs          tmpfs       1000       999         1     100% /run/user/1000
/dev/sdb1      ext4      100000     50000     50000      50% /data
/dev/sdc1      xfs       100000     91000      9000      91% /mnt/backup disk
"""


def test_df_flags_full_devices_once_and_ignores_pseudo_fs():
    findings = {f["id"]: f for f in sh.classify_df(DF, "space")}
    assert set(findings) == {"disk:space:/", "disk:space:/mnt/backup disk"}
    assert findings["disk:space:/"]["severity"] == "critical"
    assert "/home" in findings["disk:space:/"]["evidence"]
    assert findings["disk:space:/mnt/backup disk"]["severity"] == "high"
    assert all(f["id"].startswith("disk:inodes:") for f in sh.classify_df(DF, "inodes"))


def test_memory_pressure_thresholds():
    low = sh.classify_memory({"MemTotal": 1000, "MemAvailable": 50, "SwapTotal": 100, "SwapFree": 10},
                             {"full_avg60": 25.0})
    assert {f["id"]: f["severity"] for f in low} == {
        "memory:available": "high", "memory:swap": "high", "memory:pressure": "high"}
    assert sh.classify_memory({"MemTotal": 1000, "MemAvailable": 600, "SwapTotal": 0}) == []
    assert sh.parse_meminfo("MemTotal:       16000 kB\nMemAvailable:    8000 kB\n") == {
        "MemTotal": 16000, "MemAvailable": 8000}


SSHD_MAIN = """# comment
Include /etc/ssh/sshd_config.d/*.conf
PasswordAuthentication yes
PermitRootLogin yes
Match User backup
    PasswordAuthentication no
"""


def test_sshd_config_first_value_wins_and_includes_come_first():
    settings = sh.parse_sshd_config(SSHD_MAIN, lambda pattern: ["PasswordAuthentication no\n"])
    assert settings["passwordauthentication"] == "no"
    assert settings["permitrootlogin"] == "yes"
    verdict = {f["id"]: f["severity"] for f in sh.ssh_verdict(settings, True, True, "test")}
    assert verdict == {"ssh:password-auth": "high", "ssh:root-login": "high"}  # kbd-interactive default yes


def test_ssh_verdict_hardened_running_and_unknown():
    hardened = {"passwordauthentication": "no", "kbdinteractiveauthentication": "no",
                "permitrootlogin": "no"}
    assert sh.ssh_verdict(hardened, True, True, "sshd -T") == []
    assert sh.ssh_verdict({"passwordauthentication": "yes"}, False, True, "x") == []
    unknown = sh.ssh_verdict({}, True, True, "")
    assert [f["id"] for f in unknown] == ["ssh:config-unknown"] and unknown[0]["requires_privileges"]
    assert sh.parse_sshd_t("passwordauthentication no\npermitrootlogin without-password\n") == {
        "passwordauthentication": "no", "permitrootlogin": "without-password"}


SS = """tcp LISTEN 0 4096 0.0.0.0:8080 0.0.0.0:* users:(("python3",pid=10,fd=3))
tcp LISTEN 0 4096 127.0.0.1:5432 0.0.0.0:* users:(("postgres",pid=11,fd=3))
udp UNCONN 0 0 0.0.0.0:41000 0.0.0.0:* users:(("spotify",pid=12,fd=9))
udp UNCONN 0 0 0.0.0.0:5353 0.0.0.0:* users:(("spotify",pid=12,fd=10))
tcp LISTEN 0 128 [::]:22 [::]:*
"""


def test_listeners_grouped_per_process_and_loopback_ignored():
    rows = sh.parse_ss(SS)
    with_fw = {f["id"]: f for f in sh.classify_listeners(rows, True)}
    assert set(with_fw) == {"listening_ports:python3", "listening_ports:spotify", "listening_ports:tcp-22"}
    assert with_fw["listening_ports:python3"]["severity"] == "medium"
    assert with_fw["listening_ports:spotify"]["severity"] == "low"
    assert with_fw["listening_ports:tcp-22"]["requires_privileges"] is True
    no_fw = {f["id"]: f["severity"] for f in sh.classify_listeners(rows, False)}
    assert no_fw["listening_ports:python3"] == "high"
    assert no_fw["listening_ports:spotify"] == "medium"


def test_firewall_classification():
    assert sh.classify_firewall({"ufw": "active", "nftables": "inactive"}) == (True, [])
    active, findings = sh.classify_firewall({"ufw": "inactive", "nftables": None})
    assert active is False and findings[0]["id"] == "firewall:inactive"
    active, findings = sh.classify_firewall({"ufw": None, "firewalld": None})
    assert active is None and findings[0]["severity"] == "high"


def test_restart_loops_and_fs_errors_from_journal_text():
    msgs = ["foo.service: Scheduled restart job, restart counter is at 2.",
            "foo.service: Scheduled restart job, restart counter is at 7.",
            "bar.service: Started bar."]
    assert sh.parse_restart_counters(msgs) == {"foo.service": 7}
    kernel = ["blk_update_request: I/O error, dev sda, sector 123"] * 12 + ["usb 1-1: new device"]
    findings = sh.classify_fs_errors(kernel)
    assert [(f["id"], f["severity"]) for f in findings] == [("fs_errors:io", "critical")]
    assert sh.classify_fs_errors(["usb 1-1: new device"]) == []


def test_package_parsers_and_update_findings():
    apt = ("Listing...\nopenssl/jammy-security 3.0.2-0ubuntu1.15 amd64 [upgradable from: 3.0.2-0ubuntu1.14]\n"
           "vim/jammy-updates 2:8.2 amd64 [upgradable from: 2:8.1]\n")
    assert sh.parse_apt_upgradable(apt) == (2, 1)
    assert sh.parse_pacman_qu("linux 6.1-1 -> 6.2-1\nfoo 1-1 -> 2-1 [ignored]\n") == 1
    assert sh.parse_dnf_check_update("\nkernel.x86_64  6.5.1-1.fc39  updates\nvim.x86_64 2:9.0 updates\n") == 2
    ids = {f["id"]: f for f in sh.classify_updates("apt", 2, 1, True, 10)}
    assert ids["updates:security"]["severity"] == "high"
    assert {"updates:pending", "updates:reboot-required", "updates:stale-metadata"} <= set(ids)
    assert sh.classify_updates("pacman", 0, None, False, 1) == []


def test_docker_reclaimable_and_volume_caution():
    lines = [
        json.dumps({"Type": "Images", "TotalCount": "20", "Active": "5", "Size": "30GB",
                    "Reclaimable": "12.5GB (41%)"}),
        json.dumps({"Type": "Local Volumes", "TotalCount": "9", "Active": "2", "Size": "8GB",
                    "Reclaimable": "3GB (37%)"}),
        json.dumps({"Type": "Build Cache", "TotalCount": "3", "Active": "0", "Size": "100MB",
                    "Reclaimable": "100MB"}),
    ]
    findings = {f["id"]: f for f in sh.classify_docker_df(lines)}
    assert findings["docker:reclaimable:images"]["severity"] == "medium"
    assert "prune" not in findings["docker:reclaimable:local-volumes"]["suggested_fix"]
    assert "docker:reclaimable:build-cache" not in findings
    assert sh.parse_size("1.5kB") == 1500 and sh.parse_size("0B") == 0


def test_backup_verdicts():
    assert sh.backup_verdict([], [])[0]["id"] == "backups:none"
    assert sh.backup_verdict([], [])[0]["severity"] == "high"
    assert sh.backup_verdict([], ["restic"])[0]["id"] == "backups:unscheduled"
    snaps = sh.backup_verdict(["snapper: configuraciones root", "existe /.snapshots (snapshots btrfs)"], [])
    assert snaps[0]["id"] == "backups:snapshots-only" and snaps[0]["severity"] == "medium"
    real = sh.backup_verdict(["timer: borgmatic.timer borgmatic.service"], ["borg"])
    assert real[0]["severity"] == "info"


def test_permission_modes_and_smart_parsing():
    assert sh.classify_mode("private_key", 0o100644) == "high"
    assert sh.classify_mode("private_key", 0o100600) is None
    assert sh.classify_mode("ssh_dir", 0o040777) == "high"
    assert sh.classify_mode("ssh_dir", 0o040755) == "low"
    assert sh.classify_mode("sensitive", 0o100666) == "high"
    assert sh.looks_like_private_key("-----BEGIN OPENSSH PRIVATE KEY-----")
    assert sh.parse_smart_health("SMART overall-health self-assessment test result: FAILED!") is False
    assert sh.parse_smart_health("SMART Health Status: OK") is True
    assert sh.parse_smart_health("Smartctl open device: /dev/sda failed: Permission denied") is None


def test_time_sync_and_load():
    assert sh.classify_time_sync({"NTP": "no"})[0]["requires_privileges"] is True
    assert sh.classify_time_sync({"NTP": "yes", "NTPSynchronized": "yes"}) == []
    assert sh.classify_load("9.0 8.5 8.2 1/100 1", 4)[0]["severity"] == "high"
    assert sh.classify_load("0.5 0.4 0.3 1/100 1", 4) == []
