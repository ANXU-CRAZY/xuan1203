import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

import install_huiyan_land as installer


class InstallerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.artifacts = root / 'artifacts'
        self.artifacts.mkdir()
        self.destination = root / 'installed'
        self.patches = [patch.object(installer, 'ARTIFACTS', self.artifacts),
                        patch.object(installer, 'DESTINATION', self.destination),
                        patch.object(installer.sys, 'platform', 'win32')]
        for item in self.patches:
            item.start()
            self.addCleanup(item.stop)

    def make_package(self, extra=None):
        archive = self.artifacts / 'source.zip'
        with zipfile.ZipFile(archive, 'w') as package:
            package.writestr('方舟慧眼-轻量版/方舟慧眼-轻量版.exe', b'executable')
            package.writestr('方舟慧眼-轻量版/checkpoints/model.pt', b'weights')
            if extra:
                package.writestr(extra, b'invalid')
        data = archive.read_bytes()
        parts = []
        for index, chunk in enumerate((data[:len(data)//2], data[len(data)//2:]), 1):
            name = f'land-{index:02}.part'
            (self.artifacts / name).write_bytes(chunk)
            parts.append({'name': name, 'size': len(chunk), 'sha256': hashlib.sha256(chunk).hexdigest()})
        (self.artifacts / 'manifest.json').write_text(json.dumps({
            'archive_sha256': hashlib.sha256(data).hexdigest(), 'parts': parts,
        }), encoding='utf-8')

    def test_valid_package_installs(self):
        self.make_package()
        installer.install()
        self.assertEqual((self.destination / '方舟慧眼-轻量版/checkpoints/model.pt').read_bytes(), b'weights')

    def test_corrupt_part_is_rejected(self):
        self.make_package()
        (self.artifacts / 'land-01.part').write_bytes(b'corrupted')
        with self.assertRaises(SystemExit):
            installer.install()
        self.assertFalse((self.destination / '方舟慧眼-轻量版').exists())

    def test_path_traversal_is_rejected(self):
        self.make_package('方舟慧眼-轻量版/../../outside.txt')
        with self.assertRaises(SystemExit):
            installer.install()
        self.assertFalse((self.destination.parent / 'outside.txt').exists())

    def test_existing_install_is_not_overwritten(self):
        self.make_package()
        (self.destination / '方舟慧眼-轻量版').mkdir(parents=True)
        with self.assertRaises(SystemExit):
            installer.install()


if __name__ == '__main__':
    unittest.main()
