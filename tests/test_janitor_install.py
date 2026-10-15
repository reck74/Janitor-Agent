"""Installation contracts, using temporary homes and real config/default imports."""
import json
import os
from pathlib import Path

import pytest
import hermes_yaml as yaml

from janitor_ext.install import prepare_profile, read_secrets, configure_credentials
from janitor_ext.honcho import prepare_service, checkout_server


def test_profile_preserves_persona_secrets_and_custom_choices(tmp_path):
    home = tmp_path / "janitor"; home.mkdir()
    (home / "SOUL.md").write_text("My custom persona")
    (home / ".env").write_text('CUSTOM_TOKEN="keep me"\n')
    (home / "config.yaml").write_text(yaml.safe_dump({"model": {"default": "my-model"}, "agent": {"max_turns": 7}, "_config_version": 23}))
    report = prepare_profile(home, {"MINIMAX_API_KEY": "fake-minimax", "HONCHO_API_KEY": "fake-honcho"}, "cloud")
    config = yaml.safe_load((home / "config.yaml").read_text())
    assert config["model"]["default"] == "my-model"
    assert config["agent"]["max_turns"] == 7
    assert config["_config_version"] == 23  # Only the migration engine may advance it.
    assert (home / "SOUL.md").read_text() == "My custom persona"
    assert read_secrets(home / ".env")["CUSTOM_TOKEN"] == "keep me"
    assert Path(report["backup"]).joinpath("SOUL.md").read_text() == "My custom persona"
    assert (home / ".env").stat().st_mode & 0o777 == 0o600
    assert "baseUrl" not in json.loads((home / "honcho.json").read_text())


def test_new_profile_uses_current_defaults_and_rerun_keeps_bytes(tmp_path):
    from hermes_cli.config_defaults import DEFAULT_CONFIG
    keys = {"MINIMAX_API_KEY": "fake", "HONCHO_API_KEY": "fake-cloud"}
    prepare_profile(tmp_path, keys, "cloud")
    config = yaml.safe_load((tmp_path / "config.yaml").read_text())
    assert config["_config_version"] == DEFAULT_CONFIG["_config_version"]
    before = {name: (tmp_path / name).read_bytes() for name in ("config.yaml", ".env", "SOUL.md", "honcho.json")}
    prepare_profile(tmp_path, keys, "cloud")
    assert before == {name: (tmp_path / name).read_bytes() for name in before}


def test_noninteractive_cloud_requires_both_credentials(tmp_path, monkeypatch):
    for key in ("MINIMAX_API_KEY", "HONCHO_API_KEY", "OPENAI_API_KEY"):
        monkeypatch.delenv(key, raising=False)
    with pytest.raises(ValueError, match="MINIMAX_API_KEY"):
        configure_credentials(tmp_path, non_interactive=True, mode="cloud")
    monkeypatch.setenv("MINIMAX_API_KEY", "fake")
    with pytest.raises(ValueError, match="HONCHO_API_KEY"):
        configure_credentials(tmp_path, non_interactive=True, mode="cloud")
    monkeypatch.setenv("HONCHO_API_KEY", "fake")
    _, mode = configure_credentials(tmp_path, non_interactive=True, mode="cloud")
    assert mode == "cloud"  # No OpenAI requirement for cloud memory.


def test_switching_local_to_cloud_does_not_send_cloud_key_to_localhost(tmp_path):
    prepare_profile(tmp_path, {"MINIMAX_API_KEY": "fake", "OPENAI_API_KEY": "fake"}, "local")
    prepare_profile(tmp_path, {"MINIMAX_API_KEY": "fake", "HONCHO_API_KEY": "fake-cloud"}, "cloud")
    assert "HONCHO_BASE_URL" not in read_secrets(tmp_path / ".env")
    assert "baseUrl" not in json.loads((tmp_path / "honcho.json").read_text())


