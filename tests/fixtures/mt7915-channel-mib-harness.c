/* Userspace transport doubles around the unchanged production function. */
#include <assert.h>
#include <errno.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

typedef uint16_t u16;
typedef uint32_t u32;
typedef uint64_t u64;
typedef uint32_t __le32;
typedef uint64_t __le64;
#define cpu_to_le32(x) (x)
#define le64_to_cpu(x) (x)
#define ARRAY_SIZE(a) (sizeof(a) / sizeof((a)[0]))
#define MCU_EXT_CMD(x) (0)

struct mt7915_mcu_mib { __le32 band, offs; __le64 data; } __attribute__((packed));
enum {
    MIB_TX_TIME = 81, MIB_RX_TIME = 82, MIB_OBSS_AIRTIME = 86,
    MIB_NON_WIFI_TIME = 87, MIB_TXOP_INIT_COUNT = 88,
    MIB_TX_TIME_V2 = 6, MIB_RX_TIME_V2 = 8,
    MIB_OBSS_AIRTIME_V2 = 490, MIB_NON_WIFI_TIME_V2 = 491,
};
struct mt76_channel_state { u64 cc_tx, cc_bss_rx, cc_rx, cc_busy; };
struct mt76_phy { struct mt76_channel_state *chan_state; unsigned int band_idx; };
struct mt76_dev { u16 chip; };
struct mt7915_dev { struct mt76_dev mt76; };
struct mt7915_phy {
    struct mt76_phy *mt76;
    struct mt7915_dev *dev;
    struct mt76_channel_state state_ts;
};
struct sk_buff { unsigned char *data; size_t len, headlen; };
static size_t skb_headlen(struct sk_buff *skb) { return skb->headlen; }
static bool is_mt7915(struct mt76_dev *dev) { return dev->chip == 0x7915; }
static bool is_mt7981(struct mt76_dev *dev) { return dev->chip == 0x7981; }

enum reply { VALID, STALE, REORDERED, SHORT, NONLINEAR, TRANSPORT_ERROR };
static enum reply sequence[3];
static unsigned int calls, frees, band;
static u64 counters[5] = {10, 100, 20, 30, 1};
static void responses(enum reply a, enum reply b, enum reply c)
{
    sequence[0] = a; sequence[1] = b; sequence[2] = c;
    calls = frees = 0;
}
static void dev_kfree_skb(struct sk_buff *skb)
{
    free(skb->data);
    free(skb);
    frees++;
}
static int mt76_mcu_send_and_get_msg(struct mt76_dev *dev, int cmd,
                                    const struct mt7915_mcu_mib *req,
                                    size_t bytes, bool wait, struct sk_buff **out)
{
    static const u32 v2[] = {491, 6, 8, 490}, v1[] = {87, 81, 82, 86, 88};
    const u32 *order = is_mt7915(dev) ? v1 : v2;
    size_t n = is_mt7915(dev) ? 5 : 4, prefix = is_mt7915(dev) ? 20 : 0;
    (void)cmd;
    assert(calls < 3 && wait && bytes == n * sizeof(*req));
    for (size_t i = 0; i < n; i++)
        assert(req[i].band == band && req[i].offs == order[i] && req[i].data == 0);
    enum reply kind = sequence[calls++];
    if (kind == TRANSPORT_ERROR)
        return -ETIMEDOUT;
    struct sk_buff *skb = calloc(1, sizeof(*skb));
    assert(skb);
    size_t needed = prefix + bytes;
    skb->len = kind == STALE ? 328 : kind == SHORT ? needed - 1 : needed + 20;
    skb->headlen = kind == NONLINEAR ? needed - 1 : skb->len;
    skb->data = calloc(1, skb->headlen);
    assert(skb->data);
    if (skb->headlen >= needed && kind != STALE) {
        struct mt7915_mcu_mib *res = (void *)(skb->data + prefix);
        for (size_t i = 0; i < n; i++) {
            /* MT7981 reports band 0 even for a band 1 query. */
            res[i].band = 0;
            res[i].offs = is_mt7915(dev) ? 0 : req[i].offs;
            res[i].data = counters[i];
        }
        if (kind == REORDERED) {
            res[0].offs = req[1].offs;
            res[1].offs = req[0].offs;
        }
    }
    *out = skb;
    return 0;
}

#include "mcu.c"

static void equal_state(const struct mt76_channel_state *a,
                        const struct mt76_channel_state *b)
{
    assert(!memcmp(a, b, sizeof(*a)));
}

