#!/usr/bin/env python3
"""Read-only health audit of a Linux machine for the janitor-system-health skill.

Prints one JSON document to stdout (``findings[]`` + ``skipped[]``) and short
human hints to stderr. Never calls sudo, never changes system state and never
writes anything except the optional ``--output`` file. A probe that cannot run
(missing tool, no permission) is listed under ``skipped``; the exit code is
non-zero only on an internal error (bad arguments, unwritable ``--output``).

Stdlib only. Parsing/classification lives in pure functions that take text or
data so the logic is testable without touching the host.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import re
import stat
import subprocess
import sys
import time
from pathlib import Path
from typing import Callable, Iterable

SCHEMA_VERSION = 1
SEVERITIES = ("critical", "high", "medium", "low", "info")
SEVERITY_RANK = {name: rank for rank, name in enumerate(SEVERITIES)}
CMD_TIMEOUT = 15
GIB = 1024 ** 3

# Filesystems that are not persistent storage the user can fill.
PSEUDO_FS = frozenset({
    "tmpfs", "devtmpfs", "squashfs", "overlay", "efivarfs", "proc", "sysfs", "cgroup",
    "cgroup2", "devpts", "securityfs", "pstore", "bpf", "tracefs", "debugfs", "configfs",
    "fusectl", "mqueue", "hugetlbfs", "autofs", "ramfs", "nsfs", "fuse.portal",
    "fuse.gvfsd-fuse", "binfmt_misc", "rpc_pipefs", "iso9660", "udf", "zram",
})

ALL_INTERFACES = frozenset({"0.0.0.0", "*", "[::]", "::", "[::0]"})
# UDP services that normally bind every interface on a workstation.
BENIGN_UDP_PORTS = frozenset({68, 546, 5353, 5355, 1900})

BACKUP_WORDS = re.compile(
    r"backup|borg|restic|snapper|timeshift|rsnapshot|btrbk|duplicity|duplicati|kopia|"
    r"rclone|deja-dup|bacula|urbackup|snapshot", re.I)

_SNAPSHOT_ONLY = re.compile(r"snapper|timeshift|snapshot", re.I)
_OFF_DISK = re.compile(r"backup|borg|restic|rsnapshot|btrbk|duplicity|duplicati|kopia|rclone|"
                       r"deja-dup|bacula|urbackup", re.I)

FS_ERROR_PATTERNS = (
    ("ext4", re.compile(r"EXT4-fs (error|critical)|EXT4-fs warning.*(error|corrupt)", re.I)),
    ("btrfs", re.compile(r"BTRFS (error|critical)|BTRFS.*(corrupt|csum failed|checksum error)", re.I)),
    ("xfs", re.compile(r"XFS \(.*\):.*(corrupt|error|shutdown)", re.I)),
    ("io", re.compile(r"I/O error, dev |Buffer I/O error|blk_update_request: I/O error|"
                      r"critical medium error|Medium Error", re.I)),
    ("ata", re.compile(r"ata\d+(\.\d+)?: (failed command|exception Emask|status: \{ DRDY ERR)", re.I)),
    ("nvme", re.compile(r"nvme\d+.*(I/O \d+ .*timeout|controller is down|I/O error)", re.I)),
)


class Skip(Exception):
    """A probe cannot run here; the message is the user-facing reason."""


# ---------------------------------------------------------------------------
# Host helpers (the only code that touches the machine)
# ---------------------------------------------------------------------------

def find_tool(name: str, path: str | None = None) -> str | None:
    """Resolve *name* against PATH only (no fallbacks: a hidden tool counts as absent)."""
    for directory in (path if path is not None else os.environ.get("PATH", "")).split(os.pathsep):
        if not directory:
            continue
        candidate = os.path.join(directory, name)
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate
    return None


class CmdResult:
    def __init__(self, rc: int, out: str, err: str):
        self.rc, self.out, self.err = rc, out, err


def run(argv: list[str], timeout: int = CMD_TIMEOUT) -> CmdResult | None:
    """Run a read-only command; ``None`` when the tool is not on PATH."""
    exe = find_tool(argv[0])
    if exe is None:
        return None
    env = dict(os.environ, LC_ALL="C", LANG="C", SYSTEMD_PAGER="", PAGER="cat", SYSTEMD_COLORS="0")
    try:
        proc = subprocess.run([exe, *argv[1:]], capture_output=True, text=True, timeout=timeout,
                              env=env, stdin=subprocess.DEVNULL, errors="replace")
    except subprocess.TimeoutExpired:
        return CmdResult(-1, "", f"timeout after {timeout}s")
    except OSError as exc:
        return CmdResult(-1, "", str(exc))
    return CmdResult(proc.returncode, proc.stdout, proc.stderr)


def read_text(path: str | Path, limit: int = 1_000_000) -> str | None:
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            return fh.read(limit)
    except OSError:
        return None


def user_home() -> Path:
    """The OS user's home (Hermes exports HERMES_REAL_HOME when HOME is a profile home)."""
    for var in ("HERMES_REAL_HOME", "HOME"):
        value = os.environ.get(var, "").strip()
        if value:
            return Path(value)
    return Path.home()


def display_path(path: Path, home: Path) -> str:
    try:
        return "~/" + str(path.relative_to(home))
    except ValueError:
        return str(path)


# ---------------------------------------------------------------------------
# Finding model
# ---------------------------------------------------------------------------

def make_finding(probe: str, key: str, severity: str, area: str, title: str, evidence: str,
                 suggested_fix: str, requires_privileges: bool = False) -> dict:
    if severity not in SEVERITY_RANK:
        raise ValueError(f"bad severity {severity!r}")
    return {
        "id": f"{probe}:{key}",
        "probe": probe,
        "severity": severity,
        "area": area,
        "title": title,
        "evidence": evidence.strip()[:2000],
        "suggested_fix": suggested_fix,
        "requires_privileges": bool(requires_privileges),
    }


def worst(*severities: str) -> str:
    return min(severities, key=lambda s: SEVERITY_RANK[s])


def human_bytes(n: float) -> str:
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if abs(n) < 1024 or unit == "TiB":
            return f"{n:.1f} {unit}" if unit != "B" else f"{int(n)} B"
        n /= 1024
    return f"{n:.1f} TiB"


# ---------------------------------------------------------------------------
# Pure parsers / classifiers
# ---------------------------------------------------------------------------

def usage_severity(percent: int) -> str | None:
    if percent >= 95:
        return "critical"
    if percent >= 90:
        return "high"
    if percent >= 80:
        return "medium"
    return None


def parse_df(text: str) -> list[dict]:
    """Parse ``df -P -T`` (or ``df -P -T -i``) output into rows."""
    rows = []
    for line in text.splitlines()[1:]:
        parts = line.split()
        if len(parts) < 7 or not parts[5].endswith("%"):
            continue
        pct = parts[5].rstrip("%")
        rows.append({
            "source": parts[0], "fstype": parts[1], "total": parts[2], "used": parts[3],
            "avail": parts[4], "percent": int(pct) if pct.isdigit() else None,
            "mount": " ".join(parts[6:]),
        })
    return rows


