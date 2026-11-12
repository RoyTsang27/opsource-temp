# mac80211 forward-path build recovery, 2026-11-12

The failure at `net/mac80211/iface.c` used an enum value and context member
which were not defined by Linux 6.18.63. The mac80211 update omitted two matching
kernel backports. Both are now carried from OpenWrt's kernel series:

- `95133a416809`: pass `net_device_path_ctx` to `dev_fill_forward_path()`.
- `3ae37eafd366`: add the IEEE 802.11 path type, context flag and flowtable handling.

The legacy xt_FLOWOFFLOAD caller is adjusted to the new context argument as
well. It keeps its existing path selection; MediaTek and Airoha continue to
request the driver-specific path, while nftables requests the IEEE 802.11 path.

The cumulative 6.18.60 migration kit includes all three source adjustments.
The smaller [repair kit](../updates/mac80211-forward-path/) applies them to an
already upgraded 6.18.63 directory and documents the kernel/module rebuild.

Local validation reproduced both reported compiler diagnostics using the
actual mac80211 guard and native 6.18.63 declarations. After the kernel header
patch, the code compiled for the host and passed AArch64 and MIPS syntax checks.
The executable probe verifies that the IEEE 802.11 path terminates correctly
and that the unset flag preserves the driver path. Full firmware compilation
and hardware runtime behavior still require validation on the Linux build host.
