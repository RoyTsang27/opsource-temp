import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('llvm_setup', ROOT / 'scripts/setup-llvm-bpf.py')
llvm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(llvm)
NINJA = os.environ.get('NINJA_TEST_BIN') or shutil.which('ninja')


class PrebuiltTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_manifest_accepts_standard_checksum_formats(self):
        for filename in ('tool.tar.zst', './tool.tar.zst', '*tool.tar.zst', '*./tool.tar.zst'):
            with self.subTest(filename=filename):
                listing = ('a' * 64 + '  ' + filename + '\n').encode()
                with mock.patch.object(llvm, 'request', return_value=io.BytesIO(listing)):
                    self.assertEqual(llvm.archive_checksum('tool.tar.zst'), 'a' * 64)

    def test_missing_or_invalid_checksum_is_rejected(self):
        for listing in (b'', b'bad  tool.tar.zst\n'):
            with mock.patch.object(llvm, 'request', return_value=io.BytesIO(listing)):
                with self.assertRaises(ValueError):
                    llvm.archive_checksum('tool.tar.zst')

    def test_download_rejects_tampering(self):
        with mock.patch.object(llvm, 'request', return_value=io.BytesIO(b'tampered')):
            with self.assertRaisesRegex(ValueError, 'SHA256 mismatch'):
                llvm.download('tool', hashlib.sha256(b'original').hexdigest(), self.root / 'archive')

    def test_download_enforces_size_limit(self):
        with mock.patch.object(llvm, 'request', return_value=io.BytesIO(b'large')):
            with mock.patch.object(llvm, 'MAX_ARCHIVE', 1):
                with self.assertRaisesRegex(ValueError, 'size limit'):
                    llvm.download('tool', 'a' * 64, self.root / 'archive')

    def extract_members(self, members):
        data = io.BytesIO()
        with tarfile.open(fileobj=data, mode='w') as archive:
            for name, kind, target in members:
                member = tarfile.TarInfo(name)
                member.type, member.linkname = kind, target
                content = b'22.1.3\n' if kind == tarfile.REGTYPE else b''
                member.size = len(content)
                archive.addfile(member, io.BytesIO(content))
        process = mock.MagicMock()
        process.__enter__.return_value = process
        process.stdout = io.BytesIO(data.getvalue())
        process.wait.return_value = 0
        with mock.patch.object(llvm.subprocess, 'Popen', return_value=process):
            llvm.extract(self.root / 'archive', self.root, 'llvm-bpf-version', 'zstd')

    def test_archive_layout_and_internal_toolchain_link(self):
        self.extract_members([
            ('llvm-bpf-version/.llvm-version', tarfile.REGTYPE, ''),
            ('llvm-bpf', tarfile.SYMTYPE, 'llvm-bpf-version'),
        ])
        self.assertEqual((self.root / 'llvm-bpf/.llvm-version').read_text(), '22.1.3\n')

    def test_archive_traversal_links_and_unexpected_members_are_rejected(self):
        for entry in (
            ('unrelated/file', tarfile.REGTYPE, ''),
            ('llvm-bpf-version/../../outside', tarfile.REGTYPE, ''),
            ('llvm-bpf', tarfile.SYMTYPE, '../../outside'),
            ('llvm-bpf-version/link', tarfile.LNKTYPE, '/outside'),
        ):
            with self.subTest(entry=entry), self.assertRaises((ValueError, tarfile.TarError)):
                self.extract_members([entry])

    def test_config_preserves_device_and_package_selection(self):
        original = ('CONFIG_TARGET_mediatek_filogic_DEVICE_xiaomi_mi-router-ax3000t=y\n'
                    'CONFIG_PACKAGE_luci=y\nCONFIG_USE_LLVM_BUILD=y\n'
                    'CONFIG_BPF_TOOLCHAIN_BUILD_LLVM=y\n')
        selected = llvm.prebuilt_config(original)
        self.assertIn(original.splitlines()[0], selected)
        self.assertIn('CONFIG_PACKAGE_luci=y\n', selected)
        self.assertNotIn('CONFIG_USE_LLVM_BUILD=y\n', selected)
        self.assertIn('CONFIG_BPF_TOOLCHAIN_PREBUILT=y\n', selected)
        self.assertIn('CONFIG_USE_LLVM_PREBUILT=y\n', selected)
        self.assertEqual(llvm.prebuilt_config(selected), selected)

    def test_buildbot_and_all_host_tools_are_not_silently_changed(self):
        for option in ('BUILDBOT', 'BUILD_ALL_HOST_TOOLS'):
            with self.assertRaisesRegex(ValueError, option):
                llvm.prebuilt_config('CONFIG_' + option + '=y\n')

    def test_failed_defconfig_restores_original_configuration(self):
        original = 'CONFIG_USE_LLVM_BUILD=y\n'
        (self.root / '.config').write_text(original)
        with mock.patch.object(llvm.subprocess, 'run', side_effect=subprocess.CalledProcessError(1, 'make')):
            with self.assertRaises(subprocess.CalledProcessError):
                llvm.configure(self.root)
        self.assertEqual((self.root / '.config').read_text(), original)
        self.assertEqual((self.root / '.config.llvm-bpf.backup').read_text(), original)

    def test_unresolved_prebuilt_selection_restores_configuration(self):
        original = 'CONFIG_USE_LLVM_BUILD=y\n'
        (self.root / '.config').write_text(original)

        def wrong_resolution(*args, **kwargs):
            (self.root / '.config').write_text(original)

        with mock.patch.object(llvm.subprocess, 'run', side_effect=wrong_resolution):
            with self.assertRaisesRegex(ValueError, 'Kconfig'):
                llvm.configure(self.root)
        self.assertEqual((self.root / '.config').read_text(), original)

    def test_failed_setup_restores_previous_toolchain_link(self):
        prefix = 'llvm-bpf-22.1.3.Linux-x86_64'
        (self.root / '.config').write_text('CONFIG_TARGET_mediatek=y\n')
        (self.root / 'tools/llvm-bpf').mkdir(parents=True)
        (self.root / 'tools/llvm-bpf/Makefile').write_text('PKG_VERSION:=22.1.3\n')
        (self.root / prefix).mkdir()
        (self.root / prefix / '.op-source-archive-sha256').write_text('a' * 64)
        (self.root / 'llvm-bpf').symlink_to('old-toolchain')
        with mock.patch.object(llvm.platform, 'system', return_value='Linux'), \
             mock.patch.object(llvm.platform, 'machine', return_value='x86_64'), \
             mock.patch.object(llvm, 'archive_checksum', return_value='a' * 64), \
             mock.patch.object(llvm.shutil, 'which', return_value='/zstd'), \
             mock.patch.object(llvm, 'smoke_test'), \
             mock.patch.object(llvm, 'configure', side_effect=ValueError('Kconfig failure')):
            with self.assertRaisesRegex(ValueError, 'Kconfig failure'):
                llvm.setup(self.root)
        self.assertEqual((self.root / 'llvm-bpf').readlink(), Path('old-toolchain'))

    def test_unsupported_host_is_rejected_before_downloading(self):
        with mock.patch.object(llvm.platform, 'system', return_value='Darwin'):
            with mock.patch.object(llvm, 'request') as request:
                with self.assertRaisesRegex(ValueError, 'Linux x86-64'):
                    llvm.setup(self.root)
                request.assert_not_called()