def classify_df(text: str, kind: str = "space") -> list[dict]:
    """Findings for mounts over the usage thresholds. *kind* is ``space`` or ``inodes``."""
    # One finding per backing device: btrfs subvolumes and bind mounts of the same source
    # share usage, so they are folded into the shortest mount path.
    by_source: dict[str, list[dict]] = {}
    for row in parse_df(text):
        if row["fstype"] in PSEUDO_FS or row["percent"] is None:
            continue
        if row["mount"].startswith(("/snap/", "/run/", "/sys/", "/proc/", "/dev/")):
            continue
        by_source.setdefault(row["source"], []).append(row)
    findings = []
    for rows in by_source.values():
        rows.sort(key=lambda r: (len(r["mount"]), r["mount"]))
        row, others = rows[0], [r["mount"] for r in rows[1:]]
        sev = usage_severity(row["percent"])
        if sev is None:
            continue
        what = "espacio" if kind == "space" else "inodos"

        def amount(value: str) -> str:
            return human_bytes(int(value) * 1024) if kind == "space" and value.isdigit() else value
        fix = ("Libera espacio con la skill janitor-cleanup (caches, papelera, Docker) o revisa "
               f"los mayores consumidores: du -xh --max-depth=2 '{row['mount']}' | sort -h | tail -20")
        if kind == "inodes":
            fix = ("Busca directorios con millones de archivos pequeños: "
                   f"find '{row['mount']}' -xdev -type d -size +1M 2>/dev/null | head")
        findings.append(make_finding(
            "disk", f"{kind}:{row['mount']}", sev, "almacenamiento",
            f"{row['mount']} al {row['percent']}% de {what}",
            f"{row['source']} ({row['fstype']}) usado {amount(row['used'])} de {amount(row['total'])}, "
            f"libre {amount(row['avail'])}"
            + (f"; también montado en {', '.join(others)}" if others else ""), fix))
    return findings


def parse_meminfo(text: str) -> dict[str, int]:
    """``/proc/meminfo`` → values in KiB."""
    values = {}
    for line in text.splitlines():
        m = re.match(r"(\w+(?:\(\w+\))?):\s+(\d+)", line)
        if m:
            values[m.group(1)] = int(m.group(2))
    return values


def parse_psi(text: str) -> dict[str, float]:
    """``/proc/pressure/*`` → {'some_avg60': x, 'full_avg60': y}."""
    out = {}
    for line in text.splitlines():
        kind, _, rest = line.partition(" ")
        m = re.search(r"avg60=([\d.]+)", rest)
        if m:
            out[f"{kind}_avg60"] = float(m.group(1))
    return out


def classify_memory(meminfo: dict[str, int], psi: dict[str, float] | None = None) -> list[dict]:
    findings = []
    total, avail = meminfo.get("MemTotal", 0), meminfo.get("MemAvailable")
    if total and avail is not None:
        pct = 100 * avail / total
        sev = "high" if pct < 10 else "medium" if pct < 20 else None
        if sev:
            findings.append(make_finding(
                "memory", "available", sev, "memoria",
                f"Solo {pct:.0f}% de RAM disponible",
                f"MemAvailable {human_bytes(avail * 1024)} de MemTotal {human_bytes(total * 1024)}",
                "Identifica el proceso que más memoria usa (ps -eo pid,comm,%mem,rss --sort=-%mem | head) "
                "y ciérralo o limítalo; si es constante, amplía RAM o swap."))
    swap_total, swap_free = meminfo.get("SwapTotal", 0), meminfo.get("SwapFree", 0)
    if swap_total:
        used_pct = 100 * (swap_total - swap_free) / swap_total
        if used_pct >= 50:
            findings.append(make_finding(
                "memory", "swap", "high" if used_pct >= 80 else "medium", "memoria",
                f"Swap al {used_pct:.0f}%",
                f"SwapTotal {human_bytes(swap_total * 1024)}, libre {human_bytes(swap_free * 1024)}",
                "Revisa qué procesos están paginados (smem o /proc/<pid>/status VmSwap) y reduce la carga."))
    if psi and psi.get("full_avg60", 0) >= 5:
        findings.append(make_finding(
            "memory", "pressure", "high" if psi["full_avg60"] >= 20 else "medium", "memoria",
            "Presión de memoria sostenida (PSI)",
            f"/proc/pressure/memory full avg60={psi['full_avg60']:.2f} some avg60={psi.get('some_avg60', 0):.2f}",
            "El sistema está esperando por memoria: reduce procesos residentes o añade RAM."))
    return findings


def classify_load(loadavg_text: str, cpus: int) -> list[dict]:
    parts = loadavg_text.split()
    if len(parts) < 3 or cpus <= 0:
        return []
    l1, l5, l15 = (float(p) for p in parts[:3])
    ratio = l15 / cpus
    if ratio < 1:
        return []
    return [make_finding(
        "load", "loadavg", "high" if ratio >= 2 else "medium", "cpu",
        f"Carga sostenida por encima de los núcleos ({ratio:.1f}x)",
        f"loadavg {l1} {l5} {l15} con {cpus} CPU",
        "Revisa los procesos que más CPU o E/S consumen: ps -eo pid,comm,%cpu,stat --sort=-%cpu | head; "
        "procesos en estado D indican espera de disco.")]


def parse_ps(text: str) -> list[dict]:
    """``ps -eo pid=,comm=,%cpu=,%mem=,rss=`` → rows."""
    rows = []
    for line in text.splitlines():
        parts = line.split()
        if len(parts) < 5:
            continue
        try:
            rows.append({"pid": int(parts[0]), "comm": " ".join(parts[1:-3]),
                         "cpu": float(parts[-3]), "mem": float(parts[-2]), "rss_kib": int(parts[-1])})
        except ValueError:
            continue
    return rows


def classify_processes(rows: list[dict]) -> list[dict]:
    if not rows:
        return []
    top_cpu = sorted(rows, key=lambda r: r["cpu"], reverse=True)[:5]
    top_mem = sorted(rows, key=lambda r: r["mem"], reverse=True)[:5]
    fmt = lambda r: f"{r['comm']} (pid {r['pid']}) cpu {r['cpu']}% mem {r['mem']}%"  # noqa: E731
    findings = [make_finding(
        "load", "top-processes", "info", "cpu", "Procesos que más CPU y memoria consumen",
        "CPU: " + "; ".join(fmt(r) for r in top_cpu) + "\nMEM: " + "; ".join(fmt(r) for r in top_mem),
        "Solo informativo. %CPU de ps es la media desde que arrancó el proceso.")]
    for r in rows:
        if r["mem"] >= 40:
            findings.append(make_finding(
                "load", f"memhog:{r['comm']}", "medium", "memoria",
                f"{r['comm']} usa el {r['mem']}% de la RAM", fmt(r),
                f"Comprueba si {r['comm']} tiene una fuga o un límite mal puesto; reinícialo o acótalo "
                "(systemd MemoryMax=) tras confirmarlo."))
    return findings


def parse_failed_units(text: str) -> list[str]:
    """``systemctl --failed --no-legend --plain`` → unit names."""
    units = []
    for line in text.splitlines():
        parts = line.strip().lstrip("●* ").split()
        if parts and "." in parts[0]:
            units.append(parts[0])
    return units


def parse_restart_counters(messages: Iterable[str]) -> dict[str, int]:
    """Max systemd restart counter per unit from journal messages."""
    counters: dict[str, int] = {}
    for msg in messages:
        m = re.search(r"^(\S+?): Scheduled restart job, restart counter is at (\d+)", msg.strip())
        if m:
            counters[m.group(1)] = max(counters.get(m.group(1), 0), int(m.group(2)))
    return counters