def test_cloud_deploy_uses_normalized_endpoint(tmp_path, monkeypatch):
    import janitor_ext.install as installer
    from janitor_ext import honcho
    import janitor_ext.migrate as migration
    prepare_profile(tmp_path, {"MINIMAX_API_KEY": "fake", "OPENAI_API_KEY": "fake"}, "local")
    config = json.loads((tmp_path / "honcho.json").read_text())
    config["hosts"]["hermes"]["baseUrl"] = "http://localhost:1973"
    (tmp_path / "honcho.json").write_text(json.dumps(config))
    monkeypatch.setenv("HONCHO_API_KEY", "fake-cloud")
    monkeypatch.delenv("HONCHO_BASE_URL", raising=False)
    calls = []
    monkeypatch.setattr(installer.subprocess, "run", lambda *args, **kwargs: None)
    monkeypatch.setattr(installer, "install_honcho_plugin", lambda: None)
    from types import SimpleNamespace
    monkeypatch.setattr(installer, "honcho_connection", lambda home: SimpleNamespace(
        base_url=None, api_key="fake-cloud", workspace_id="Janitor-Workspace"))
    monkeypatch.setattr(migration, "migrate", lambda *args, **kwargs: {})
    monkeypatch.setattr(honcho, "verify_memory", lambda endpoint, **kwargs: calls.append((endpoint, kwargs)))
    installer.main(["--home", str(tmp_path), "--honcho-mode", "cloud", "--non-interactive"])
    assert calls == [("https://api.honcho.dev", {"api_key": "fake-cloud", "workspace": "Janitor-Workspace"})]


def test_server_checkout_handles_initial_no_checkout_and_preserves_edits(tmp_path, monkeypatch):
    import subprocess
    from janitor_ext import honcho
    origin = tmp_path / "origin"; origin.mkdir()
    subprocess.run(["git", "init", "-q", str(origin)], check=True)
    (origin / "server.txt").write_text("audited server")
    subprocess.run(["git", "-C", str(origin), "add", "."], check=True)
    subprocess.run(["git", "-C", str(origin), "-c", "user.name=Acceptance", "-c", "user.email=test@example.invalid", "commit", "-qm", "fixture"], check=True)
    ref = subprocess.check_output(["git", "-C", str(origin), "rev-parse", "HEAD"], text=True).strip()
    original_run = subprocess.run
    def run(command, **kwargs):
        if command[:2] == ["git", "clone"]:
            command = [str(origin) if value == "https://github.com/plastic-labs/honcho.git" else value for value in command]
        return original_run(command, **kwargs)
    monkeypatch.setattr(honcho, "HONCHO_REF", ref)
    monkeypatch.setattr(honcho.subprocess, "run", run)
    target = tmp_path / "installed"
    checkout_server(target)
    assert (target / "server.txt").read_text() == "audited server"
    checkout_server(target)  # Idempotent checkout of the same audited commit.
    (target / "server.txt").write_text("personal edit")
    with pytest.raises(RuntimeError, match="local changes"):
        checkout_server(target)
    assert (target / "server.txt").read_text() == "personal edit"


def test_local_memory_preserves_volume_login_and_routes_minimax(tmp_path):
    prepare_profile(tmp_path, {"MINIMAX_API_KEY": "fake-minimax", "OPENAI_API_KEY": "fake-embedding"}, "local")
    docker = tmp_path / "docker"; docker.mkdir()
    (docker / "honcho-compose.yml").write_text(yaml.safe_dump({"services": {"old-db": {"environment": {"POSTGRES_USER": "existing-user", "POSTGRES_PASSWORD": "existing-pass"}}}}))
    prepare_service(tmp_path)
    secrets = read_secrets(tmp_path / "honcho.env")
    assert secrets["HONCHO_POSTGRES_USER"] == "existing-user"
    assert secrets["HONCHO_POSTGRES_PASSWORD"] == "existing-pass"
    assert secrets["LLM_ANTHROPIC_API_KEY"] == "fake-minimax"
    assert "janitor-honcho-database" in secrets["DB_CONNECTION_URI"]
    assert str(tmp_path / "src/honcho") == secrets["JANITOR_HONCHO_SOURCE"]
    import tomllib
    config = tomllib.loads((tmp_path / "honcho.toml").read_text())
    assert config["deriver"]["model_config"]["transport"] == "anthropic"
    assert config["embedding"]["model_config"]["transport"] == "openai"


