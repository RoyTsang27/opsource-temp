/* SPDX-License-Identifier: GPL-2.0 */
/* Unmodified forward-path declarations from Linux 6.18.63. */
enum net_device_path_type {
	DEV_PATH_ETHERNET = 0,
	DEV_PATH_VLAN,
	DEV_PATH_BRIDGE,
	DEV_PATH_PPPOE,
	DEV_PATH_DSA,
	DEV_PATH_MTK_WDMA,
};

struct net_device_path {
	enum net_device_path_type	type;
	const struct net_device		*dev;
	union {
		struct {
			u16		id;
			__be16		proto;
			u8		h_dest[ETH_ALEN];
		} encap;
		struct {
			enum {
				DEV_PATH_BR_VLAN_KEEP,
				DEV_PATH_BR_VLAN_TAG,
				DEV_PATH_BR_VLAN_UNTAG,
				DEV_PATH_BR_VLAN_UNTAG_HW,
			}		vlan_mode;
			u16		vlan_id;
			__be16		vlan_proto;
		} bridge;
		struct {
			int port;
			u16 proto;
		} dsa;
		struct {
			u8 wdma_idx;
			u8 queue;
			u16 wcid;
			u8 bss;
			u8 amsdu;
		} mtk_wdma;
	};
};

#define NET_DEVICE_PATH_STACK_MAX	5
#define NET_DEVICE_PATH_VLAN_MAX	2

struct net_device_path_stack {
	int			num_paths;
	struct net_device_path	path[NET_DEVICE_PATH_STACK_MAX];
};

struct net_device_path_ctx {
	const struct net_device *dev;
	u8			daddr[ETH_ALEN];

	int			num_vlans;
	struct {
		u16		id;
		__be16		proto;
	} vlan[NET_DEVICE_PATH_VLAN_MAX];
};