def classify_fs_errors(lines: Iterable[str]) -> list[dict]:
    """Kernel log lines → one finding per error family with count and a sample."""
    hits: dict[str, list[str]] = {}
    for line in lines:
        for family, rx in FS_ERROR_PATTERNS:
            if rx.search(line):
                hits.setdefault(family, []).append(line.strip())
                break
    findings = []
    for family, samples in hits.items():
        sev = "critical" if family in ("io", "ext4", "btrfs", "xfs") and len(samples) >= 10 else "high"
        findings.append(make_finding(
            "fs_errors", family, sev, "almacenamiento",
            f"Errores de disco/sistema de archivos en el kernel ({family}, {len(samples)} líneas)",
            "\n".join(samples[-3:]),
            "Haz copia de seguridad YA de lo importante, revisa SMART (sudo smartctl -a <disco>) y "
            "programa una comprobación del sistema de archivos (fsck/btrfs scrub) desmontado o al arrancar."))
    return findings


def parse_kv(text: str) -> dict[str, str]:
    out = {}
    for line in text.splitlines():
        key, sep, value = line.partition("=")
        if sep:
            out[key.strip()] = value.strip()
    return out


def classify_time_sync(props: dict[str, str]) -> list[dict]:
    if props.get("NTP") == "no":
        return [make_finding(
            "time_sync", "ntp", "medium", "tiempo", "Sincronización horaria (NTP) desactivada",
            "timedatectl: NTP=no", "sudo timedatectl set-ntp true", requires_privileges=True)]
    if props.get("NTPSynchronized") == "no":
        return [make_finding(
            "time_sync", "unsynced", "low", "tiempo", "El reloj no está sincronizado",
            "timedatectl: NTP=yes, NTPSynchronized=no",
            "Revisa el servicio de tiempo: systemctl status systemd-timesyncd chronyd ntpd")]
    return []


def parse_ss(text: str) -> list[dict]:
    """``ss -H -tulpn`` → listeners with proto, address, port and process (if visible)."""
    rows = []
    for line in text.splitlines():
        parts = line.split()
        if len(parts) < 5:
            continue
        proto, local = parts[0], parts[4]
        addr, _, port = local.rpartition(":")
        addr = re.sub(r"%\S+$", "", addr)  # strip interface scope (0.0.0.0%lo)
        m = re.search(r'users:\(\("([^"]+)",pid=(\d+)', line)
        try:
            port_num = int(port)
        except ValueError:
            continue
        rows.append({"proto": proto, "addr": addr, "port": port_num,
                     "process": m.group(1) if m else None, "pid": int(m.group(2)) if m else None})
    return rows


def classify_listeners(rows: list[dict], firewall_active: bool | None) -> list[dict]:
    """Listeners bound to every interface, one finding per owning process (stable id across runs:
    client apps open fresh ephemeral UDP ports every time). TCP is a service; UDP outside the
    well-known workstation ports is usually a client socket and ranks lower. No active firewall
    raises every level by one."""
    groups: dict[str, dict] = {}
    for r in rows:
        if r["addr"] not in ALL_INTERFACES:
            continue
        key = r["process"] or f"{r['proto']}-{r['port']}"
        g = groups.setdefault(key, {"process": r["process"], "pid": r["pid"], "tcp": set(), "udp": set()})
        g["tcp" if r["proto"].startswith("tcp") else "udp"].add(r["port"])
    bump = {"low": "medium", "medium": "high", "high": "high"}
    findings = []
    for key, g in sorted(groups.items()):
        udp_real = {p for p in g["udp"] if p not in BENIGN_UDP_PORTS}
        sev = "medium" if g["tcp"] else "low"
        if firewall_active is False and (g["tcp"] or udp_real):
            sev = bump[sev]
        ports = ([f"tcp/{p}" for p in sorted(g["tcp"])] + [f"udp/{p}" for p in sorted(g["udp"])])
        shown = ", ".join(ports[:12]) + (f" (+{len(ports) - 12} más)" if len(ports) > 12 else "")
        owner = f"{g['process']} (pid {g['pid']})" if g["process"] else "proceso no visible sin privilegios"
        fix = (f"Si {g['process'] or 'el servicio'} no debe ser accesible desde la red, átalo a 127.0.0.1 "
               "en su configuración o bloquea esos puertos en el firewall.")
        findings.append(make_finding(
            "listening_ports", key, sev, "red",
            f"{g['process'] or 'Proceso desconocido'} escucha en todas las interfaces ({len(ports)} puertos)",
            f"{owner}: {shown}",
            fix if g["process"] else fix + " Para ver el dueño: sudo ss -tulpn",
            requires_privileges=g["process"] is None))
    return findings


def classify_firewall(states: dict[str, str | None]) -> tuple[bool | None, list[dict]]:
    """*states* maps ufw/firewalld/nftables/iptables → 'active'|'inactive'|None (not installed).

    Returns (firewall_active, findings). ``None`` when nothing could be determined."""
    active = [name for name, st in states.items() if st == "active"]
    present = [name for name, st in states.items() if st is not None]
    if active:
        return True, []
    if not present:
        return None, [make_finding(
            "firewall", "none-installed", "high", "red", "No hay ningún firewall instalado",
            "Ni ufw, ni firewalld, ni nftables, ni iptables en PATH",
            "Instala y activa uno (ufw es el más simple): sudo ufw default deny incoming && sudo ufw enable",
            requires_privileges=True)]
    return False, [make_finding(
        "firewall", "inactive", "high", "red", "Firewall instalado pero inactivo",
        "Estado: " + ", ".join(f"{n}={states[n]}" for n in present),
        "Actívalo tras revisar las reglas, p. ej. sudo ufw enable o sudo systemctl enable --now firewalld",
        requires_privileges=True)]


SSHD_DEFAULTS = {"passwordauthentication": "yes", "permitrootlogin": "prohibit-password",
                 "kbdinteractiveauthentication": "yes", "pubkeyauthentication": "yes"}


def parse_sshd_config(text: str, include_loader: Callable[[str], list[str]] | None = None) -> dict:
    """Effective global sshd settings (first value wins; stops at the first ``Match``)."""
    values: dict[str, str] = {}

    def walk(body: str, depth: int) -> bool:
        for raw in body.splitlines():
            line = raw.split("#", 1)[0].strip()
            if not line:
                continue
            parts = line.split(None, 1)
            key = parts[0].lower()
            arg = parts[1].strip().strip('"') if len(parts) > 1 else ""
            if key == "match":
                return False
            if key == "include" and include_loader and depth < 5:
                for pattern in arg.split():
                    for included in include_loader(pattern):
                        if not walk(included, depth + 1):
                            return False
                continue
            values.setdefault(key, arg.split()[0].lower() if arg else "")
        return True

    walk(text, 0)
    return values


def parse_sshd_t(text: str) -> dict:
    """``sshd -T`` output → lowercase key/value."""
    out = {}
    for line in text.splitlines():
        parts = line.strip().split(None, 1)
        if len(parts) == 2:
            out.setdefault(parts[0].lower(), parts[1].strip().lower())
    return out