@unittest.skipUnless(NINJA, 'Ninja is unavailable; set NINJA_TEST_BIN for the concurrency preflight')
class NinjaLimitTests(unittest.TestCase):
    def check_limit(self, jobs, expected):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'include').mkdir()
            (root / 'bin').mkdir()
            (root / 'bin/ninja').symlink_to(NINJA)
            rule = (ROOT / 'rules.mk').read_text().split('NINJA = \\\n', 1)[1].split('\n\n', 1)[0]
            (root / 'rules.mk').write_text('NINJA = \\\n' + rule + '\n')
            (root / 'include/host-build.mk').write_text('')
            (root / 'include/cmake.mk').write_text('')
            harness = root / 'Makefile'
            harness.write_text(f'TOPDIR:={root}\nINCLUDE_DIR:={root}/include\n'
                               f'STAGING_DIR_HOST:={root}\n'
                               f'include {ROOT}/tools/llvm-bpf/Makefile\n'
                               'all:\n\t+$(NINJA) -C $(TOPDIR)\n')
            worker = root / 'worker.py'
            worker.write_text('import json, os, sys, time\n'
                              'from pathlib import Path\n'
                              'fd=os.open("events", os.O_WRONLY|os.O_CREAT|os.O_APPEND, 0o600)\n'
                              'os.write(fd, (json.dumps(1)+"\\n").encode())\n'
                              'time.sleep(0.25)\n'
                              'Path(sys.argv[1]).touch()\n'
                              'os.write(fd, (json.dumps(-1)+"\\n").encode())\n'
                              'os.close(fd)\n')
            (root / 'build.ninja').write_text(
                'rule work\n  command = ' + shlex.quote(sys.executable) + ' ' +
                shlex.quote(str(worker)) + ' $out\n' +
                ''.join(f'build out{i}: work\n' for i in range(4)))
            command = ['make', '-f', str(harness),
                       'MAKE_JOBSERVER=--jobserver-auth=fifo:/nonexistent-test-jobserver']
            if jobs:
                command.append('LLVM_BPF_JOBS=' + jobs)
            result = subprocess.run(command, cwd=root, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            current = peak = 0
            for line in (root / 'events').read_text().splitlines():
                current += json.loads(line)
                peak = max(current, peak)
            self.assertEqual(current, 0)
            self.assertEqual(peak, expected)

    def test_default_runs_one_job_even_with_unusable_parent_jobserver(self):
        self.check_limit(None, 1)

    def test_explicit_override_sets_the_limit(self):
        self.check_limit('2', 2)


if __name__ == '__main__':
    unittest.main()
