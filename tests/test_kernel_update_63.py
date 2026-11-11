import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / 'updates/kernel-6.18.63'
spec = importlib.util.spec_from_file_location('kernel_update_63', BUNDLE / 'update.py')
updater = importlib.util.module_from_spec(spec)
spec.loader.exec_module(updater)


@unittest.skipUnless(shutil.which('git'), 'git is needed for the 6.18.60 source fixture')
class Kernel63UpdateTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.manifest = updater.load_bundle(BUNDLE)
        for entry in self.manifest['files']:
            if entry['after'] is not None:
                target = self.root / entry['path']
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes((BUNDLE / entry['payload']).read_bytes())
        subprocess.run(['git', 'apply', '--reverse', str(BUNDLE / self.manifest['patch'])],
                       cwd=self.root, check=True, capture_output=True)
        (self.root / 'rules.mk').write_text('# OpenWrt build root\n')
        for name in ('.config', 'dl/keep', 'build_dir/keep', 'staging_dir/keep', 'feeds/keep'):
            target = self.root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(b'custom build data')

    def plan(self):
        return updater.build_plan(self.root, self.manifest, BUNDLE)

    def test_60_update_installs_mt76_dependencies_and_preserves_existing_build(self):
        backup = updater.apply(self.root, self.plan(), '6.18.63')
        self.assertTrue((backup / 'manifest.json').is_file())
        for entry in self.manifest['files']:
            path = self.root / entry['path']
            self.assertEqual(updater.digest(path.read_bytes()) if path.exists() else None,
                             entry['after'], entry['path'])
        source = (self.root / 'package/kernel/mt76/Makefile').read_text()
        self.assertIn('PKG_SOURCE_VERSION:=' + self.manifest['mt76']['source_commit'], source)
        self.assertIn('PKG_MIRROR_HASH:=' + self.manifest['mt76']['mirror_sha256'], source)
        self.assertTrue((self.root / 'target/linux/generic/pending-6.18/797-00-wifi-cfg80211-add-the-flow-key-and-flow-description-.patch').exists())
        for name in ('.config', 'dl/keep', 'build_dir/keep', 'staging_dir/keep', 'feeds/keep'):
            self.assertEqual((self.root / name).read_bytes(), b'custom build data')
        self.assertEqual(self.plan(), [])
        self.assertIsNone(updater.apply(self.root, self.plan(), '6.18.63'))

    def test_custom_mt76_makefile_blocks_all_changes(self):
        source = self.root / 'package/kernel/mt76/Makefile'
        source.write_bytes(source.read_bytes() + b'\n# local driver override\n')
        before = (self.root / 'target/linux/generic/kernel-6.18').read_bytes()
        with self.assertRaisesRegex(ValueError, 'locally modified'):
            self.plan()
        self.assertEqual((self.root / 'target/linux/generic/kernel-6.18').read_bytes(), before)
        self.assertFalse((self.root / '.kernel-update-backups').exists())

    def test_failure_after_wireless_writes_rolls_back_changes(self):
        changes = self.plan()
        atomic_write = updater.atomic_write
        failed = False

        def fail_once(path, payload, mode):
            nonlocal failed
            if path == self.root / 'target/linux/generic/kernel-6.18' and not failed:
                failed = True
                raise OSError('simulated write failure')
            atomic_write(path, payload, mode)

        with mock.patch.object(updater, 'atomic_write', side_effect=fail_once):
            with self.assertRaisesRegex(OSError, 'simulated write failure'):
                updater.apply(self.root, changes, '6.18.63')
        self.assertTrue(failed)
        for entry in changes:
            path = self.root / entry['path']
            self.assertEqual(path.read_bytes() if path.exists() else None, entry['original'])