def ssh_verdict(settings: dict, running: bool, exposed: bool, source: str) -> list[dict]:
    """Findings for sshd exposure given effective settings (empty dict = unknown)."""
    if not running:
        return []
    if not settings:
        return [make_finding(
            "ssh", "config-unknown", "info", "ssh", "sshd activo; configuración no legible",
            "Ni sshd -T ni /etc/ssh/sshd_config son legibles sin privilegios",
            "sudo sshd -T | grep -Ei 'passwordauthentication|permitrootlogin|kbdinteractive'",
            requires_privileges=True)]
    eff = {k: settings.get(k, SSHD_DEFAULTS[k]) for k in SSHD_DEFAULTS}
    findings = []
    where = "expuesto en todas las interfaces" if exposed else "no expuesto fuera de loopback"
    if eff["passwordauthentication"] == "yes" or eff["kbdinteractiveauthentication"] == "yes":
        findings.append(make_finding(
            "ssh", "password-auth", "high" if exposed else "medium", "ssh",
            "SSH acepta autenticación por contraseña",
            f"PasswordAuthentication={eff['passwordauthentication']} "
            f"KbdInteractiveAuthentication={eff['kbdinteractiveauthentication']} ({source}; {where})",
            "Con tu clave ya instalada, pon PasswordAuthentication no y KbdInteractiveAuthentication no "
            "en /etc/ssh/sshd_config.d/ y recarga: sudo systemctl reload sshd (o ssh)",
            requires_privileges=True))
    if eff["permitrootlogin"] == "yes":
        findings.append(make_finding(
            "ssh", "root-login", "high", "ssh", "SSH permite login de root con contraseña",
            f"PermitRootLogin=yes ({source}; {where})",
            "PermitRootLogin no (o prohibit-password) en /etc/ssh/sshd_config.d/ y recarga sshd",
            requires_privileges=True))
    return findings


def classify_mode(kind: str, mode: int) -> str | None:
    """Severity for a permission problem. *kind*: ssh_dir | private_key | ssh_file | gnupg_dir | sensitive."""
    perm = stat.S_IMODE(mode)
    if kind == "private_key":
        return "high" if perm & 0o077 else None
    if kind in ("ssh_dir", "gnupg_dir"):
        if perm & 0o022:
            return "high"
        return "low" if perm & 0o055 else None
    if kind == "ssh_file":
        return "high" if perm & 0o022 else None
    if kind == "sensitive":
        return "high" if perm & 0o002 else None
    return None


def looks_like_private_key(head: str) -> bool:
    return "PRIVATE KEY" in head and head.lstrip().startswith("-----BEGIN")


def classify_updates(manager: str, pending: int, security: int | None, reboot: bool | None,
                     db_age_days: float | None) -> list[dict]:
    findings = []
    upgrade = {"pacman": "sudo pacman -Syu", "apt": "sudo apt update && sudo apt upgrade",
               "dnf": "sudo dnf upgrade --refresh"}.get(manager, "actualiza con tu gestor de paquetes")
    if security:
        findings.append(make_finding(
            "updates", "security", "high", "paquetes", f"{security} actualizaciones de seguridad pendientes",
            f"{manager}: {security} paquetes con avisos de seguridad", upgrade, requires_privileges=True))
    if pending:
        findings.append(make_finding(
            "updates", "pending", "medium" if pending >= 50 else "low", "paquetes",
            f"{pending} actualizaciones pendientes", f"{manager}: {pending} paquetes actualizables",
            upgrade, requires_privileges=True))
    if reboot:
        findings.append(make_finding(
            "updates", "reboot-required", "medium", "paquetes", "Reinicio pendiente",
            "El kernel o bibliotecas en ejecución ya no coinciden con los instalados",
            "Reinicia cuando puedas: systemctl reboot"))
    if db_age_days is not None and db_age_days > 7:
        refresh = {"pacman": "checkupdates (pacman-contrib, sin root)", "apt": "sudo apt update",
                   "dnf": "sudo dnf makecache"}.get(manager, "refresca los metadatos")
        findings.append(make_finding(
            "updates", "stale-metadata", "low", "paquetes",
            f"Metadatos de paquetes sin refrescar hace {db_age_days:.0f} días",
            "La lista de pendientes puede estar incompleta", refresh,
            requires_privileges=manager != "pacman"))
    return findings


def parse_pacman_qu(text: str) -> int:
    return sum(1 for line in text.splitlines() if "->" in line and "[ignored]" not in line)


def parse_apt_upgradable(text: str) -> tuple[int, int]:
    pending = security = 0
    for line in text.splitlines():
        if "[upgradable from:" not in line:
            continue
        pending += 1
        suite = line.split(" ", 1)[0].partition("/")[2]
        if "-security" in suite:
            security += 1
    return pending, security


def parse_dnf_check_update(text: str) -> int:
    count = 0
    for line in text.splitlines():
        parts = line.split()
        if line.startswith(("Obsoleting", "Last metadata", "Security:")) or not parts:
            if line.startswith("Obsoleting"):
                break
            continue
        if len(parts) == 3 and "." in parts[0]:
            count += 1
    return count


def parse_size(text: str) -> float:
    """Docker size string ('1.2GB', '512.3MB', '0B', '1.5kB') → bytes."""
    m = re.match(r"\s*([\d.]+)\s*([kKMGTP]?i?B)", text or "")
    if not m:
        return 0.0
    mult = {"B": 1, "kB": 1e3, "KB": 1e3, "MB": 1e6, "GB": 1e9, "TB": 1e12, "PB": 1e15,
            "KiB": 1024, "MiB": 1024 ** 2, "GiB": 1024 ** 3, "TiB": 1024 ** 4}.get(m.group(2), 1)
    return float(m.group(1)) * mult


def classify_docker_df(lines: Iterable[str]) -> list[dict]:
    findings = []
    for line in lines:
        try:
            row = json.loads(line)
        except (json.JSONDecodeError, TypeError):
            continue
        kind = row.get("Type", "")
        reclaim = parse_size(row.get("Reclaimable", ""))
        total = int(str(row.get("TotalCount", "0")) or 0)
        active = int(str(row.get("Active", "0")) or 0)
        evidence = (f"{kind}: total {row.get('TotalCount')}, activos {row.get('Active')}, "
                    f"tamaño {row.get('Size')}, recuperable {row.get('Reclaimable')}")
        if kind == "Containers" and total - active >= 10:
            findings.append(make_finding(
                "docker", "stopped-containers", "low", "docker", f"{total - active} contenedores detenidos",
                evidence, "Revísalos (docker ps -a --filter status=exited) y elimínalos con la skill "
                          "janitor-cleanup tras confirmar."))
        if reclaim < 1e9:
            continue
        sev = "medium" if reclaim >= 10e9 else "low"
        if kind == "Local Volumes":
            fix = ("Los volúmenes contienen datos: lista los no usados (docker volume ls -f dangling=true), "
                   "verifica cada uno y elimina solo los confirmados.")
        else:
            fix = {"Images": "docker image prune (colgantes) o docker image prune -a tras confirmar",
                   "Build Cache": "docker builder prune",
                   "Containers": "docker container prune"}.get(kind, "docker system df -v para el detalle")
            fix += " — vía la skill janitor-cleanup, con confirmación."
        findings.append(make_finding(
            "docker", f"reclaimable:{kind.lower().replace(' ', '-')}", sev, "docker",
            f"Docker: {human_bytes(reclaim)} recuperables en {kind}", evidence, fix))
    return findings


