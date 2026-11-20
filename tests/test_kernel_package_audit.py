import importlib.util
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('kernel_package_audit', ROOT / 'scripts/kernel-package-audit.py')
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


class PackageMetadataTests(unittest.TestCase):
    def test_dependency_expressions_consume_both_sides(self):
        values = {'CONFIG_Y': 'y', 'CONFIG_M': 'm', 'CONFIG_N': 'n'}
        for expression, expected in (
            ('Y||N', True), ('N&&Y||M', True), ('!(Y||M)', False),
            ('Y&&(N||M)', True), ('!N&&!M', False), ('ABSENT||N', False),
        ):
            with self.subTest(expression=expression):
                self.assertEqual(audit.enabled_expression(expression, values), expected)

    def test_actual_package_autoloads_resolve_for_all_supported_kernels(self):
        for version in ('6.12', '6.18', '7.3'):
            with self.subTest(version=version):
                rows, _ = audit.resolve(ROOT, Path('/kernel'), 'arm64', 'mediatek', 'filogic', version, None)
                self.assertGreater(len(rows), 1000)
                for name, row in rows.items():
                    for item in row['files'] + row['autoload']:
                        self.assertNotIn('@', item, (version, name, item))
                    for item in row['autoload']:
                        self.assertNotIn(':', item, (version, name, item))


class FeedPatchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'scripts').mkdir()
        shutil.copyfile(ROOT / 'scripts/apply-feed-patches.py', self.root / 'scripts/apply-feed-patches.py')
        self.patches = self.root / 'config/feeds-patches/example'
        self.patches.mkdir(parents=True)
        self.feed = self.root / 'feeds/example'
        self.feed.mkdir(parents=True)
        (self.feed / 'Makefile').write_text('old\n')

    def run_patches(self):
        return subprocess.run(['python3', str(self.root / 'scripts/apply-feed-patches.py'), 'example'],
                              text=True, capture_output=True)

    def test_feed_patch_is_idempotent(self):
        (self.patches / '001.patch').write_text('--- a/Makefile\n+++ b/Makefile\n@@ -1 +1 @@\n-old\n+new\n')
        self.assertEqual(self.run_patches().returncode, 0)
        second = self.run_patches()
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertIn('Already applied', second.stdout)
        self.assertEqual((self.feed / 'Makefile').read_text(), 'new\n')

    def test_mismatched_patch_does_not_partly_edit_feed(self):
        (self.patches / '001.patch').write_text('--- a/Makefile\n+++ b/Makefile\n@@ -1 +1 @@\n-wrong\n+new\n')
        result = self.run_patches()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual((self.feed / 'Makefile').read_text(), 'old\n')

    def version_patch(self, version):
        return ('--- a/Makefile\n+++ b/Makefile\n'
                '@@ -1,2 +1,2 @@\n-old\n+' + version + '\n # setting\n')

    def test_feed_patch_upgrade_preserves_local_edits(self):
        patch = self.patches / '001.patch'
        (self.feed / 'Makefile').write_text('old\n# setting\n')
        patch.write_text(self.version_patch('first'))
        self.assertEqual(self.run_patches().returncode, 0)
        # The edit is outside the replaced hunk, in the same file.
        (self.feed / 'Makefile').write_text('first\n# setting\n# local setting\n')
        patch.write_text(self.version_patch('second'))
        result = self.run_patches()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('Updated', result.stdout)
        self.assertEqual((self.feed / 'Makefile').read_text(), 'second\n# setting\n# local setting\n')
        self.assertEqual(self.run_patches().returncode, 0)

    def test_conflicting_feed_patch_upgrade_leaves_files_untouched(self):
        patch = self.patches / '001.patch'
        (self.feed / 'Makefile').write_text('old\n# setting\n')
        patch.write_text(self.version_patch('first'))
        self.assertEqual(self.run_patches().returncode, 0)
        (self.feed / 'Makefile').write_text('user version\n')
        patch.write_text(self.version_patch('second'))
        self.assertNotEqual(self.run_patches().returncode, 0)
        self.assertEqual((self.feed / 'Makefile').read_text(), 'user version\n')

    def test_upgrade_from_source_history_without_receipt(self):
        patch = self.patches / '001.patch'
        (self.feed / 'Makefile').write_text('old\n# setting\n')
        patch.write_text(self.version_patch('first'))
        subprocess.run(['git', 'init', '-q', str(self.root)], check=True)
        subprocess.run(['git', '-C', str(self.root), 'add', 'config'], check=True)
        subprocess.run(['git', '-C', str(self.root), '-c', 'user.name=Feed test',
                        '-c', 'user.email=feed@example.invalid', 'commit', '-qm', 'old patch'],
                       check=True)
        (self.feed / 'Makefile').write_text('first\n# setting\n')
        patch.write_text(self.version_patch('second'))
        result = self.run_patches()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.feed / 'Makefile').read_text(), 'second\n# setting\n')


if __name__ == '__main__':
    unittest.main()
