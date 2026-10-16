"""Exclusive disposable directory ownership for expensive installation fixtures."""
from dataclasses import dataclass
import json
from pathlib import Path
import uuid

from pm.filesystem import remove_tree


@dataclass(frozen=True)
class OwnedDirectory:
    path: Path
    token: str

    @classmethod
    def create(cls, path: Path):
        path.mkdir(parents=True, exist_ok=False)
        owned = cls(path.resolve(), uuid.uuid4().hex)
        (owned.path / '.e2e-owner.json').write_text(json.dumps({
            'path': str(owned.path), 'token': owned.token,
        }), encoding='utf-8')
        return owned

    def remove(self):
        marker = self.path / '.e2e-owner.json'
        if self.path.is_symlink() or self.path.resolve() != self.path or marker.is_symlink():
            raise ValueError('Fixture ownership path changed; refusing cleanup')
        expected = {'path': str(self.path), 'token': self.token}
        if json.loads(marker.read_text(encoding='utf-8')) != expected:
            raise ValueError('Fixture ownership marker changed; refusing cleanup')
        remove_tree(self.path)
