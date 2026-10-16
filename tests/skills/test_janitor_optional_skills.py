"""Optional deployment contracts exercise real scripts/config without a daemon."""
from pathlib import Path
import json
import os
import re
import shutil
import shlex
import subprocess
import sys
from types import SimpleNamespace

import hermes_yaml as yaml
import pytest

from janitor_ext import volumes

ROOT = Path(__file__).resolve().parents[2]
SERVICES = ('lightrag', 'n8n', 'nocodb', 'waha', 'firecrawl')


@pytest.mark.parametrize('healthy', [True, False])
def test_opencode_probe_only_reads_health_and_propagates_failure(tmp_path, healthy):
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    calls = []
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass
        def do_GET(self):
            calls.append((self.command, self.path, self.headers.get('Authorization')))
            data = json.dumps({'healthy': healthy, 'version': 'fixture'}).encode()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    try:
        result = subprocess.run([sys.executable, str(ROOT / 'skills/janitor-opencode/scripts/health.py'),
                                 '--port', str(server.server_port)],
                                env=dict(os.environ, OPENCODE_SERVER_PASSWORD='fake-probe-password'),
                                capture_output=True, text=True, timeout=15, check=False)
        assert result.returncode == (0 if healthy else 1), result.stderr
        assert json.loads(result.stdout)['ok'] is healthy
        assert len(calls) == 1 and calls[0][:2] == ('GET', '/global/health')
        assert calls[0][2].startswith('Basic ')
        assert 'fake-probe-password' not in result.stdout + result.stderr
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=5)


@pytest.mark.parametrize('name', SERVICES)
def test_compose_is_pinned_isolated_and_docker_accepts_config(name, tmp_path, monkeypatch):
    source = ROOT / f'skills/janitor-{name}/scripts/{name}-compose.yml'
    model = yaml.safe_load(source.read_text())
    assert model['name'] == 'janitor-' + name
    for service in model['services'].values():
        assert service['container_name'].startswith('janitor-')
        assert re.fullmatch(r'.+@sha256:[0-9a-f]{64}', service['image'])
    for kind in ('volumes', 'networks'):
        for config in model.get(kind, {}).values():
            assert config['name'].startswith('janitor-')
    if not shutil.which('docker'):
        pytest.skip('Docker Compose CLI unavailable; structural contracts already checked')
    docker_dir = tmp_path / 'docker'; docker_dir.mkdir()
    values = ('POSTGRES_PASSWORD=test-pg\nNOCODB_DB_PASSWORD=test-noco\nN8N_ENCRYPTION_KEY=test-key\n'
              'WAHA_API_KEY=test-waha\nLIGHTRAG_API_KEY=test-lightrag\nAUTH_ACCOUNTS=admin:test\n')
    env_file = docker_dir / (name + '.env'); env_file.write_text(values)
    docker_config = tmp_path / 'docker-config'
    docker_config.mkdir()
    env = dict(os.environ, HERMES_HOME=str(tmp_path), HOME=str(tmp_path), USERPROFILE=str(tmp_path),
               DOCKER_CONFIG=str(docker_config))
    result = subprocess.run(['docker', 'compose', '-f', str(source), '--env-file', str(env_file), 'config', '--quiet'],
                            env=env, capture_output=True, text=True, timeout=60, check=False)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize('name', SERVICES)
def test_deploy_propagates_docker_pull_failure(name, tmp_path, monkeypatch, janitor_bash):
    binary = tmp_path / 'bin'; binary.mkdir()
    docker = binary / 'docker'
    docker.write_text('#!/bin/sh\ncase "$1" in info) exit 0;; compose) case " $* " in *" pull "*) exit 37;; esac;; esac\nexit 0\n', encoding='utf-8', newline='\n')
    docker.chmod(0o755)
    env = dict(os.environ, PATH=binary.as_posix() + os.pathsep + os.environ['PATH'], HERMES_HOME=(tmp_path / 'profile').as_posix(),
               JANITOR_SERVICE_ENV='1', JANITOR_SERVICE_PYTHON=Path(sys.executable).as_posix(), MINIMAX_API_KEY='test-secret')
    result = subprocess.run([janitor_bash, (ROOT / f'skills/janitor-{name}/scripts/deploy.sh').as_posix()],
                            env=env, capture_output=True, text=True, timeout=15, check=False)
    assert result.returncode == 37, result.stderr + result.stdout


