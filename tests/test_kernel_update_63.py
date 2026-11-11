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

    def test_launcher_updates_current_build_root_and_can_be_repeated(self):
        for expected in ('96 source file updates', '0 source file updates'):
            result = subprocess.run(['sh', str(BUNDLE / 'update.sh')], cwd=self.root,
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('op-source', result.stdout)
            self.assertIn(expected, result.stdout)
        self.assertEqual((self.root / '.config').read_bytes(), b'custom build data')

    def test_launcher_check_accepts_explicit_root_without_writes(self):
        before = (self.root / 'target/linux/generic/kernel-6.18').read_bytes()
        result = subprocess.run(['sh', str(BUNDLE / 'update.sh'), str(self.root), '--check'],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.root / 'target/linux/generic/kernel-6.18').read_bytes(), before)
        self.assertFalse((self.root / '.kernel-update-backups').exists())


@unittest.skipUnless(shutil.which('git'), 'git is needed for the ImmortalWrt source fixture')
class ImmortalWrt63UpdateTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='immortal build ')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.bundle = BUNDLE / 'profiles/immortalwrt'
        self.manifest = updater.load_bundle(self.bundle)

    def fixture(self, master=False):
        for entry in self.manifest['files']:
            if entry['after'] is not None:
                target = self.root / entry['path']
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes((self.bundle / entry['payload']).read_bytes())
        patch = self.manifest['extra_patches'][0]['path'] if master else self.manifest['patch']
        subprocess.run(['git', 'apply', '--reverse', str(self.bundle / patch)],
                       cwd=self.root, check=True, capture_output=True)
        (self.root / 'rules.mk').write_text('# ImmortalWrt build root\n')
        for check in self.manifest['source_checks']:
            target = self.root / check['path']
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text('\n'.join(check['required_lines']) + '\n# ImmortalWrt customization\n')
        for name in ('.config', 'feeds.conf.default', 'feeds/keep', 'dl/keep',
                     'staging_dir/keep', 'build_dir/keep', 'target/linux/mediatek/image/custom.mk'):
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b'ImmortalWrt user build data')

    def test_auto_detection_and_upgrade_preserve_immortalwrt_customizations(self):
        self.fixture()
        preserved = {str(p.relative_to(self.root)): p.read_bytes() for p in self.root.rglob('*')
                     if p.is_file() and str(p.relative_to(self.root)) not in
                     {e['path'] for e in self.manifest['files']}}
        manifest, changes = updater.select_plan(self.root, BUNDLE)
        self.assertEqual(manifest['source'], 'ImmortalWrt')
        self.assertEqual(len(changes), 14)
        updater.apply(self.root, changes, manifest['kernel'])
        for name, data in preserved.items():
            self.assertEqual((self.root / name).read_bytes(), data, name)
        self.assertEqual(updater.select_plan(self.root, BUNDLE)[1], [])

    def test_current_master_patch_and_launcher_update(self):
        self.fixture(master=True)
        result = subprocess.run(['sh', str(BUNDLE / 'update.sh')], cwd=self.root,
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('Detected source: ImmortalWrt', result.stdout)
        self.assertIn('15 source file updates', result.stdout)
        self.assertEqual(updater.select_plan(self.root, BUNDLE)[1], [])

    def test_plain_patch_applies_to_original_60(self):
        self.fixture()
        subprocess.run(['git', 'apply', str(self.bundle / self.manifest['patch'])],
                       cwd=self.root, check=True, capture_output=True)
        self.assertEqual(updater.select_plan(self.root, BUNDLE)[1], [])

    def test_local_patch_conflict_prevents_all_writes(self):
        self.fixture()
        path = self.root / 'package/kernel/mac80211/patches/build/160-backports-sockaddr_unsized-is-in-6.18.57.patch'
        path.write_bytes(path.read_bytes() + b'\n# local customization\n')
        before = (self.root / 'target/linux/generic/kernel-6.18').read_bytes()
        with self.assertRaisesRegex(ValueError, 'locally modified'):
            updater.select_plan(self.root, BUNDLE)
        self.assertEqual((self.root / 'target/linux/generic/kernel-6.18').read_bytes(), before)
        self.assertFalse((self.root / '.kernel-update-backups').exists())

    def test_unsupported_driver_is_rejected_without_writes(self):
        self.fixture()
        driver = self.root / 'package/kernel/mt76/Makefile'
        driver.write_text('PKG_SOURCE_VERSION:=custom-driver\n')
        with self.assertRaisesRegex(ValueError, 'unsupported wireless source'):
            updater.select_plan(self.root, BUNDLE)
        self.assertFalse((self.root / '.kernel-update-backups').exists())

    def test_extra_patch_checksum_is_validated(self):
        self.fixture()
        local = self.root / 'copied-profile'
        shutil.copytree(self.bundle, local)
        (local / self.manifest['extra_patches'][0]['path']).write_bytes(b'tampered')
        with self.assertRaisesRegex(ValueError, 'patch failed its checksum'):
            updater.load_bundle(local)


class RebuildTests(unittest.TestCase):
    def test_rebuild_runs_in_order_with_requested_jobs(self):
        root = Path('/build')
        with mock.patch.object(updater.subprocess, 'run') as run:
            updater.rebuild(root, 1)
        self.assertEqual([call.args[0] for call in run.call_args_list], [
            ['make', 'defconfig'], ['make', 'target/linux/clean'],
            ['make', 'package/kernel/mac80211/clean'], ['make', 'package/kernel/mt76/clean'],
            ['make', 'target/linux/prepare', '-j1', 'V=s'], ['make', '-j1', 'V=s']])
        self.assertTrue(all(call.kwargs == {'cwd': root, 'check': True} for call in run.call_args_list))

    def test_rebuild_stops_at_first_failure(self):
        failure = subprocess.CalledProcessError(2, ['make', 'target/linux/prepare', '-j1', 'V=s'])
        with mock.patch.object(updater.subprocess, 'run', side_effect=[None] * 4 + [failure]) as run:
            with self.assertRaises(subprocess.CalledProcessError):
                updater.rebuild(Path('/build'), 2)
        self.assertEqual(run.call_count, 5)
