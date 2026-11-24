"""Safety layer shared by the Janitor file skills (janitor-cleanup, janitor-file-organizer).

Each skill loads in place from its own directory, so this module is shipped as a
byte-identical copy in both ``scripts/`` dirs (a test enforces the copies match).

The contract it implements (AGENTS.md directive #19):
  * every mutation comes from a plan file produced by a read-only ``plan`` step;
  * each path is re-validated at apply time (bounds, denylist, symlinks, git state,
    filesystem, fingerprint) — the plan file is never trusted;
  * removal means the freedesktop.org Trash, never unlink/rmtree; when a
    spec-compliant trash is impossible the item is skipped;
  * nothing here ever calls ``sudo``.

Python 3 stdlib only, Linux.
"""
from __future__ import annotations

import ctypes
import datetime as _dt
import errno
import hashlib
import json
import os
import pwd
import stat
import subprocess
import time
import urllib.parse
from dataclasses import dataclass, field

# --------------------------------------------------------------------------- homes


def _abs_env(name: str) -> str | None:
    value = os.environ.get(name, "")
    return value if value and os.path.isabs(value) else None


def user_home() -> str:
    """The real user's home. Inside the agent's terminal HOME may be redirected;
    HERMES_REAL_HOME then carries the real one."""
    for var in ("HERMES_REAL_HOME", "HOME"):
        value = _abs_env(var)
        if value:
            return os.path.realpath(value)
    return os.path.realpath(pwd.getpwuid(os.getuid()).pw_dir)


def xdg_dir(var: str, default_rel: str, home: str | None = None) -> str:
    value = _abs_env(var)
    return os.path.realpath(value) if value else os.path.join(home or user_home(), default_rel)


def xdg_data_home(home: str | None = None) -> str:
    return xdg_dir("XDG_DATA_HOME", ".local/share", home)


def xdg_cache_home(home: str | None = None) -> str:
    return xdg_dir("XDG_CACHE_HOME", ".cache", home)


def xdg_config_home(home: str | None = None) -> str:
    return xdg_dir("XDG_CONFIG_HOME", ".config", home)


def xdg_state_home(home: str | None = None) -> str:
    return xdg_dir("XDG_STATE_HOME", ".local/state", home)


def home_trash_dir(home: str | None = None) -> str:
    return os.path.join(xdg_data_home(home), "Trash")


def agent_homes(extra: list[str] | None = None) -> list[str]:
    """Agent homes to protect: HERMES_HOME (and, for a profile, the root home
    that holds ``profiles/``), the resolver from hermes_constants when importable,
    and any ``--agent-home`` given on the command line."""
    found: list[str] = []
    candidates = list(extra or [])
    env_home = _abs_env("HERMES_HOME")
    if env_home:
        candidates.append(env_home)
    else:
        try:  # only importable when run inside the agent's own venv
            from hermes_constants import get_hermes_home  # type: ignore

            candidates.append(str(get_hermes_home()))
        except Exception:
            pass
    for cand in candidates:
        real = os.path.realpath(cand)
        found.append(real)
        parent = os.path.dirname(real)
        if os.path.basename(parent) == "profiles":
            found.append(os.path.dirname(parent))
    return sorted(set(found))


def plans_dir() -> str:
    """Default location for plan/undo/result files: inside the agent home, which
    the denylist protects, so no skill can ever act on its own plans."""
    env_home = _abs_env("HERMES_HOME")
    base = os.path.realpath(env_home) if env_home else os.path.join(xdg_state_home(), "janitor")
    return os.path.join(base, "janitor-plans")


def find_executable(name: str) -> str | None:
    """Look *name* up on the user's PATH. The user's own tools (their pip, docker,
    gio) are exactly what these skills act on, so PATH is the right question."""
    for directory in os.environ.get("PATH", "").split(os.pathsep):
        if not directory:
            continue
        candidate = os.path.join(directory, name)
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate
    return None


# --------------------------------------------------------------------------- bounds

SYSTEM_PATHS = (
    "/etc", "/usr", "/var", "/boot", "/bin", "/sbin", "/lib", "/lib32", "/lib64",
    "/proc", "/sys", "/dev", "/run", "/root", "/srv", "/opt", "/snap", "/efi", "/mnt",
    "/media",
)

