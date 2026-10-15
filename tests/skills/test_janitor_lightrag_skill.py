"""LightRAG is a self-contained optional stack with persistent credentials/data."""
from pathlib import Path
import json
import os
import subprocess
import sys

import hermes_yaml as yaml
import pytest

ROOT = Path(__file__).resolve().parents[2]
SKILL = ROOT / 'skills/janitor-lightrag'


def test_lightrag_embeddings_are_independent_and_persisted():
    model = yaml.safe_load((SKILL / 'scripts/lightrag-compose.yml').read_text())
    app = model['services']['lightrag']
    embeddings = model['services']['lightrag-embeddings']
    assert app['networks'] == ['janitor-lightrag-network']
    assert 'lightrag-embeddings' in app['depends_on']
    assert embeddings['container_name'] == 'janitor-lightrag-embeddings'
    assert embeddings['volumes'] == ['lightrag_embeddings:/root/.ollama']
    assert model['volumes']['lightrag_embeddings']['name'].startswith('janitor-')
    assert all(not cfg.get('external') for cfg in model['networks'].values())
    assert model['services']['lightrag-db']['volumes'] == ['lightrag_pg:/var/lib/postgresql']


def _pull_failure_env(tmp_path, monkeypatch):
    bin_dir = tmp_path / 'bin'; bin_dir.mkdir()
    docker = bin_dir / 'docker'
    docker.write_text('#!/bin/sh\ncase "$1" in info) exit 0;; compose) case " $* " in *" pull "*) exit 37;; esac;; esac\nexit 0\n')
    docker.chmod(0o755)
    home = tmp_path / 'profile'
    monkeypatch.setenv('PATH', str(bin_dir) + os.pathsep + os.environ['PATH'])
    monkeypatch.setenv('HERMES_HOME', str(home))
    monkeypatch.setenv('JANITOR_SERVICE_ENV', '1')
    monkeypatch.setenv('JANITOR_SERVICE_PYTHON', sys.executable)
    monkeypatch.setenv('MINIMAX_API_KEY', 'test-minimax-not-a-real-key')
    return home


def test_fresh_deploy_uses_minimax_and_does_not_claim_success_on_pull_failure(tmp_path, monkeypatch):
    home = _pull_failure_env(tmp_path, monkeypatch)
    result = subprocess.run(['bash', str(SKILL / 'scripts/deploy.sh')], capture_output=True, text=True, timeout=10, check=False)
    assert result.returncode == 37
    text = (home / 'docker/lightrag.env').read_text()
    assert 'LLM_BINDING_HOST=https://api.minimax.io/v1' in text
    assert 'LLM_MODEL=MiniMax-M2.7' in text
    assert 'LLM_BINDING_API_KEY=test-minimax-not-a-real-key' in text
    query_options = next(line.partition('=')[2] for line in text.splitlines()
                         if line.startswith('QUERY_OPENAI_LLM_EXTRA_BODY='))
    assert json.loads(query_options) == {'reasoning_split': True}
    assert 'POSTGRES_HOST=lightrag-db' in text
    assert 'POSTGRES_USER=lightrag' in text
    assert 'POSTGRES_DATABASE=lightrag' in text
    assert 'TOKEN_SECRET=' in text
    assert 'EMBEDDING_BINDING_HOST=http://janitor-lightrag-embeddings:11434' in text
    assert 'EMBEDDING_MODEL=nomic-embed-text:v1.5' in text
    assert not (home / '.env').exists(), 'failed deploy must not publish a working API'
    assert (home / 'docker/lightrag.env').stat().st_mode & 0o077 == 0


def test_rerun_preserves_credentials_and_custom_llm_with_embedding_backup(tmp_path, monkeypatch):
    home = _pull_failure_env(tmp_path, monkeypatch)
    # BSD sed does not accept the GNU `sed -i SCRIPT FILE` call. The migration
    # must not depend on that external editing command on any host.
    sed = tmp_path / 'bin/sed'
    sed.write_text('#!/bin/sh\necho "in-place sed unavailable" >&2\nexit 64\n', encoding='utf-8')
    sed.chmod(0o755)
    directory = home / 'docker'; directory.mkdir(parents=True)
    env_file = directory / 'lightrag.env'
    original = ('POSTGRES_PASSWORD=old-password\nLIGHTRAG_API_KEY=old-api\nAUTH_ACCOUNTS=admin:old-auth\n'
                'LLM_API_KEY=custom-key\nLLM_BINDING_HOST=https://custom.invalid/v1?x=a&y=b\n'
                '# Keep custom values verbatim.\nCUSTOM_VALUE=spaces / ampersand & equals= café\n'
                'EMBEDDING_BINDING_HOST=http://janitor-honcho-ollama:11434\nEMBEDDING_MODEL=nomic-embed-text\n')
    env_file.write_text(original)
    monkeypatch.delenv('MINIMAX_API_KEY')
    result = subprocess.run(['bash', str(SKILL / 'scripts/deploy.sh')], capture_output=True, text=True, timeout=10, check=False)
    assert result.returncode == 37
    after = env_file.read_text()
    assert 'POSTGRES_PASSWORD=old-password' in after and 'LLM_API_KEY=custom-key' in after
    assert 'LLM_BINDING_HOST=https://custom.invalid/v1?x=a&y=b\n' in after
    assert '# Keep custom values verbatim.\nCUSTOM_VALUE=spaces / ampersand & equals= café\n' in after
    assert 'LLM_BINDING_API_KEY=custom-key' in after
    assert 'POSTGRES_HOST=lightrag-db' in after
    assert 'POSTGRES_DATABASE=lightrag' in after
    assert 'TOKEN_SECRET=' in after
    assert 'EMBEDDING_BINDING_HOST=http://janitor-lightrag-embeddings:11434' in after
    assert next(directory.glob('lightrag.env.pre-isolated-embeddings.*.bak')).read_text() == original


