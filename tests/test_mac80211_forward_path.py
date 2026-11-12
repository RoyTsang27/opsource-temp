from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
PATCH = ROOT / 'target/linux/generic/backport-6.18/706-02-v7.3-netfilter-flowtable-restore-ieee80211-forward-path.patch'
WIRELESS = ROOT / 'package/kernel/mac80211/patches/subsys/007-netfilter-flowtable-restore-ieee80211-forward-path.patch'


@unittest.skipUnless(shutil.which('cc') and shutil.which('patch'), 'a C compiler and patch are required')
class ForwardPathTests(unittest.TestCase):
    def test_real_mac80211_guard_compiles_and_preserves_the_driver_path(self):
        with tempfile.TemporaryDirectory() as temporary:
            work = Path(temporary)
            header = work / 'include/linux/netdevice.h'
            header.parent.mkdir(parents=True)
            fixture = (ROOT / 'tests/fixtures/netdevice-forward-path-6.18.63.h').read_text()
            # Keep the original line numbers for older system patch programs.
            header.write_text('\n' * 872 + fixture + '\nenum tc_setup_type {\n\tTC_SETUP_FIXTURE,\n};\n')
            guard = '\n'.join(line[1:] for line in WIRELESS.read_text().splitlines()
                              if line.startswith('+') and not line.startswith('+++'))
            probe = work / 'probe.c'
            probe.write_text('''typedef unsigned char u8;
typedef unsigned short u16, __be16;
typedef _Bool bool;
#define ETH_ALEN 6
#define NULL ((void *)0)
struct net_device { int id; };
#include "include/linux/netdevice.h"
static int forward_path(struct net_device_path_ctx *ctx, struct net_device_path *path)
{
''' + guard + '''
    return -95;
}
int main(void)
{
    struct net_device dev = { 1 };
    struct net_device_path_ctx ctx = { .dev = &dev };
    struct net_device_path path = { .type = DEV_PATH_MTK_WDMA };
    if (forward_path(&ctx, &path) != -95 || ctx.dev != &dev || path.type != DEV_PATH_MTK_WDMA)
        return 1;
    ctx.ieee80211 = 1;
    if (forward_path(&ctx, &path) || ctx.dev || path.dev != &dev || path.type != DEV_PATH_IEEE80211)
        return 2;
    return 0;
}
''')
            command = ['cc', '-std=c11', '-Wall', '-Wextra', '-Werror', str(probe), '-o', str(work / 'probe')]
            before = subprocess.run(command, capture_output=True, text=True)
            self.assertNotEqual(before.returncode, 0)
            self.assertIn('ieee80211', before.stderr)
            self.assertIn('DEV_PATH_IEEE80211', before.stderr)
            native = PATCH.read_text().split('--- a/include/linux/netdevice.h', 1)[1].split('--- a/net/mac80211/iface.c', 1)[0]
            result = subprocess.run(['patch', '-p1', '--fuzz=0', '--force'], cwd=work,
                                    input='--- a/include/linux/netdevice.h' + native,
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            subprocess.run(command, check=True, capture_output=True)
            subprocess.run([str(work / 'probe')], check=True)
            clang = shutil.which('clang')
            if clang:
                for target in ('aarch64-linux-gnu', 'mipsel-linux-gnu'):
                    result = subprocess.run([clang, '-target', target, '-ffreestanding', '-nostdinc',
                                             '-std=c11', '-Wall', '-Wextra', '-Werror', '-fsyntax-only', str(probe)],
                                            capture_output=True, text=True)
                    self.assertEqual(result.returncode, 0, result.stderr)

    def test_migration_kit_contains_the_kernel_companion(self):
        bundle = ROOT / 'updates/kernel-6.18.63'
        required = [*sorted(PATCH.parent.glob('706-*.patch')),
                    ROOT / 'target/linux/generic/hack-6.18/650-netfilter-add-xt_FLOWOFFLOAD-target.patch']
        self.assertEqual(len(required), 3)
        delta = (bundle / 'patches/op-source-6.18.60-to-6.18.63.patch').read_text()
        for patch in required:
            self.assertEqual((bundle / 'files' / patch.relative_to(ROOT)).read_bytes(), patch.read_bytes())
            self.assertIn(str(patch.relative_to(ROOT)), delta)