def _plugin_record(home):
    from janitor_ext.install import HONCHO_REF
    plugin = home / 'plugins/honcho'; plugin.mkdir(parents=True)
    record = {'honcho': {'source': 'https://github.com/plastic-labs/honcho#hermes-plugin-honcho',
                         'revision': HONCHO_REF, 'pinned': True}}
    (home / 'plugins/.install-metadata.json').write_text(json.dumps(record))
    (plugin / '__init__.py').write_text('# Personalized file must survive reruns\n')
    return plugin


def test_honcho_installer_rejects_structured_dependency_failure(tmp_path, monkeypatch):
    import janitor_ext.install as installer
    import hermes_cli.plugins_cmd_install as command
    monkeypatch.setattr('hermes_constants.get_hermes_home', lambda: tmp_path)
    monkeypatch.setattr(command, 'dashboard_install_plugin', lambda *args, **kwargs: {'ok': False, 'error': 'dependency resolution failed'})
    monkeypatch.setattr(installer, '_verify_fresh_honcho', lambda home: pytest.fail('must not report success after refusal'))
    with pytest.raises(RuntimeError, match='dependency resolution failed'):
        installer.install_honcho_plugin()


def test_honcho_installs_exact_pin_then_checks_fresh_pm(tmp_path, monkeypatch):
    import janitor_ext.install as installer
    import hermes_cli.plugins_cmd_install as command
    from hermes_cli import memory_setup
    monkeypatch.setattr('hermes_constants.get_hermes_home', lambda: tmp_path)
    calls = []
    def install(*args, **kwargs):
        calls.append(kwargs); _plugin_record(tmp_path)
        return {'ok': True}
    monkeypatch.setattr(command, 'dashboard_install_plugin', install)
    monkeypatch.setattr(memory_setup, 'prepare_memory_provider_dependencies', lambda name: calls.append(name))
    monkeypatch.setattr(installer, '_verify_fresh_honcho', lambda home: calls.append(home))
    installer.install_honcho_plugin()
    assert calls[0]['ref'] == installer.HONCHO_REF and calls[0]['force'] is False
    assert calls[0]['assume_deps_consent'] is True
    assert calls[1:] == ['honcho', tmp_path]


def test_existing_pinned_provider_preserves_files_and_reprepares_pm(tmp_path, monkeypatch):
    import janitor_ext.install as installer
    import hermes_cli.plugins_cmd_install as command
    from hermes_cli import memory_setup
    plugin = _plugin_record(tmp_path); before = (plugin / '__init__.py').read_bytes()
    monkeypatch.setattr('hermes_constants.get_hermes_home', lambda: tmp_path)
    monkeypatch.setattr(command, 'dashboard_install_plugin', lambda *args, **kwargs: pytest.fail('must not replace existing files'))
    prepared = []
    monkeypatch.setattr(memory_setup, 'prepare_memory_provider_dependencies', lambda name: prepared.append(name))
    monkeypatch.setattr(installer, '_verify_fresh_honcho', lambda home: prepared.append(home))
    installer.install_honcho_plugin()
    assert (plugin / '__init__.py').read_bytes() == before
    assert prepared == ['honcho', tmp_path]


def test_custom_provider_is_preserved_and_install_is_not_claimed(tmp_path, monkeypatch):
    import janitor_ext.install as installer
    plugin = _plugin_record(tmp_path)
    metadata = tmp_path / 'plugins/.install-metadata.json'
    data = json.loads(metadata.read_text()); data['honcho']['revision'] = 'f' * 40; metadata.write_text(json.dumps(data))
    before = (plugin / '__init__.py').read_bytes()
    monkeypatch.setattr('hermes_constants.get_hermes_home', lambda: tmp_path)
    with pytest.raises(RuntimeError, match='was preserved'):
        installer.install_honcho_plugin()
    assert (plugin / '__init__.py').read_bytes() == before