def test_skill_documents_active_paths_and_model_download():
    text = (SKILL / 'SKILL.md').read_text()
    assert '~/.janitor/skills/janitor-lightrag/scripts/deploy.sh' in text
    assert 'nomic-embed-text:v1.5' in text
    assert 'MINIMAX_API_KEY' in text
    assert 'skills/devops/' not in text
    assert 'ollama pull nomic-embed-text:v1.5' in (SKILL / 'scripts/deploy.sh').read_text()


def test_lightrag_profile_credentials_are_unique_after_reinstall(tmp_path):
    profile = tmp_path / 'profile'
    docker = profile / 'docker'
    docker.mkdir(parents=True)
    (docker / 'lightrag.env').write_text('LIGHTRAG_API_KEY=test-lightrag-api\nAUTH_ACCOUNTS=admin:test-password\n')
    (profile / '.env').write_text('MINIMAX_API_KEY=untouched\nLIGHTRAG_WEBUI_USER=previous\nLIGHTRAG_WEBUI_PASSWORD=previous\n')
    fixture = tmp_path / 'deploy-functions.sh'
    source = (SKILL / 'scripts/deploy.sh').read_text()
    assert source.endswith('main "$@"\n')
    fixture.write_text(source.removesuffix('main "$@"\n'))
    env = dict(os.environ, HERMES_HOME=str(profile), JANITOR_SERVICE_ENV='1')
    for _ in range(2):
        result = subprocess.run(['bash', '-c', 'source "$1"; inject_janitor_env', 'bash', str(fixture)],
                                env=env, text=True, capture_output=True, timeout=10, check=False)
        assert result.returncode == 0, result.stderr
    content = (profile / '.env').read_text()
    for key in ('LIGHTRAG_API_URL', 'LIGHTRAG_API_KEY', 'LIGHTRAG_WEBUI_USER', 'LIGHTRAG_WEBUI_PASSWORD'):
        assert sum(line.startswith(key + '=') for line in content.splitlines()) == 1, key
    assert 'MINIMAX_API_KEY=untouched\n' in content
    assert 'LIGHTRAG_WEBUI_USER=admin\n' in content
    assert 'LIGHTRAG_WEBUI_PASSWORD=test-password\n' in content
    assert (profile / '.env').stat().st_mode & 0o077 == 0


@pytest.mark.parametrize("digest, present", [
    ("8688dbc0926c1dfdc1b8b7489034e1fedb06f6ac66472dd2d7f0ed6d7d23ba29", True),
    ("8688dbc0926c1dfdc1b8b7489034e1fedb06f6ac66472dd2d7f0ed6d7d23ba29", False),
    ("f" * 64, True),
    ("f" * 64, False),
    ("missing", True),
])
def test_deploy_rejects_embedding_model_drift_before_starting_app(tmp_path, digest, present):
    binary = tmp_path / 'bin'
    binary.mkdir()
    trace = tmp_path / 'docker-calls'
    docker = binary / 'docker'
    docker.write_text(
        '#!/bin/sh\n'
        'printf "%s\\n" "$*" >> "$DOCKER_CALLS"\n'
        'case " $* " in\n'
        '  *" test -f "*) [ "$MODEL_PRESENT" = 1 ]; exit $?;;\n'
        '  *" sha256sum "*)\n'
        '    [ "$MODEL_DIGEST" != missing ] || exit 1\n'
        '    printf "%s  manifest\\n" "$MODEL_DIGEST";;\n'
        'esac\n'
    )
    docker.chmod(0o755)
    python = binary / 'python'
    python.write_text('#!/bin/sh\nexit 0\n')
    python.chmod(0o755)
    source = (SKILL / 'scripts/deploy.sh').read_text()
    fixture = tmp_path / 'deploy-functions.sh'
    fixture.write_text(source.removesuffix('main "$@"\n'))
    env = dict(os.environ, PATH=str(binary) + os.pathsep + os.environ['PATH'],
               HERMES_HOME=str(tmp_path / 'profile'), JANITOR_SERVICE_ENV='1',
               JANITOR_SERVICE_PYTHON=str(python), DOCKER_CALLS=str(trace), MODEL_DIGEST=digest, MODEL_PRESENT=str(int(present)))
    result = subprocess.run(['bash', '-c', 'source "$1"; launch', 'bash', str(fixture)],
                            env=env, text=True, capture_output=True, timeout=10, check=False)
    app_started = any(line.endswith(' up -d') for line in trace.read_text().splitlines())
    if present:
        assert not any(' ollama pull ' in line for line in trace.read_text().splitlines())
    if digest.startswith('8688db'):
        assert result.returncode == 0, result.stderr
        assert app_started
    else:
        assert result.returncode != 0
        assert not app_started
