import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('llvm_speed_update', ROOT / 'updates/llvm-bpf-speed/update.py')
update = importlib.util.module_from_spec(spec)
spec.loader.exec_module(update)


class SpeedUpdateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.root = self.base / 'source'
        self.bundle = self.base / 'bundle'
        (self.root / 'tools/llvm-bpf').mkdir(parents=True)
        (self.root / 'rules.mk').write_text('# build root\n')
        (self.root / 'tools/llvm-bpf/Makefile').write_bytes(b'old recipe\n')
        (self.root / '.config').write_text('CONFIG_TARGET_mediatek=y\n')
        (self.root / 'build_dir').mkdir()
        (self.root / 'build_dir/completed.o').write_bytes(b'keep compiled objects')
        entries = []
        for relative, original, updated in (
            ('tools/llvm-bpf/Makefile', b'old recipe\n', b'automatic recipe\n'),
            ('scripts/llvm-bpf-jobs.py', None, b'worker detector\n'),
        ):
            path = self.bundle / 'files' / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(updated)
            entries.append(dict(path=relative, before=[update.digest(original)], after=update.digest(updated)))
        (self.bundle / 'manifest.json').write_text(json.dumps(dict(files=entries)))

    def snapshot(self):
        return {str(path.relative_to(self.root)): path.read_bytes()
                for path in self.root.rglob('*') if path.is_file()}

    def test_preflight_does_not_write_and_apply_preserves_config_and_objects(self):
        before = self.snapshot()
        changes = update.plan(self.root, self.bundle)
        self.assertEqual(self.snapshot(), before)
        backup = update.apply(self.root, changes)
        self.assertEqual((backup / 'tools/llvm-bpf/Makefile').read_bytes(), b'old recipe\n')
        self.assertEqual((self.root / '.config').read_bytes(), before['.config'])
        self.assertEqual((self.root / 'build_dir/completed.o').read_bytes(), before['build_dir/completed.o'])
        self.assertEqual((self.root / 'scripts/llvm-bpf-jobs.py').read_bytes(), b'worker detector\n')
        self.assertEqual(update.plan(self.root, self.bundle), [])

    def test_local_edit_is_rejected_before_writing_anything(self):
        (self.root / 'scripts').mkdir()
        (self.root / 'scripts/llvm-bpf-jobs.py').write_text('local edit')
        before = self.snapshot()
        with self.assertRaisesRegex(ValueError, 'Locally modified'):
            update.plan(self.root, self.bundle)
        self.assertEqual(self.snapshot(), before)

    def test_tampered_payload_is_rejected(self):
        (self.bundle / 'files/tools/llvm-bpf/Makefile').write_text('tampered')
        before = self.snapshot()
        with self.assertRaisesRegex(ValueError, 'checksum mismatch'):
            update.plan(self.root, self.bundle)
        self.assertEqual(self.snapshot(), before)

    def test_symlink_destination_is_rejected(self):
        outside = self.base / 'outside'
        outside.mkdir()
        (self.root / 'scripts').symlink_to(outside)
        with self.assertRaisesRegex(ValueError, 'symbolic link'):
            update.plan(self.root, self.bundle)
        self.assertEqual(list(outside.iterdir()), [])

    def test_mid_update_failure_restores_original_files(self):
        before = self.snapshot()
        changes = update.plan(self.root, self.bundle)
        write = update.atomic_write
        failed = False

        def fail_new_script(path, data, mode):
            nonlocal failed
            if path == self.root / 'scripts/llvm-bpf-jobs.py' and not failed:
                failed = True
                raise OSError('simulated interrupted write')
            return write(path, data, mode)

        with mock.patch.object(update, 'atomic_write', side_effect=fail_new_script):
            with self.assertRaisesRegex(OSError, 'interrupted write'):
                update.apply(self.root, changes)
        after = {key: value for key, value in self.snapshot().items() if not key.startswith('.llvm-bpf-backups/')}
        self.assertEqual(after, before)

    def test_change_after_preflight_is_not_overwritten(self):
        changes = update.plan(self.root, self.bundle)
        recipe = self.root / 'tools/llvm-bpf/Makefile'
        recipe.write_text('concurrent edit')
        with self.assertRaisesRegex(ValueError, 'changed after preflight'):
            update.apply(self.root, changes)
        self.assertEqual(recipe.read_text(), 'concurrent edit')

    def test_wrong_directory_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'build root'):
            update.plan(self.base, self.bundle)


if __name__ == '__main__':
    unittest.main()
