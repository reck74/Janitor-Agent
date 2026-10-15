"""Backups and skill relocation never discard committed state or personalized skills."""
import hashlib
import json
import sqlite3
from pathlib import Path

from janitor_ext.migrate import migrate, snapshot, relocate_skills


def test_snapshot_includes_wal_data_profiles_and_verifiable_hashes(tmp_path):
    profile = tmp_path / "profiles/work"; profile.mkdir(parents=True)
    (profile / ".env").write_text("TOKEN=fake\n")
    database = tmp_path / "state.db"
    with sqlite3.connect(database) as live:
        live.execute("PRAGMA journal_mode=WAL")
        live.execute("CREATE TABLE memories(value TEXT)")
        live.execute("INSERT INTO memories VALUES ('preserved')"); live.commit()
        backup = snapshot(tmp_path)
        with sqlite3.connect(backup / "state.db") as saved:
            assert saved.execute("SELECT value FROM memories").fetchone() == ("preserved",)
    manifest = json.loads((backup / "manifest.json").read_text())
    assert {entry["path"] for entry in manifest["files"]} >= {"state.db", "profiles/work/.env"}
    assert all(entry["sha256"] == hashlib.sha256((backup / entry["path"]).read_bytes()).hexdigest()
               for entry in manifest["files"])
    assert (backup / "profiles/work/.env").stat().st_mode & 0o777 == 0o600


def test_dry_run_does_not_create_backup_or_modify_files(tmp_path):
    (tmp_path / "config.yaml").write_text("_config_version: 23\n")
    before = list(tmp_path.rglob("*"))
    report = migrate(tmp_path)
    assert report["apply"] is False
    assert before == list(tmp_path.rglob("*"))


def test_skill_collision_preserves_both_copies_without_duplicate_active_name(tmp_path):
    old = tmp_path / "skills/devops/janitor-n8n"; old.mkdir(parents=True)
    current = tmp_path / "skills/janitor-n8n"; current.mkdir()
    (old / "SKILL.md").write_text("custom old skill")
    (current / "SKILL.md").write_text("current skill")
    backup = snapshot(tmp_path)
    relocate_skills(tmp_path, backup)
    assert not old.exists()
    assert (current / "SKILL.md").read_text() == "current skill"
    assert (backup / "displaced-skills/janitor-n8n/SKILL.md").read_text() == "custom old skill"


def test_profile_schema_migration_repairs_only_selected_honcho(monkeypatch):
    import janitor_ext.migrate as migration
    import janitor_ext.install as installer
    from hermes_cli import config
    calls = []
    monkeypatch.setattr(config, 'migrate_config', lambda **kwargs: calls.append('schema'))
    monkeypatch.setattr(config, 'load_config', lambda: {'memory': {'provider': 'honcho'}})
    monkeypatch.setattr(installer, 'install_honcho_plugin', lambda: calls.append('pinned-honcho'))
    migration.migrate_profile()
    assert calls == ['schema', 'pinned-honcho']
    calls.clear()
    monkeypatch.setattr(config, 'load_config', lambda: {'memory': {'provider': 'custom-provider'}})
    migration.migrate_profile()
    assert calls == ['schema']


def test_source_completion_repairs_honcho_per_dependency_home(tmp_path, monkeypatch):
    import janitor_ext.migrate as migration
    import pm.plugins_state as state
    import hermes_cli.memory_provider_migration as upstream
    import subprocess
    homes = [tmp_path / 'default', tmp_path / 'profiles/work', tmp_path / 'profiles/custom']
    monkeypatch.setattr(state, 'dependency_homes', lambda: homes)
    monkeypatch.setattr(upstream, 'configured_provider', lambda home: 'custom' if home == homes[-1] else 'honcho')
    calls = []
    monkeypatch.setattr(subprocess, 'run', lambda args, **kwargs: calls.append((args, kwargs)))
    migration.prepare_source_update(tmp_path)
    assert [call[1]['env']['HERMES_HOME'] for call in calls] == [str(home) for home in homes[:2]]
    assert all(call[1]['check'] is True and 'install_honcho_plugin' in call[0][-1] for call in calls)


def test_distribution_hook_failure_cannot_fall_through_to_unpinned_migration(tmp_path, monkeypatch):
    import pytest
    from hermes_cli import source_build, distribution_identity, main_install_repair, memory_provider_migration
    monkeypatch.setattr(main_install_repair, '_install_configured_features_missing_deps', lambda root: None)
    def broken(root): raise RuntimeError('mandatory pinned memory refused')
    monkeypatch.setattr(distribution_identity, 'distribution_provider', lambda root, key: broken)
    monkeypatch.setattr(memory_provider_migration, 'migrate_all_homes', lambda: pytest.fail('must not install a different catalog pin'))
    with pytest.raises(source_build.ProductBuildError, match='mandatory pinned memory refused'):
        source_build.build_update_products(tmp_path, desktop=False)