def backup_verdict(evidence: list[str], tools: list[str]) -> list[dict]:
    """Backup findings from collected evidence lines and installed backup tools."""
    snapshot_only = evidence and all(
        _SNAPSHOT_ONLY.search(e) and not _OFF_DISK.search(e) for e in evidence)
    if snapshot_only:
        return [make_finding(
            "backups", "snapshots-only", "medium", "copias",
            "Solo hay snapshots locales; ninguna copia fuera del disco",
            "\n".join(evidence[:10]),
            "Los snapshots mueren con el disco. Añade una copia a otro dispositivo o remoto "
            "(restic o borg con timer de systemd) y prueba una restauración.")]
    if evidence:
        return [make_finding(
            "backups", "evidence", "info", "copias", "Hay indicios de copias de seguridad",
            "\n".join(evidence[:10]),
            "Comprueba que la última copia es reciente y que sabes restaurarla.")]
    if tools:
        return [make_finding(
            "backups", "unscheduled", "medium", "copias",
            "Herramientas de copia instaladas pero sin programación ni configuración visible",
            "Instaladas: " + ", ".join(tools),
            "Programa la copia (timer de systemd o cron) y verifica una restauración.")]
    return [make_finding(
        "backups", "none", "high", "copias", "No se encontró ninguna evidencia de copias de seguridad",
        "Sin timeshift, snapper, borg, restic, rsnapshot, btrbk, snapshots btrfs ni timers/cron de backup",
        "Configura al menos una copia automática (restic o borg a disco externo/remoto; "
        "snapper/timeshift para snapshots del sistema).")]


# ---------------------------------------------------------------------------
# Probes
# ---------------------------------------------------------------------------

class Context:
    def __init__(self, home: Path, home_budget: float):
        self.home = home
        self.home_budget = home_budget
        self.firewall_active: bool | None = None
        self.listeners: list[dict] | None = None
        self.partial_skips: list[dict] = []

    def partial_skip(self, probe: str, reason: str) -> None:
        self.partial_skips.append({"probe": probe, "reason": reason})


def _require(result: CmdResult | None, tool: str, package: str | None = None) -> CmdResult:
    if result is None:
        raise Skip(f"{tool} no está en PATH" + (f" (paquete {package})" if package else ""))
    return result


def probe_disk(ctx: Context) -> list[dict]:
    space = _require(run(["df", "-P", "-T"]), "df", "coreutils")
    findings = classify_df(space.out, "space")
    inodes = run(["df", "-P", "-T", "-i"])
    if inodes is not None:
        findings += classify_df(inodes.out, "inodes")
    return findings


def _dir_usage(root: Path, deadline: float, max_depth: int = 40) -> tuple[int, bool]:
    """Disk usage (st_blocks) of *root* without following symlinks or crossing devices."""
    try:
        st = root.lstat()
    except OSError:
        return 0, False
    total, dev = st.st_blocks * 512, st.st_dev
    if not stat.S_ISDIR(st.st_mode):
        return total, False
    stack, partial = [(root, 0)], False
    while stack:
        if time.monotonic() > deadline:
            return total, True
        current, depth = stack.pop()
        try:
            with os.scandir(current) as it:
                for entry in it:
                    try:
                        est = entry.stat(follow_symlinks=False)
                    except OSError:
                        continue
                    total += est.st_blocks * 512
                    if stat.S_ISDIR(est.st_mode) and est.st_dev == dev:
                        if depth + 1 < max_depth:
                            stack.append((Path(entry.path), depth + 1))
                        else:
                            partial = True
        except OSError:
            continue
    return total, partial


def probe_home_usage(ctx: Context) -> list[dict]:
    home = ctx.home
    if not home.is_dir():
        raise Skip(f"el directorio personal {home} no existe")
    deadline = time.monotonic() + ctx.home_budget
    sizes, partial = [], False
    try:
        entries = sorted(os.scandir(home), key=lambda e: e.name)
    except OSError as exc:
        raise Skip(f"no se puede listar el directorio personal: {exc}") from exc
    for entry in entries:
        size, part = _dir_usage(Path(entry.path), deadline)
        partial = partial or part
        sizes.append((size, Path(entry.path)))
        if time.monotonic() > deadline:
            partial = True
            break
    sizes.sort(reverse=True)
    findings = [make_finding(
        "home_usage", "top", "info", "almacenamiento", "Mayores consumidores del directorio personal",
        "\n".join(f"{human_bytes(s)}  {display_path(p, home)}" for s, p in sizes[:10])
        + ("\n(medición parcial: se agotó el presupuesto de tiempo)" if partial else ""),
        "Solo informativo; para limpiar usa la skill janitor-cleanup.")]
    by_name = {p.name: s for s, p in sizes}
    if by_name.get(".cache", 0) >= 5 * GIB:
        findings.append(make_finding(
            "home_usage", "cache", "low", "almacenamiento", f"~/.cache ocupa {human_bytes(by_name['.cache'])}",
            f"~/.cache: {human_bytes(by_name['.cache'])}",
            "Limpia caches regenerables con la skill janitor-cleanup (muestra antes de borrar)."))
    trash = home / ".local" / "share" / "Trash"
    if trash.is_dir():
        tsize, _ = _dir_usage(trash, time.monotonic() + 5)
        if tsize >= 2 * GIB:
            findings.append(make_finding(
                "home_usage", "trash", "low", "almacenamiento", f"La papelera ocupa {human_bytes(tsize)}",
                f"~/.local/share/Trash: {human_bytes(tsize)}",
                "Revisa y vacía la papelera cuando confirmes que no necesitas nada de ella."))
    return findings


def probe_memory(ctx: Context) -> list[dict]:
    text = read_text("/proc/meminfo")
    if text is None:
        raise Skip("/proc/meminfo no legible")
    psi = read_text("/proc/pressure/memory")
    return classify_memory(parse_meminfo(text), parse_psi(psi) if psi else None)


def probe_load(ctx: Context) -> list[dict]:
    text = read_text("/proc/loadavg")
    if text is None:
        raise Skip("/proc/loadavg no legible")
    findings = classify_load(text, os.cpu_count() or 1)
    ps = run(["ps", "-eo", "pid=,comm=,%cpu=,%mem=,rss="])
    if ps is None:
        ctx.partial_skip("load.processes", "ps no está en PATH (paquete procps)")
    else:
        findings += classify_processes(parse_ps(ps.out))
    return findings


def probe_systemd_units(ctx: Context) -> list[dict]:
    system = _require(run(["systemctl", "--failed", "--no-legend", "--plain", "--no-pager"]), "systemctl")
    if system.rc != 0 and not system.out:
        raise Skip(f"systemctl no responde (¿sin systemd?): {system.err.strip()[:200]}")
    findings = []
    for unit in parse_failed_units(system.out):
        findings.append(make_finding(
            "systemd_units", f"system:{unit}", "high", "servicios", f"Unidad del sistema fallida: {unit}",
            f"systemctl --failed → {unit}",
            f"Diagnostica: systemctl status {unit}; journalctl -u {unit} -b. Si sobra: sudo systemctl disable {unit}; "
            f"para limpiar el estado: sudo systemctl reset-failed {unit}", requires_privileges=True))
    user = run(["systemctl", "--user", "--failed", "--no-legend", "--plain", "--no-pager"])
    if user is None or (user.rc != 0 and not user.out):
        ctx.partial_skip("systemd_units.user", "sin sesión de systemd de usuario accesible")
    else:
        for unit in parse_failed_units(user.out):
            findings.append(make_finding(
                "systemd_units", f"user:{unit}", "medium", "servicios", f"Unidad de usuario fallida: {unit}",
                f"systemctl --user --failed → {unit}",
                f"systemctl --user status {unit}; journalctl --user -u {unit} -b; "
                f"systemctl --user reset-failed {unit}"))
    return findings