def test_fresh_provider_probe_uses_pm_launcher_not_old_python(tmp_path, monkeypatch):
    import janitor_ext.install as installer
    calls = []
    monkeypatch.setattr(installer.subprocess, 'run', lambda argv, **kwargs: calls.append((argv, kwargs)))
    installer._verify_fresh_honcho(tmp_path)
    argv, kwargs = calls[0]
    assert argv[0] == str(installer.ROOT / 'scripts/janitor')
    assert argv[1:4] == ['--run-module', 'janitor_ext.install', '--home']
    assert argv[-1] == '--verify-honcho' and kwargs['check'] is True
    assert kwargs['env']['HERMES_HOME'] == str(tmp_path)


def test_honcho_personalized_server_toml_survives_rerun(tmp_path):
    prepare_profile(tmp_path, {'MINIMAX_API_KEY': 'fake', 'OPENAI_API_KEY': 'fake'}, 'local')
    prepare_service(tmp_path)
    config = tmp_path / 'honcho.toml'
    config.write_text(config.read_text() + '\n[custom]\noperator_setting = "preserved"\n')
    before = config.read_bytes()
    prepare_service(tmp_path)
    assert config.read_bytes() == before


def _transport_config():
    return {'embedding': {'VECTOR_DIMENSIONS': 2, 'model_config': {'transport': 'openai', 'model': 'embedding-test'}},
            'deriver': {'model_config': {'transport': 'anthropic', 'model': 'MiniMax-M2.7',
                                       'overrides': {'base_url': 'https://api.minimax.io/anthropic'}}}}


def test_local_readiness_exercises_embeddings_and_reasoning_with_server_config():
    import io
    from janitor_ext.honcho_probe import probe_transports
    calls = []
    class Response(io.BytesIO):
        status = 200
    def opener(request, timeout):
        calls.append((request.full_url, json.loads(request.data), request.headers, timeout))
        payload = {'data': [{'embedding': [0.1, 0.2]}]} if request.full_url.endswith('/embeddings') else {'stop_reason': 'end_turn', 'content': [{'type': 'text', 'text': 'OK'}]}
        return Response(json.dumps(payload).encode())
    probe_transports(_transport_config(), {'LLM_OPENAI_API_KEY': 'fake-openai', 'LLM_ANTHROPIC_API_KEY': 'fake-minimax'}, opener=opener)
    assert calls[0][1] == {'model': 'embedding-test', 'input': 'Janitor readiness', 'dimensions': 2}
    assert calls[1][0] == 'https://api.minimax.io/anthropic/v1/messages'
    assert calls[1][1]['max_tokens'] == 512
    assert calls[1][2]['X-api-key'] == 'fake-minimax'


def test_embedding_401_fails_without_echoing_provider_body_or_credentials():
    from urllib.error import HTTPError
    from janitor_ext.honcho_probe import probe_transports
    import io
    def refused(request, timeout):
        raise HTTPError(request.full_url, 401, 'fake-openai-secret rejected', {}, io.BytesIO(b'provider-body-sensitive'))
    with pytest.raises(RuntimeError, match='OpenAI embeddings.*401') as error:
        probe_transports(_transport_config(), {'LLM_OPENAI_API_KEY': 'fake-openai-secret'}, opener=refused)
    assert 'fake-openai-secret' not in str(error.value)
    assert 'provider-body-sensitive' not in str(error.value)


def test_local_probe_runs_inside_server_without_credentials_in_command(monkeypatch):
    from janitor_ext import honcho
    calls = []
    monkeypatch.setattr(honcho.subprocess, 'run', lambda args, **kwargs: calls.append((args, kwargs)))
    honcho.probe_local_transports()
    assert calls[0][0][:4] == ['docker', 'exec', 'janitor-honcho-api', 'python']
    assert calls[0][1]['check'] is True
    assert 'LLM_OPENAI_API_KEY' in calls[0][0][-1]