# Relative to the user's home. Secrets, browser/mail profiles, keyrings, VM storage,
# cloud credentials and the trash itself (emptying it is a tool-command action).
HOME_DENYLIST = (
    ".ssh", ".gnupg", ".password-store", ".local/share/password-store", ".pki",
    ".local/share/keyrings", ".local/share/kwalletd", ".config/keepassxc",
    ".mozilla", ".librewolf", ".waterfox", ".zen", ".floorp", ".thunderbird",
    ".config/google-chrome", ".config/google-chrome-beta", ".config/google-chrome-unstable",
    ".config/chromium", ".config/BraveSoftware", ".config/vivaldi", ".config/opera",
    ".config/microsoft-edge", ".config/thorium", ".var/app",
    ".local/share/libvirt", ".config/libvirt", "VirtualBox VMs", ".vagrant.d",
    ".local/share/gnome-boxes", ".local/share/containers", ".docker", ".kube",
    ".aws", ".azure", ".config/gcloud", ".config/op", ".local/share/Trash",
)

VM_IMAGE_EXTS = (".qcow2", ".qcow", ".vdi", ".vmdk", ".vhd", ".vhdx", ".ova", ".ovf")

AGENT_MARKERS = ("SOUL.md", "config.yaml")


def within(path: str, base: str) -> bool:
    return path == base or path.startswith(base.rstrip("/") + "/")


@dataclass
class Bounds:
    """Resolved roots and protected paths for one run."""

    home: str
    roots: list[str]
    deny: list[str]
    agent: list[str]
    _git_cache: dict = field(default_factory=dict)
    stats_cache: dict = field(default_factory=dict)

    @classmethod
    def build(cls, roots: list[str] | None, agent_home: list[str] | None = None,
              explicit_roots: list[str] | None = None) -> "Bounds":
        """``roots`` may come from a plan file; any root outside the home must also
        appear in ``explicit_roots`` (given on the command line this run)."""
        home = user_home()
        agent = agent_homes(agent_home)
        deny = sorted({os.path.join(home, rel) for rel in HOME_DENYLIST}
                      | {home_trash_dir(home)} | set(agent))
        explicit = {os.path.realpath(r) for r in (explicit_roots or [])}
        resolved: list[str] = []
        for root in roots or [home]:
            real = os.path.realpath(os.path.expanduser(root))
            reason = cls._root_refusal(real, home, deny, explicit)
            if reason:
                raise BoundsError(f"raíz rechazada {real}: {reason}")
            resolved.append(real)
        return cls(home=home, roots=sorted(set(resolved)), deny=deny, agent=agent)

    @staticmethod
    def _root_refusal(real: str, home: str, deny: list[str], explicit: set[str]) -> str | None:
        if real == "/":
            return "la raíz del sistema nunca es una raíz válida"
        if not os.path.isdir(real) or os.path.islink(real):
            return "no es un directorio"
        if not within(real, home):
            if any(within(real, s) for s in SYSTEM_PATHS):
                return "ruta del sistema"
            if real not in explicit:
                return "fuera del home; hay que pasarla con --root en esta ejecución"
        for d in deny:
            if within(real, d):
                return f"protegida ({d})"
        return None

    # ---- per-path validation -------------------------------------------------

    def resolve(self, path: str) -> str:
        """Canonical path of *path* itself: parent resolved, last component kept,
        so a symlink is judged (and moved) as the link, never its target."""
        absolute = os.path.abspath(os.path.expanduser(path))
        name = os.path.basename(absolute)
        return os.path.join(os.path.realpath(os.path.dirname(absolute)), name)

    def root_of(self, real: str) -> str | None:
        best = None
        for root in self.roots:
            if within(real, root) and real != root and (best is None or len(root) > len(best)):
                best = root
        return best

    def refusal(self, path: str, *, check_git: bool = True) -> str | None:
        """Why *path* may not be touched, or None. Fail closed on any doubt."""
        real = self.resolve(path)
        name = os.path.basename(real)
        if name in ("", ".", ".."):
            return "nombre de ruta inválido"
        try:
            st = os.lstat(real)
        except FileNotFoundError:
            return "ya no existe"
        except OSError as exc:
            return f"no se puede leer: {exc.strerror}"
        root = self.root_of(real)
        if root is None:
            return "fuera de las raíces permitidas"
        if stat.S_ISLNK(st.st_mode):
            target = os.path.realpath(real)
            if self.root_of(target) is None and target not in self.roots:
                return "enlace simbólico que apunta fuera de las raíces"
        if not within(real, self.home) and any(within(real, s) for s in SYSTEM_PATHS):
            return "ruta del sistema"
        for d in self.deny:
            if within(real, d):
                return f"ruta protegida ({os.path.relpath(d, self.home) if within(d, self.home) else d})"
            if within(d, real):
                return "contiene una ruta protegida"
        rel_parts = os.path.relpath(real, root).split(os.sep)
        if ".git" in rel_parts:
            return "metadatos de git"
        if name.lower().endswith(VM_IMAGE_EXTS):
            return "imagen de máquina virtual"
        try:
            if os.lstat(root).st_dev != st.st_dev:
                return "otro sistema de archivos (montaje dentro de la raíz)"
        except OSError:
            return "raíz inaccesible"
        marker = self._agent_marker_ancestor(real, root)
        if marker:
            return f"home de un agente ({marker})"
        if stat.S_ISDIR(st.st_mode):
            ts = tree_stats(real)
            self.stats_cache[real] = ts
            if ts.has_git:
                return "contiene un repositorio git"
            if ts.agent_marker:
                return "contiene el home de un agente"
            if ts.foreign_dev:
                return "contiene un punto de montaje"
            if ts.truncated:
                return "no se pudo recorrer completo"
        if check_git:
            reason = self.git_refusal(real)
            if reason:
                return reason
        return None

    def _agent_marker_ancestor(self, real: str, root: str) -> str | None:
        cur = os.path.dirname(real) if not os.path.isdir(real) or os.path.islink(real) else real
        while within(cur, root):
            if all(os.path.isfile(os.path.join(cur, m)) for m in AGENT_MARKERS):
                return cur
            if cur == root:
                break
            cur = os.path.dirname(cur)
        return None

    # ---- git -------------------------------------------------------------------

    def git_top(self, real: str) -> str | None:
        cur = os.path.dirname(real)
        while True:
            if os.path.lexists(os.path.join(cur, ".git")):
                return cur
            parent = os.path.dirname(cur)
            if parent == cur:
                return None
            cur = parent

    def git_refusal(self, real: str) -> str | None:
        top = self.git_top(real)
        if top is None:
            return None
        if top not in self._git_cache:
            self._git_cache[top] = git_dirty_reason(top)
        reason = self._git_cache[top]
        return f"repositorio git con {reason}" if reason else None


