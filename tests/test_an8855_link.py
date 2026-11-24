"""Exercise AN8855 link transitions and switch statistics with simulated registers."""

from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


def function(source, name):
    start = re.search(r'^static void\s+' + re.escape(name) + r'\(', source, re.M).start()
    return source[start:source.index('\n}', start) + 2]


def run_program(program, source):
    program.write_text(source)
    binary = program.with_suffix('')
    compiled = subprocess.run(['cc', '-std=gnu11', '-Wall', '-Wextra', '-Werror',
                               '-Wno-unused-parameter', str(program), '-o', str(binary)],
                              capture_output=True, text=True)
    if compiled.returncode:
        return compiled
    return subprocess.run([str(binary)], capture_output=True, text=True)


@unittest.skipUnless(shutil.which('cc'), 'a C compiler is required')
class An8855LinkTests(unittest.TestCase):
    def test_port_register_across_link_transitions(self):
        for version in ('6.18', '7.3'):
            with self.subTest(kernel=version), tempfile.TemporaryDirectory() as tmp:
                driver = ROOT / f'target/linux/mediatek/files-{version}/drivers/net/dsa'
                definitions = re.findall(r'^#define\s+AN8855_PMCR_.*$',
                                         (driver / 'an8855.h').read_text(), re.M)
                source = (driver / 'an8855.c').read_text()
                callbacks = [function(source, f'an8855_phylink_mac_link_{state}')
                             for state in ('down', 'up')]
                result = run_program(Path(tmp) / 'an8855-link.c',
                                     '\n'.join([ENVIRONMENT, *definitions, *callbacks, MAIN]))
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_mib_offset_and_failed_reads(self):
        for version in ('6.18', '7.3'):
            with self.subTest(kernel=version), tempfile.TemporaryDirectory() as tmp:
                driver = ROOT / f'target/linux/mediatek/files-{version}/drivers/net/dsa'
                definitions = re.findall(r'^#define\s+AN8855_PORT_MIB_.*$',
                                         (driver / 'an8855.h').read_text(), re.M)
                reader = function((driver / 'an8855.c').read_text(), 'an8855_read_port_stats')
                result = run_program(Path(tmp) / 'an8855-mib.c',
                                     '\n'.join([MIB_ENVIRONMENT, *definitions, reader, MIB_MAIN]))
                self.assertEqual(result.returncode, 0, result.stderr)


ENVIRONMENT = r'''
#include <assert.h>
#include <errno.h>
#include <stdbool.h>
#include <stdint.h>

typedef uint32_t u32;
typedef int phy_interface_t;
struct phy_device;

#define BIT(n) (1U << (n))
#define GENMASK(h, l) ((UINT32_MAX >> (31 - (h))) & (UINT32_MAX << (l)))
#define FIELD_PREP_CONST(mask, value) ((value) << __builtin_ctz(mask))
#define SPEED_10 10
#define SPEED_100 100
#define SPEED_1000 1000
#define SPEED_2500 2500
#define SPEED_5000 5000
#define DUPLEX_FULL 1
#define FIXED 0
#define INBAND 1
#define phylink_autoneg_inband(mode) ((mode) == INBAND)
#define dsa_phylink_to_port(config) ((config)->port)
#define dsa_port_is_cpu(port) ((port)->index == 5)

struct regmap {
    u32 address;
    u32 value;
    int error;
};
struct an8855_priv { struct regmap *regmap; };
struct dsa_switch { struct an8855_priv *priv; };
struct dsa_port { struct dsa_switch *ds; int index; };
struct phylink_config { struct dsa_port *port; };

static int errors;
#define dev_err(...) ((void)++errors)
#define dev_err_ratelimited(...) dev_err(__VA_ARGS__)

int regmap_read(struct regmap *map, u32 address, u32 *value)
{
    assert(address == map->address);
    if (!map->error)
        *value = map->value;
    return map->error;
}

int regmap_write(struct regmap *map, u32 address, u32 value)
{
    assert(address == map->address);
    if (!map->error)
        map->value = value;
    return map->error;
}

static int regmap_update_bits(struct regmap *map, u32 address, u32 mask, u32 value)
{
    u32 previous;
    int error = regmap_read(map, address, &previous);

    assert((value & ~mask) == 0);
    if (error)
        return error;
    return regmap_write(map, address, (previous & ~mask) | value);
}

static int regmap_clear_bits(struct regmap *map, u32 address, u32 mask)
{
    return regmap_update_bits(map, address, mask, 0);
}
'''

