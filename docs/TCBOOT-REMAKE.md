# Nokia MD/TF tcboot firmware

The previous custom tcboot partition include and shared image definition have
been replaced using the project requested by the owner:
[OpenWrt-for-XG-040G-MD](https://github.com/xiangtailiang/OpenWrt-for-XG-040G-MD/tree/e5320831b9d7f77315e6bd141cb2931c5cb27092).
Its main build workflow selects `nokia_xg-040g-md-tcboot` from
[`xiangtailiang/openwrt`](https://github.com/xiangtailiang/openwrt/tree/fb42bd65924c99c1c0e1f95fe0b3a285656814a7).
The older `patch/` directory in the wrapper project is not used by that main
workflow. The remake follows the active source's DTS, image layout and early
environment MAC setup. No extra feeds or unrelated packages were imported.

The MD tcboot DTS follows the pinned reference's hardware and partition map.
It protects the first 512 KiB bootloader partition, exposes the following
512 KiB environment, and allocates the remaining 255 MiB to UBI.
The factory image uses a FIT kernel at load/entry address `0x80088000`, padded
to 8 MiB, followed by UBI with 128 KiB eraseblocks and 2 KiB pages/subpages.
UBI uses volume IDs 0/1/2 for kernel/rootfs/rootfs_data. The source retains
image size checks and firmware signing.

The 2026-11-22 TTL log reaches Linux but fails with `UBI: EOF marker found`,
`the layout volume was not found`, and `Waiting for root device /dev/ubiblock0_1`.
The shared recipe inherited `-E 5` from the stock profile. These Linux EOF
markers are unsafe when U-Boot attaches UBI first: U-Boot can atomically move
both volume-table copies past the markers while updating or autoresizing
volumes, whereas OpenWrt's Linux scanner ignores every block after a marker.
This explains the different U-Boot/Linux attach results in the log; a flash
dump would be needed to confirm the live table's exact location on that device.
Both tcboot recipes now override the inherited options with `-s 2048` and
generate no EOF markers. A build-time factory checker rejects their return.

The same log shows U-Boot replacing the DTS boot arguments with
`ubi.mtd=ubi root=/dev/ubiblock0_1 rootwait`. Both DTS variants now inherit
`bootargs-append` to create `ubi.block=0,rootfs` and select the SquashFS block
root `/dev/ubiblock0_1`, even when U-Boot rewrites `bootargs`. The old
`root=ubi0:rootfs` syntax was unsuitable for a SquashFS root. The deferred NPU
firmware request occurs while rootfs is unavailable; it is not the attach error.

The TF tcboot profile inherits this layout and retains its separate board
identity, disabled USB controllers, and `lan1` WAN / `lan2`–`lan4` LAN mapping.
The reference only covers MD; the TF hardware adaptation still needs testing
on a physical TF device. Both boards read `ethaddr` directly from the
environment during initial network setup, before `fw_env.config` exists.

Existing stock and OpenWrt U-Boot/UBI menuconfig entries are preserved. The
owner's main devices map to the following existing profiles:

| Device | Target | Profiles in menuconfig |
| --- | --- | --- |
| Xiaomi AX3000T | mediatek/filogic | `xiaomi_mi-router-ax3000t`, `xiaomi_mi-router-ax3000t-ubootmod` |
| NBEL/Nokia XG-040G-MD | airoha/an7581 | `nokia_xg-040g-md`, `nokia_xg-040g-md-ubi`, `nokia_xg-040g-md-tcboot` |
| NBEL/Nokia XG-040G-MF | airoha/an7583 | `nokia_xg-040g-mf`, `nokia_xg-040g-mf-ubi` |
| NBEL/Nokia XG-140G-TF | airoha/an7581 | `nokia_xg-140g-tf-tcboot` |
| Cudy TR3000 v1 | mediatek/filogic | `cudy_tr3000-v1`, `cudy_tr3000-256mb-v1`, `cudy_tr3000-v1-ubootmod` |
| Cudy TR1200 v1 | ramips/mt76x8 | `cudy_tr1200-v1` |

Select the profile matching the installed bootloader and flash layout. An MF
tcboot layout is not defined by the supplied MD reference; both existing MF
entries remain available. The automated three-device default matrix remains
AX3000T, TR3000 and TR1200, with MD/TF tcboot available as explicit selections.

Use `factory.bin` with the installed tcboot Web recovery, and `sysupgrade.bin`
for subsequent upgrades. MD and TF images advertise both tcboot board IDs,
and either board accepts either profile's sysupgrade archive without forcing
the board check. The TF variant keeps USB disabled; using its image on MD
also disables USB. Use the MD image when MD USB support is required.
Initial port defaults follow the flashed profile: MD has four LAN ports;
TF has `lan1` as WAN and `lan2`–`lan4` as LAN.
This interchangeability covers firmware for these two tcboot profiles, not
their bootloaders or stock/official-UBI images.

The upgrade path requires an existing UBI device with `kernel`/`rootfs` at
IDs 0/1. It rejects other profiles, a raw FIT, a factory image and missing
or misplaced firmware volumes before writing. Upgrades target UBI volumes rather
than the FIT parser's fixed kernel partition, preserving existing identity
volumes such as `ri` and `bosa`. Optical PON integration remains separate.

To recover the reported non-booting installation, rebuild from the fixed
commit and install the new `factory.bin` through tcboot recovery. The recovery
operation must erase/reformat the UBI area so old EOF markers are removed;
an in-place kernel/rootfs volume update alone cannot remove markers elsewhere
in flash. Preserve or back up any device-specific `ri`/`bosa` volumes before
reinitializing UBI, and restore them if the recovery procedure removes them.
No bootloader replacement or full-flash erase is needed for this fix.

See the [boot-fix validation record](validation/tcboot-boot-fix-6.18.64.json)
for device-tree, packaging, shared metadata, signature and regression results.
The [earlier preflight record](validation/tcboot-remake-6.18.64.json) describes
the superseded recipe. Packaging checks use fixture kernel/rootfs payloads;
they do not constitute a complete Linux firmware build or a hardware boot test.