def test_reasoning_probe_rejects_thinking_only_max_tokens_result():
    import io
    from janitor_ext.honcho_probe import probe_transports
    class Response(io.BytesIO): status = 200
    def opener(request, timeout):
        data = {'data': [{'embedding': [0.1, 0.2]}]} if request.full_url.endswith('/embeddings') else {
            'stop_reason': 'max_tokens', 'content': [{'type': 'thinking', 'thinking': 'internal'}]}
        return Response(json.dumps(data).encode())
    with pytest.raises(RuntimeError, match='did not finish with generated text'):
        probe_transports(_transport_config(), {'LLM_OPENAI_API_KEY': 'fake', 'LLM_ANTHROPIC_API_KEY': 'fake'}, opener=opener)


def test_provider_readiness_detects_missing_sdk_even_with_current_pm(tmp_path, monkeypatch):
    import builtins
    import janitor_ext.install as installer
    import pm.client
    _plugin_record(tmp_path)
    monkeypatch.setattr(pm.client, 'venv_is_current', lambda **kwargs: True)
    original = builtins.__import__
    def missing(name, *args, **kwargs):
        if name == 'honcho': raise ModuleNotFoundError("No module named 'honcho'")
        return original(name, *args, **kwargs)
    monkeypatch.setattr(builtins, '__import__', missing)
    with pytest.raises(RuntimeError, match='Honcho SDK is missing'):
        installer.verify_honcho_provider(tmp_path)


def test_install_shell_preserves_selected_profile(tmp_path):
    import shutil
    import subprocess
    root = tmp_path / 'source'
    scripts = root / 'scripts'
    scripts.mkdir(parents=True)
    shutil.copyfile(Path(__file__).resolve().parents[1] / 'scripts/janitor-install.sh', scripts / 'janitor-install.sh')
    launcher = scripts / 'janitor'
    launcher.write_text('#!/bin/sh\nprintf "%s\\n" "$HERMES_HOME" "$@"\n')
    launcher.chmod(0o755)
    selected = tmp_path / 'home/profiles/work'
    result = subprocess.run(['bash', str(scripts / 'janitor-install.sh'), '--profile-only'],
                            env=dict(os.environ, HERMES_HOME=str(selected), JANITOR_HOME=str(tmp_path / 'home')),
                            capture_output=True, text=True, check=True)
    assert result.stdout.splitlines()[0] == str(selected)
    assert str(tmp_path / 'home') not in result.stdout.splitlines()[1:]


@pytest.mark.parametrize('module_name', ['install', 'honcho'])
def test_service_entrypoints_repair_only_selected_profile(tmp_path, monkeypatch, module_name):
    import importlib
    module = importlib.import_module('janitor_ext.' + module_name)
    selected = tmp_path / 'profiles/work'
    monkeypatch.setenv('JANITOR_HOME', str(tmp_path))
    monkeypatch.setenv('HERMES_HOME', str(selected))
    calls = []
    if module_name == 'install':
        monkeypatch.setattr(module, 'configure_credentials', lambda home, **kwargs: ({}, 'cloud'))
        monkeypatch.setattr(module, 'prepare_profile', lambda home, *args: calls.append(home) or {})
        module.main(['--profile-only', '--non-interactive'])
    else:
        monkeypatch.setattr(module, 'prepare_service', lambda home: calls.append(home))
        module.main(['--prepare-only'])
    assert calls == [selected]
    assert not list(tmp_path.glob('config.yaml'))