def test_optional_environment_does_not_evaluate_shell_and_respects_profile(tmp_path, monkeypatch):
    from janitor_ext import optional_deploy
    marker = tmp_path / 'injected'
    (tmp_path / '.env').write_text(f'MINIMAX_API_KEY=$(touch {marker})\n')
    monkeypatch.delenv('MINIMAX_API_KEY', raising=False)
    monkeypatch.setenv('HERMES_HOME', str(tmp_path))
    monkeypatch.setenv('JANITOR_HOME', str(tmp_path / 'wrong'))
    seen = []
    monkeypatch.setattr(optional_deploy.os, 'execvpe', lambda command, argv, env: seen.append((command, argv, env)))
    script = ROOT / 'skills/janitor-lightrag/scripts/deploy.sh'
    optional_deploy.main([str(script)])
    assert seen[0][2]['MINIMAX_API_KEY'] == f'$(touch {marker})'
    assert seen[0][2]['HERMES_HOME'] == str(tmp_path)
    assert seen[0][2]['JANITOR_SERVICE_PYTHON'] == sys.executable
    assert seen[0][2]['JANITOR_CORE_ROOT'] == str(ROOT)
    assert not marker.exists()


def _model():
    return {'name': 'janitor-test', 'volumes': {'data': {'name': 'janitor-test-data'}},
            'services': {'test': {'container_name': 'janitor-test',
                                  'volumes': [{'type': 'volume', 'source': 'data', 'target': '/data'}]}}}


def _old_container():
    return {'Config': {'Labels': {'com.docker.compose.project': 'docker'}}, 'State': {'Running': True},
            'Mounts': [{'Type': 'volume', 'Name': 'docker_old_data', 'Destination': '/data'}]}


def _migration_docker(tmp_path, monkeypatch, *, fail_copy=False, target_exists=False):
    calls = []
    def docker(*args, check=True):
        calls.append(args)
        value = ''
        if args[0] == 'compose': value = json.dumps(_model())
        elif args[0] == 'inspect': value = json.dumps([_old_container()])
        elif args[:2] == ('volume', 'inspect'):
            if not target_exists: return SimpleNamespace(returncode=1, stdout='', stderr='Error: no such volume')
            value = '[{}]'
        elif args[0] == 'ps': value = 'janitor-test\n'
        elif args[0] == 'run' and fail_copy: raise subprocess.CalledProcessError(41, args)
        return SimpleNamespace(returncode=0, stdout=value, stderr='')
    monkeypatch.setattr(volumes, '_run', docker)
    return calls


def test_migration_copies_offline_readonly_and_keeps_old_volume_and_container(tmp_path, monkeypatch):
    calls = _migration_docker(tmp_path, monkeypatch)
    result = volumes.migrate_compose(tmp_path / 'compose.yml', tmp_path / 'test.env')
    assert result == [{'source': 'docker_old_data', 'target': 'janitor-test-data'}]
    commands = [c[0] for c in calls]
    assert commands.index('stop') < commands.index('run') < commands.index('rename')
    copy = next(c for c in calls if c[0] == 'run')
    assert 'type=volume,src=docker_old_data,dst=/from,readonly' in copy
    assert 'none' in copy and '--read-only' in copy
    assert not any(c[0] == 'rm' or c[:2] == ('volume', 'rm') for c in calls)
    receipt = json.loads((tmp_path / 'janitor-test-volume-migration.json').read_text())
    assert receipt['janitor-test-data']['completed'] is True


def test_copy_failure_restarts_original_and_never_claims_completion(tmp_path, monkeypatch):
    calls = _migration_docker(tmp_path, monkeypatch, fail_copy=True)
    with pytest.raises(subprocess.CalledProcessError):
        volumes.migrate_compose(tmp_path / 'compose.yml', tmp_path / 'test.env')
    assert ('start', 'janitor-test') in calls
    assert not any(c[0] == 'rename' for c in calls)
    assert not (tmp_path / 'janitor-test-volume-migration.json').exists()


def test_existing_unconfirmed_destination_refuses_before_stopping(tmp_path, monkeypatch):
    calls = _migration_docker(tmp_path, monkeypatch, target_exists=True)
    with pytest.raises(RuntimeError, match='without a completed'):
        volumes.migrate_compose(tmp_path / 'compose.yml', tmp_path / 'test.env')
    assert not any(c[0] in ('stop', 'run', 'rename') for c in calls)


