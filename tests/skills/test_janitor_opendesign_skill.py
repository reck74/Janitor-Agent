"""OpenDesign integration owns only the requested checkout and Janitor scope."""

from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import os
from pathlib import Path
import subprocess
import shutil
import shlex
import threading

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "skills/janitor-opendesign/scripts"


def test_opendesign_copies_its_bundled_icon_to_requested_checkout(tmp_path):
    source = tmp_path / "isolated open design"
    icon_dir = source / "apps/web/public/agent-icons"
    icon_dir.mkdir(parents=True)
    env = {**os.environ, "HOME": str(tmp_path / "home"), "OD_SOURCE_DIR": str(source)}
    for _ in range(2):
        result = subprocess.run(["bash", str(SCRIPTS / "03-copy-icon.sh")], env=env,
                                capture_output=True, text=True, check=False, timeout=10)
        assert result.returncode == 0, result.stderr
        assert (icon_dir / "janitor.png").read_bytes() == (SCRIPTS.parent / "icon/janitor.png").read_bytes()


def test_opendesign_installer_uses_owned_scope_and_propagates_failure(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "package.json").write_text('{}')
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    capture = tmp_path / "scope-arguments"
    systemd = bin_dir / "systemd-run"
    systemd.write_text('#!/bin/sh\nprintf "%s\\n" "$@" > "$SCOPE_ARGS"\nexit 17\n')
    systemd.chmod(0o755)
    env = {**os.environ, "HOME": str(tmp_path / "home"), "OD_INSTALL_DIR": str(source),
           "PATH": str(bin_dir) + os.pathsep + os.environ["PATH"], "SCOPE_ARGS": str(capture)}
    result = subprocess.run(["bash", str(SCRIPTS / "safe-pnpm-install.sh"), "install", "--frozen-lockfile"],
                            env=env, capture_output=True, text=True, check=False, timeout=10)
    assert result.returncode == 17, result.stderr
    args = capture.read_text().splitlines()
    assert any(arg.startswith("--unit=janitor-") for arg in args), args
    assert args[-3:] == ["pnpm", "install", "--frozen-lockfile"]


@contextmanager
def _health_server(status):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(status)
            self.end_headers()
            self.wfile.write(b'{"version":"test-release"}')

        def log_message(self, *_args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_address[1]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


@pytest.mark.parametrize("daemon_status,web_status,expected", [(200, 200, 0), (503, 200, 1), (200, 503, 1)])
def test_opendesign_status_requires_both_services(daemon_status, web_status, expected, tmp_path):
    with _health_server(daemon_status) as daemon_port, _health_server(web_status) as web_port:
        result = subprocess.run(
            ["bash", str(SCRIPTS / "status.sh")],
            env={**os.environ, "HOME": str(tmp_path), "OD_DAEMON_PORT": str(daemon_port),
                 "OD_WEB_PORT": str(web_port)},
            capture_output=True, text=True, check=False, timeout=15,
        )
    assert result.returncode == expected, result.stdout + result.stderr
    assert ("DOWN" in result.stdout) is bool(expected)


@pytest.mark.parametrize(("actual_version", "expected"), [("v24.21.0", 0), ("v26.12.0", 2), ("unavailable", 2)])
def test_opendesign_gate_checks_executed_node_not_a_separate_mise_node(tmp_path, actual_version, expected):
    source = tmp_path / "source"
    source.mkdir()
    (source / "package.json").write_text('{"engines":{"node":"~24"}}')
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    # BSD grep rejects PCRE; that failure must never turn a version mismatch into success.
    unsupported = tmp_path / "unsupported-grep-option"
    grep = bin_dir / "grep"
    grep.write_text('#!/bin/sh\nfor arg do case "$arg" in -*P*) '
                    f'touch {shlex.quote(str(unsupported))}; exit 2;; esac; done\n'
                    f'exec {shlex.quote(shutil.which("grep"))} "$@"\n')
    grep.chmod(0o755)
    for name, body in {"mise": "echo v24.21.0", "node": f"echo {actual_version}"}.items():
        script = bin_dir / name
        script.write_text("#!/bin/sh\n" + body + "\n")
        script.chmod(0o755)
    result = subprocess.run(
        ["bash", str(SCRIPTS / "check-node-version.sh")],
        env={**os.environ, "OD_INSTALL_DIR": str(source), "PATH": str(bin_dir) + os.pathsep + os.environ["PATH"]},
        capture_output=True, text=True, check=False, timeout=10,
    )
    assert result.returncode == expected, result.stdout + result.stderr
    assert not unsupported.exists(), "Node gate relies on a GNU-only grep option"
    if expected == 0:
        assert "OK: Node" in result.stderr


def test_opendesign_orchestrator_routes_source_override_to_same_runtime(tmp_path):
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    (scripts / "integrate-janitor.sh").write_bytes((SCRIPTS / "integrate-janitor.sh").read_bytes())
    capture = tmp_path / "runtime-root"
    for name in ["check-node-version.sh", "status.sh"]:
        (scripts / name).write_text('#!/bin/sh\nprintf "%s\n" "$OD_INSTALL_DIR" >> "$ROOT_CAPTURE"\n')
    source = tmp_path / "requested-checkout"
    source.mkdir()
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "janitor").write_text("#!/bin/sh\nexit 0\n")
    (bin_dir / "janitor").chmod(0o755)
    env = {**os.environ, "OD_SOURCE_DIR": str(source), "ROOT_CAPTURE": str(capture),
           "PATH": str(bin_dir) + os.pathsep + os.environ["PATH"]}
    env.pop("OD_INSTALL_DIR", None)
    result = subprocess.run(["bash", str(scripts / "integrate-janitor.sh"), "status"],
                            env=env, capture_output=True, text=True, check=False, timeout=10)
    assert result.returncode == 0, result.stdout + result.stderr
    assert capture.read_text().splitlines() == [str(source), str(source)]



def test_opendesign_start_forwards_headless_target_and_failure(tmp_path):
    source = tmp_path / "source"
    binary = source / "node_modules/.bin/tools-dev"
    binary.parent.mkdir(parents=True)
    (source / "package.json").write_text('{}')
    capture = tmp_path / "start-args"
    binary.write_text('#!/bin/sh\nprintf "%s\n" "$@" > "$START_ARGS"\nexit 19\n')
    binary.chmod(0o755)
    result = subprocess.run(
        ["bash", str(SCRIPTS / "start.sh"), "web", "--no-env-file"],
        env={**os.environ, "OD_SOURCE_DIR": str(source), "START_ARGS": str(capture),
             "OD_DAEMON_PORT": "56471", "OD_WEB_PORT": "56472"},
        capture_output=True, text=True, check=False, timeout=10,
    )
    assert result.returncode == 19, result.stdout + result.stderr
    assert capture.read_text().splitlines() == ["start", "web", "--no-env-file", "--daemon-port", "56471", "--web-port", "56472"]