def test_snapshot_covers_private_state_and_nested_sqlite_without_following_links(tmp_path):
    home = tmp_path / "home"; home.mkdir()
    expected = {"auth.json", "active_profile", "memory/USER.md", "memory/MEMORY.md", "memories/USER.md", "memories/MEMORY.md", "auth/credential.json", "secrets/opaque.key", "profiles/work/auth.json"}
    for name in expected:
        path = home / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_text("private " + name)
    database = home / "auth/tokens.sqlite3"
    with sqlite3.connect(database) as live:
        live.execute("PRAGMA journal_mode=WAL")
        live.execute("CREATE TABLE tokens(value TEXT)"); live.execute("INSERT INTO tokens VALUES ('saved')"); live.commit()
        outside = tmp_path / "outside"; outside.mkdir(); (outside / "secret.txt").write_text("outside")
        (home / "secrets/foreign").symlink_to(outside, target_is_directory=True)
        (home / "auth/foreign.json").symlink_to(outside / "secret.txt")
        cache = home / "auth/.cache"; cache.mkdir(); (cache / "junk").write_text("regenerable")
        backup = snapshot(home)
        with sqlite3.connect(backup / "auth/tokens.sqlite3") as saved:
            assert saved.execute("SELECT value FROM tokens").fetchone() == ("saved",)
    manifest = json.loads((backup / "manifest.json").read_text())
    assert {entry["path"] for entry in manifest["files"]} == expected | {"auth/tokens.sqlite3"}
    for entry in manifest["files"]:
        saved = backup / entry["path"]
        assert hashlib.sha256(saved.read_bytes()).hexdigest() == entry["sha256"]
        assert saved.stat().st_mode & 0o777 == 0o600
        if entry["path"] in expected:
            assert saved.read_bytes() == (home / entry["path"]).read_bytes()


def test_migration_defaults_to_selected_profile_and_root_requires_explicit_scope(tmp_path, monkeypatch, capsys):
    import janitor_ext.migrate as migration
    root = tmp_path / 'home'
    selected = root / 'profiles/work'
    selected.mkdir(parents=True)
    (root / '.env').write_text('ROOT=untouched\n')
    (selected / '.env').write_text('PROFILE=selected\n')
    monkeypatch.setenv('JANITOR_HOME', str(root))
    monkeypatch.setenv('HERMES_HOME', str(selected))
    migration.main(['--dry-run'])
    report = json.loads(capsys.readouterr().out)
    assert report['home'] == str(selected)
    assert report['profiles'] == [str(selected)]
    migration.main(['--all-profiles', '--dry-run'])
    report = json.loads(capsys.readouterr().out)
    assert set(report['profiles']) == {str(root), str(selected)}
    assert not list(root.glob('backups/*'))


def test_snapshot_restores_durable_docker_credentials_and_bind_mount_data(tmp_path):
    from janitor_ext.migrate import restore_snapshot
    home = tmp_path / 'home'
    expected = {f'docker/{name}.env': 'PASSWORD=fixture-' + name for name in ('firecrawl', 'n8n', 'nocodb', 'waha', 'lightrag')}
    expected |= {'docker/n8n-compose.yml': 'services: {}\n', 'docker/local-files/workflow.json': '{"fixture":true}',
                 'profiles/work/docker/firecrawl.env': 'PASSWORD=profile-fixture'}
    for relative, content in expected.items():
        target = home / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)
    outside = tmp_path / 'outside'
    outside.mkdir()
    (outside / 'do-not-copy').write_text('foreign')
    (home / 'docker/foreign').symlink_to(outside, target_is_directory=True)
    backup = snapshot(home)
    inventory = json.loads((backup / 'manifest.json').read_text())
    assert {entry['path'] for entry in inventory['files']} == set(expected)
    restored = tmp_path / 'restored'
    restore_snapshot(backup, restored)
    for relative, content in expected.items():
        assert (restored / relative).read_text() == content
        assert (restored / relative).stat().st_mode & 0o777 == 0o600


def test_honcho_dump_is_registered_verified_and_not_restored_as_profile_file(tmp_path):
    from janitor_ext.migrate import record_backup_artifact, restore_snapshot
    import pytest
    home = tmp_path / 'home'
    home.mkdir()
    (home / '.env').write_text('KEY=preserved\n')
    backup = snapshot(home)
    dump = backup / 'honcho-postgres.dump'
    dump.write_bytes(b'PGDMP-fixture')
    record_backup_artifact(backup, dump, kind='postgres-dump')
    report = restore_snapshot(backup, tmp_path / 'restored')
    assert report['externalArtifacts'] == ['honcho-postgres.dump']
    assert not (tmp_path / 'restored/honcho-postgres.dump').exists()
    dump.write_bytes(b'corrupted')
    with pytest.raises(ValueError, match='checksum'):
        restore_snapshot(backup, tmp_path / 'corrupt-restored')
    assert not (tmp_path / 'corrupt-restored').exists()
