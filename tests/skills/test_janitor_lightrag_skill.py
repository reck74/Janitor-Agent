"""LightRAG is a self-contained optional stack with persistent credentials/data."""
from pathlib import Path
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
    directory = home / 'docker'; directory.mkdir(parents=True)
    env_file = directory / 'lightrag.env'
    original = ('POSTGRES_PASSWORD=old-password\nLIGHTRAG_API_KEY=old-api\nAUTH_ACCOUNTS=admin:old-auth\n'
                'LLM_API_KEY=custom-key\nLLM_BINDING_HOST=https://custom.invalid/v1\n'
                'EMBEDDING_BINDING_HOST=http://janitor-honcho-ollama:11434\nEMBEDDING_MODEL=nomic-embed-text\n')
    env_file.write_text(original)
    monkeypatch.delenv('MINIMAX_API_KEY')
    result = subprocess.run(['bash', str(SKILL / 'scripts/deploy.sh')], capture_output=True, text=True, timeout=10, check=False)
    assert result.returncode == 37
    after = env_file.read_text()
    assert 'POSTGRES_PASSWORD=old-password' in after and 'LLM_API_KEY=custom-key' in after
    assert 'LLM_BINDING_HOST=https://custom.invalid/v1' in after
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
