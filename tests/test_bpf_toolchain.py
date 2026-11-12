from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which('make'), 'make is needed to test the real BPF include')
class BpfToolchainTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.compiler = self.root / 'llvm-bpf/bin/clang'
        self.compiler.parent.mkdir(parents=True)
        (self.root / 'Makefile').write_text(
            'TOPDIR := ' + str(self.root) + '\n'
            'CONFIG_HAS_BPF_TOOLCHAIN := y\n'
            'CONFIG_USE_LLVM_PREBUILT := y\n'
            'include ' + str(ROOT / 'include/bpf.mk') + '\n'
            'all download refresh:\n\t@echo "BPF compiler version: $(CLANG_VER)"\n')

    def compiler_script(self, body):
        self.compiler.write_text('#!/bin/sh\n' + body + '\n')
        self.compiler.chmod(0o755)

    def make(self, *arguments):
        return subprocess.run(['make', '--no-print-directory', *arguments], cwd=self.root,
                              capture_output=True, text=True)

    def test_missing_prebuilt_compiler_reports_the_install_command(self):
        result = self.make()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('BPF compiler is missing or not executable', result.stderr)
        self.assertIn(str(self.compiler), result.stderr)
        self.assertIn('python3 scripts/setup-llvm-bpf.py', result.stderr)
        self.assertNotIn('version too old', result.stderr)
        self.assertNotIn('integer', result.stderr)

    def test_nonexecutable_compiler_is_reported_as_unavailable(self):
        self.compiler.write_text('unusable compiler')
        result = self.make()
        self.assertIn('BPF compiler is missing or not executable', result.stderr)

    def test_compiler_that_cannot_run_is_not_reported_as_too_old(self):
        self.compiler_script('echo "missing shared library" >&2\nexit 127')
        result = self.make()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Cannot query the BPF compiler version', result.stderr)
        self.assertNotIn('version too old', result.stderr)
        self.assertNotIn('integer', result.stderr)

    def test_invalid_version_macro_cannot_reach_the_numeric_comparison(self):
        self.compiler_script("printf '%s\\n' '#define __clang_major__ invalid'")
        result = self.make()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Cannot query the BPF compiler version', result.stderr)
        self.assertNotIn('integer', result.stderr)

    def test_old_compiler_still_reports_the_minimum_version(self):
        self.compiler_script("printf '%s\\n' '#define __clang_major__ 11'")
        result = self.make()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Minimum required: 12, found: 11', result.stderr)

    def test_supported_versions_pass(self):
        for version in (12, 22):
            with self.subTest(version=version):
                self.compiler_script("printf '%s\\n' '#define __clang_major__ " + str(version) + "'")
                result = self.make()
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn('BPF compiler version: ' + str(version), result.stdout)

    def test_metadata_download_and_refresh_do_not_require_installed_tools(self):
        for arguments in (('DUMP=1',), ('download',), ('refresh',)):
            with self.subTest(arguments=arguments):
                result = self.make(*arguments)
                self.assertEqual(result.returncode, 0, result.stderr)
