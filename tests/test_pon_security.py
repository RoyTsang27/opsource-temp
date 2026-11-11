"""Exercise the integrated PON code without accessing router hardware."""
import json
import os
from pathlib import Path
import re
import shutil
import shlex
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
PON = ROOT / 'package/pon'
SECURE = PON / 'userspace/airoha-ponctl/files/pon-secure.sh'
DATA = PON / 'userspace/luci-app-pon/root/usr/libexec/airoha-pon-data'
SHELL = shlex.split(os.environ.get('PON_TEST_SHELL', 'sh'))


class OmciLengthTests(unittest.TestCase):
    @unittest.skipUnless(sys.platform == 'linux', 'compiled against Linux in CI')
    def test_actual_driver_normalizer_rejects_all_wrapping_lengths(self):
        compiler = shutil.which('cc')
        if not compiler:
            self.skipTest('C compiler is required')
        source = (PON / 'drivers/airoha-xpon/src/airoha-xpon-omci.c').read_text()
        constants = '\n'.join(re.findall(r'^#define AIROHA_OMCI_(?:BASELINE|EXTENDED|HEADER|MAX)[^\n]+', source, re.M))
        start = source.index('static int airoha_xpon_omci_normalize_tx(')
        end = source.index('\nstatic netdev_tx_t', start)
        harness = r'''
#include <assert.h>
#include <errno.h>
#include <stdint.h>
#include <string.h>
typedef uint8_t u8;
typedef uint16_t u16;
struct sk_buff { unsigned int len; u8 data[2000]; };
static int pskb_may_pull(struct sk_buff *skb, unsigned int len) { return skb->len >= len; }
static int pskb_trim(struct sk_buff *skb, unsigned int len) {
    assert(len <= skb->len); skb->len = len; return 0;
}
static unsigned int get_unaligned_be16(const u8 *p) { return ((unsigned int)p[0] << 8) | p[1]; }
'''
        harness += constants + '\n' + source[start:end] + r'''
int main(void) {
    struct sk_buff skb = {0};
    for (unsigned int declared = 0; declared <= 65535; declared++) {
        skb.len = 10;
        skb.data[3] = 0x0b;
        skb.data[8] = declared >> 8; skb.data[9] = declared;
        int result = airoha_xpon_omci_normalize_tx(&skb);
        assert(declared == 0 ? result == 0 && skb.len == 10 : result == -EMSGSIZE);
    }
    for (unsigned int body = 0; body <= 1970; body++) {
        skb.data[8] = body >> 8; skb.data[9] = body;
        skb.len = 10 + body;
        assert(airoha_xpon_omci_normalize_tx(&skb) == 0 && skb.len == 10 + body);
        skb.len = 14 + body;
        int result = airoha_xpon_omci_normalize_tx(&skb);
        assert(body <= 1966 ? result == 0 && skb.len == 10 + body : result == -EMSGSIZE);
    }
    skb.data[3] = 0x0a;
    skb.len = 48; assert(airoha_xpon_omci_normalize_tx(&skb) == 0 && skb.len == 44);
    skb.len = 44; assert(airoha_xpon_omci_normalize_tx(&skb) == 0);
    skb.len = 43; assert(airoha_xpon_omci_normalize_tx(&skb) == -EMSGSIZE);
    skb.len = 9; assert(airoha_xpon_omci_normalize_tx(&skb) == -EMSGSIZE);
    skb.len = 10; skb.data[3] = 0xff;
    assert(airoha_xpon_omci_normalize_tx(&skb) == -EPROTONOSUPPORT);
}
'''
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            (path / 'test.c').write_text(harness)
            subprocess.run([compiler, '-std=c11', '-Wall', '-Wextra', '-Werror',
                            str(path / 'test.c'), '-o', str(path / 'test')], check=True)
            subprocess.run([str(path / 'test')], check=True)