_JOURNAL_DENIED = ("insufficient permissions", "not seeing messages from other users and the system")


def _journal(args: list[str]) -> tuple[list[str], bool]:
    """Run journalctl; returns (lines, system_journal_visible)."""
    res = _require(run(["journalctl", "--no-pager", *args], timeout=30), "journalctl")
    denied = any(marker in res.err for marker in _JOURNAL_DENIED)
    if res.rc != 0 and not res.out and not denied:
        raise Skip(f"journalctl falló: {res.err.strip()[:200]}")
    return res.out.splitlines(), not denied


def probe_unit_flapping(ctx: Context) -> list[dict]:
    lines, visible = _journal(["--since=-24h", "-o", "cat", "-n", "20000", "SYSLOG_IDENTIFIER=systemd"])
    user = run(["journalctl", "--no-pager", "--user", "--since=-24h", "-o", "cat", "-n", "20000",
                "SYSLOG_IDENTIFIER=systemd"], timeout=30)
    if user is not None:
        lines += user.out.splitlines()
    findings = []
    for unit, count in sorted(parse_restart_counters(lines).items()):
        if count >= 3:
            findings.append(make_finding(
                "unit_flapping", unit, "high" if count >= 20 else "medium", "servicios",
                f"{unit} se reinicia en bucle ({count} reinicios en 24 h)",
                f"journal: '{unit}: Scheduled restart job, restart counter is at {count}'",
                f"journalctl -u {unit} --since=-24h | tail -50 para ver por qué muere; corrige la causa, "
                "no subas RestartSec."))
    if not visible:
        findings.append(make_finding(
            "unit_flapping", "journal-access", "info", "servicios",
            "El journal del sistema no es legible sin privilegios",
            "journalctl avisa de permisos insuficientes; solo se revisó el journal del usuario",
            "sudo journalctl --since=-24h -g 'restart counter is at' (o añade tu usuario al grupo systemd-journal)",
            requires_privileges=True))
    return findings


def probe_fs_errors(ctx: Context) -> list[dict]:
    lines, visible = _journal(["-k", "-p", "warning", "--since=-7d", "-o", "cat", "-n", "5000"])
    if not visible and not lines:
        return [make_finding(
            "fs_errors", "journal-access", "info", "almacenamiento",
            "El log del kernel no es legible sin privilegios",
            "journalctl -k avisa de permisos insuficientes",
            "sudo journalctl -k -p warning --since=-7d | grep -Ei 'I/O error|EXT4-fs error|BTRFS (error|critical)|XFS'",
            requires_privileges=True)]
    return classify_fs_errors(lines)


def _boot_kernel_missing(release: str) -> bool | None:
    for base in ("/usr/lib/modules", "/lib/modules"):
        if Path(base).is_dir():
            return not (Path(base) / release).exists()
    return None


def probe_kernel(ctx: Context) -> list[dict]:
    release = os.uname().release
    uptime_text = read_text("/proc/uptime")
    days = float(uptime_text.split()[0]) / 86400 if uptime_text else None
    findings = [make_finding(
        "kernel", "info", "info", "sistema", f"Kernel {release}",
        f"uname -r: {release}" + (f"; uptime {days:.1f} días" if days is not None else ""),
        "Solo informativo.")]
    if days is not None and days > 90:
        findings.append(make_finding(
            "kernel", "uptime", "low", "sistema", f"{days:.0f} días sin reiniciar",
            f"/proc/uptime: {days:.0f} días", "Los parches de kernel no se aplican hasta reiniciar."))
    return findings


def _updates_pacman(ctx: Context):
    res = run(["pacman", "-Qu"], timeout=60)
    pending = parse_pacman_qu(res.out) if res else 0
    sync = list(Path("/var/lib/pacman/sync").glob("*.db"))
    age = (time.time() - max(p.stat().st_mtime for p in sync)) / 86400 if sync else None
    security = None
    audit = run(["arch-audit", "-u"], timeout=60)
    if audit is None:
        ctx.partial_skip("updates.security", "arch-audit no está en PATH; no se distinguen las de seguridad")
    elif audit.rc == 0 or audit.out:
        security = sum(1 for line in audit.out.splitlines() if line.startswith("Package "))
    else:
        ctx.partial_skip("updates.security", f"arch-audit falló (necesita red): {audit.err.strip()[:120]}")
    return pending, security, age


def _updates_apt(ctx: Context):
    res = run(["apt", "list", "--upgradable"], timeout=60)
    pending, security = parse_apt_upgradable(res.out) if res else (0, 0)
    lists = Path("/var/lib/apt/lists")
    age = (time.time() - lists.stat().st_mtime) / 86400 if lists.is_dir() else None
    return pending, security, age


def _updates_dnf(ctx: Context):
    res = run(["dnf", "-q", "-C", "check-update"], timeout=60)
    if res is not None and res.rc not in (0, 100):
        ctx.partial_skip("updates.pending", f"dnf sin caché local: {res.err.strip()[:120]}")
        pending = 0
    else:
        pending = parse_dnf_check_update(res.out) if res else 0
    sec = run(["dnf", "-q", "-C", "updateinfo", "list", "--security"], timeout=60)
    security = (sum(1 for line in sec.out.splitlines() if line.strip()) if sec and sec.rc == 0 else None)
    if security is None:
        ctx.partial_skip("updates.security", "dnf updateinfo no disponible desde caché")
    return pending, security, None


def probe_updates(ctx: Context) -> list[dict]:
    for manager, tool, fn in (("pacman", "pacman", _updates_pacman), ("apt", "apt", _updates_apt),
                              ("dnf", "dnf", _updates_dnf)):
        if find_tool(tool):
            pending, security, age = fn(ctx)
            break
    else:
        raise Skip("ningún gestor de paquetes soportado en PATH (pacman, apt, dnf)")
    reboot: bool | None = None
    if Path("/run/reboot-required").exists() or Path("/var/run/reboot-required").exists():
        reboot = True
    elif manager == "dnf":
        nr = run(["needs-restarting", "-r"], timeout=30)
        reboot = nr.rc == 1 if nr else None
    if not reboot:
        reboot = _boot_kernel_missing(os.uname().release) or reboot
    return classify_updates(manager, pending, security, reboot, age)


def probe_smart(ctx: Context) -> list[dict]:
    scan = _require(run(["smartctl", "--scan"]), "smartctl", "smartmontools")
    devices = [line.split()[0] for line in scan.out.splitlines() if line.startswith("/dev/")]
    if not devices:
        lsblk = run(["lsblk", "-dno", "NAME,TYPE"])
        devices = [f"/dev/{l.split()[0]}" for l in (lsblk.out.splitlines() if lsblk else [])
                   if l.split()[1:] == ["disk"]]
    if not devices:
        raise Skip("no se detectaron discos")
    findings = []
    for dev in devices:
        res = run(["smartctl", "-H", dev], timeout=30)
        verdict = parse_smart_health(res.out if res else "")
        if verdict is None:
            findings.append(make_finding(
                "smart", f"access:{dev}", "info", "almacenamiento", f"SMART de {dev} requiere privilegios",
                (res.out or res.err).strip().splitlines()[-1][:300] if res and (res.out or res.err) else "sin salida",
                f"sudo smartctl -H {dev}", requires_privileges=True))
        elif verdict is False:
            findings.append(make_finding(
                "smart", f"failing:{dev}", "critical", "almacenamiento", f"SMART reporta fallo en {dev}",
                "\n".join(l for l in res.out.splitlines() if "result" in l.lower() or "status" in l.lower()),
                f"Copia de seguridad inmediata y reemplazo del disco. Detalle: sudo smartctl -a {dev}"))
    return findings


