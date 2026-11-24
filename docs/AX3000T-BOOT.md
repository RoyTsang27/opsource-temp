# AX3000T access-point startup

The follow-up TTL capture from 2026-11-23 reaches OpenWrt userspace, completes
WED and Wi-Fi firmware initialization, registers both radios and brings up the
AP interfaces. At 16.465 seconds the WA firmware reports:

```text
WA: --> drop by reaseon:1, msdu id = 0x7fe9 but failed!
WA: txblk
WA: host txd
```

The capture continues through both AP interfaces and a LAN link entering the
forwarding state at 22.55 seconds. It contains one Linux boot and no final
panic, watchdog-expiry report, reboot message or second boot banner. The WA
message identifies a transmit-path problem; it does not by itself prove what
resets the router. The earlier `regmap_write` panic is a separate corrected
failure.

## Default mitigation

Both AX3000T profiles now load `mt7915e wed_enable=N`. This bypasses WED
wireless acceleration during startup while retaining both Wi-Fi radios and
Ethernet. Forwarding uses the software path, with a possible throughput/CPU
tradeoff. Other Filogic/MT7622 profiles keep their existing WED default.
The same default applies when a multiple-device build includes either AX3000T
profile, since those images share the driver's module-loader parameters.

The setting is under **Kernel modules → Wireless Drivers → kmod-mt7915e →
Enable MediaTek WED wireless acceleration** (`CONFIG_PACKAGE_MT7915_WED`).
Explicitly enabling it restores `wed_enable=Y` for investigation. The mt76
package release is incremented and the setting is tracked as a package
configuration dependency, so existing build caches regenerate its loader file.

This is a mitigation for the suspect WED transmit path. A physical boot test
with the new default is needed to determine whether it stops the reported
reboots. The firmware binaries and cut-through descriptor format are kept at
their pinned versions.

## Rebuild the matching layout

This particular capture loads `xiaomi_mi-router-ax3000t-ubootmod`, uses a
112 MiB `ubi` partition, and mounts the FIT root filesystem successfully.
Use the `ax3000t-ubootmod` build profile for this installed layout. Its output
is the `*-xiaomi_mi-router-ax3000t-ubootmod-squashfs-sysupgrade.itb` image.
The separate stock-layout profile uses a different image and partition map.

After updating the source, resolve the configuration and rebuild the mt76
package and firmware. Check the generated image's module file or, after boot:

```sh
cat /etc/modules.d/mt7915e
cat /sys/module/mt7915e/parameters/wed_enable
```

Expected output is `mt7915e wed_enable=N` and `N`, respectively. Retained custom
files in the writable overlay can override the newly generated loader file.

## Wired Ethernet checks

The Linux 7.3.6 capture with the build timestamp `2026-11-23 23:04:22 UTC`
matches the source timestamp of `53aa6747f`. The AN8855 port MAC fix is in
the later commit `89b152cfb`. Compare `DISTRIB_REVISION` with the build's
`source-commit.txt` to identify the firmware. The GCC revision printed in
the kernel banner identifies the toolchain.

Both AX3000T layouts include `ethtool`, `bridge`, and iproute2's `ip`. Take
these readings before and after sending ARP or DHCP traffic from a wired
client connected to LAN2.

```sh
cat /etc/openwrt_release
cat /sys/module/mt7915e/parameters/wed_enable
bridge -d link show dev lan2
ethtool -S lan2 --groups eth-mac rmon
ethtool -S eth0
ip -s link show dev lan2
ip -s link show dev eth0
```

The AN8855 MAC counters show whether frames reached the external switch
port. The MediaTek `eth0` counters show whether those frames reached the
CPU-side Ethernet MAC.

## Existing-device serial workaround

At the OpenWrt `Press the [f] key ...` prompt, enter failsafe before the normal
Wi-Fi module load. Then apply the same default to the existing loader file:

```sh
mount_root
sed -i 's/wed_enable=[^[:space:]]*/wed_enable=N/g' /etc/modules.d/mt7915e
cat /etc/modules.d/mt7915e
reboot
```

If rebooting continues with WED disabled, capture serial output through the
next `F0`/BL2 banner, including the reset reason and elapsed time. In a usable
shell, collect `logread`, `dmesg` and any files under `/sys/fs/pstore/` before
another reboot. Those distinguish a firmware recovery, kernel panic, watchdog
reset and userspace-triggered reboot.
