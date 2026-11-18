# Nokia tcboot remake, 2026-11-18

The previous custom tcboot partition include and shared image definition have
been replaced using the project requested by the owner:
[OpenWrt-for-XG-040G-MD](https://github.com/xiangtailiang/OpenWrt-for-XG-040G-MD/tree/e5320831b9d7f77315e6bd141cb2931c5cb27092).
Its main build workflow selects `nokia_xg-040g-md-tcboot` from
[`xiangtailiang/openwrt`](https://github.com/xiangtailiang/openwrt/tree/fb42bd65924c99c1c0e1f95fe0b3a285656814a7).
The older `patch/` directory in the wrapper project is not used by that main
workflow. The remake follows the active source's DTS, image layout and early
environment MAC setup. No extra feeds or unrelated packages were imported.

The MD tcboot DTS is identical to the pinned reference. It explicitly boots
`ubi0:rootfs`, protects the first 512 KiB bootloader partition, exposes the
following 512 KiB environment, and allocates the remaining 255 MiB to UBI.
The factory image uses a FIT kernel at load/entry address `0x80088000`, padded
to 8 MiB, followed by UBI with 128 KiB eraseblocks and 2 KiB pages/subpages.
The source retains image size checks and firmware signing.

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

Use `factory.bin` with the matching installed tcboot Web recovery, and
`sysupgrade.bin` for subsequent upgrades of the same tcboot profile. The
upgrade path requires an existing UBI device with `kernel` and `rootfs`
volumes. It rejects another board's archive, a raw FIT, a factory image and
missing firmware volumes before writing. Upgrades target UBI volumes rather
than the FIT parser's fixed kernel partition, preserving existing identity
volumes such as `ri` and `bosa`. Optical PON integration remains separate.

See the [local preflight record](validation/tcboot-remake-6.18.64.json) for
device-tree, packaging and regression results. Packaging checks use fixture
kernel/rootfs payloads; they do not constitute a complete Linux firmware
build or a hardware boot test.