def parse_smart_health(text: str) -> bool | None:
    """True = healthy, False = failing, None = unknown/unreadable."""
    m = re.search(r"overall-health self-assessment test result:\s*(\w+)", text)
    if m:
        return m.group(1).upper() == "PASSED"
    m = re.search(r"SMART Health Status:\s*(\w+)", text)
    if m:
        return m.group(1).upper() == "OK"
    return None


def probe_time_sync(ctx: Context) -> list[dict]:
    res = _require(run(["timedatectl", "show", "-p", "NTP", "-p", "NTPSynchronized"]), "timedatectl")
    if res.rc != 0:
        raise Skip(f"timedatectl no responde: {res.err.strip()[:200]}")
    return classify_time_sync(parse_kv(res.out))


def probe_firewall(ctx: Context) -> list[dict]:
    states: dict[str, str | None] = {}
    for name, tool, unit in (("ufw", "ufw", "ufw"), ("firewalld", "firewall-cmd", "firewalld"),
                             ("nftables", "nft", "nftables"), ("iptables", "iptables", "iptables")):
        if not find_tool(tool):
            states[name] = None
            continue
        st = run(["systemctl", "is-active", unit])
        state = st.out.strip() if st else ""
        if name == "ufw":
            conf = read_text("/etc/ufw/ufw.conf") or ""
            if re.search(r"^\s*ENABLED\s*=\s*no", conf, re.M):
                state = "inactive"
        states[name] = "active" if state == "active" else "inactive"
    if all(v is None for v in states.values()) and not find_tool("systemctl"):
        raise Skip("ni herramientas de firewall ni systemctl en PATH")
    ctx.firewall_active, findings = classify_firewall(states)
    return findings


def probe_listening_ports(ctx: Context) -> list[dict]:
    res = _require(run(["ss", "-H", "-tulpn"]), "ss", "iproute2")
    if res.rc != 0:
        raise Skip(f"ss falló: {res.err.strip()[:200]}")
    ctx.listeners = parse_ss(res.out)
    return classify_listeners(ctx.listeners, ctx.firewall_active)


def _sshd_running(ctx: Context) -> bool | None:
    for unit in ("sshd", "ssh"):
        st = run(["systemctl", "is-active", unit])
        if st and st.out.strip() == "active":
            return True
    if ctx.listeners is not None:
        return any(r["port"] == 22 and r["proto"] == "tcp" for r in ctx.listeners)
    return False if find_tool("systemctl") else None


def probe_ssh(ctx: Context) -> list[dict]:
    running = _sshd_running(ctx)
    if running is None:
        raise Skip("no se puede saber si sshd está activo (sin systemctl ni ss)")
    if not running:
        return []
    exposed = any(r["port"] == 22 and r["addr"] in ALL_INTERFACES for r in (ctx.listeners or []))
    settings, source = {}, ""
    res = run(["sshd", "-T"])
    if res is not None and res.rc == 0 and res.out:
        settings, source = parse_sshd_t(res.out), "sshd -T"
    else:
        text = read_text("/etc/ssh/sshd_config")
        if text is not None:
            def loader(pattern: str) -> list[str]:
                base = Path(pattern if pattern.startswith("/") else f"/etc/ssh/{pattern}")
                return [read_text(p) or "" for p in sorted(base.parent.glob(base.name))]
            settings, source = parse_sshd_config(text, loader), "/etc/ssh/sshd_config"
    return ssh_verdict(settings, True, exposed, source)


def probe_permissions(ctx: Context) -> list[dict]:
    home, findings = ctx.home, []

    def check(path: Path, kind: str, label: str, fix: str) -> None:
        try:
            st = path.lstat()
        except OSError:
            return
        if stat.S_ISLNK(st.st_mode):
            return
        sev = classify_mode(kind, st.st_mode)
        if sev:
            findings.append(make_finding(
                "permissions", f"{kind}:{display_path(path, home)}", sev, "seguridad",
                f"{label}: {display_path(path, home)} con permisos {oct(stat.S_IMODE(st.st_mode))}",
                f"{display_path(path, home)} modo {stat.filemode(st.st_mode)}", fix))

    ssh = home / ".ssh"
    if ssh.is_dir():
        check(ssh, "ssh_dir", "~/.ssh demasiado abierto", f"chmod 700 '{ssh}'")
        try:
            children = sorted(ssh.iterdir())
        except OSError:
            children = []
        for child in children:
            if not child.is_file() or child.is_symlink():
                continue
            head = ""
            if not child.name.endswith(".pub"):
                try:
                    with open(child, encoding="ascii", errors="ignore") as fh:
                        head = fh.read(64)
                except OSError:
                    head = ""
            if looks_like_private_key(head):
                check(child, "private_key", "Clave privada legible por otros", f"chmod 600 '{child}'")
            else:
                check(child, "ssh_file", "Archivo de ~/.ssh escribible por otros", f"chmod go-w '{child}'")
    gnupg = home / ".gnupg"
    if gnupg.is_dir():
        check(gnupg, "gnupg_dir", "~/.gnupg demasiado abierto", f"chmod 700 '{gnupg}'")
    for rc in (".bashrc", ".bash_profile", ".profile", ".zshrc", ".zprofile", ".config/fish/config.fish"):
        check(home / rc, "sensitive", "Script de arranque escribible por cualquiera", f"chmod o-w '{home / rc}'")
    deadline, scanned = time.monotonic() + 15, 0
    for sub in (".ssh", ".gnupg", ".config", ".local/bin", "bin", ".local/share/applications"):
        root = home / sub
        if not root.is_dir():
            continue
        for dirpath, dirnames, filenames in os.walk(root):
            if time.monotonic() > deadline or scanned > 300000:
                ctx.partial_skip("permissions.world-writable", "escaneo acotado por tiempo/archivos")
                return findings
            for name in dirnames + filenames:
                scanned += 1
                check(Path(dirpath) / name, "sensitive", "Escribible por cualquier usuario",
                      f"chmod o-w '{Path(dirpath) / name}'")
    return findings