class BoundsError(Exception):
    pass


def _git(top: str, *args: str) -> subprocess.CompletedProcess:
    env = dict(os.environ, GIT_OPTIONAL_LOCKS="0", LC_ALL="C")
    return subprocess.run(
        ["git", "-c", "core.fsmonitor=false", "-C", top, *args],
        capture_output=True, text=True, timeout=30, env=env, check=False)


def git_dirty_reason(top: str) -> str | None:
    """None when the work tree is clean and fully pushed; otherwise why not.
    Fails closed: no git binary or any git error counts as dirty."""
    if find_executable("git") is None:
        return "estado desconocido (git no está instalado)"
    try:
        status = _git(top, "status", "--porcelain=v1", "--untracked-files=normal")
        if status.returncode != 0:
            return "estado desconocido (git falló)"
        if status.stdout.strip():
            return "cambios sin commit"
        stash = _git(top, "stash", "list")
        if stash.returncode != 0 or stash.stdout.strip():
            return "stash pendiente"
        unpushed = _git(top, "rev-list", "--count", "--branches", "--not", "--remotes")
        if unpushed.returncode != 0:
            return "estado desconocido (git falló)"
        if unpushed.stdout.strip() not in ("", "0"):
            return "commits sin push"
    except (OSError, subprocess.TimeoutExpired):
        return "estado desconocido (git no respondió)"
    return None


def git_ignored(top: str, real: str) -> bool:
    try:
        return _git(top, "check-ignore", "-q", "--", real).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


# --------------------------------------------------------------------------- budgets & walks


