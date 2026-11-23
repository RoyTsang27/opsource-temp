"""Resolve WED defaults with Kconfig and generate the real module loader file."""
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
AX3000T = (
    'TARGET_mediatek_filogic_DEVICE_xiaomi_mi-router-ax3000t',
    'TARGET_mediatek_filogic_DEVICE_xiaomi_mi-router-ax3000t-ubootmod',
    'TARGET_DEVICE_mediatek_filogic_DEVICE_xiaomi_mi-router-ax3000t',
    'TARGET_DEVICE_mediatek_filogic_DEVICE_xiaomi_mi-router-ax3000t-ubootmod',
)


def definition(text, name):
    return re.search(r'^define ' + re.escape(name) + r'\n(.*?)^endef$',
                     text, re.M | re.S).group(0) + '\n'


class Mt7915WedDefaultsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.root = Path(cls.temporary.name)
        tool = cls.root / 'config-tool'
        shutil.copytree(ROOT / 'scripts/config', tool,
                        ignore=shutil.ignore_patterns('*.o', 'conf', 'mconf', 'nconf', 'qconf'))
        subprocess.run(['make', '-s', '-C', str(tool), 'conf'], check=True,
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        cls.conf = tool / 'conf'
        cls.recipe = (ROOT / 'package/kernel/mt76/Makefile').read_text()
        cls.autoload = definition((ROOT / 'include/kernel.mk').read_text(), 'ModuleAutoLoad')

    def resolve(self, target='filogic', profile=None, override=None):
        directory = Path(tempfile.mkdtemp(dir=self.root))
        symbols = AX3000T + ('TARGET_mediatek_filogic', 'TARGET_mediatek_mt7622',
                            'PACKAGE_kmod-mt7915e')
        config = '\n'.join('config ' + symbol + '\n\tbool "' + symbol + '"\n'
                           for symbol in symbols)
        option = definition(self.recipe, 'KernelPackage/mt7915e/config')
        config += option.split('\n', 1)[1].rsplit('endef', 1)[0]
        (directory / 'Kconfig').write_text(config)
        preset = 'CONFIG_PACKAGE_kmod-mt7915e=y\nCONFIG_TARGET_mediatek_' + target + '=y\n'
        if profile:
            preset += 'CONFIG_' + profile + '=y\n'
        if override is not None:
            preset += 'CONFIG_PACKAGE_MT7915_WED=' + ('y' if override else 'n') + '\n'
        (directory / 'preset').write_text(preset)
        resolved = directory / '.config'
        result = subprocess.run([str(self.conf), '--fatalrecursive', '--defconfig=preset', 'Kconfig'],
                                cwd=directory, env=dict(os.environ, KCONFIG_CONFIG=str(resolved)),
                                text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        settings = set(resolved.read_text().splitlines())
        self.assertIn('CONFIG_PACKAGE_kmod-mt7915e=y', settings)
        makefile = directory / 'Makefile'
        makefile.write_text('include ' + str(resolved) + '\n' + self.autoload +
                            definition(self.recipe, 'KernelPackage/mt7915e') +
                            '$(eval $(KernelPackage/mt7915e))\n'
                            'all:\n\t$(call ModuleAutoLoad,mt7915e,' + str(directory / 'image') +
                            ',,,mt7915e)\n')
        subprocess.run(['make', '-s', '-f', str(makefile)], cwd=directory, check=True,
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        return settings, (directory / 'image/etc/modules.d/mt7915e').read_text().strip()

    def test_ax3000t_defaults_disable_wed_for_both_layouts_and_multi_device_builds(self):
        for profile in AX3000T:
            with self.subTest(profile=profile):
                settings, loader = self.resolve(profile=profile)
                self.assertNotIn('CONFIG_PACKAGE_MT7915_WED=y', settings)
                self.assertEqual(loader, 'mt7915e wed_enable=N')

    def test_other_filogic_and_mt7622_defaults_keep_wed_enabled(self):
        for target in ('filogic', 'mt7622'):
            with self.subTest(target=target):
                settings, loader = self.resolve(target=target)
                self.assertIn('CONFIG_PACKAGE_MT7915_WED=y', settings)
                self.assertEqual(loader, 'mt7915e wed_enable=Y')

    def test_explicit_opt_in_for_ax3000t_is_respected(self):
        settings, loader = self.resolve(profile=AX3000T[1], override=True)
        self.assertIn('CONFIG_PACKAGE_MT7915_WED=y', settings)
        self.assertEqual(loader, 'mt7915e wed_enable=Y')

    def test_explicit_disable_for_other_devices_is_respected(self):
        settings, loader = self.resolve(override=False)
        self.assertNotIn('CONFIG_PACKAGE_MT7915_WED=y', settings)
        self.assertEqual(loader, 'mt7915e wed_enable=N')


if __name__ == '__main__':
    unittest.main()