int main(int argc, char **argv)
{
    (void)argv;
    struct mt76_channel_state state = {0};
    struct mt76_phy mphy = {.chan_state = &state};
    struct mt7915_dev dev = {.mt76 = {.chip = 0x7981}};
    struct mt7915_phy phy = {.mt76 = &mphy, .dev = &dev};
    if (argc > 1) {
        phy.state_ts = (struct mt76_channel_state){1000, 1000, 1000, 1000};
        responses(VALID, VALID, VALID);
        assert(mt7915_mcu_get_chan_mib_info(&phy, false) == 0);
        assert(state.cc_tx == UINT64_MAX - 899);
        puts("Negative control: original production function wraps TX survey totals");
        return 0;
    }
    for (band = 0; band < 2; band++) {
        mphy.band_idx = band;
        state = (struct mt76_channel_state){0};
        phy.state_ts = (struct mt76_channel_state){0};
        memcpy(counters, (u64[]){10, 100, 20, 30, 1}, sizeof(counters));
        responses(STALE, REORDERED, VALID);
        assert(mt7915_mcu_get_chan_mib_info(&phy, false) == 0 && calls == 3 && frees == 3);
        struct mt76_channel_state expected = {100, 20, 50, 160};
        equal_state(&state, &expected);
        equal_state(&phy.state_ts, &expected);

        /* Each field can decrease while the others stay equal or increase. */
        const u64 backwards[][5] = {
            {1000, 99, 20, 30, 1}, {10, 100, 19, 31, 1},
            {20, 100, 20, 29, 1}, {9, 100, 20, 30, 1},
        };
        for (unsigned int i = 0; i < ARRAY_SIZE(backwards); i++) {
            memcpy(counters, backwards[i], sizeof(counters));
            responses(VALID, VALID, VALID);
            assert(mt7915_mcu_get_chan_mib_info(&phy, false) == -EINVAL && calls == 1 && frees == 1);
            equal_state(&state, &expected);
            equal_state(&phy.state_ts, &expected);
        }
        /* Repeated old/new snapshots must not ratchet the accumulated totals. */
        for (int i = 0; i < 16; i++) {
            memcpy(counters, (u64[]){1, 10, 2, 3, 1}, sizeof(counters));
            responses(VALID, VALID, VALID);
            assert(mt7915_mcu_get_chan_mib_info(&phy, false) == -EINVAL);
            memcpy(counters, (u64[]){10, 100, 20, 30, 1}, sizeof(counters));
            responses(VALID, VALID, VALID);
            assert(mt7915_mcu_get_chan_mib_info(&phy, false) == 0);
            equal_state(&state, &expected);
            equal_state(&phy.state_ts, &expected);
        }
        memcpy(counters, (u64[]){12, 110, 22, 33, 1}, sizeof(counters));
        responses(VALID, VALID, VALID);
        assert(mt7915_mcu_get_chan_mib_info(&phy, false) == 0);
        expected = (struct mt76_channel_state){110, 22, 55, 177};
        equal_state(&state, &expected);
        equal_state(&phy.state_ts, &expected);

        struct mt76_channel_state baseline = phy.state_ts;
        responses(SHORT, NONLINEAR, STALE);
        assert(mt7915_mcu_get_chan_mib_info(&phy, true) == -EINVAL && calls == 3 && frees == 3);
        equal_state(&state, &expected);
        equal_state(&phy.state_ts, &baseline);
        responses(STALE, TRANSPORT_ERROR, VALID);
        assert(mt7915_mcu_get_chan_mib_info(&phy, false) == -ETIMEDOUT && calls == 2 && frees == 1);
        equal_state(&state, &expected);
        equal_state(&phy.state_ts, &baseline);

        /* Explicit channel change/reset must still accept a lower baseline. */
        memcpy(counters, (u64[]){1, 10, 2, 3, 1}, sizeof(counters));
        responses(VALID, VALID, VALID);
        assert(mt7915_mcu_get_chan_mib_info(&phy, true) == 0 && frees == 1);
        equal_state(&state, &expected);
        baseline = (struct mt76_channel_state){10, 2, 5, 16};
        equal_state(&phy.state_ts, &baseline);
        memcpy(counters, (u64[]){2, 12, 3, 4, 1}, sizeof(counters));
        responses(VALID, VALID, VALID);
        assert(mt7915_mcu_get_chan_mib_info(&phy, false) == 0);
        expected = (struct mt76_channel_state){112, 23, 57, 182};
        equal_state(&state, &expected);
    }
    /* Legacy MT7915 layout and TX backoff adjustment are preserved. */
    dev.mt76.chip = 0x7915;
    band = mphy.band_idx = 0;
    memcpy(counters, (u64[]){10, 100, 20, 30, 1}, sizeof(counters));
    state = phy.state_ts = (struct mt76_channel_state){0};
    responses(VALID, VALID, VALID);
    assert(mt7915_mcu_get_chan_mib_info(&phy, false) == 0 && calls == 1 && frees == 1);
    assert(state.cc_tx == 21 && state.cc_busy == 81);
    puts("PASS: both bands, each backwards counter, alternating snapshots, channel reset, reply validation, transport errors, legacy layout");
    return 0;
}
