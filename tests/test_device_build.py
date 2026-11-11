import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import tarfile
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('device_build', ROOT / 'scripts/device-build.py')
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


class SelectionTests(unittest.TestCase):
    def test_default_matrix_builds_three_devices_on_correct_targets(self):
        entries = builder.matrix('all')['include']
        self.assertEqual([(e['device'], e['target'], e['subtarget']) for e in entries],
                         [('ax3000t', 'mediatek', 'filogic'),
                          ('tr3000', 'mediatek', 'filogic'),
                          ('tr1200', 'ramips', 'mt76x8')])

    def test_optional_layouts_are_explicit_single_device_choices(self):
        for name in ['ax3000t-ubootmod', 'tr3000-256mb', 'tr3000-ubootmod',
                     'xg-040g-md-tcboot', 'xg-140g-tf-tcboot']:
            with self.subTest(name=name):
                self.assertEqual([e['device'] for e in builder.matrix(name)['include']], [name])

    def test_unknown_device_is_rejected(self):
        for name in ['tr3000-v2', '../ax3000t', 'all; echo unsafe']:
            with self.subTest(name=name), self.assertRaises(ValueError):
                builder.matrix(name)

    def test_device_sources_and_presets_exist(self):
        builder.check_source()

    def resolved_config(self):
        return '\n'.join([
            'CONFIG_TARGET_ramips=y', 'CONFIG_TARGET_ramips_mt76x8=y',
            'CONFIG_TARGET_ramips_mt76x8_DEVICE_cudy_tr1200-v1=y',
            'CONFIG_TARGET_ROOTFS_SQUASHFS=y', 'CONFIG_SIGN_FIRMWARE=y',
            'CONFIG_DOWNLOAD_CHECK_CERTIFICATE=y', 'CONFIG_USE_APK=y',
            'CONFIG_PACKAGE_kmod-mt7603=y', 'CONFIG_PACKAGE_kmod-mt7615e=y',
            'CONFIG_PACKAGE_kmod-mt7663-firmware-ap=y', 'CONFIG_PACKAGE_kmod-usb2=y',
            'CONFIG_PACKAGE_luci-ssl=y'])

    def test_resolved_config_requires_correct_device_and_wifi(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / '.config'
            good = self.resolved_config()
            path.write_text(good)
            builder.check_config('tr1200', path)
            cases = [good.replace('CONFIG_PACKAGE_kmod-mt7615e=y', ''),
                     good.replace('cudy_tr1200-v1', 'cudy_wr300-v1'),
                     good + '\nCONFIG_TARGET_ramips_mt76x8_DEVICE_cudy_wr300-v1=y',
                     good + '\nCONFIG_TARGET_ALL_PROFILES=y',
                     good.replace('CONFIG_SIGN_FIRMWARE=y', '')]
            for text in cases:
                with self.subTest(text=text):
                    path.write_text(text)
                    with self.assertRaises(ValueError): builder.check_config('tr1200', path)

    def test_tr1200_backup_partition_matches_its_address(self):
        source = (ROOT / 'target/linux/ramips/dts/mt7628an_cudy_tr1200-v1.dts').read_text()
        partition = source.split('partition@fe0000 {', 1)[1].split('};', 1)[0]
        self.assertIn('reg = <0xfe0000 0x10000>;', partition)


class ImageTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.output = Path(self.temporary.name)
        payload = b'firmware test payload'
        (self.output / 'tr1200-sysupgrade.bin').write_bytes(payload)
        self.info = {
            'target': 'ramips/mt76x8', 'linux_kernel': {'version': builder.manifest()['kernel']},
            'profiles': {'cudy_tr1200-v1': {'images': [{
                'type': 'sysupgrade', 'name': 'tr1200-sysupgrade.bin',
                'size': len(payload), 'sha256': hashlib.sha256(payload).hexdigest()}]}}}

    def write_info(self):
        (self.output / 'profiles.json').write_text(json.dumps(self.info))

    def test_complete_correct_image_is_accepted(self):
        self.write_info()
        builder.check_images('tr1200', self.output)

    def test_missing_sysupgrade_is_rejected(self):
        self.info['profiles']['cudy_tr1200-v1']['images'][0]['type'] = 'initramfs'
        self.write_info()
        with self.assertRaises(ValueError): builder.check_images('tr1200', self.output)

    def test_corrupted_image_is_rejected(self):
        self.write_info()
        (self.output / 'tr1200-sysupgrade.bin').write_bytes(b'x' * 21)
        with self.assertRaises(ValueError): builder.check_images('tr1200', self.output)

    def test_wrong_kernel_or_profile_is_rejected(self):
        self.info['linux_kernel']['version'] = '6.18.52'
        self.write_info()
        with self.assertRaises(ValueError): builder.check_images('tr1200', self.output)
        self.info['linux_kernel']['version'] = builder.manifest()['kernel']
        self.info['profiles']['other-device'] = self.info['profiles']['cudy_tr1200-v1']
        self.write_info()
        with self.assertRaises(ValueError): builder.check_images('tr1200', self.output)

    def test_tcboot_requires_factory_and_sysupgrade(self):
        entry = builder.device('xg-040g-md-tcboot')
        self.info['target'] = 'airoha/an7581'
        self.info['profiles'][entry['profile']] = self.info['profiles'].pop('cudy_tr1200-v1')
        images = self.info['profiles'][entry['profile']]['images']
        self.write_info()
        with self.assertRaisesRegex(ValueError, 'No factory image'):
            builder.check_images('xg-040g-md-tcboot', self.output)
        factory = self.output / 'factory.bin'
        factory.write_bytes(b'factory image')
        images.append({'type': 'factory', 'name': factory.name, 'size': factory.stat().st_size,
                       'sha256': hashlib.sha256(factory.read_bytes()).hexdigest()})
        self.write_info()
        builder.check_images('xg-040g-md-tcboot', self.output)


class TcbootUpgradeTests(unittest.TestCase):
    def test_only_matching_archive_and_existing_ubi_can_reach_flash(self):
        base = ROOT / 'package/base-files/files/lib/upgrade'
        platform = ROOT / 'target/linux/airoha/an7581/base-files/lib/upgrade/platform.sh'
        check = r'''
            . "$1/common.sh"
            eval "$(sed '/^\. \/lib\/functions\.sh$/d' "$1/nand.sh")"
            . "$2"
            test_board="$3"
            layout="$5"
            board_name() { echo "$test_board"; }
            nand_find_ubi() { [ "$layout" = attached ] && echo ubi0; }
            nand_find_volume() { echo "ubi0_$2"; }
            nand_do_upgrade() { [ "$CI_SKIP_KERNEL_MTD" = 1 ] && echo "ready to write"; }
            "$6" "$4"
        '''
        for name in ['xg-040g-md-tcboot', 'xg-140g-tf-tcboot']:
            entry = builder.device(name)
            with self.subTest(device=name), tempfile.TemporaryDirectory() as temporary:
                files = Path(temporary)
                directory = files / ('sysupgrade-' + entry['profile'])
                directory.mkdir()
                (directory / 'CONTROL').write_text('BOARD=' + entry['profile'] + '\n')
                (directory / 'kernel').write_bytes(bytes.fromhex('d00dfeed'))
                (directory / 'root').write_bytes(b'hsqs')
                archive = files / 'sysupgrade.bin'
                with tarfile.open(archive, 'w') as tar:
                    tar.add(directory, arcname=directory.name)
                broken = files / 'kernel-only.bin'
                with tarfile.open(broken, 'w') as tar:
                    tar.add(directory, arcname=directory.name, recursive=False)
                    for member in ['CONTROL', 'kernel']:
                        tar.add(directory / member, arcname=directory.name + '/' + member)

                def run(board, image, layout='attached', action='platform_do_upgrade'):
                    return subprocess.run(['bash', '-c', check, 'tcboot', str(base), str(platform),
                                           board, str(image), layout, action],
                                          capture_output=True, text=True)

                board = entry['compatible']
                result = run(board, archive, action='platform_check_image')
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn('ready to write', run(board, archive).stdout)
                other_board = ('nokia,xg-140g-tf-tcboot' if '040g' in board
                               else 'nokia,xg-040g-md-tcboot')
                for result in [run(board, archive, 'absent'), run(board, broken),
                               run(board, directory / 'kernel'), run(other_board, archive)]:
                    self.assertNotEqual(result.returncode, 0)
                    self.assertNotIn('ready to write', result.stdout)


if __name__ == '__main__':
    unittest.main()
