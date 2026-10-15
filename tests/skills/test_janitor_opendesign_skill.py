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


def test_opendesign_copies_its_bundled_icon_to_requested_checkout(tmp_path, janitor_bash):
    source = tmp_path / "isolated open design"
    icon_dir = source / "apps/web/public/agent-icons"
    icon_dir.mkdir(parents=True)
    env = {**os.environ, "HOME": (tmp_path / "home").as_posix(), "OD_SOURCE_DIR": source.as_posix()}
    for _ in range(2):
        result = subprocess.run([janitor_bash, (SCRIPTS / "03-copy-icon.sh").as_posix()], env=env,
                                capture_output=True, text=True, check=False, timeout=10)
        assert result.returncode == 0, result.stderr
        assert (icon_dir / "janitor.png").read_bytes() == (SCRIPTS.parent / "icon/janitor.png").read_bytes()


def test_opendesign_installer_uses_owned_scope_and_propagates_failure(tmp_path, janitor_bash):
    source = tmp_path / "source"
    source.mkdir()
    (source / "package.json").write_text('{}', encoding='utf-8', newline='\n')
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    capture = tmp_path / "scope-arguments"
    systemd = bin_dir / "systemd-run"
    systemd.write_text('#!/bin/sh\nprintf "%s\\n" "$@" > "$SCOPE_ARGS"\nexit 17\n', encoding='utf-8', newline='\n')
    systemd.chmod(0o755)
    env = {**os.environ, "HOME": (tmp_path / "home").as_posix(), "OD_INSTALL_DIR": source.as_posix(),
           "PATH": bin_dir.as_posix() + os.pathsep + os.environ["PATH"], "SCOPE_ARGS": capture.as_posix()}
    result = subprocess.run([janitor_bash, (SCRIPTS / "safe-pnpm-install.sh").as_posix(), "install", "--frozen-lockfile"],
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
def test_opendesign_status_requires_both_services(daemon_status, web_status, expected, tmp_path, janitor_bash):
    with _health_server(daemon_status) as daemon_port, _health_server(web_status) as web_port:
        result = subprocess.run(
            [janitor_bash, (SCRIPTS / "status.sh").as_posix()],
            env={**os.environ, "HOME": tmp_path.as_posix(), "OD_DAEMON_PORT": str(daemon_port),
                 "OD_WEB_PORT": str(web_port)},
            capture_output=True, text=True, check=False, timeout=15,
        )
    assert result.returncode == expected, result.stdout + result.stderr
    assert ("DOWN" in result.stdout) is bool(expected)


@pytest.mark.parametrize(("actual_version", "expected"), [("v24.21.0", 0), ("v26.12.0", 2), ("unavailable", 2)])
def test_opendesign_gate_checks_executed_node_not_a_separate_mise_node(tmp_path, actual_version, expected, janitor_bash):
    source = tmp_path / "source"
    source.mkdir()
    (source / "package.json").write_text('{"engines":{"node":"~24"}}', encoding='utf-8', newline='\n')
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    # BSD grep rejects PCRE; that failure must never turn a version mismatch into success.
    unsupported = tmp_path / "unsupported-grep-option"
    grep = bin_dir / "grep"
    grep.write_text('#!/bin/sh\nfor arg do case "$arg" in -*P*) '
                    f'touch {shlex.quote(unsupported.as_posix())}; exit 2;; esac; done\n'
                    f'exec {shlex.quote(Path(shutil.which("grep")).as_posix())} "$@"\n', encoding='utf-8', newline='\n')
    grep.chmod(0o755)
    for name, body in {"mise": "echo v24.21.0", "node": f"echo {actual_version}"}.items():
        script = bin_dir / name
        script.write_text("#!/bin/sh\n" + body + "\n", encoding='utf-8', newline='\n')
        script.chmod(0o755)
    result = subprocess.run(
        [janitor_bash, (SCRIPTS / "check-node-version.sh").as_posix()],
        env={**os.environ, "OD_INSTALL_DIR": source.as_posix(), "PATH": bin_dir.as_posix() + os.pathsep + os.environ["PATH"]},
        capture_output=True, text=True, check=False, timeout=10,
    )
    assert result.returncode == expected, result.stdout + result.stderr
    assert not unsupported.exists(), "Node gate relies on a GNU-only grep option"
    if expected == 0:
        assert "OK: Node" in result.stderr


def test_opendesign_orchestrator_routes_source_override_to_same_runtime(tmp_path, janitor_bash):
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    (scripts / "integrate-janitor.sh").write_bytes((SCRIPTS / "integrate-janitor.sh").read_bytes())
    capture = tmp_path / "runtime-root"
    for name in ["check-node-version.sh", "status.sh"]:
        (scripts / name).write_text('#!/bin/sh\nprintf "%s\n" "$OD_INSTALL_DIR" >> "$ROOT_CAPTURE"\n', encoding='utf-8', newline='\n')
    source = tmp_path / "requested-checkout"
    source.mkdir()
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "janitor").write_text("#!/bin/sh\nexit 0\n", encoding='utf-8', newline='\n')
    (bin_dir / "janitor").chmod(0o755)
    env = {**os.environ, "OD_SOURCE_DIR": source.as_posix(), "ROOT_CAPTURE": capture.as_posix(),
           "PATH": bin_dir.as_posix() + os.pathsep + os.environ["PATH"]}
    env.pop("OD_INSTALL_DIR", None)
    result = subprocess.run([janitor_bash, (scripts / "integrate-janitor.sh").as_posix(), "status"],
                            env=env, capture_output=True, text=True, check=False, timeout=10)
    assert result.returncode == 0, result.stdout + result.stderr
    assert capture.read_text().splitlines() == [source.as_posix(), source.as_posix()]



def test_opendesign_start_forwards_headless_target_and_failure(tmp_path, janitor_bash):
    source = tmp_path / "source"
    binary = source / "node_modules/.bin/tools-dev"
    binary.parent.mkdir(parents=True)
    (source / "package.json").write_text('{}', encoding='utf-8', newline='\n')
    capture = tmp_path / "start-args"
    binary.write_text('#!/bin/sh\nprintf "%s\n" "$@" > "$START_ARGS"\nexit 19\n', encoding='utf-8', newline='\n')
    binary.chmod(0o755)
    result = subprocess.run(
        [janitor_bash, (SCRIPTS / "start.sh").as_posix(), "web", "--no-env-file"],
        env={**os.environ, "OD_SOURCE_DIR": source.as_posix(), "START_ARGS": capture.as_posix(),
             "OD_DAEMON_PORT": "56471", "OD_WEB_PORT": "56472"},
        capture_output=True, text=True, check=False, timeout=10,
    )
    assert result.returncode == 19, result.stdout + result.stderr
    assert capture.read_text().splitlines() == ["start", "web", "--no-env-file", "--daemon-port", "56471", "--web-port", "56472"]