@pytest.mark.parametrize('named', [False, True])
@pytest.mark.parametrize('mode', ['local', 'cloud'])
def test_honcho_mode_switch_normalizes_nested_and_host_endpoints(tmp_path, named, mode):
    home = tmp_path / 'profiles/work' if named else tmp_path
    home.mkdir(parents=True, exist_ok=True)
    stale = 'http://localhost:1973/' if mode == 'cloud' else 'https://old-cloud.example.invalid'
    config = {'baseUrl': stale, 'endpoint': {'baseUrl': stale, 'timeout': 15},
              'hosts': {'hermes': {'baseUrl': stale, 'endpoint': {'baseUrl': stale}, 'workspace': 'private-work'}}}
    (home / 'honcho.json').write_text(json.dumps(config))
    prepare_profile(home, {'MINIMAX_API_KEY': 'fixture', 'HONCHO_API_KEY': 'fixture-cloud', 'OPENAI_API_KEY': 'fixture'}, mode)
    installed = json.loads((home / 'honcho.json').read_text())
    expected = 'http://127.0.0.1:1973' if mode == 'local' else 'https://api.honcho.dev'
    host = installed['hosts']['hermes']
    effective = host.get('baseUrl') or host.get('endpoint', {}).get('baseUrl') or installed.get('baseUrl') or installed.get('endpoint', {}).get('baseUrl') or 'https://api.honcho.dev'
    assert effective == expected
    assert installed.get('endpoint', {}).get('timeout') == 15
    assert host['workspace'] == 'private-work'


def test_explicit_cloud_proxy_endpoint_survives_local_endpoint_normalization(tmp_path):
    endpoint = 'http://127.0.0.1:39837'
    prepare_profile(tmp_path, {'MINIMAX_API_KEY': 'fake', 'HONCHO_API_KEY': 'fake-cloud',
                              'HONCHO_BASE_URL': endpoint}, 'cloud')
    assert read_secrets(tmp_path / '.env')['HONCHO_BASE_URL'] == endpoint
    config = json.loads((tmp_path / 'honcho.json').read_text())
    assert config['baseUrl'] == endpoint
    assert config['hosts']['hermes']['baseUrl'] == endpoint


@pytest.mark.parametrize('named', [False, True])
def test_honcho_mode_switch_normalizes_provider_yaml_fallback(tmp_path, named):
    home = tmp_path / 'profiles/work' if named else tmp_path
    home.mkdir(parents=True, exist_ok=True)
    (home / 'config.yaml').write_text(yaml.safe_dump({'honcho': {'base_url': 'http://localhost:1973', 'timeout': 19}}))
    (home / 'honcho.json').write_text(json.dumps({'hosts': {'hermes_work': {'workspace': 'private-work'}}}))
    credentials = {'MINIMAX_API_KEY': 'fixture', 'HONCHO_API_KEY': 'fixture-cloud', 'OPENAI_API_KEY': 'fixture'}
    prepare_profile(home, credentials, 'cloud')
    config = yaml.safe_load((home / 'config.yaml').read_text())
    assert not config['honcho'].get('base_url')  # The pinned SDK builder falls back to this after honcho.json.
    assert config['honcho']['timeout'] == 19
    prepare_profile(home, credentials, 'local')
    config = yaml.safe_load((home / 'config.yaml').read_text())
    assert config['honcho']['base_url'] == 'http://127.0.0.1:1973'
    assert json.loads((home / 'honcho.json').read_text())['hosts']['hermes_work']['workspace'] == 'private-work'


def _honcho_database_state(owner):
    return {'State': {'Running': True}, 'Config': {'Labels': {
        'com.docker.compose.project': 'janitor-honcho',
        'com.docker.compose.project.config_files': str(owner / 'docker/honcho-compose.yml'),
    }, 'Env': ['POSTGRES_USER=fixture-user', 'POSTGRES_PASSWORD=fixture-password']}}


def _existing_honcho_owner(home):
    (home / 'docker').mkdir(parents=True)
    (home / 'docker/honcho-compose.yml').write_text('name: janitor-honcho\n')
    (home / 'honcho.env').write_text('HONCHO_POSTGRES_USER=fixture-user\nHONCHO_POSTGRES_PASSWORD=fixture-password\n')


