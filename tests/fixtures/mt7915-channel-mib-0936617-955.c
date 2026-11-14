// SPDX-License-Identifier: BSD-3-Clause-Clear
/* Copyright (C) 2020 MediaTek Inc.
 * Production function from mt76 0936617dc529ff9da0385221d3fa6de732231177,
 * with this repository's patch 955 applied, before patch 962.
 * Firmware transport and kernel types are supplied by the test harness.
 */
int mt7915_mcu_get_chan_mib_info(struct mt7915_phy *phy, bool chan_switch)
{
	struct mt76_channel_state *state = phy->mt76->chan_state;
	struct mt76_channel_state *state_ts = &phy->state_ts;
	struct mt7915_dev *dev = phy->dev;
	struct mt7915_mcu_mib *res, req[5] = {};
	struct sk_buff *skb;
	bool check_offsets = is_mt7981(&dev->mt76);
	const u32 *offs;
	int i, ret, len, offs_cc, attempt;
	u64 cc_tx;

	/* strict order */
	if (is_mt7915(&dev->mt76)) {
		static const u32 chip_offs[] = {
			MIB_NON_WIFI_TIME,
			MIB_TX_TIME,
			MIB_RX_TIME,
			MIB_OBSS_AIRTIME,
			MIB_TXOP_INIT_COUNT,
		};
		len = ARRAY_SIZE(chip_offs);
		offs = chip_offs;
		offs_cc = 20;
	} else {
		static const u32 chip_offs[] = {
			MIB_NON_WIFI_TIME_V2,
			MIB_TX_TIME_V2,
			MIB_RX_TIME_V2,
			MIB_OBSS_AIRTIME_V2
		};
		len = ARRAY_SIZE(chip_offs);
		offs = chip_offs;
		offs_cc = 0;
	}

	for (i = 0; i < len; i++) {
		req[i].band = cpu_to_le32(phy->mt76->band_idx);
		req[i].offs = cpu_to_le32(offs[i]);
	}

	/*
	 * On MT7981, an unrelated late reply can match a reused sequence
	 * number. Check the echoed offsets before using any survey counters.
	 */
	for (attempt = 1; ; attempt++) {
		ret = mt76_mcu_send_and_get_msg(&dev->mt76,
					       MCU_EXT_CMD(GET_MIB_INFO),
					       req, len * sizeof(req[0]), true,
					       &skb);
		if (ret)
			return ret;

		if (skb_headlen(skb) >= offs_cc + len * sizeof(*res)) {
			res = (struct mt7915_mcu_mib *)(skb->data + offs_cc);
			if (!check_offsets)
				break;

			for (i = 0; i < len; i++)
				if (res[i].offs != req[i].offs)
					break;
			if (i == len)
				break;
		}

		dev_kfree_skb(skb);
		if (!check_offsets || attempt == 3)
			return -EINVAL;
	}

#define __res_u64(s) le64_to_cpu(res[s].data)
	/* subtract Tx backoff time from Tx duration for MT7915 */
	if (is_mt7915(&dev->mt76)) {
		u64 backoff = (__res_u64(4) & 0xffff) * 79;  /* 16us + 9us * 7 */
		cc_tx = __res_u64(1) - backoff;
	} else {
		cc_tx = __res_u64(1);
	}

	if (chan_switch)
		goto out;

	state->cc_tx += cc_tx - state_ts->cc_tx;
	state->cc_bss_rx += __res_u64(2) - state_ts->cc_bss_rx;
	state->cc_rx += __res_u64(2) + __res_u64(3) - state_ts->cc_rx;
	state->cc_busy += __res_u64(0) + cc_tx + __res_u64(2) + __res_u64(3) -
			  state_ts->cc_busy;

out:
	state_ts->cc_tx = cc_tx;
	state_ts->cc_bss_rx = __res_u64(2);
	state_ts->cc_rx = __res_u64(2) + __res_u64(3);
	state_ts->cc_busy = __res_u64(0) + cc_tx + __res_u64(2) + __res_u64(3);
#undef __res_u64

	dev_kfree_skb(skb);

	return 0;
}
