from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
PATCH_NAME = '962-mt7915-reject-backwards-MT7981-survey-snapshots.patch'
PATCH = ROOT / 'package/kernel/mt76/patches' / PATCH_NAME
FIXTURES = ROOT / 'tests/fixtures'


@unittest.skipUnless(shutil.which('clang') and shutil.which('patch'), 'clang and patch are required')
class ChannelMibTests(unittest.TestCase):
    def test_production_function_rejects_old_snapshots_without_rebasing(self):
        with tempfile.TemporaryDirectory() as temporary:
            work = Path(temporary)
            source = work / 'mt7915/mcu.c'
            source.parent.mkdir()
            shutil.copyfile(FIXTURES / 'mt7915-channel-mib-0936617-955.c', source)
            shutil.copyfile(FIXTURES / 'mt7915-channel-mib-harness.c', source.parent / 'probe.c')
            executable = work / 'probe'

            def compile_and_run(*args):
                result = subprocess.run([
                    'clang', '-std=gnu11', '-O1', '-g', '-Wall', '-Wextra', '-Werror',
                    '-fsanitize=address,undefined', '-fno-sanitize-recover=all',
                    '-fno-omit-frame-pointer', str(source.parent / 'probe.c'), '-o', str(executable),
                ], capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                result = subprocess.run([str(executable), *args], capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                return result.stdout

            self.assertIn('original production function wraps', compile_and_run('negative-control'))
            result = subprocess.run(['patch', '-p1', '--batch', '--fuzz=0', '-i', str(PATCH)],
                                    cwd=work, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn('alternating snapshots', compile_and_run())

    def test_migration_kit_contains_the_same_fix(self):
        bundle = ROOT / 'updates/kernel-6.18.63'
        self.assertEqual((bundle / 'files/package/kernel/mt76/patches' / PATCH_NAME).read_bytes(),
                         PATCH.read_bytes())
        self.assertIn(PATCH_NAME, (bundle / 'patches/op-source-6.18.60-to-6.18.63.patch').read_text())