MAIN = r'''
int main(void)
{
    const u32 mac_config = FIELD_PREP_CONST(AN8855_PMCR_IFG_XMIT, 1) |
                           AN8855_PMCR_MAC_MODE | AN8855_PMCR_BACKOFF_EN |
                           AN8855_PMCR_BACKPR_EN;
    const u32 enabled = AN8855_PMCR_TX_EN | AN8855_PMCR_RX_EN;
    const u32 forced = AN8855_PMCR_FORCE_MODE | AN8855_PMCR_FORCE_LNK |
                       AN8855_PMCR_FORCE_FDX;
    struct regmap map = { AN8855_PMCR_P(5), mac_config, 0 };
    struct an8855_priv priv = { &map };
    struct dsa_switch ds = { &priv };
    struct dsa_port port = { &ds, 5 };
    struct phylink_config config = { &port };
    u32 cpu_up = mac_config | enabled | forced | AN8855_PMCR_FORCE_SPEED_2500 |
                 BIT(4) | BIT(5);

    an8855_phylink_mac_link_up(&config, 0, FIXED, 0, SPEED_2500, DUPLEX_FULL,
                              false, false);
    assert(map.value == cpu_up);
    an8855_phylink_mac_link_down(&config, FIXED, 0);
    assert(map.value == (cpu_up & ~(enabled | AN8855_PMCR_FORCE_LNK)));
    an8855_phylink_mac_link_up(&config, 0, FIXED, 0, SPEED_2500, DUPLEX_FULL,
                              false, false);
    assert(map.value == cpu_up);
    an8855_phylink_mac_link_up(&config, 0, INBAND, 0, SPEED_1000, DUPLEX_FULL,
                              false, false);
    assert(map.value == (cpu_up & ~AN8855_PMCR_FORCE_MODE));

    port.index = 1;
    map.address = AN8855_PMCR_P(1);
    map.value = AN8855_PMCR_FORCE_SPEED_100 | AN8855_PMCR_FORCE_EEE100 | BIT(5);
    an8855_phylink_mac_link_up(&config, 0, FIXED, 0, SPEED_10, DUPLEX_FULL,
                              true, false);
    assert(map.value == (enabled | forced | BIT(4)));
    an8855_phylink_mac_link_up(&config, 0, FIXED, 0, SPEED_1000, DUPLEX_FULL,
                              false, true);
    assert(map.value == (enabled | forced | AN8855_PMCR_FORCE_SPEED_1000 | BIT(5)));

    u32 previous = map.value;
    an8855_phylink_mac_link_up(&config, 0, FIXED, 0, SPEED_5000, DUPLEX_FULL,
                              false, false);
    assert(map.value == previous && errors == 1);
    map.error = -EIO;
    an8855_phylink_mac_link_up(&config, 0, FIXED, 0, SPEED_100, DUPLEX_FULL,
                              false, false);
    assert(map.value == previous && errors == 2);
    return 0;
}
'''

MIB_ENVIRONMENT = r'''
#include <assert.h>
#include <errno.h>
#include <stdint.h>

typedef uint8_t u8;
typedef uint32_t u32;
typedef uint64_t u64;

struct regmap { u32 address, error_address; };
struct an8855_priv { struct regmap *regmap; };

static int regmap_read(struct regmap *map, u32 address, u32 *value)
{
    if (address % 4 || address == map->error_address)
        return -EIO;
    assert(address == map->address || address == map->address + 4);
    *value = address == map->address ? 23 : 5;
    return 0;
}
'''

MIB_MAIN = r'''
int main(void)
{
    struct regmap map = { 0x1021423c, 0 };
    struct an8855_priv priv = { &map };
    u64 count = UINT64_MAX;

    an8855_read_port_stats(&priv, 1, AN8855_PORT_MIB_TX_PKT_SZ_256_TO_511, 1, &count);
    assert(count == 23);

    map.address = 0x1021424c;
    an8855_read_port_stats(&priv, 1, AN8855_PORT_MIB_TX_BYTES, 2, &count);
    assert(count == (UINT64_C(5) << 32 | 23));

    count = UINT64_MAX;
    map.error_address = map.address + 4;
    an8855_read_port_stats(&priv, 1, AN8855_PORT_MIB_TX_BYTES, 2, &count);
    assert(count == UINT64_MAX);

    map.error_address = map.address;
    an8855_read_port_stats(&priv, 1, AN8855_PORT_MIB_TX_BYTES, 2, &count);
    assert(count == UINT64_MAX);
    return 0;
}
'''