def test_named_profile_reuses_owned_running_honcho_without_reconfiguring_it(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from janitor_ext import honcho
    root = tmp_path / 'root'
    selected = root / 'profiles/work'
    selected.mkdir(parents=True)
    _existing_honcho_owner(root)
    (selected / 'honcho.json').write_text('{"workspace":"profile-private"}')
    (selected / '.env').write_text('HONCHO_API_KEY=profile-fixture\n')
    before = {path: path.read_bytes() for path in (root / 'honcho.env', selected / '.env', selected / 'honcho.json')}
    monkeypatch.setenv('JANITOR_HOME', str(root))
    calls = []
    def run(command, **kwargs):
        calls.append(command)
        if command[:2] == ['docker', 'inspect']:
            assert command[-1] in ('janitor-honcho-database', 'janitor-honcho-api')
            return SimpleNamespace(returncode=0, stdout=json.dumps([_honcho_database_state(root)]))
        assert command == ['docker', 'info']
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(honcho.subprocess, 'run', run)
    monkeypatch.setattr(honcho, 'prepare_service', lambda home: pytest.fail('shared owner must not be rewritten'))
    monkeypatch.setattr(honcho, 'verify_memory', lambda: calls.append('memory-ready'))
    monkeypatch.setattr(honcho, 'probe_local_transports', lambda: calls.append('transports-ready'))
    honcho.deploy(selected)
    assert calls[-2:] == ['memory-ready', 'transports-ready']
    assert before == {path: path.read_bytes() for path in before}
    assert not (selected / 'honcho.env').exists()
    assert not (selected / 'backups').exists()


@pytest.mark.parametrize('ownership', ['external', 'missing', 'multiple', 'wrong-project', 'credential-mismatch'])
def test_local_honcho_refuses_external_or_ambiguous_owner_before_writes(tmp_path, monkeypatch, ownership):
    from types import SimpleNamespace
    from janitor_ext import honcho
    selected = tmp_path / 'root'
    selected.mkdir()
    owner = tmp_path / 'external' if ownership == 'external' else selected
    _existing_honcho_owner(owner)
    state = _honcho_database_state(owner)
    labels = state['Config']['Labels']
    mutations = {
        'missing': labels.clear,
        'multiple': lambda: labels.update({'com.docker.compose.project.config_files':
            labels['com.docker.compose.project.config_files'] + ',' + str(owner / 'docker/another.yml')}),
        'wrong-project': lambda: labels.update({'com.docker.compose.project': 'foreign'}),
        'credential-mismatch': lambda: state['Config']['Env'].__setitem__(0, 'POSTGRES_USER=other-user'),
    }
    if mutation := mutations.get(ownership):
        mutation()
    monkeypatch.setenv('JANITOR_HOME', str(selected))
    def run(command, **kwargs):
        if command == ['docker', 'inspect', 'janitor-honcho-database']:
            return SimpleNamespace(returncode=0, stdout=json.dumps([state]))
        assert command == ['docker', 'info']
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(honcho.subprocess, 'run', run)
    with pytest.raises(RuntimeError, match='owner|ownership|credentials'):
        honcho.deploy(selected)
    assert not (selected / 'backups').exists()


def test_provider_guard_rejects_local_yaml_fallback_in_cloud_profile(tmp_path, monkeypatch):
    import sys
    from types import SimpleNamespace
    import pm.client
    import janitor_ext.install as installer
    _plugin_record(tmp_path)
    (tmp_path / 'config.yaml').write_text(yaml.safe_dump({'janitor': {'honcho_mode': 'cloud'},
                                                        'honcho': {'base_url': 'http://127.0.0.1:1973'}}))
    monkeypatch.setitem(sys.modules, 'honcho', SimpleNamespace(Honcho=lambda: None))
    monkeypatch.setattr(pm.client, 'venv_is_current', lambda **kwargs: True)
    monkeypatch.setattr(installer, 'honcho_connection', lambda home: SimpleNamespace(base_url=None, environment='production'))
    with pytest.raises(RuntimeError, match='Cloud Honcho still resolves to a local endpoint'):
        installer.verify_honcho_provider(tmp_path)


def test_local_honcho_owner_upgrade_keeps_dump_in_verified_backup(tmp_path, monkeypatch):
    import hashlib
    from types import SimpleNamespace
    from janitor_ext import honcho, volumes
    _existing_honcho_owner(tmp_path)
    monkeypatch.setenv('JANITOR_HOME', str(tmp_path))
    calls = []
    def run(command, **kwargs):
        calls.append(command)
        if command == ['docker', 'inspect', 'janitor-honcho-database']:
            return SimpleNamespace(returncode=0, stdout=json.dumps([_honcho_database_state(tmp_path)]))
        if command[:4] == ['docker', 'exec', 'janitor-honcho-database', 'pg_dump']:
            kwargs['stdout'].write(b'fixture database dump')
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(honcho.subprocess, 'run', run)
    monkeypatch.setattr(honcho, 'prepare_service', lambda home: tmp_path / 'source')
    monkeypatch.setattr(honcho, 'checkout_server', lambda source: None)
    monkeypatch.setattr(volumes, 'migrate_compose', lambda *args: None)
    monkeypatch.setattr(honcho, 'verify_memory', lambda: None)
    monkeypatch.setattr(honcho, 'probe_local_transports', lambda: None)
    honcho.deploy(tmp_path)
    backups = list((tmp_path / 'backups').iterdir())
    assert len(backups) == 1
    manifest = json.loads((backups[0] / 'manifest.json').read_text())
    assert {'path': 'honcho-postgres.dump', 'kind': 'postgres-dump',
            'sha256': hashlib.sha256(b'fixture database dump').hexdigest()} in manifest['files']
    assert any(command[-6:] == ['pg_dump', '-U', 'fixture-user', '-d', 'honcho', '-Fc'] for command in calls)
    assert read_secrets(tmp_path / 'honcho.env')['HONCHO_POSTGRES_PASSWORD'] == 'fixture-password'


@pytest.mark.parametrize('named', [False, True])
def test_honcho_connection_uses_profile_secrets_without_stale_process_endpoint(tmp_path, monkeypatch, named):
    import importlib
    from types import SimpleNamespace
    from plugins import memory
    from agent.secret_scope import get_secret, current_secret_scope
    from hermes_constants import get_hermes_home
    from janitor_ext.install import honcho_connection
    home = tmp_path / 'profiles/work' if named else tmp_path
    home.mkdir(parents=True, exist_ok=True)
    (home / '.env').write_text('HONCHO_API_KEY=profile-cloud-fixture\n')
    monkeypatch.setenv('HERMES_HOME', str(home))
    monkeypatch.setenv('HONCHO_API_KEY', 'stale-process-fixture')
    monkeypatch.setenv('HONCHO_BASE_URL', 'http://localhost:1973')
    class Provider:
        pass
    class ClientConfig:
        @classmethod
        def from_global_config(cls, config_path):
            assert get_hermes_home() == home
            assert config_path == home / 'honcho.json'
            return SimpleNamespace(api_key=get_secret('HONCHO_API_KEY'), base_url=get_secret('HONCHO_BASE_URL'))
    original_import = importlib.import_module
    monkeypatch.setattr(memory, 'load_memory_provider', lambda *args, **kwargs: Provider())
    monkeypatch.setattr(importlib, 'import_module', lambda name: SimpleNamespace(HonchoClientConfig=ClientConfig)
                        if name == Provider.__module__ + '.client' else original_import(name))
    before = current_secret_scope()
    connection = honcho_connection(home)
    assert connection.api_key == 'profile-cloud-fixture'
    assert connection.base_url is None
    assert current_secret_scope() is before


def test_honcho_transport_timeout_is_bounded_and_diagnostic_redacted(monkeypatch):
    import subprocess
    from janitor_ext import honcho
    def stall(command, **kwargs):
        timeout = kwargs.get('timeout')
        assert timeout is not None and 0 < timeout <= 180
        raise subprocess.TimeoutExpired(command, timeout, stderr='sensitive-provider-token')
    monkeypatch.setattr(honcho.subprocess, 'run', stall)
    with pytest.raises(RuntimeError, match='readiness failed') as error:
        honcho.probe_local_transports()
    assert 'sensitive-provider-token' not in str(error.value)