def test_browser_installs_with_pm_and_failure_reaches_caller(tmp_path, janitor_bash):
    python = tmp_path / 'python'
    python.write_text('#!/bin/sh\nprintf "%s\\n" "$*" > "$BROWSER_CALL"\nexit 39\n', encoding='utf-8', newline='\n')
    python.chmod(0o755)
    out = tmp_path / 'call'
    env = dict(os.environ, JANITOR_SERVICE_ENV='1', JANITOR_SERVICE_PYTHON=python.as_posix(), BROWSER_CALL=out.as_posix())
    result = subprocess.run([janitor_bash, (ROOT / 'skills/janitor-browser/scripts/install.sh').as_posix()], env=env, check=False)
    assert result.returncode == 39
    assert out.read_text().strip() == '-m pm.launch install agent-browser chromium cua-driver'


def test_n8n_auth_encodes_quoted_profile_password_as_json(tmp_path, monkeypatch):
    from janitor_ext import service_auth
    import http.cookiejar
    password = 'quotes" and backslash\\ and $(literal)'
    (tmp_path / '.env').write_text('N8N_USER_PASSWORD=' + json.dumps(password) + '\n')
    monkeypatch.delenv('N8N_USER_PASSWORD', raising=False)
    seen = []
    class Response:
        status = 200
        def __enter__(self): return self
        def __exit__(self, *args): pass
    class Opener:
        def __init__(self, jar): self.jar = jar
        def open(self, request, timeout):
            seen.append(json.loads(request.data))
            self.jar.set_cookie(http.cookiejar.Cookie(0, 'n8n-auth', 'test-cookie', None, False,
                '127.0.0.1', False, False, '/', True, False, None, True, None, None, {}))
            return Response()
    monkeypatch.setattr(service_auth.urllib.request, 'build_opener', lambda processor: Opener(processor.cookiejar))
    cookie = service_auth.n8n_login(tmp_path)
    try:
        assert seen[0]['password'] == password
        assert 'n8n-auth' in cookie.read_text()
        if os.name == 'posix':
            assert cookie.stat().st_mode & 0o077 == 0
    finally:
        cookie.unlink()


def test_seeded_custom_skill_executes_from_active_profile_without_overwriting(tmp_path, monkeypatch):
    from janitor_ext import optional_deploy
    profile = tmp_path / 'profiles/work'
    script = profile / 'skills/janitor-custom/scripts/deploy.sh'; script.parent.mkdir(parents=True)
    script.write_text('#!/bin/sh\necho user-custom-service\n')
    before = script.read_bytes()
    (profile / '.env').write_text('CUSTOM_SECRET="profile-only"\n')
    monkeypatch.setenv('HERMES_HOME', str(profile))
    seen = []
    monkeypatch.setattr(optional_deploy.os, 'execvpe', lambda command, argv, env: seen.append((command, argv, env)))
    optional_deploy.main([str(script), '--custom'])
    assert seen[0][1] == ['bash', str(script), '--custom']
    assert seen[0][2]['CUSTOM_SECRET'] == 'profile-only'
    assert script.read_bytes() == before


def test_profile_skill_symlink_cannot_escape_authorized_roots(tmp_path, monkeypatch):
    from janitor_ext import optional_deploy
    home = tmp_path / 'home'
    outside = tmp_path / 'outside/janitor-escape/scripts/deploy.sh'; outside.parent.mkdir(parents=True)
    outside.write_text('echo should-not-run\n')
    scripts = home / 'skills/janitor-escape/scripts'; scripts.mkdir(parents=True)
    (scripts / 'deploy.sh').symlink_to(outside)
    monkeypatch.setenv('HERMES_HOME', str(home))
    monkeypatch.setattr(optional_deploy.os, 'execvpe', lambda *args: pytest.fail('symlink escape executed'))
    with pytest.raises(SystemExit, match='selected profile'):
        optional_deploy.main([str(scripts / 'deploy.sh')])