class Budget:
    """Run-wide time budget plus a file-count budget per phase (category), so one
    huge cache cannot starve the rest of the scan. Hits are reported, never silent."""

    def __init__(self, max_seconds: float, max_files: int):
        self.deadline = time.monotonic() + max_seconds
        self.max_files = max_files
        self.files = 0
        self.hits: list[str] = []
        self._phase = ""
        self._phase_hit = False
        self._timed_out = False

    def phase(self, name: str) -> None:
        self._phase, self.files, self._phase_hit = name, 0, False

    def tick(self, n: int = 1) -> bool:
        self.files += n
        if self._timed_out or self._phase_hit:
            return False
        if self.files > self.max_files:
            self._phase_hit = True
            label = f"{self._phase}: " if self._phase else ""
            self.hits.append(f"{label}límite de archivos ({self.max_files})")
        elif self.files % 256 == 0 and time.monotonic() > self.deadline:
            self._timeout()
        return not (self._timed_out or self._phase_hit)

    def _timeout(self) -> None:
        if not self._timed_out:
            self._timed_out = True
            label = f" (en {self._phase})" if self._phase else ""
            self.hits.append(f"límite de tiempo{label}")

    @property
    def exhausted(self) -> bool:
        if not self._timed_out and time.monotonic() > self.deadline:
            self._timeout()
        return self._timed_out or self._phase_hit

    @property
    def hit(self) -> str | None:
        return "; ".join(self.hits) or None


@dataclass
class TreeStats:
    files: int = 0
    size: int = 0          # apparent bytes
    disk: int = 0          # allocated bytes (what deleting would reclaim)
    max_mtime_ns: int = 0
    has_git: bool = False
    foreign_dev: bool = False
    agent_marker: bool = False
    truncated: bool = False


def tree_stats(path: str, budget: Budget | None = None, max_entries: int | None = None) -> TreeStats:
    """Stats of a file or directory tree. Never follows symlinks, never leaves the
    filesystem of *path*, counts each inode once."""
    out = TreeStats()
    try:
        top = os.lstat(path)
    except OSError:
        return out
    seen: set[tuple[int, int]] = set()

    def account(st: os.stat_result) -> None:
        out.max_mtime_ns = max(out.max_mtime_ns, st.st_mtime_ns)
        key = (st.st_dev, st.st_ino)
        if key in seen:
            return
        seen.add(key)
        out.files += 1
        out.size += st.st_size
        out.disk += st.st_blocks * 512

    account(top)
    if not stat.S_ISDIR(top.st_mode):
        return out
    stack = [path]
    count = 0
    while stack:
        current = stack.pop()
        try:
            names = os.listdir(current)
        except OSError:
            continue
        if all(m in names for m in AGENT_MARKERS):
            out.agent_marker = True
        for name in names:
            count += 1
            if (budget is not None and not budget.tick()) or (max_entries and count > max_entries):
                out.truncated = True
                return out
            child = os.path.join(current, name)
            try:
                st = os.lstat(child)
            except OSError:
                continue
            if name == ".git":
                out.has_git = True
            if st.st_dev != top.st_dev:
                out.foreign_dev = True
                continue
            account(st)
            if stat.S_ISDIR(st.st_mode):
                stack.append(child)
    return out


def fingerprint(path: str, budget: Budget | None = None,
                stats: TreeStats | None = None) -> dict | None:
    """Identity of *path* at plan time; apply skips anything whose fingerprint moved."""
    try:
        st = os.lstat(path)
    except OSError:
        return None
    if stat.S_ISLNK(st.st_mode):
        return {"kind": "link", "target": os.readlink(path), "ino": st.st_ino}
    if stat.S_ISREG(st.st_mode):
        return {"kind": "file", "size": st.st_size, "mtime_ns": st.st_mtime_ns,
                "ino": st.st_ino, "dev": st.st_dev}
    if stat.S_ISDIR(st.st_mode):
        ts = stats if stats is not None else tree_stats(path, budget)
        return {"kind": "dir", "files": ts.files, "size": ts.size,
                "max_mtime_ns": ts.max_mtime_ns, "ino": st.st_ino, "dev": st.st_dev,
                "truncated": ts.truncated}
    return {"kind": "other"}


