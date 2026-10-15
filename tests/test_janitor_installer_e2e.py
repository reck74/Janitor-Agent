"""Local protocol E2E; the CI smoke additionally acquires PM and builds products."""
import json
import os
from pathlib import Path
import subprocess
import sys
from urllib.request import Request, urlopen

import pytest

from janitor_ext.ci_smoke import HONCHO_KEY, REPLY, STAGES, provider_stand_in, snapshot_source

pytestmark = pytest.mark.skipif(sys.platform != "linux", reason="Janitor bootstrap release target is Linux")

ROOT = Path(__file__).resolve().parents[1]


def _git(root, *args):
    return subprocess.run(["git", "-c", "core.hooksPath=/dev/null", "-c", "commit.gpgsign=false",
                           "-c", "user.name=Janitor Test", "-c", "user.email=janitor-test@example.invalid",
                           *args], cwd=root, text=True, capture_output=True, check=True).stdout.strip()


def _fixture(tmp_path):
    source = tmp_path / "remote"; source.mkdir()
    _git(source, "init", "-b", "main")
    (source / "README.md").write_text("isolated Janitor repository fixture\n")
    _git(source, "add", ".")
    _git(source, "commit", "-m", "test fixture")
    commit = _git(source, "rev-parse", "HEAD")
    home = tmp_path / "home"; home.mkdir()
    binary = tmp_path / "bin"; binary.mkdir()
    docker = binary / "docker"
    docker.write_text('#!/bin/sh\n[ "$1" = info ] || exit 99\nexit "${JANITOR_TEST_DOCKER_STATUS:-0}"\n')
    docker.chmod(0o755)
    env = {key: value for key, value in os.environ.items() if key in {"PATH", "LANG", "LC_ALL", "TZ", "TMPDIR"}}
    env.update(HOME=str(home), JANITOR_HOME=str(home / ".janitor"), HERMES_HOME=str(home / ".janitor"),
               JANITOR_REPO_URL=source.as_uri(), PATH=str(binary) + os.pathsep + env["PATH"])
    destination = home / ".janitor/janitor-core"
    command = ["bash", str(ROOT / "scripts/bootstrap.sh"), "--dir", str(destination),
               "--hermes-home", env["JANITOR_HOME"], "--commit", commit, "--branch", "main", "--non-interactive", "--json"]
    return source, destination, commit, env, command


def test_bootstrap_manifest_matches_complete_acceptance_ladder():
    result = subprocess.run(["bash", str(ROOT / "scripts/bootstrap.sh"), "--manifest"], text=True, capture_output=True, check=True)
    manifest = json.loads(result.stdout)
    assert manifest["protocol_version"] == 1
    assert tuple(stage["name"] for stage in manifest["stages"]) == STAGES


def test_prerequisites_and_repository_use_real_git_without_host_installation(tmp_path):
    source, destination, commit, env, command = _fixture(tmp_path)
    for stage in ("prerequisites", "repository"):
        result = subprocess.run([*command, "--stage", stage], env=env, text=True, capture_output=True, timeout=30, check=False)
        assert result.returncode == 0, result.stderr + result.stdout
        frame = json.loads(result.stdout.splitlines()[-1])
        assert frame == {"ok": True, "stage": stage, "skipped": False, "reason": ""}
    assert _git(destination, "rev-parse", "HEAD") == commit
    assert _git(destination, "remote", "get-url", "origin") == source.as_uri()
    assert (destination / "README.md").read_text() == "isolated Janitor repository fixture\n"
    # No runtime stage was requested, so no acquisition or product command ran.
    assert not (destination / ".hermes").exists()


def test_noninteractive_docker_failure_reports_failed_stage_before_clone(tmp_path):
    _, destination, _, env, command = _fixture(tmp_path)
    env["JANITOR_TEST_DOCKER_STATUS"] = "1"
    result = subprocess.run([*command, "--stage", "prerequisites"], env=env, text=True, capture_output=True, timeout=30, check=False)
    assert result.returncode != 0
    assert json.loads(result.stdout.splitlines()[-1])["ok"] is False
    assert "Docker is unavailable" in result.stderr
    assert not destination.exists()


def test_snapshot_includes_fork_working_files_and_excludes_ignored_state(tmp_path):
    source, _, _, _, _ = _fixture(tmp_path)
    (source / ".gitignore").write_text("secrets.env\nnode_modules/\n")
    (source / "janitor_ext").mkdir()
    (source / "janitor_ext/new.py").write_text("value = 'working copy'\n")
    (source / "secrets.env").write_text("synthetic ignored secret")
    (source / "node_modules").mkdir()
    (source / "node_modules/big.js").write_text("ignored dependency")
    snapshot = tmp_path / "snapshot"
    commit = snapshot_source(source, snapshot)
    assert _git(snapshot, "rev-parse", "HEAD") == commit
    assert (snapshot / "janitor_ext/new.py").is_file()
    assert not (snapshot / "secrets.env").exists()
    assert not (snapshot / "node_modules").exists()
    assert _git(snapshot, "status", "--porcelain") == ""


@pytest.mark.parametrize("stream", [False, True])
def test_provider_stand_in_serves_anthropic_wire_protocol_on_loopback(stream):
    with provider_stand_in() as (url, calls):
        request = Request(url + "/v1/messages", data=json.dumps({"model": "MiniMax-M2.7", "stream": stream}).encode(),
                          headers={"Content-Type": "application/json"})
        with urlopen(request, timeout=5) as response:
            body = response.read().decode()
            assert REPLY in body
            if stream:
                assert "event: message_start" in body and "event: message_stop" in body
            else:
                assert json.loads(body)["stop_reason"] == "end_turn"
        assert calls == [{"path": "/v1/messages", "model": "MiniMax-M2.7"}]


def test_cloud_memory_verification_uses_configured_endpoint_and_authentication():
    from janitor_ext.honcho import verify_memory
    from urllib.error import HTTPError
    with provider_stand_in() as (url, calls):
        verify_memory(url, api_key=HONCHO_KEY, workspace="janitor-ci")
        assert calls[-1] == {"path": "/v3/workspaces", "model": None, "accepted_auth": True}
        with pytest.raises(HTTPError) as error:
            verify_memory(url, api_key="invalid-synthetic-key", workspace="janitor-ci")
        assert error.value.code == 401


def test_bootstrap_configuration_stage_preserves_explicit_profile(tmp_path):
    source = tmp_path / 'source'
    scripts = source / 'scripts'
    scripts.mkdir(parents=True)
    delegate = scripts / 'janitor-install.sh'
    delegate.write_text('#!/bin/sh\nprintf "%s\\n" "$HERMES_HOME"\n')
    selected = tmp_path / 'home/profiles/work'
    result = subprocess.run(['bash', str(ROOT / 'scripts/bootstrap.sh'), '--dir', str(source),
                             '--stage', 'config', '--non-interactive'],
                            env=dict(os.environ, HERMES_HOME=str(selected), JANITOR_HOME=str(tmp_path / 'home')),
                            capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == str(selected)
