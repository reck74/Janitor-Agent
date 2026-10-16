"""Installation fixture cleanup never removes preexisting or unowned data."""
import json
import pytest
from tests.e2e.core.windows_update._owned_directory import OwnedDirectory


def test_exclusive_creation_preserves_existing_directory(tmp_path):
    existing = tmp_path / 'existing'
    existing.mkdir()
    keep = existing / 'user-data'
    keep.write_text('preserve')
    with pytest.raises(FileExistsError):
        OwnedDirectory.create(existing)
    assert keep.read_text() == 'preserve'


def test_owned_tree_can_be_released(tmp_path):
    owned = OwnedDirectory.create(tmp_path / 'fixture')
    (owned.path / 'installed').write_text('fixture data')
    owned.remove()
    assert not owned.path.exists()


@pytest.mark.parametrize('mutation', ['token', 'path', 'missing'])
def test_changed_ownership_refuses_cleanup(tmp_path, mutation):
    owned = OwnedDirectory.create(tmp_path / 'fixture')
    marker = owned.path / '.e2e-owner.json'
    keep = owned.path / 'preserve'
    keep.write_text('unchanged')
    if mutation == 'missing':
        marker.unlink()
    else:
        data = json.loads(marker.read_text())
        data[mutation] = 'different'
        marker.write_text(json.dumps(data))
    with pytest.raises((ValueError, FileNotFoundError)):
        owned.remove()
    assert keep.read_text() == 'unchanged'


@pytest.mark.platforms('posix')
def test_replaced_directory_symlink_preserves_external_data(tmp_path):
    owned = OwnedDirectory.create(tmp_path / 'fixture')
    retained = tmp_path / 'retained'
    owned.path.rename(retained)
    owned.path.symlink_to(retained, target_is_directory=True)
    with pytest.raises(ValueError, match='ownership path changed'):
        owned.remove()
    assert (retained / '.e2e-owner.json').is_file()