def fingerprint_matches(path: str, expected: dict | None,
                        stats: TreeStats | None = None) -> tuple[bool, str]:
    if not isinstance(expected, dict) or "kind" not in expected:
        return False, "el plan no trae huella del archivo"
    if expected.get("truncated"):
        return False, "la huella del plan quedó incompleta (presupuesto agotado)"
    current = fingerprint(path, stats=stats)
    if current is None:
        return False, "ya no existe"
    if current.get("truncated"):
        return False, "no se pudo recalcular la huella completa"
    if current != expected:
        return False, "cambió desde el plan"
    return True, ""


# --------------------------------------------------------------------------- moves

_AT_FDCWD = -100
_RENAME_NOREPLACE = 1
try:
    _LIBC = ctypes.CDLL(None, use_errno=True)
    _RENAMEAT2 = getattr(_LIBC, "renameat2", None)
except OSError:  # pragma: no cover - static binaries
    _RENAMEAT2 = None


def rename_noreplace(src: str, dst: str) -> None:
    """Atomic rename that fails with FileExistsError instead of replacing *dst*."""
    if _RENAMEAT2 is not None:
        rc = _RENAMEAT2(_AT_FDCWD, os.fsencode(src), _AT_FDCWD, os.fsencode(dst), _RENAME_NOREPLACE)
        if rc == 0:
            return
        err = ctypes.get_errno()
        if err not in (errno.ENOSYS, errno.EINVAL):
            raise OSError(err, os.strerror(err), dst)
    if os.path.lexists(dst):
        raise FileExistsError(errno.EEXIST, "ya existe", dst)
    os.rename(src, dst)


# --------------------------------------------------------------------------- trash


class TrashError(Exception):
    pass


def _device_of(path: str) -> int:
    cur = path
    while not os.path.exists(cur):
        cur = os.path.dirname(cur)
    return os.stat(cur).st_dev


def _mount_top(path: str, dev: int) -> str:
    cur = os.path.dirname(path)
    while True:
        parent = os.path.dirname(cur)
        if parent == cur:
            return cur
        try:
            if os.lstat(parent).st_dev != dev:
                return cur
        except OSError:
            return cur
        cur = parent


def _ensure_private_dir(path: str, *, must_own: bool = True) -> None:
    os.makedirs(path, mode=0o700, exist_ok=True)
    st = os.lstat(path)
    if stat.S_ISLNK(st.st_mode) or not stat.S_ISDIR(st.st_mode):
        raise TrashError(f"{path} no es un directorio de papelera válido")
    if must_own and st.st_uid != os.getuid():
        raise TrashError(f"{path} no pertenece al usuario")


def trash_location(real: str, home: str | None = None) -> tuple[str, str | None]:
    """(trash dir, topdir) per the freedesktop.org Trash spec; topdir is None for the
    home trash. Raises TrashError when no compliant trash exists for *real*."""
    st = os.lstat(real)
    home_trash = home_trash_dir(home)
    if _device_of(home_trash) == st.st_dev:
        return home_trash, None
    uid = str(os.getuid())
    top = _mount_top(real, st.st_dev)
    admin = os.path.join(top, ".Trash")
    try:
        ast = os.lstat(admin)
        if stat.S_ISDIR(ast.st_mode) and not stat.S_ISLNK(ast.st_mode) and ast.st_mode & stat.S_ISVTX:
            return os.path.join(admin, uid), top
    except OSError:
        pass
    return os.path.join(top, f".Trash-{uid}"), top


def _encode_trash_path(value: str) -> str:
    return urllib.parse.quote(os.fsencode(value), safe="/")


def _decode_trash_path(value: str) -> str:
    return os.fsdecode(urllib.parse.unquote_to_bytes(value))


def _read_trashinfo(info_path: str) -> dict:
    data: dict = {}
    try:
        with open(info_path, encoding="utf-8", errors="surrogateescape") as fh:
            for line in fh:
                key, sep, value = line.rstrip("\n").partition("=")
                if sep and key in ("Path", "DeletionDate"):
                    data[key] = value
    except OSError:
        pass
    return data