def probe_backups(ctx: Context) -> list[dict]:
    evidence: list[str] = []
    tools = [t for t in ("timeshift", "snapper", "borg", "restic", "rsnapshot", "btrbk", "kopia",
                         "duplicity", "deja-dup") if find_tool(t)]
    if Path("/etc/timeshift/timeshift.json").is_file() or Path("/etc/timeshift.json").is_file():
        evidence.append("timeshift configurado (/etc/timeshift*)")
    configs = sorted(Path("/etc/snapper/configs").glob("*")) if Path("/etc/snapper/configs").is_dir() else []
    if configs:
        evidence.append("snapper: configuraciones " + ", ".join(p.name for p in configs))
    if Path("/.snapshots").is_dir():
        evidence.append("existe /.snapshots (snapshots btrfs)")
    if Path("/etc/rsnapshot.conf").is_file():
        evidence.append("rsnapshot configurado (/etc/rsnapshot.conf)")
    for scope in ([], ["--user"]):
        res = run(["systemctl", *scope, "list-timers", "--all", "--no-legend", "--plain", "--no-pager"])
        for line in (res.out.splitlines() if res else []):
            if BACKUP_WORDS.search(line):
                units = [p for p in line.split() if p.endswith((".timer", ".service"))]
                evidence.append(f"timer{' de usuario' if scope else ''}: {' '.join(units) or line.strip()[:120]}")
    cron_files = [Path("/etc/crontab"), *sorted(Path("/etc/cron.d").glob("*"))] if Path("/etc/cron.d").is_dir() \
        else [Path("/etc/crontab")]
    for period in ("hourly", "daily", "weekly", "monthly"):
        d = Path(f"/etc/cron.{period}")
        if d.is_dir():
            evidence += [f"cron.{period}: {p.name}" for p in sorted(d.iterdir()) if BACKUP_WORDS.search(p.name)]
    for f in cron_files:
        text = read_text(f) or ""
        evidence += [f"{f}: {l.strip()[:120]}" for l in text.splitlines()
                     if BACKUP_WORDS.search(l) and not l.lstrip().startswith("#")]
    crontab = run(["crontab", "-l"])
    if crontab and crontab.rc == 0:
        evidence += [f"crontab de usuario: {l.strip()[:120]}" for l in crontab.out.splitlines()
                     if BACKUP_WORDS.search(l) and not l.lstrip().startswith("#")]
    for cfg in (".config/borgmatic", ".config/restic", ".config/timeshift", ".config/kopia", ".config/btrbk"):
        if (ctx.home / cfg).exists():
            evidence.append(f"configuración en ~/{cfg}")
    return backup_verdict(evidence, tools)


def probe_docker(ctx: Context) -> list[dict]:
    res = _require(run(["docker", "system", "df", "--format", "{{json .}}"], timeout=60), "docker")
    if res.rc != 0:
        err = res.err.strip()
        if "permission denied" in err.lower():
            return [make_finding(
                "docker", "access", "info", "docker", "Docker requiere privilegios para auditarse",
                err.splitlines()[0][:300] if err else "permission denied",
                "sudo docker system df (o añade tu usuario al grupo docker, que equivale a root)",
                requires_privileges=True)]
        raise Skip(f"el demonio de Docker no responde: {err.splitlines()[0][:200] if err else res.rc}")
    findings = classify_docker_df(res.out.splitlines())
    dangling = run(["docker", "images", "-f", "dangling=true", "-q"], timeout=60)
    count = len(dangling.out.split()) if dangling and dangling.rc == 0 else 0
    if count >= 5:
        findings.append(make_finding(
            "docker", "dangling-images", "low", "docker", f"{count} imágenes colgantes (<none>)",
            f"docker images -f dangling=true → {count}",
            "docker image prune vía la skill janitor-cleanup, con confirmación."))
    return findings


PROBES: dict[str, Callable[[Context], list[dict]]] = {
    "disk": probe_disk,
    "home_usage": probe_home_usage,
    "memory": probe_memory,
    "load": probe_load,
    "systemd_units": probe_systemd_units,
    "unit_flapping": probe_unit_flapping,
    "updates": probe_updates,
    "kernel": probe_kernel,
    "smart": probe_smart,
    "fs_errors": probe_fs_errors,
    "time_sync": probe_time_sync,
    "firewall": probe_firewall,          # before listening_ports/ssh: they read its verdict
    "listening_ports": probe_listening_ports,
    "ssh": probe_ssh,
    "permissions": probe_permissions,
    "backups": probe_backups,
    "docker": probe_docker,
}


def sort_findings(findings: list[dict]) -> list[dict]:
    return sorted(findings, key=lambda f: (SEVERITY_RANK[f["severity"]], f["area"], f["id"]))


def audit(selected: list[str], home: Path, home_budget: float, log=lambda msg: None) -> dict:
    ctx = Context(home, home_budget)
    findings, skipped, probes = [], [], {}
    for name in PROBES:
        if name not in selected:
            continue
        started = time.monotonic()
        try:
            result = PROBES[name](ctx)
            findings += result
            probes[name] = "ok"
            log(f"[{name}] ok: {len(result)} hallazgos ({time.monotonic() - started:.1f}s)")
        except Skip as exc:
            skipped.append({"probe": name, "reason": str(exc)})
            probes[name] = "skipped"
            log(f"[{name}] omitido: {exc}")
        except Exception as exc:  # a broken probe must not sink the whole audit
            skipped.append({"probe": name, "reason": f"error interno: {type(exc).__name__}: {exc}"})
            probes[name] = "error"
            log(f"[{name}] error interno: {exc}")
    skipped += ctx.partial_skips
    findings = sort_findings(findings)
    summary = {sev: sum(1 for f in findings if f["severity"] == sev) for sev in SEVERITIES}
    os_release = parse_kv(read_text("/etc/os-release") or "")
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0).isoformat(),
        "system": {"os": os_release.get("PRETTY_NAME", "").strip('"') or None,
                   "os_id": os_release.get("ID", "").strip('"') or None,
                   "kernel": os.uname().release, "privileged": os.geteuid() == 0},
        "probes": probes,
        "summary": summary,
        "findings": findings,
        "skipped": skipped,
    }


def write_output(path: Path, document: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Auditoría de salud del sistema (solo lectura).")
    parser.add_argument("--output", type=Path, help="Además de stdout, escribe el JSON en este archivo.")
    parser.add_argument("--only", help="Lista de sondas separadas por comas.")
    parser.add_argument("--skip", help="Sondas a omitir, separadas por comas.")
    parser.add_argument("--home-budget", type=float, default=20.0,
                        help="Segundos máximos para medir el directorio personal (por defecto 20).")
    parser.add_argument("--list-probes", action="store_true", help="Lista las sondas y sale.")
    parser.add_argument("--quiet", action="store_true", help="Sin pistas en stderr.")
    args = parser.parse_args(argv)
    if args.list_probes:
        print("\n".join(PROBES))
        return 0
    selected = list(PROBES)
    if args.only:
        selected = [p.strip() for p in args.only.split(",") if p.strip()]
    if args.skip:
        drop = {p.strip() for p in args.skip.split(",")}
        selected = [p for p in selected if p not in drop]
    unknown = [p for p in selected if p not in PROBES]
    if unknown:
        parser.error(f"sondas desconocidas: {', '.join(unknown)} (usa --list-probes)")
    log = (lambda msg: None) if args.quiet else (lambda msg: print(msg, file=sys.stderr))
    if sys.platform != "linux":
        log("Aviso: esta auditoría está pensada para Linux; muchas sondas se omitirán.")
    document = audit(selected, user_home(), args.home_budget, log)
    if args.output:
        try:
            write_output(args.output, document)
        except OSError as exc:
            print(f"No se pudo escribir {args.output}: {exc}", file=sys.stderr)
            return 2
    json.dump(document, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    s = document["summary"]
    log(f"Resumen: {s['critical']} críticos, {s['high']} altos, {s['medium']} medios, "
        f"{s['low']} bajos, {s['info']} informativos; {len(document['skipped'])} omitidos.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
