"""Regression coverage for U-Boot/Linux UBI handoff on both tcboot boards."""
import importlib.util
from pathlib import Path
import re
import struct
import subprocess
import tempfile
import unittest
import zlib

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('tcboot_image', ROOT / 'scripts/check-tcboot-image.py')
tcboot = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tcboot)
FIT = bytes.fromhex('d00dfeed') + struct.pack('>I', 40) + bytes(32)


def crc(data):
    return data + struct.pack('>I', zlib.crc32(data) ^ 0xffffffff)


def block(volume=0, leb=0, data=b'', eof=False):
    ec = bytearray(60)
    ec[:5] = b'UBI#\x01'
    if eof:
        ec[5:8] = b'EOF'
    struct.pack_into('>II', ec, 16, 2048, 4096)
    vid = bytearray(60)
    vid[:6] = b'UBI!\x01\x01'
    struct.pack_into('>II', vid, 8, volume, leb)
    return (crc(ec).ljust(2048, b'\xff') + crc(vid).ljust(2048, b'\xff') + data).ljust(
        tcboot.ERASEBLOCK, b'\xff')


def payload(eof=False):
    records = []
    for name in (b'kernel', b'rootfs', b'rootfs_data'):
        record = bytearray(168)
        struct.pack_into('>II', record, 0, 9, 1)
        record[12] = 1
        struct.pack_into('>H', record, 14, len(name))
        record[16:16 + len(name)] = name
        record[144] = int(name == b'rootfs_data')
        records.append(crc(record))
    table = b''.join(records + [crc(bytes(168))] * 125)
    image = (block(tcboot.LAYOUT_VOLUME, 0, table) +
             block(tcboot.LAYOUT_VOLUME, 1, table) + block(0, 0, FIT) + block(1, 0, b'hsqs'))
    return image + (block(eof=True) * 5 if eof else b'')


class TcbootFactoryTests(unittest.TestCase):
    def test_factory_envelope_and_ubi_payload(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'factory.bin'
            path.write_bytes(FIT.ljust(tcboot.KERNEL_SLOT, b'\0') + payload())
            tcboot.check(path)
            path.write_bytes(FIT.ljust(tcboot.KERNEL_SLOT, b'\0') + payload(eof=True))
            with self.assertRaisesRegex(ValueError, 'EOF markers'):
                tcboot.check(path)

    def test_rejects_missing_table_bad_crc_and_wrong_payload(self):
        good = payload()
        bad_crc = bytearray(good)
        bad_crc[60] ^= 1
        for bad in (good[:-1], good[2 * tcboot.ERASEBLOCK:], bad_crc,
                    good[:3 * tcboot.ERASEBLOCK] + block(1, 0, b'wrong-rootfs')):
            with self.subTest(size=len(bad)), self.assertRaises(ValueError):
                tcboot.check_ubi(bad, FIT)
        with self.assertRaisesRegex(ValueError, 'recovery FIT'):
            tcboot.check_ubi(good, FIT[:-1] + b'!')

    def test_eof_hides_relocated_layout_from_linux_but_not_uboot(self):
        # Model a U-Boot table rewrite: old table PEBs are erased, and the
        # atomic LEB change places the live copies after the factory payload.
        # OpenWrt scan_peb() treats every PEB after its first EOF as erased.
        def visible_tables(blocks, linux):
            found = 0
            for part in blocks:
                if linux and part[5:8] == b'EOF':
                    break
                if part[2048:2052] == b'UBI!' and int.from_bytes(part[2056:2060], 'big') == tcboot.LAYOUT_VOLUME:
                    found += 1
            return found

        for eof in (True, False):
            image = payload(eof)
            blocks = [image[i:i + tcboot.ERASEBLOCK] for i in range(0, len(image), tcboot.ERASEBLOCK)]
            moved = [b'\xff' * tcboot.ERASEBLOCK] * 2 + blocks[2:] + blocks[:2]
            self.assertEqual(visible_tables(moved, linux=False), 2)
            self.assertEqual(visible_tables(moved, linux=True), 0 if eof else 2)

    def test_both_resolved_recipes_disable_markers_and_share_metadata(self):
        for profile in ('nokia_xg-040g-md-tcboot', 'nokia_xg-140g-tf-tcboot'):
            makefile = ('include ' + str(ROOT / 'target/linux/airoha/image/an7581.mk') + '\n' +
                        '$(eval $(call Device/' + profile + '))\n' +
                        'all:\n\t@echo "$(UBINIZE_OPTS)"\n' +
                        '\t@echo "$(SUPPORTED_DEVICES)"\n')
            result = subprocess.run(['make', '--no-print-directory', '-f', '-'],
                                    input=makefile, text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            options, supported = result.stdout.splitlines()
            self.assertEqual(options.split(), ['-s', '2048'])
            self.assertEqual(set(supported.split()), {'nokia,xg-040g-md-tcboot', 'nokia,xg-140g-tf-tcboot'})

    def test_bootloader_arguments_retain_squashfs_block_mapping(self):
        source = (ROOT / 'target/linux/airoha/dts/an7581-nokia_xg-040g-md-tcboot.dts').read_text()
        append = re.search(r'bootargs-append = "([^"]+)";', source).group(1)
        self.assertTrue(append.startswith(' '))  # fdt.c uses strlcat.
        # Exact bootloader command line from the failing TTL log.
        args = ('ubi.mtd=ubi root=/dev/ubiblock0_1 rootwait' + append).split()
        self.assertIn('ubi.block=0,rootfs', args)
        self.assertIn('rootfstype=squashfs', args)
        self.assertEqual([a for a in args if a.startswith('root=')][-1], 'root=/dev/ubiblock0_1')


if __name__ == '__main__':
    unittest.main()
