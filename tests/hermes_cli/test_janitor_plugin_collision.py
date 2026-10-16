"""Plugin discovery and listing agree when backups declare the active plugin name."""

import pytest

from hermes_cli.plugins_discovery import resolve_listing_collision, resolve_manifest_winners
from hermes_cli.plugins_manifest import PluginManifest


@pytest.mark.parametrize('reverse', [False, True])
def test_canonical_copy_wins_in_either_discovery_order_and_both_paths_are_reported(tmp_path, caplog, reverse):
    live = PluginManifest('foo', version='2', source='user', path=str(tmp_path / 'foo'))
    backup = PluginManifest('foo', version='1', source='user', path=str(tmp_path / 'foo.bak-x'))
    manifests = [backup, live] if reverse else [live, backup]
    assert resolve_manifest_winners(manifests)['foo'] is live
    assert live.path in caplog.text and backup.path in caplog.text
    rows = [(m.name, m.version, '', m.source, m.path, m.name) for m in manifests]
    assert resolve_listing_collision(*rows)[4] == live.path


def test_ambiguous_noncanonical_copies_keep_first_and_warn(tmp_path, caplog):
    first = PluginManifest('foo', source='user', path=str(tmp_path / 'foo.old'))
    second = PluginManifest('foo', source='user', path=str(tmp_path / 'foo.new'))
    assert resolve_manifest_winners([first, second])['foo'] is first
    assert first.path in caplog.text and second.path in caplog.text


def test_source_precedence_and_bundled_impostor_guard_remain(tmp_path):
    bundled = PluginManifest('foo', source='bundled', path=str(tmp_path / 'bundled/foo'))
    user = PluginManifest('foo', source='user', path=str(tmp_path / 'user/foo'))
    project = PluginManifest('foo', source='project', path=str(tmp_path / 'project/foo'))
    assert resolve_manifest_winners([bundled, user, project])['foo'] is project
    impostor = PluginManifest('foo', source='user', path=str(tmp_path / 'user/impostor'))
    assert resolve_manifest_winners([bundled, impostor])['foo'] is bundled


def test_git_listing_label_does_not_give_a_backup_precedence(tmp_path):
    live = ('foo', '2', '', 'user', tmp_path / 'foo', 'foo')
    backup = ('foo', '1', '', 'git', tmp_path / 'foo.bak-x', 'foo')
    assert resolve_listing_collision(live, backup) is live