class Trash:
    """Move paths to the freedesktop.org Trash. ``backend``: auto (gio when present,
    else the stdlib implementation), gio, or python. There is no delete fallback."""

    def __init__(self, backend: str = "auto"):
        if backend not in ("auto", "gio", "python"):
            raise ValueError(backend)
        self.gio = find_executable("gio") if backend in ("auto", "gio") else None
        if backend == "gio" and not self.gio:
            raise TrashError("gio no está instalado")
        self.home = user_home()

    def put(self, real: str) -> dict:
        try:
            tdir, top = trash_location(real, self.home)
        except OSError as exc:
            raise TrashError(f"no se puede inspeccionar: {exc.strerror}") from exc
        if self.gio:
            record = self._put_gio(real, tdir, top)
            if record:
                return record
        return self._put_python(real, tdir, top)

    def _put_gio(self, real: str, tdir: str, top: str | None) -> dict | None:
        started = time.time() - 1
        try:
            proc = subprocess.run([self.gio, "trash", "--", real], capture_output=True,
                                  text=True, timeout=120, check=False)
        except (OSError, subprocess.TimeoutExpired):
            return None
        if proc.returncode != 0 or os.path.lexists(real):
            return None
        info = find_trashinfo(real, tdir, top, started)
        if info is None:
            return {"backend": "gio", "original": real, "trash_dir": tdir,
                    "files": None, "info": None}
        name = os.path.basename(info)[: -len(".trashinfo")]
        return {"backend": "gio", "original": real, "trash_dir": tdir,
                "files": os.path.join(tdir, "files", name), "info": info}

    def _put_python(self, real: str, tdir: str, top: str | None) -> dict:
        try:
            _ensure_private_dir(tdir)
            files_dir = os.path.join(tdir, "files")
            info_dir = os.path.join(tdir, "info")
            _ensure_private_dir(files_dir)
            _ensure_private_dir(info_dir)
        except OSError as exc:
            raise TrashError(f"no se puede crear la papelera en {tdir}: {exc.strerror}") from exc
        if os.stat(files_dir).st_dev != os.lstat(real).st_dev:
            raise TrashError("la papelera está en otro sistema de archivos")
        base = os.path.basename(real)
        path_value = real if top is None else os.path.relpath(real, top)
        when = _dt.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
        body = f"[Trash Info]\nPath={_encode_trash_path(path_value)}\nDeletionDate={when}\n"
        for i in range(10000):
            name = base if i == 0 else f"{base}.{i}"
            info_path = os.path.join(info_dir, name + ".trashinfo")
            files_path = os.path.join(files_dir, name)
            if os.path.lexists(files_path):
                continue
            try:
                fd = os.open(info_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            except FileExistsError:
                continue
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(body)
            try:
                rename_noreplace(real, files_path)
            except FileExistsError:
                os.unlink(info_path)  # our own just-written metadata, not user data
                continue
            except OSError as exc:
                os.unlink(info_path)
                raise TrashError(f"no se pudo mover a la papelera: {exc.strerror}") from exc
            return {"backend": "python", "original": real, "trash_dir": tdir,
                    "files": files_path, "info": info_path}
        raise TrashError("no hay nombre libre en la papelera")


def find_trashinfo(real: str, tdir: str, top: str | None, since: float) -> str | None:
    """The newest .trashinfo in *tdir* written after *since* that points at *real*."""
    info_dir = os.path.join(tdir, "info")
    try:
        names = os.listdir(info_dir)
    except OSError:
        return None
    best = None
    for name in names:
        if not name.endswith(".trashinfo"):
            continue
        full = os.path.join(info_dir, name)
        try:
            mtime = os.stat(full).st_mtime
        except OSError:
            continue
        if mtime < since:
            continue
        raw = _read_trashinfo(full).get("Path")
        if raw is None:
            continue
        decoded = _decode_trash_path(raw)
        original = decoded if os.path.isabs(decoded) else os.path.join(top or "/", decoded)
        if original == real and (best is None or mtime >= best[0]):
            best = (mtime, full)
    return best[1] if best else None


def restore_from_trash(record: dict) -> tuple[bool, str]:
    """Undo one Trash.put(): move the item back and drop its .trashinfo."""
    files_path, info_path, original = record.get("files"), record.get("info"), record.get("original")
    if not files_path or not info_path or not original:
        return False, "sin ubicación en la papelera; restaurar desde el gestor de archivos"
    if not os.path.lexists(files_path):
        return False, "ya no está en la papelera"
    info = _read_trashinfo(info_path)
    raw = info.get("Path")
    if raw is None:
        return False, ".trashinfo ilegible"
    decoded = _decode_trash_path(raw)
    tdir = os.path.dirname(os.path.dirname(info_path))
    top = None if os.path.isabs(decoded) else os.path.dirname(
        tdir if os.path.basename(tdir).startswith(".Trash-") else os.path.dirname(tdir))
    target = decoded if top is None else os.path.join(top, decoded)
    if target != original:
        return False, "el .trashinfo no coincide con el registro"
    os.makedirs(os.path.dirname(original), exist_ok=True)
    try:
        rename_noreplace(files_path, original)
    except FileExistsError:
        return False, "ya existe un archivo en la ruta original"
    except OSError as exc:
        return False, exc.strerror or "error al mover"
    os.unlink(info_path)  # metadata only; the data is back in place
    return True, ""


def trash_items(trash_dir: str) -> list[dict]:
    """Items in one trash dir with their deletion date (for the trash-age report)."""
    items = []
    info_dir = os.path.join(trash_dir, "info")
    try:
        names = os.listdir(info_dir)
    except OSError:
        return items
    for name in names:
        if not name.endswith(".trashinfo"):
            continue
        data = _read_trashinfo(os.path.join(info_dir, name))
        try:
            when = _dt.datetime.strptime(data.get("DeletionDate", ""), "%Y-%m-%dT%H:%M:%S")
        except ValueError:
            continue
        items.append({"name": name[: -len(".trashinfo")], "deleted": when.timestamp(),
                      "files": os.path.join(trash_dir, "files", name[: -len(".trashinfo")])})
    return items


# --------------------------------------------------------------------------- duplicates

_PARTIAL = 64 * 1024


def _hash_file(path: str, limit: int | None, budget: Budget | None) -> str | None:
    h = hashlib.sha256()
    try:
        with open(path, "rb", buffering=0) as fh:
            remaining = limit
            while True:
                if budget is not None and budget.exhausted:
                    return None
                chunk = fh.read(1024 * 1024 if remaining is None else min(remaining, 1024 * 1024))
                if not chunk:
                    break
                h.update(chunk)
                if remaining is not None:
                    remaining -= len(chunk)
                    if remaining <= 0:
                        break
    except OSError:
        return None
    return h.hexdigest()


def find_duplicates(files: list[tuple[str, int]], budget: Budget | None = None,
                    max_bytes: int | None = None) -> tuple[list[dict], bool]:
    """Group identical files: size → first 64 KiB hash → full hash. Hard links are
    one file. Returns (groups, complete) where each group is {size, sha256, paths}."""
    by_size: dict[int, list[str]] = {}
    seen_inodes: set[tuple[int, int]] = set()
    for path, size in files:
        try:
            st = os.lstat(path)
        except OSError:
            continue
        key = (st.st_dev, st.st_ino)
        if key in seen_inodes or not stat.S_ISREG(st.st_mode):
            continue
        seen_inodes.add(key)
        by_size.setdefault(size, []).append(path)
    hashed = 0
    groups: list[dict] = []
    for size in sorted((s for s, p in by_size.items() if len(p) > 1), reverse=True):
        by_partial: dict[str, list[str]] = {}
        for path in by_size[size]:
            digest = _hash_file(path, _PARTIAL, budget)
            if digest is None:
                if budget is not None and budget.exhausted:
                    return groups, False
                continue
            by_partial.setdefault(digest, []).append(path)
        for paths in by_partial.values():
            if len(paths) < 2:
                continue
            by_full: dict[str, list[str]] = {}
            for path in paths:
                if max_bytes is not None and hashed + size > max_bytes:
                    return groups, False
                digest = _hash_file(path, None, budget) if size > _PARTIAL else _hash_file(path, _PARTIAL, budget)
                hashed += size
                if digest is None:
                    if budget is not None and budget.exhausted:
                        return groups, False
                    continue
                by_full.setdefault(digest, []).append(path)
            for digest, same in by_full.items():
                if len(same) > 1:
                    groups.append({"size": size, "sha256": digest, "paths": sorted(same)})
    return groups, True


# --------------------------------------------------------------------------- write-ahead journal


class JournalError(Exception):
    pass


class Journal:
    """Append-only JSONL write-ahead journal. Each record is flushed and fsynced
    before append() returns, so the caller only acts on what is already durable.
    Created exclusively: an existing journal is never reused or truncated."""

    def __init__(self, path: str, header: dict):
        self.path = path
        self._seq = 0
        try:
            os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_APPEND, 0o600)
        except FileExistsError as exc:
            raise JournalError(f"ya existe {path}") from exc
        except OSError as exc:
            raise JournalError(f"no se puede crear {path}: {exc.strerror}") from exc
        self._fh = os.fdopen(fd, "a", encoding="utf-8")
        self.append(header)
        try:
            dfd = os.open(os.path.dirname(os.path.abspath(path)), os.O_RDONLY)
            try:
                os.fsync(dfd)
            finally:
                os.close(dfd)
        except OSError as exc:
            raise JournalError(f"no se puede sincronizar {path}: {exc.strerror}") from exc

    def next_seq(self) -> int:
        self._seq += 1
        return self._seq

    def append(self, record: dict) -> None:
        try:
            self._fh.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
            self._fh.flush()
            os.fsync(self._fh.fileno())
        except (OSError, ValueError) as exc:
            raise JournalError(f"no se puede escribir {self.path}: {exc}") from exc

    def close(self) -> None:
        try:
            self._fh.close()
        except OSError:
            pass


