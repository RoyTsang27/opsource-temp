"""Check PON profile inheritance and resolved package selection policy."""
import importlib.util
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('defaults', ROOT / 'scripts/check-device-defaults.py')
defaults = importlib.util.module_from_spec(spec)
spec.loader.exec_module(defaults)


def definition(text, name):
    return re.search(r'^define ' + re.escape(name) + r'\n.*?^endef$',
                     text, re.M | re.S).group() + '\n'


class PonProfileTests(unittest.TestCase):
    def expanded_profiles(self, subtarget):
        image = ROOT / 'target/linux/airoha/image'
        source = (image / (subtarget + '.mk')).read_text()
        bases = re.findall(r'call Device/AirohaPonProfile,([^,]+),[^)]+', source)
        shared = (image / 'Makefile').read_text()
        shared = '\n'.join(line for line in shared.splitlines()
                           if not line.startswith('include ') and 'call BuildImage' not in line)
        generic = (ROOT / 'include/image.mk').read_text()
        keys = ('DEVICE_MODEL', 'DEVICE_DTS', 'DEVICE_DTS_CONFIG', 'DEVICE_PACKAGES',
                'SUPPORTED_DEVICES', 'BOARD_NAME', 'DEVICE_IMG_PREFIX', 'KERNEL',
                'KERNEL_INITRAMFS', 'KERNEL_LOADADDR', 'KERNEL_SIZE', 'IMAGE_SIZE',
                'BLOCKSIZE', 'PAGESIZE', 'UBINIZE_OPTS', 'UBINIZE_PARTS_AFTER',
                'IMAGES', 'IMAGE/factory.bin', 'IMAGE/sysupgrade.bin', 'IMAGE/sysupgrade.itb')
        harness = ('comma := ,\nIMG_PREFIX := opsource-temp-airoha-' + subtarget + '\n'
                   'KDIR := /tmp/profile-check\nCONFIG_TARGET_airoha_' + subtarget + ' := y\n'
                   + definition(generic, 'Device/InitProfile')
                   + definition(generic, 'Device/Init') + shared + '\n'
                   'include ' + str(image / 'pon.mk') + '\n'
                   'include ' + str(image / (subtarget + '.mk')) + '\n')
        for base in bases:
            for profile in (base, base + '-pon'):
                harness += ('$(eval $(call Device/InitProfile))\n'
                            '$(eval $(call Device/Init,' + profile + '))\n'
                            '$(eval $(call Device/Default,' + profile + '))\n'
                            '$(eval $(call Device/' + profile + ',' + profile + '))\n')
                for key in keys:
                    harness += '$(info FIELD|' + profile + '|' + key + '|$(' + key + '))\n'
        harness += '.PHONY: all\nall: ; @:\n'
        with tempfile.TemporaryDirectory() as temporary:
            makefile = Path(temporary) / 'Makefile'
            makefile.write_text(harness)
            result = subprocess.run(['make', '-s', '-f', str(makefile)],
                                    text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        expanded = {}
        for line in result.stdout.splitlines():
            if line.startswith('FIELD|'):
                _, profile, key, value = line.split('|', 3)
                expanded.setdefault(profile, {})[key] = value
        return bases, expanded

    def test_pon_profiles_keep_board_layout_and_add_optical_defaults(self):
        count = 0
        pon_packages = {'kmod-airoha-xpon', 'kmod-airoha-pon-frontend', 'airoha-ponctl',
                        'airoha-pond', 'airoha-pon-debug', 'luci-app-pon', 'luci-app-iptv'}
        for subtarget in ('an7581', 'an7583'):
            bases, expanded = self.expanded_profiles(subtarget)
            count += len(bases)
            for base in bases:
                with self.subTest(profile=base):
                    original, pon = expanded[base], expanded[base + '-pon']
                    self.assertEqual(pon['DEVICE_MODEL'], original['DEVICE_MODEL'] + '(Pon)')
                    self.assertEqual(pon['BOARD_NAME'], original['BOARD_NAME'] or base)
                    self.assertEqual(pon['DEVICE_IMG_PREFIX'], original['DEVICE_IMG_PREFIX'] + '-pon')
                    self.assertGreaterEqual(set(pon['DEVICE_PACKAGES'].split()),
                                            set(original['DEVICE_PACKAGES'].split()) | pon_packages)
                    for key in original.keys() - {'DEVICE_MODEL', 'BOARD_NAME',
                                                   'DEVICE_IMG_PREFIX', 'DEVICE_PACKAGES'}:
                        self.assertEqual(pon[key], original[key], key)
                    self.assertTrue((ROOT / 'target/linux/airoha/dts' /
                                     (pon['DEVICE_DTS'] + '.dts')).is_file())
        self.assertEqual(count, 16)


class DefaultSelectionTests(unittest.TestCase):
    def settings(self, **extra):
        return dict({'TARGET_airoha_an7581_DEVICE_example-pon': 'y'}, **extra)

    def test_missing_builtin_driver_is_rejected_even_if_module_exists(self):
        with self.assertRaisesRegex(ValueError, 'kmod-radio'):
            defaults.check_defaults(self.settings(**{'DEFAULT_kmod-radio': 'y',
                                                     'PACKAGE_kmod-radio': 'm'}), {})

    def test_per_device_module_and_virtual_provider_are_accepted(self):
        settings = self.settings(**{'DEFAULT_TARGET_airoha_an7581': 'y',
                                    'TARGET_PER_DEVICE_ROOTFS': 'y',
                                    'MODULE_DEFAULT_kmod-radio': 'm', 'PACKAGE_kmod-radio': 'm',
                                    'DEFAULT_nftables': 'y', 'PACKAGE_nftables-json': 'y'})
        checked = defaults.check_defaults(settings, {'nftables': {'nftables-json', 'nftables-nojson'}})
        self.assertEqual(checked['defaults']['nftables'], {'nftables-json': 'y'})
        self.assertEqual(len(checked['defaults']), 2)
        self.assertEqual(checked['profiles'], ['TARGET_airoha_an7581_DEVICE_example-pon'])

    def test_unresolved_preset_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'make defconfig'):
            defaults.check_defaults(self.settings(), {})


if __name__ == '__main__':
    unittest.main()
