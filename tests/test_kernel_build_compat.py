"""Exercise kernel command-line forwarding and the downstream UBI boot path."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which('make'), 'make is required')
class KernelMakeFlagsTests(unittest.TestCase):
    def flags(self, version):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            makefile = directory / 'Makefile'
            makefile.write_text(
                '__target_inc:=1\nARCH:=aarch64\nBOARD:=mediatek\n'
                'LINUX_DIR:=' + str(directory / 'kernel') + '\n'
                'LINUX_VERSION:=' + version + '.1\n'
                'split_version=$(subst ., ,$(1))\n'
                'include ' + str(ROOT / 'include/kernel.mk') + '\n'
                '.PHONY: flags\nflags:\n\t@printf \'%s\\n\' $(KERNEL_MAKE_FLAGS)\n')
            result = subprocess.run(
                ['make', '--no-print-directory', '-s', '-f', str(makefile), 'flags',
                 'KERNEL_PATCHVER=' + version], cwd=directory, check=True,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            return result.stdout.splitlines()

    def test_dependency_tracked_syscall_check_is_not_overridden(self):
        # Use the actual kernel version, even before an old .config is refreshed.
        for version in ['7.3', '7.4', '8.0']:
            with self.subTest(version=version):
                self.assertNotIn('cmd_syscalls=', self.flags(version))

    def test_older_kernel_command_line_is_preserved(self):
        for version in ['6.12', '6.18']:
            with self.subTest(version=version):
                self.assertIn('cmd_syscalls=', self.flags(version))


@unittest.skipUnless(shutil.which('cc'), 'a C compiler is required')
class UbiAutoAttachTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temporary.cleanup)
        directory = Path(cls.temporary.name)
        patch = (ROOT / 'target/linux/generic/pending-7.3/'
                 '490-ubi-auto-attach-mtd-device-named-ubi-or-data-on-boot.patch').read_text()
        additions = '\n'.join(line[1:] for line in patch.splitlines()
                              if line.startswith('+') and not line.startswith('+++'))
        function = ('static void __init ubi_auto_attach' +
                    additions.split('static void __init ubi_auto_attach', 1)[1].split('\n}', 1)[0] +
                    '\n}\n')
        source = directory / 'ubi-auto-attach.c'
        source.write_text(UBI_ENVIRONMENT + function + UBI_MAIN)
        cls.binary = directory / 'ubi-auto-attach'
        result = subprocess.run(['cc', '-std=gnu11', '-Wall', '-Wextra', '-Werror',
                                 '-Wno-sign-compare',
                                 str(source), '-o', str(cls.binary)],
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        if result.returncode:
            raise AssertionError(result.stdout)

    def run_scenario(self, scenario):
        subprocess.run([str(self.binary), str(scenario)], check=True)

    def test_auto_attach_uses_kernel_default_wear_leveling(self):
        self.run_scenario(0)

    def test_bad_magic_releases_mtd_without_attaching(self):
        self.run_scenario(1)

    def test_device_tree_ubi_is_not_attached_twice(self):
        self.run_scenario(2)

    def test_attach_failure_releases_mtd(self):
        self.run_scenario(3)

    def test_data_partition_fallback_uses_same_defaults(self):
        self.run_scenario(4)


UBI_ENVIRONMENT = r'''
#include <assert.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>

#define __init
#define UBI_DEV_NUM_AUTO (-1)
#define MTD_NANDFLASH 1
#define MTD_NORFLASH 2
#define MTD_DATAFLASH 3
#define MTD_MLCNANDFLASH 4
#define IS_ERR(pointer) ((pointer) == NULL)
#define pr_err(...) ((void)0)
#define pr_notice(...) ((void)0)
#define loff_t int64_t
struct device_node { int unused; };
struct mtd_info { int index, type; size_t erasesize, size; };
static struct device_node node;
static struct mtd_info flash = { 0, MTD_NANDFLASH, 4096, 1048576 };
static int scenario, attached, released, lookups, locked, ubi_devices_mutex;

static struct mtd_info *open_mtd_device(const char *name)
{
    lookups++;
    return scenario == 4 && !strcmp(name, "ubi") ? NULL : &flash;
}
#define mtd_get_of_node(mtd) ((void)(mtd), &node)
#define of_device_is_compatible(np, name) ((void)(np), (void)(name), scenario == 2)
#define mtd_can_have_bb(mtd) ((void)(mtd), false)
#define mtd_block_isbad(mtd, offset) ((void)(mtd), (void)(offset), 0)
#define mtd_is_bitflip(error) ((void)(error), false)
#define put_mtd_device(mtd) ((void)(mtd), released++)
#define mutex_lock(mutex) ((void)(mutex), assert(!locked), locked = 1)
#define mutex_unlock(mutex) ((void)(mutex), assert(locked), locked = 0)

static int mtd_read(struct mtd_info *mtd, loff_t offset, size_t count,
                    size_t *length, void *buffer)
{
    assert(mtd == &flash && offset == 0 && count == 4);
    memcpy(buffer, scenario == 1 ? "bad!" : "UBI#", 4);
    *length = 4;
    return 0;
}

/* Linux 7.3 drivers/mtd/ubi/ubi.h: final argument is wl_threshold.
 * build.c documents zero as the configured kernel default. */
static int ubi_attach_mtd_dev(struct mtd_info *mtd, int ubi_num,
                              int vid_hdr_offset, int max_beb_per1024,
                              bool disable_fm, bool need_resv_pool, int wl_threshold)
{
    assert(locked && mtd == &flash && ubi_num == UBI_DEV_NUM_AUTO);
    assert(!vid_hdr_offset && !max_beb_per1024 && !disable_fm && !need_resv_pool);
    assert(wl_threshold == 0);
    attached++;
    return scenario == 3 ? -22 : 0;
}
'''

UBI_MAIN = r'''
int main(int argc, char **argv)
{
    assert(argc == 2);
    scenario = atoi(argv[1]);
    ubi_auto_attach();
    assert(!locked);
    assert(attached == (scenario == 0 || scenario == 3 || scenario == 4));
    assert(released == (scenario == 1 || scenario == 2 || scenario == 3));
    assert(lookups == (scenario == 4 ? 2 : 1));
    return 0;
}
'''