def read_journal(path: str, schema: str) -> tuple[dict, list[dict]]:
    """(header, records). A torn final line (crash mid-write) is ignored; any other
    damage is an error."""
    try:
        with open(path, encoding="utf-8") as fh:
            lines = fh.read().split("\n")
    except OSError as exc:
        raise SystemExit(f"error: no se puede leer {path}: {exc.strerror}") from exc
    if lines and lines[-1] == "":
        lines.pop()
    records = []
    for i, line in enumerate(lines):
        try:
            records.append(json.loads(line))
        except ValueError:
            if i == len(lines) - 1:
                break
            raise SystemExit(f"error: {path} dañado en la línea {i + 1}")
    if not records or not isinstance(records[0], dict) or records[0].get("schema") != schema:
        raise SystemExit(f"error: {path} no es un diario '{schema}'")
    return records[0], [r for r in records[1:] if isinstance(r, dict)]


def journal_ops(records: list[dict]) -> list[dict]:
    """Fold pending/outcome records by seq: each op gets 'outcome' = done, failed or
    None (pending without outcome: the process died between the two records)."""
    ops: dict[int, dict] = {}
    for r in records:
        seq = r.get("seq")
        if not isinstance(seq, int):
            continue
        if r.get("state") == "pending":
            ops[seq] = {**r, "outcome": None}
        elif seq in ops and r.get("state") in ("done", "failed"):
            ops[seq]["outcome"] = r["state"]
            ops[seq]["result"] = r
    return [ops[k] for k in sorted(ops)]


# --------------------------------------------------------------------------- plan files


def write_json(path: str, data: dict) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    tmp = f"{path}.tmp-{os.getpid()}"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=1, sort_keys=False)
        fh.write("\n")
    os.replace(tmp, path)


def load_json(path: str, schema: str) -> dict:
    try:
        st = os.lstat(path)
    except OSError as exc:
        raise SystemExit(f"error: no existe el archivo {path}: {exc.strerror}") from exc
    if not stat.S_ISREG(st.st_mode):
        raise SystemExit(f"error: {path} no es un archivo regular")
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError) as exc:
        raise SystemExit(f"error: {path} no es JSON válido: {exc}") from exc
    if not isinstance(data, dict) or data.get("schema") != schema:
        raise SystemExit(f"error: {path} no es un archivo '{schema}'")
    if not isinstance(data.get("entries"), list):
        raise SystemExit(f"error: {path} no tiene lista de entradas")
    return data


def digest(payload: object) -> str:
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def human(n: int | float) -> str:
    value = float(n)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if abs(value) < 1024 or unit == "TiB":
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} TiB"


def now_iso() -> str:
    return _dt.datetime.now().astimezone().isoformat(timespec="seconds")