def test_copied_honcho_skill_uses_installed_pm_launcher_and_profile(tmp_path, janitor_bash):
    selected = tmp_path / 'home/profiles/work'
    script = selected / 'skills/janitor-honcho/scripts/deploy.sh'
    script.parent.mkdir(parents=True)
    shutil.copyfile(ROOT / 'skills/janitor-honcho/scripts/deploy.sh', script)
    binary = tmp_path / 'bin'
    binary.mkdir()
    launcher = binary / 'janitor'
    launcher.write_text('#!/bin/sh\nprintf "%s\\n" "$HERMES_HOME" "$@"\n', encoding='utf-8', newline='\n')
    launcher.chmod(0o755)
    result = subprocess.run([janitor_bash, script.as_posix(), '--help'], env=dict(os.environ,
        PATH=binary.as_posix() + os.pathsep + os.environ['PATH'], HERMES_HOME=selected.as_posix(), JANITOR_HOME=(tmp_path / 'home').as_posix()),
        capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == [selected.as_posix(), '--run-module', 'janitor_ext.honcho', '--help']


def test_entire_skills_root_symlink_is_not_trusted(tmp_path, monkeypatch):
    from janitor_ext import optional_deploy
    home = tmp_path / 'home'
    home.mkdir()
    outside = tmp_path / 'outside/janitor-escape/scripts/deploy.sh'
    outside.parent.mkdir(parents=True)
    outside.write_text('echo should-not-run\n')
    (home / 'skills').symlink_to(tmp_path / 'outside', target_is_directory=True)
    monkeypatch.setenv('HERMES_HOME', str(home))
    monkeypatch.setattr(optional_deploy.os, 'execvpe', lambda *args: pytest.fail('linked root executed'))
    with pytest.raises(SystemExit, match='selected profile'):
        optional_deploy.main([str(home / 'skills/janitor-escape/scripts/deploy.sh')])


@pytest.mark.parametrize('refused', [False, True])
def test_waha_group_diff_real_http_uses_credentials_and_paginated_nocodb(tmp_path, refused):
    import importlib.util
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    spec = importlib.util.spec_from_file_location('janitor_waha_group_diff', ROOT / 'skills/janitor-waha/scripts/diff-waha-group.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    calls = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def do_GET(self):
            calls.append((self.path, self.headers.get('X-Api-Key'), self.headers.get('xc-token')))
            if refused:
                payload = {'error': 'sensitive-fixture-waha-key'}
            elif self.path.startswith('/api/sessions/'):
                payload = {'status': 'WORKING'}
            elif self.path == '/api/default/groups':
                payload = {'fixture@g.us': {'participants': [{'id': 'first'}, {'id': 'second'}]}}
            else:
                last = 'offset=1' in self.path
                payload = {'list': [{'WA LID': 'exited' if last else 'first'}], 'pageInfo': {'isLastPage': last}}
            data = json.dumps(payload).encode()
            self.send_response(401 if refused else 200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        url = f'http://127.0.0.1:{server.server_port}'
        if refused:
            with pytest.raises(RuntimeError, match='HTTP 401') as error:
                module.fetch_waha_session_status(url, 'sensitive-fixture-waha-key')
            assert 'sensitive-fixture-waha-key' not in str(error.value)
            return
        assert module.fetch_waha_session_status(url, 'fixture-waha')['status'] == 'WORKING'
        groups = module.fetch_waha_groups(url, 'fixture-waha')
        cookies = tmp_path / 'cookies'
        cookies.write_text('# Netscape HTTP Cookie File\n')
        records = module.fetch_nocodb_records(url, 'fixture-nocodb', 'table-id', str(cookies), limit=1)
        result = module.diff(groups['fixture@g.us']['participants'], records)
        assert result == {'new': [{'id': 'second'}], 'known_count': 1, 'exited': [{'WA LID': 'exited'}]}
        assert calls[:2] == [('/api/sessions/default', 'fixture-waha', None), ('/api/default/groups', 'fixture-waha', None)]
        assert all(call[2] == 'fixture-nocodb' for call in calls[2:])
        assert len(calls) == 4
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def _python_stub(path, body):
    # A shebang cannot quote an interpreter path containing spaces (Git/PM on Windows).
    executable = shlex.quote(Path(sys.executable).as_posix())
    prefix = f"#!/bin/sh\nexec {executable} - \"$@\" <<'JANITOR_PYTHON_STUB'\n"
    path.write_text(prefix + body + "\nJANITOR_PYTHON_STUB\n", encoding="utf-8", newline="\n")
    path.chmod(0o755)


def _require_absolute_mktemp_template(binary):
    """Exercise the portable operand form instead of OS-specific -t semantics."""
    native = shutil.which('mktemp')
    assert native
    wrapper = binary / 'mktemp'
    # Keep the MSYS executable in its shell: Python's Windows execv does not
    # quote argv containing spaces, unlike subprocess and Bash's "$@".
    wrapper.write_text(
        '#!/bin/sh\n[ "$#" = 1 ] || exit 64\n'
        'case "$1" in /*|[A-Za-z]:/*) ;; *) exit 64;; esac\n'
        + f'exec {shlex.quote(Path(native).as_posix())} "$@"\n',
        encoding='utf-8', newline='\n',
    )
    wrapper.chmod(0o755)


def _stubbed_shell_command(shell, binary, script, *args):
    # Set fixture precedence after the native shell has initialized its PATH.
    # Native cd also converts Windows drive paths into the shell path syntax.
    return [shell, '-c', 'export PATH="$(cd "$1" && pwd):$PATH"; shift; source "$0"',
            script.as_posix(), binary.as_posix(), *args]


@pytest.mark.parametrize('response', ['healthy', 'http-error', 'network-error'])
def test_waha_health_uses_private_scratch_and_cleans_after_every_outcome(tmp_path, response, janitor_bash):
    binary = tmp_path / 'bin'
    binary.mkdir()
    _require_absolute_mktemp_template(binary)
    scratch = tmp_path / 'scratch with spaces'
    scratch.mkdir()
    capture = tmp_path / 'curl.json'
    docker = binary / 'docker'
    docker.write_text('#!/bin/sh\ncase "$1" in inspect) echo healthy;; esac\nexit 0\n', encoding='utf-8', newline='\n')
    docker.chmod(0o755)
    curl = binary / 'curl'
    _python_stub(curl, '''import json, os, pathlib, sys
args = sys.argv[1:]
output = pathlib.Path(args[args.index('-o') + 1])
output.write_text('{"status":"ok"}', encoding='utf-8')
pathlib.Path(os.environ['CURL_CAPTURE']).write_text(json.dumps({
    'path': str(output), 'mode': output.stat().st_mode & 0o777,
}), encoding='utf-8')
if os.environ['CURL_RESPONSE'] == 'network-error':
    sys.exit(7)
print('500' if os.environ['CURL_RESPONSE'] == 'http-error' else '200', end='')
''')
    curl.chmod(0o755)
    result = subprocess.run(_stubbed_shell_command(janitor_bash, binary, ROOT / 'skills/janitor-waha/scripts/deploy.sh'),
        env=dict(os.environ, PATH=binary.as_posix() + os.pathsep + os.environ['PATH'],
                 HERMES_HOME=(tmp_path / 'profile').as_posix(), TMPDIR=scratch.as_posix(),
                 JANITOR_SERVICE_ENV='1', JANITOR_SERVICE_PYTHON=Path(shutil.which('true')).as_posix(),
                 CURL_CAPTURE=capture.as_posix(), CURL_RESPONSE=response),
        capture_output=True, text=True, timeout=15, check=False)
    assert capture.is_file(), result.stdout + result.stderr
    record = json.loads(capture.read_text(encoding='utf-8'))
    assert Path(record['path']).parent == scratch
    if os.name == 'posix':
        assert record['mode'] == 0o600
    assert not Path(record['path']).exists()
    assert list(scratch.iterdir()) == []
    assert (result.returncode == 0) is (response == 'healthy'), result.stdout + result.stderr


@pytest.mark.parametrize('valid', [True, False])
def test_waha_pair_qr_private_path_and_failed_download_cleanup(tmp_path, valid, janitor_bash):
    binary = tmp_path / 'bin'
    binary.mkdir()
    _require_absolute_mktemp_template(binary)
    scratch = tmp_path / 'scratch with spaces'
    scratch.mkdir()
    profile = tmp_path / 'profile'
    (profile / 'docker').mkdir(parents=True)
    (profile / 'docker/waha.env').write_text('WAHA_API_KEY=test\nWHATSAPP_DEFAULT_ENGINE=NOWEB\n', encoding='utf-8', newline='\n')
    capture = tmp_path / 'qr.json'
    curl = binary / 'curl'
    _python_stub(curl, '''import base64, json, os, pathlib, sys
args = sys.argv[1:]
url = next(arg for arg in args if arg.startswith('http'))
if url.endswith('/health'):
    print('200')
elif url.endswith('/auth/qr'):
    output = pathlib.Path(args[args.index('-o') + 1])
    output.write_bytes(base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Wl2O+YAAAAASUVORK5CYII=') if os.environ['QR_VALID'] == '1' else b'not png')
    pathlib.Path(os.environ['QR_CAPTURE']).write_text(json.dumps({'path': str(output), 'mode': output.stat().st_mode & 0o777}), encoding='utf-8')
elif url.split('?', 1)[0].endswith('/api/sessions'):
    print('[]')
else:
    print('{"status":"SCAN_QR_CODE"}')
''')
    curl.chmod(0o755)
    for name in ('sleep', 'xdg-open'):
        stub = binary / name
        stub.write_text('#!/bin/sh\nexit 0\n', encoding='utf-8', newline='\n')
        stub.chmod(0o755)
    result = subprocess.run(_stubbed_shell_command(janitor_bash, binary, ROOT / 'skills/janitor-waha/scripts/pair-waha.sh', '--qr'),
        env=dict(os.environ, PATH=binary.as_posix() + os.pathsep + os.environ['PATH'],
                 HERMES_HOME=profile.as_posix(), TMPDIR=scratch.as_posix(), WAHA_QR_OUTPUT='',
                 JANITOR_SERVICE_ENV='1', JANITOR_SERVICE_PYTHON=Path(sys.executable).as_posix(),
                 QR_CAPTURE=capture.as_posix(), QR_VALID='1' if valid else '0'),
        capture_output=True, text=True, timeout=15, check=False)
    assert capture.is_file(), result.stdout + result.stderr
    record = json.loads(capture.read_text(encoding='utf-8'))
    output = Path(record['path'])
    assert output.parent == scratch
    if os.name == 'posix':
        assert record['mode'] == 0o600
    assert output.exists() is valid
    assert (result.returncode == 0) is valid, result.stdout + result.stderr
    if valid:
        clean_output = re.sub(r"\x1b\[[0-9;]*m", "", result.stdout)
        announced = re.search(r"QR guardado en ([^\r\n]+)", clean_output)
        assert announced, result.stdout
        printed_path = announced.group(1)
        if os.name == "nt":
            printed_path = subprocess.check_output(
                [janitor_bash, "-c", 'cygpath -w -- "$1"', "fixture", printed_path],
                text=True, timeout=5,
            ).strip()
        assert Path(printed_path).resolve() == output.resolve()
        output.unlink()
    assert list(scratch.iterdir()) == []


@pytest.mark.platforms('posix')
def test_timed_out_volume_copy_stops_only_its_temporary_container(tmp_path, monkeypatch):
    binary = tmp_path / 'bin'
    binary.mkdir()
    docker = binary / 'docker'
    log = tmp_path / 'calls.jsonl'
    docker.write_text(f"#!{sys.executable}\n" + '''import json, os, pathlib, signal, sys
with pathlib.Path(os.environ['DOCKER_CALLS']).open('a', encoding='utf-8') as handle:
    handle.write(json.dumps(sys.argv[1:]) + '\\n')
if sys.argv[1] == 'run':
    signal.pause()
''', encoding='utf-8')
    docker.chmod(0o755)
    monkeypatch.setenv('PATH', str(binary) + os.pathsep + os.environ['PATH'])
    monkeypatch.setenv('DOCKER_CALLS', str(log))
    with pytest.raises(subprocess.TimeoutExpired):
        volumes._run('run', '--rm', '--name', 'janitor-volume-copy-fixture', 'copy-image', timeout=2)
    calls = [json.loads(line) for line in log.read_text(encoding='utf-8').splitlines()]
    assert calls == [['run', '--rm', '--name', 'janitor-volume-copy-fixture', 'copy-image'],
                     ['rm', '-f', 'janitor-volume-copy-fixture']]


@pytest.mark.parametrize('status, polled_status', [
    ('WORKING', 'WORKING'), ('SCAN_QR_CODE', 'SCAN_QR_CODE'),
    ('STARTING', 'SCAN_QR_CODE'), ('STARTING', 'WORKING'),
    ('UNKNOWN', 'UNKNOWN'), ('FAILED', 'SCAN_QR_CODE'), ('STOPPED', 'SCAN_QR_CODE'),
])
@pytest.mark.parametrize("python_newline", ["\n", "\r\n"], ids=["LF", "CRLF"])
def test_waha_pair_reuses_live_sessions_without_logging_out(tmp_path, status, polled_status, janitor_bash, python_newline):
    import base64
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    calls = []
    png = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Wl2O+YAAAAASUVORK5CYII=')

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def respond(self):
            calls.append((self.command, self.path))
            size = int(self.headers.get('Content-Length', '0'))
            if size:
                self.rfile.read(size)
            responses = {
                '/health': b'{"status":"ok"}',
                '/api/sessions': json.dumps([] if status == 'STOPPED' else [{'name': 'default', 'status': status}]).encode(),
                '/api/sessions?all=true': json.dumps([{'name': 'default', 'status': status}]).encode(),
                '/api/sessions/default': json.dumps({'status': polled_status}).encode(),
                '/api/default/auth/qr': png,
            }
            body = responses.get(self.path, b'{}')
            self.send_response(200)
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        do_GET = respond
        do_POST = respond
        do_DELETE = respond

    profile = tmp_path / 'profile'
    (profile / 'docker').mkdir(parents=True)
    (profile / 'docker/waha.env').write_text('WAHA_API_KEY=fixture-only\nWHATSAPP_DEFAULT_ENGINE=NOWEB\n', encoding='utf-8', newline='\n')
    binary = tmp_path / 'bin'
    binary.mkdir()
    for name in ('sleep', 'xdg-open'):
        stub = binary / name
        stub.write_text('#!/bin/sh\nexit 0\n', encoding='utf-8', newline='\n')
        stub.chmod(0o755)
    # Preserve Python's native text boundary, including Windows CRLF, in the real pipeline.
    python_bridge = tmp_path / "python bridge with spaces"
    bridge_code = "import sys; sys.stdout.reconfigure(newline=" + repr(python_newline) + "); exec(sys.argv[1])"
    python_bridge.write_text(
        f'#!/bin/sh\nif [ "$1" != -c ]; then exec {shlex.quote(Path(sys.executable).as_posix())} "$@"; fi\n'
        + f'exec {shlex.quote(Path(sys.executable).as_posix())} -c {shlex.quote(bridge_code)} "$2"\n',
        encoding="utf-8", newline="\n",
    )
    python_bridge.chmod(0o755)
    scratch = tmp_path / 'scratch'
    scratch.mkdir()
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        result = subprocess.run([janitor_bash, (ROOT / 'skills/janitor-waha/scripts/pair-waha.sh').as_posix(), '--qr'],
            env=dict(os.environ, PATH=binary.as_posix() + os.pathsep + os.environ['PATH'],
                     HERMES_HOME=profile.as_posix(), TMPDIR=scratch.as_posix(), WAHA_QR_OUTPUT='',
                     WAHA_BASE_URL=f'http://127.0.0.1:{server.server_port}',
                     JANITOR_SERVICE_ENV='1', JANITOR_SERVICE_PYTHON=python_bridge.as_posix()),
            capture_output=True, text=True, timeout=15, check=False)
        assert calls[:2] == [('GET', '/health'), ('GET', '/api/sessions?all=true')]
        if status in ('FAILED', 'STOPPED'):
            assert calls[2:7] == [
                ('POST', '/api/sessions/default/stop'), ('POST', '/api/sessions/default/logout'),
                ('DELETE', '/api/sessions/default'), ('POST', '/api/sessions'),
                ('POST', '/api/sessions/default/start'),
            ]
        else:
            assert all(method == 'GET' for method, _ in calls), calls
        assert result.returncode == (1 if status == 'UNKNOWN' else 0), result.stdout + result.stderr
        if polled_status in ('WORKING', 'UNKNOWN'):
            assert len(calls) == (3 if status == 'STARTING' else 2)
            assert list(scratch.iterdir()) == []
        else:
            assert calls[-2:] == [('GET', '/api/sessions/default'), ('GET', '/api/default/auth/qr')]
            assert len(list(scratch.iterdir())) == 1
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
