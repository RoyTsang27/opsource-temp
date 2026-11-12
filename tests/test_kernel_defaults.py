"""Resolve the real build Kconfig to catch unsupported preemption choices."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class KernelDefaultsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not shutil.which('make') or not shutil.which('cc'):
            raise unittest.SkipTest('make and a C compiler are required for Kconfig')
        cls.temporary = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.directory = Path(cls.temporary.name)
        sources = cls.directory / 'config-tool'
        shutil.copytree(ROOT / 'scripts/config', sources,
                        ignore=shutil.ignore_patterns('*.o', 'conf', 'mconf', 'nconf', 'qconf'))
        subprocess.run(['make', '-C', str(sources), 'conf'], check=True,
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        cls.conf = sources / 'conf'

    def resolve(self, architecture, series, preset=''):
        directory = Path(tempfile.mkdtemp(dir=self.directory))
        kconfig = 'mainmenu "Kernel defaults test"\n'
        for symbol in ['aarch64', 'mips', 'LINUX_7_3', 'LINUX_6_18']:
            enabled = symbol in (architecture, 'LINUX_' + series)
            kconfig += 'config ' + symbol + '\n\tbool\n\tdefault ' + ('y' if enabled else 'n') + '\n'
        kconfig += 'source "' + str(ROOT / 'config/Config-kernel.in') + '"\n'
        (directory / 'Kconfig').write_text(kconfig)
        (directory / 'preset').write_text(preset)
        environment = dict(os.environ, KCONFIG_CONFIG=str(directory / '.config'))
        subprocess.run([str(self.conf), '--defconfig=' + str(directory / 'preset'),
                        str(directory / 'Kconfig')], cwd=directory, env=environment,
                       check=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        return set((directory / '.config').read_text().splitlines())

    def test_linux_7_arm64_uses_supported_lazy_preemption(self):
        resolved = self.resolve('aarch64', '7_3')
        self.assertIn('CONFIG_KERNEL_PREEMPT_LAZY=y', resolved)
        self.assertNotIn('CONFIG_KERNEL_PREEMPT_NONE=y', resolved)
        self.assertNotIn('CONFIG_KERNEL_PREEMPT_VOLUNTARY=y', resolved)

    def test_linux_7_mips_uses_supported_voluntary_preemption(self):
        resolved = self.resolve('mips', '7_3')
        self.assertIn('CONFIG_KERNEL_PREEMPT_VOLUNTARY=y', resolved)
        self.assertNotIn('CONFIG_KERNEL_PREEMPT_NONE=y', resolved)
        self.assertNotIn('CONFIG_KERNEL_PREEMPT_LAZY=y', resolved)

    def test_linux_6_defaults_stay_available(self):
        for architecture in ['aarch64', 'mips']:
            with self.subTest(architecture=architecture):
                self.assertIn('CONFIG_KERNEL_PREEMPT_NONE=y', self.resolve(architecture, '6_18'))

    def test_old_linux_7_preset_migrates_to_a_supported_choice(self):
        for architecture, expected in [('aarch64', 'LAZY'), ('mips', 'VOLUNTARY')]:
            with self.subTest(architecture=architecture):
                resolved = self.resolve(architecture, '7_3', 'CONFIG_KERNEL_PREEMPT_NONE=y\n')
                self.assertIn('CONFIG_KERNEL_PREEMPT_' + expected + '=y', resolved)
                self.assertNotIn('CONFIG_KERNEL_PREEMPT_NONE=y', resolved)

    def test_explicit_full_preemption_is_respected(self):
        self.assertIn('CONFIG_KERNEL_PREEMPT=y',
                      self.resolve('aarch64', '7_3', 'CONFIG_KERNEL_PREEMPT=y\n'))
