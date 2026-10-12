"""Exercise tcboot image dispatch without accessing router flash."""
import io
from pathlib import Path
import subprocess
import tarfile
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
PLATFORM = ROOT / 'target/linux/airoha/an7581/base-files/lib/upgrade/platform.sh'
BOARD = 'nokia,xg-040g-md-tcboot'


class TcbootUpgradeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.image = self.directory / 'sysupgrade.bin'
        self.tar_image(self.image, 'nokia_xg-040g-md-tcboot')

    def tar_image(self, path, profile):
        with tarfile.open(path, 'w') as archive:
            for name in ('CONTROL', 'kernel', 'root'):
                entry = tarfile.TarInfo('sysupgrade-' + profile + '/' + name)
                entry.size = 4
                archive.addfile(entry, io.BytesIO(b'test'))

    def run_platform(self, command, missing='', platform=PLATFORM):
        mocks = r'''
board_name() { echo nokia,xg-040g-md-tcboot; }
nand_do_platform_check() { echo "checked:$1"; }
# Match the OpenWrt helpers: an unsuccessful search may return status 0
# while producing no output. Callers must check the returned device name.
nand_find_ubi() { [ "$MISSING" = ubi ] && return 0; echo ubi0; }
nand_find_volume() { [ "$MISSING" = "$2" ] && return 0; echo ubi0_1; }
nand_do_upgrade() { echo "upgraded:$CI_UBIPART:$CI_KERNPART:$CI_SKIP_KERNEL_MTD"; }
fit_do_upgrade() { echo 'unexpected FIT upgrade'; return 1; }
fw_setenv() { echo 'unexpected environment write'; return 1; }
'''
        return subprocess.run(['sh', '-c', platform.read_text() + '\n' + mocks + '\n'
                               'MISSING="$2"\n' + command, 'test', str(self.image), missing],
                              text=True, capture_output=True)

    def test_accepts_own_sysupgrade_tar(self):
        result = self.run_platform('platform_check_image "$1"')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), 'checked:' + BOARD)

    def test_rejects_raw_fit_and_another_board_archive(self):
        for image in (b'\xd0\x0d\xfe\xed' + b'\0' * 1024, None):
            if image is None:
                self.tar_image(self.image, 'nokia_xg-040g-md-ubi')
            else:
                self.image.write_bytes(image)
            result = self.run_platform('platform_check_image "$1"')
            self.assertNotEqual(result.returncode, 0)
            self.assertNotIn('checked:', result.stdout)

    def test_upgrade_uses_ubi_kernel_volume(self):
        result = self.run_platform('platform_do_upgrade "$1"')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), 'upgraded:ubi:kernel:1')

    def test_missing_ubi_or_personal_data_blocks_flash(self):
        for missing in ('ubi', 'bosa', 'ri'):
            with self.subTest(missing=missing):
                result = self.run_platform('platform_do_upgrade "$1"', missing)
                self.assertNotEqual(result.returncode, 0)
                self.assertNotIn('upgraded:', result.stdout)
                self.assertNotIn('environment write', result.stdout)

    def test_missing_existing_ubi_base_volume_is_detected(self):
        for target in ('an7581', 'an7583'):
            platform = ROOT / 'target/linux/airoha' / target / 'base-files/lib/upgrade/platform.sh'
            for missing in ('fip', 'ubootenv', 'ubootenv2', 'factory', 'bosa', 'ri'):
                with self.subTest(target=target, missing=missing):
                    result = self.run_platform('airoha_require_ubi_layout factory bosa ri',
                                               missing, platform)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn('UBI base volume ' + missing + ' is missing', result.stdout)
                    self.assertEqual(result.stderr, '')


if __name__ == '__main__':
    unittest.main()