class RuntimeDirectoryTests(unittest.TestCase):
    def run_library(self, directory, command):
        source = SECURE.read_text().replace('PON_RUNTIME_DIR=/tmp/ponwrt',
                                           "PON_RUNTIME_DIR='" + str(directory) + "'")
        return subprocess.run([*SHELL, '-c', source + '\n' + command], capture_output=True)

    def test_rejects_symlink_without_changing_its_target(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / 'victim'
            target.mkdir(mode=0o755)
            (root / 'runtime').symlink_to(target)
            result = self.run_library(root / 'runtime', 'pon_runtime_init board')
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(target.stat().st_mode & 0o777, 0o755)
            self.assertFalse((target / 'board').exists())

    def test_rejects_existing_directory_with_public_permissions(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'runtime'
            path.mkdir(mode=0o755)
            result = self.run_library(path, 'pon_runtime_init board')
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(path.stat().st_mode & 0o777, 0o755)


@unittest.skipUnless(os.geteuid() == 0, 'run as root in Linux CI for ownership and upload checks')
class BoardUploadTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.runtime = self.root / 'runtime'
        secure = SECURE.read_text().replace('PON_RUNTIME_DIR=/tmp/ponwrt',
                                           "PON_RUNTIME_DIR='" + str(self.runtime) + "'")
        source = DATA.read_text()
        source = re.sub(r'^\. /[^\n]+\n', '', source, flags=re.M)
        # Mock only the hardware discovery/writer. All input, locking, backup,
        # validation and readback code is the real installed shell script.
        fake = r'''
load_target() { name="$1"; storage=ubi; capacity=8; target="$FAKE_FLASH"; actual_size=8; }
locate_target() { :; }
ubiupdatevol() { cp "$2" "$1"; }
'''
        source = source.replace('case "$1" in\nprepare)', fake + '\ncase "$1" in\nprepare)', 1)
        self.script = self.root / 'helper'
        self.script.write_text(secure + '\n' + source)
        self.flash = self.root / 'flash'
        self.flash.write_bytes(b'original')

    def run_helper(self, *args):
        return subprocess.run([*SHELL, str(self.script), *args], capture_output=True,
                              env={**os.environ, 'FAKE_FLASH': str(self.flash)})

    def prepare(self):
        result = self.run_helper('prepare')
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def test_uploads_are_unique_private_and_backups_survive_readback(self):
        first, second = self.prepare(), self.prepare()
        self.assertNotEqual(first['token'], second['token'])
        upload = Path(first['path'])
        self.assertEqual(upload.stat().st_mode & 0o777, 0o600)
        self.assertEqual(upload.parent.stat().st_mode & 0o777, 0o700)
        upload.write_bytes(b'new!')
        result = self.run_helper('write', 'factory', first['token'])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.flash.read_bytes(), b'new!')
        backups = list(upload.parent.glob('backup-factory.*'))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_bytes(), b'original')
        self.assertEqual(backups[0].stat().st_mode & 0o777, 0o600)

    def test_symlink_hardlink_and_oversized_uploads_cannot_write_flash(self):
        for kind in ('symlink', 'hardlink', 'oversized'):
            with self.subTest(kind=kind):
                upload = self.prepare()
                path = Path(upload['path'])
                path.unlink()
                if kind == 'symlink':
                    path.symlink_to(self.flash)
                elif kind == 'hardlink':
                    os.link(self.flash, path)
                else:
                    path.write_bytes(b'x' * 9)
                result = self.run_helper('write', 'factory', upload['token'])
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(self.flash.read_bytes(), b'original')

    def test_refuses_untrusted_owner_and_path_traversal(self):
        upload = self.prepare()
        path = Path(upload['path'])
        path.write_bytes(b'new!')
        os.chown(path, 65534, 65534)
        self.assertNotEqual(self.run_helper('write', 'factory', upload['token']).returncode, 0)
        self.assertNotEqual(self.run_helper('write', 'factory', '../flash').returncode, 0)
        self.assertEqual(self.flash.read_bytes(), b'original')

    def test_refuses_attacker_owned_runtime_directory(self):
        self.runtime.mkdir(mode=0o700)
        os.chown(self.runtime, 65534, 65534)
        self.assertNotEqual(self.run_helper('prepare').returncode, 0)
        self.assertFalse((self.runtime / 'board').exists())


class DefaultPonTests(unittest.TestCase):
    def test_stale_feed_links_cannot_override_audited_packages(self):
        awk = shutil.which('gawk')
        if not awk:
            self.skipTest('GNU awk is required')
        with tempfile.TemporaryDirectory() as directory:
            override = Path(directory) / 'overrides'
            result = subprocess.run([awk, '-v', 'of=' + str(override), '-f',
                                     str(ROOT / 'include/scan.awk')],
                                    input='pon/userspace/airoha-ponctl\nfeeds/pon_userspace/airoha-ponctl\n'
                                          'system/ordinary\nfeeds/custom/ordinary\n',
                                    text=True, capture_output=True, check=True)
            self.assertIn('pon/userspace/airoha-ponctl', result.stdout.splitlines())
            self.assertNotIn('feeds/pon_userspace/airoha-ponctl', result.stdout.splitlines())
            self.assertIn('feeds/custom/ordinary', result.stdout.splitlines())
            self.assertEqual(override.read_text().splitlines(), ['system/ordinary'])

    def test_sensitive_bundle_requires_write_permission(self):
        acl = json.loads((PON / 'userspace/luci-app-pon/root/usr/share/rpcd/acl.d/luci-app-pon.json').read_text())['luci-app-pon']
        bundle = '/tmp/ponwrt/debug/pon-debug.tar.gz'
        self.assertNotIn(bundle, acl['read']['file'])
        self.assertEqual(acl['write']['file'][bundle], ['read'])


if __name__ == '__main__':
    unittest.main()
