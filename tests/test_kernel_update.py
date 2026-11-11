import importlib.util
import io
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / 'updates/kernel-6.18.59'
spec = importlib.util.spec_from_file_location('kernel_update', BUNDLE / 'update.py')
updater = importlib.util.module_from_spec(spec)
spec.loader.exec_module(updater)


@unittest.skipUnless(shutil.which('git'), 'git is needed to reconstruct the original 6.18.55 fixture')
class UpdateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.manifest = updater.load_bundle(BUNDLE)
        for entry in self.manifest['files']:
            target = self.root / entry['path']
            target.parent.mkdir(parents=True, exist_ok=True)
            if entry['after'] is not None:
                target.write_bytes((BUNDLE / entry['payload']).read_bytes())
        result = subprocess.run(['git', 'apply', '--reverse', str(BUNDLE / self.manifest['patch'])],
                                cwd=self.root, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        (self.root / 'rules.mk').write_text('# Existing OpenWrt root\n')
        (self.root / '.config').write_text('CONFIG_TARGET_mediatek_filogic=y\nCONFIG_PACKAGE_custom=y\n')
        for directory in ('dl', 'staging_dir', 'build_dir'):
            (self.root / directory).mkdir()
            (self.root / directory / 'keep').write_bytes(b'existing cached build data')

    def plan(self):
        return updater.build_plan(self.root, self.manifest, BUNDLE)

    def assert_updated(self):
        for entry in self.manifest['files']:
            path = self.root / entry['path']
            data = path.read_bytes() if path.exists() else None
            self.assertEqual(updater.digest(data), entry['after'], entry['path'])

    def test_public_unified_patch_applies_cleanly_to_original_55(self):
        result = subprocess.run(['git', 'apply', str(BUNDLE / self.manifest['patch'])],
                                cwd=self.root, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assert_updated()

    def test_upgrade_55_backs_up_files_and_preserves_configuration_and_caches(self):
        changes = self.plan()
        self.assertEqual(len(changes), 11)
        backup = updater.apply(self.root, changes, '6.18.59')
        self.assert_updated()
        journal = json.loads((backup / 'manifest.json').read_text())
        self.assertEqual(len(journal['files']), len(changes))
        for entry in changes:
            if entry['original'] is not None:
                self.assertEqual((backup / 'files' / entry['path']).read_bytes(), entry['original'])
        self.assertIn('CONFIG_PACKAGE_custom=y', (self.root / '.config').read_text())
        for directory in ('dl', 'staging_dir', 'build_dir'):
            self.assertEqual((self.root / directory / 'keep').read_bytes(), b'existing cached build data')

    def test_partial_updates_from_56_and_57_are_supported(self):
        for version in ('6.18.56', '6.18.57'):
            with self.subTest(version=version):
                metadata = ('LINUX_VERSION-6.18 = .' + version.rsplit('.', 1)[1] + '\n'
                            'LINUX_KERNEL_HASH-' + version + ' = ' + self.manifest['supported_kernels'][version] + '\n')
                (self.root / 'target/linux/generic/kernel-6.18').write_text(metadata)
                for entry in self.manifest['files']:
                    if entry['after'] is None:
                        (self.root / entry['path']).unlink(missing_ok=True)
                updater.apply(self.root, self.plan(), '6.18.59')
                self.assert_updated()

    def test_repeated_update_is_a_noop(self):
        updater.apply(self.root, self.plan(), '6.18.59')
        count = len(list((self.root / '.kernel-update-backups').iterdir()))
        self.assertEqual(self.plan(), [])
        self.assertIsNone(updater.apply(self.root, self.plan(), '6.18.59'))
        self.assertEqual(len(list((self.root / '.kernel-update-backups').iterdir())), count)

    def test_published_58_migration_is_supported(self):
        previous = ROOT / 'updates/kernel-6.18.58'
        for entry in json.loads((previous / 'manifest.json').read_text())['files']:
            path = self.root / entry['path']
            if entry['after'] is None:
                path.unlink(missing_ok=True)
            else:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes((previous / entry['payload']).read_bytes())
        changes = self.plan()
        self.assertEqual(len(changes), 4)
        updater.apply(self.root, changes, '6.18.59')
        self.assert_updated()

    def test_older_bundle_integrity_is_retained(self):
        previous = ROOT / 'updates/kernel-6.18.58'
        manifest = json.loads((previous / 'manifest.json').read_text())
        self.assertEqual(updater.digest((previous / manifest['patch']).read_bytes()), manifest['patch_sha256'])
        for entry in manifest['files']:
            if entry['after'] is not None:
                self.assertEqual(updater.digest((previous / entry['payload']).read_bytes()), entry['after'])

    def test_custom_source_modification_aborts_before_any_changes(self):
        path = self.root / 'package/kernel/mac80211/Makefile'
        path.write_text(path.read_text() + '\n# Local customization\n')
        original = (self.root / 'target/linux/generic/kernel-6.18').read_bytes()
        with self.assertRaisesRegex(ValueError, 'locally modified'):
            self.plan()
        self.assertEqual((self.root / 'target/linux/generic/kernel-6.18').read_bytes(), original)
        self.assertFalse((self.root / '.kernel-update-backups').exists())

    def test_optional_op_source_manifest_preserves_custom_devices(self):
        path = self.root / 'config/device-build.json'
        path.parent.mkdir()
        data = {'kernel': '6.18.55', 'kernel_sha256': self.manifest['supported_kernels']['6.18.55'],
                'devices': {'custom-router': {'target': 'mediatek', 'extra': [1, 2, 3]}}}
        path.write_text(json.dumps(data))
        updater.apply(self.root, self.plan(), '6.18.59')
        updated = json.loads(path.read_text())
        self.assertEqual(updated['kernel'], '6.18.59')
        self.assertEqual(updated['kernel_sha256'], self.manifest['kernel_sha256'])
        self.assertEqual(updated['devices'], data['devices'])

    def test_mid_update_write_failure_restores_original_files(self):
        changes = self.plan()
        original_write = updater.atomic_write
        failed = False

        def fail_once(path, content, mode):
            nonlocal failed
            if path == self.root / 'target/linux/generic/kernel-6.18' and not failed:
                failed = True
                raise OSError('simulated disk write failure')
            return original_write(path, content, mode)

        with mock.patch.object(updater, 'atomic_write', side_effect=fail_once):
            with self.assertRaisesRegex(OSError, 'disk write'):
                updater.apply(self.root, changes, '6.18.59')
        self.assertTrue(failed)
        for entry in changes:
            path = self.root / entry['path']
            self.assertEqual(path.read_bytes() if path.exists() else None, entry['original'])

    def test_symlink_cannot_redirect_a_source_update(self):
        path = self.root / 'package/kernel/mac80211/Makefile'
        original = path.read_bytes()
        path.unlink()
        outside = self.root / 'external-file'
        outside.write_bytes(original)
        path.symlink_to(outside)
        with self.assertRaisesRegex(ValueError, 'symbolic link'):
            self.plan()
        self.assertEqual(outside.read_bytes(), original)

    def test_check_mode_has_no_writes(self):
        before = (self.root / 'target/linux/generic/kernel-6.18').read_bytes()
        result = subprocess.run(['python3', str(BUNDLE / 'update.py'), str(self.root), '--check'], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.root / 'target/linux/generic/kernel-6.18').read_bytes(), before)
        self.assertFalse((self.root / '.kernel-update-backups').exists())

    def test_corrupt_download_does_not_replace_existing_archive(self):
        target = self.root / 'dl/linux-6.18.59.tar.xz'
        target.write_bytes(b'existing incomplete archive')
        with mock.patch.object(updater.urllib.request, 'urlopen', return_value=io.BytesIO(b'tampered')):
            with self.assertRaisesRegex(ValueError, 'checksum mismatch'):
                updater.download_kernel(self.root, self.manifest)
        self.assertEqual(target.read_bytes(), b'existing incomplete archive')
        self.assertEqual(list((self.root / 'dl').glob('.kernel-download-*')), [])

    def test_payload_tampering_is_rejected(self):
        local = self.root / 'copied-bundle'
        shutil.copytree(BUNDLE, local)
        entry = next(item for item in self.manifest['files'] if item['after'])
        (local / entry['payload']).write_bytes(b'tampered')
        with self.assertRaisesRegex(ValueError, 'payload failed'):
            updater.load_bundle(local)

    def test_bundle_payloads_match_current_source(self):
        current = json.loads((ROOT / 'config/device-build.json').read_text())
        bundle = ROOT / ('updates/kernel-' + current['kernel'])
        if not bundle.is_dir():
            self.skipTest('No migration bundle for the current kernel')
        spec = importlib.util.spec_from_file_location('current_kernel_update', bundle / 'update.py')
        current_updater = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(current_updater)
        manifest = current_updater.load_bundle(bundle)
        self.assertEqual(manifest['kernel_sha256'], current['kernel_sha256'])
        for entry in manifest['files']:
            path = ROOT / entry['path']
            self.assertEqual(current_updater.digest(path.read_bytes()) if path.exists() else None,
                             entry['after'], entry['path'])


if __name__ == '__main__':
    unittest.main()
