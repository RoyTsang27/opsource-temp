"""Run the prepared kernel's WO loader against legacy and syscon boot mappings.

Set WED_TEST_KERNEL to a kernel tree after OpenWrt target/linux/prepare.
The actual loader, register helpers and optional syscon lookup are compiled;
only hardware access and firmware delivery are replaced with test doubles.
"""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


def function(source, declaration):
    start = source.index(declaration)
    return source[start:source.index('\n}', start) + 2] + '\n'


@unittest.skipUnless(os.environ.get('WED_TEST_KERNEL'),
                     'set WED_TEST_KERNEL to a prepared MediaTek kernel')
@unittest.skipUnless(shutil.which('cc'), 'a C compiler is required')
class WedBootTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        kernel = Path(os.environ['WED_TEST_KERNEL'])
        wed = (kernel / 'drivers/net/ethernet/mediatek/mtk_wed_mcu.c').read_text()
        syscon = (kernel / 'drivers/mfd/syscon.c').read_text()
        memory = wed[wed.index('static struct mtk_wed_wo_memory_region mem_region[]'):]
        memory = memory[:memory.index('\n};') + 3] + '\n'
        cls.temporary = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temporary.cleanup)
        directory = Path(cls.temporary.name)
        source = directory / 'wed-boot.c'
        source.write_text(ENVIRONMENT + memory +
                          function(syscon, 'struct regmap *syscon_regmap_lookup_by_phandle_optional(') +
                          function(wed, 'static u32 wo_r32(') +
                          function(wed, 'static void wo_w32(') +
                          'static int\n' + function(wed, 'mtk_wed_mcu_load_firmware(') + MAIN)
        cls.binary = directory / 'wed-boot'
        result = subprocess.run(['cc', '-std=gnu11', '-Wall', '-Wextra', '-Werror',
                                 '-Wno-sign-compare', str(source), '-o', str(cls.binary)],
                                capture_output=True, text=True)
        if result.returncode:
            raise AssertionError(result.stdout + result.stderr)

    def scenario(self, name):
        result = subprocess.run([str(self.binary), name], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_missing_phandle_uses_legacy_boot_registers(self):
        self.scenario('legacy')

    def test_syscon_mapping_skips_legacy_boot_region(self):
        self.scenario('syscon')

    def test_deferred_probe_stops_before_firmware_or_register_access(self):
        self.scenario('defer')

    def test_lookup_error_stops_before_firmware_or_register_access(self):
        self.scenario('invalid')

    def test_missing_legacy_region_stops_before_register_access(self):
        self.scenario('missing-region')

    def test_missing_firmware_stops_before_boot_register_access(self):
        self.scenario('missing-firmware')

    def test_firmware_load_failure_releases_firmware_without_booting(self):
        self.scenario('firmware-error')


ENVIRONMENT = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#include <string.h>
#include <errno.h>

typedef uint32_t u32;
#define EPROBE_DEFER 517
#define ARRAY_SIZE(array) (sizeof(array) / sizeof((array)[0]))
#define ERR_PTR(error) ((void *)(intptr_t)(error))
#define PTR_ERR(pointer) ((long)(intptr_t)(pointer))
#define IS_ERR(pointer) ((uintptr_t)(pointer) >= (uintptr_t)-4095)
#define MTK_WED_SCR0 0
#define MTK_WED_DUMMY_CR_FWDL 0
#define MTK_WO_MCU_CFG_LS_WA_BOOT_ADDR_ADDR 0x64
#define MTK_WO_MCU_CFG_LS_WM_BOOT_ADDR_ADDR 0x60
#define MTK_WO_MCU_CFG_LS_WF_MCCR_CLR_ADDR 0x1c
#define MTK_WO_MCU_CFG_LS_WF_MCU_CFG_WM_WA_ADDR 0x50
#define MTK_WO_MCU_CFG_LS_WF_WM_WA_WA_CPU_RSTB_MASK 1
#define MTK_WO_MCU_CFG_LS_WF_WM_WA_WM_CPU_RSTB_MASK (1 << 5)
#define MT7981_FIRMWARE_WO "mediatek/mt7981_wo.bin"
#define MT7986_FIRMWARE_WO0 "mt7986_0"
#define MT7986_FIRMWARE_WO1 "mt7986_1"
#define MT7988_FIRMWARE_WO0 "mt7988_0"
#define MT7988_FIRMWARE_WO1 "mt7988_1"

enum { MTK_WED_WO_REGION_EMI, MTK_WED_WO_REGION_ILM,
       MTK_WED_WO_REGION_DATA, MTK_WED_WO_REGION_BOOT };
struct device_node { int unused; };
struct regmap { int unused; };
struct mtk_wed_hw { struct device_node *node; void *dev, *wed_dev; int version, index; };
struct mtk_wed_wo { struct mtk_wed_hw *hw; struct regmap *boot_regmap; };
struct mtk_wed_wo_memory_region { const char *name; bool shared; void *addr; uintptr_t phy_addr; };
struct mtk_wed_fw_trailer { char fw_ver[10], build_date[15]; unsigned char chip_id, num_region; };
struct firmware { const unsigned char *data; size_t size; };
static struct regmap boot_map;
static u32 registers[64];
static const char *scenario;
static int boot_mappings, firmware_requests, firmware_releases, raw_reads, raw_writes;
static int map_reads, map_writes;
#define is_scenario(name) (!strcmp(scenario, (name)))

static void dev_info(void *device, const char *format, ...)
{
    (void)device; (void)format;
}

static struct regmap *syscon_regmap_lookup_by_phandle(struct device_node *node,
                                                     const char *property)
{
    (void)node;
    assert(!strcmp(property, "mediatek,wo-cpuboot"));
    if (is_scenario("syscon")) return &boot_map;
    if (is_scenario("defer")) return ERR_PTR(-EPROBE_DEFER);
    if (is_scenario("invalid")) return ERR_PTR(-EINVAL);
    return ERR_PTR(-ENODEV);
}

static int mtk_wed_get_reserved_memory_region(struct mtk_wed_hw *hw, const char *name,
                                             struct mtk_wed_wo_memory_region *region)
{
    (void)hw;
    if (!strcmp(name, "wo-boot")) {
        boot_mappings++;
        assert(!is_scenario("syscon"));
        if (is_scenario("missing-region")) return -ENOENT;
    }
    region->addr = registers;
    region->phy_addr = 0x47d80000;
    return 0;
}

static int regmap_read(struct regmap *map, u32 reg, u32 *value)
{
    assert(map == &boot_map && reg / 4 < ARRAY_SIZE(registers));
    map_reads++; *value = registers[reg / 4]; return 0;
}
static int regmap_write(struct regmap *map, u32 reg, u32 value)
{
    assert(map == &boot_map && reg / 4 < ARRAY_SIZE(registers));
    map_writes++; registers[reg / 4] = value; return 0;
}
static u32 readl(void *address)
{
    assert((uintptr_t)address >= (uintptr_t)registers &&
           (uintptr_t)address < (uintptr_t)(registers + ARRAY_SIZE(registers)));
    raw_reads++; return *(u32 *)address;
}
static void writel(u32 value, void *address)
{
    assert((uintptr_t)address >= (uintptr_t)registers &&
           (uintptr_t)address < (uintptr_t)(registers + ARRAY_SIZE(registers)));
    raw_writes++; *(u32 *)address = value;
}
static int mtk_wed_mcu_load_ilm(struct mtk_wed_wo *wo)
{
    (void)wo; return 0;
}
#define mtk_wed_is_v3_or_greater(hw) ((hw)->version >= 3)
#define of_device_is_compatible(node, compatible) ((void)(node), (void)(compatible), true)
#define wed_w32(device, reg, value) ((void)(device), (void)(reg), (void)(value))
static int request_firmware(const struct firmware **fw, const char *name, void *device)
{
    static struct mtk_wed_fw_trailer trailer;
    static const struct firmware image = { (const unsigned char *)&trailer, sizeof(trailer) };
    (void)device;
    assert(!strcmp(name, MT7981_FIRMWARE_WO));
    firmware_requests++;
    if (is_scenario("missing-firmware")) return -ENOENT;
    *fw = &image; return 0;
}
#define mtk_wed_mcu_run_firmware(wo, fw) ((void)(wo), (void)(fw), is_scenario("firmware-error") ? -EIO : 0)
#define release_firmware(fw) ((void)(fw), firmware_releases++)
'''

MAIN = r'''
int main(int argc, char **argv)
{
    assert(argc == 2);
    scenario = argv[1];
    struct mtk_wed_hw hw = { .version = 2 };
    struct mtk_wed_wo wo = { .hw = &hw };
    int result = mtk_wed_mcu_load_firmware(&wo);
    int expected = 0;
    if (is_scenario("defer")) expected = -EPROBE_DEFER;
    if (is_scenario("invalid")) expected = -EINVAL;
    if (is_scenario("missing-region") || is_scenario("missing-firmware")) expected = -ENOENT;
    if (is_scenario("firmware-error")) expected = -EIO;
    assert(result == expected);
    if (is_scenario("defer") || is_scenario("invalid")) {
        assert(!boot_mappings && !firmware_requests && !firmware_releases);
    } else {
        assert(boot_mappings == !is_scenario("syscon"));
        assert(firmware_requests == !is_scenario("missing-region"));
        assert(firmware_releases == (!is_scenario("missing-region") &&
                                     !is_scenario("missing-firmware")));
    }
    assert(raw_reads == (!result && !is_scenario("syscon")));
    assert(raw_writes == (!result && !is_scenario("syscon") ? 3 : 0));
    assert(map_reads == (!result && is_scenario("syscon")));
    assert(map_writes == (!result && is_scenario("syscon") ? 3 : 0));
    if (!result) {
        assert(registers[0x60 / 4] == 0x47d8);
        assert(registers[0x1c / 4] == 0xc00);
        assert(registers[0x50 / 4] == (1 << 5));
    }
    return 0;
}
'''


if __name__ == '__main__':
    unittest.main()
