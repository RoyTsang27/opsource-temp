# Nokia XG-040G-MD with tcboot

Profile: `nokia_xg-040g-md-tcboot`, AN7581. This profile is selected in the supplied
AN7581 multi-device configuration and has a separate minimal configuration in
`configs/an7581-tcboot.config`.

The boot layout and kernel load address follow the existing
[tcboot source](https://github.com/xiangtailiang/openwrt/blob/67d579ed20011b2c601e75bdd9fa86f7b619fc69/target/linux/airoha/dts/an7581-nokia_xg-040g-md-tcboot.dts)
and [image definition](https://github.com/xiangtailiang/openwrt/blob/67d579ed20011b2c601e75bdd9fa86f7b619fc69/target/linux/airoha/image/an7581.mk).
The reference is adapted to PonWrt's existing LAN names, PON driver and calibration
bindings. The separately maintained
[tcboot bootstrap](https://github.com/Ljzd-PRO/xg040g-openwrt-switch/blob/22bd32ab0cb417138763174f3840a67584ff63cf/patches/openwrt/0001-airoha-add-xg040g-tcboot-switch-bootstrap.patch)
corroborates the layout.

| Partition | Offset | Size |
| --- | --- | --- |
| bootloader, read-only in Linux | 0 | 512 KiB |
| env | 512 KiB | 512 KiB |
| ubi | 1 MiB | 255 MiB |

The FIT kernel loads at `0x80088000`. The factory file reserves an 8 MiB kernel
prefix followed by UBI. Kernel and rootfs retain volume IDs 0 and 1. Static
`bosa` and `ri` volumes are reserved after rootfs/rootfs_data, initially containing
256 KiB of erased bytes each, so first-boot rootfs_data expansion cannot consume
their space. Restore the device's own stock backups in LuCI PON board-data
configuration before using PON, then reboot to reload calibration and identity.
The device tree retains BOSA calibration at offset 2, PON serial at RI offset
0x1a and base MAC at RI offset 0x3e.

Build on a supported Linux OpenWrt build host:

```sh
cp feeds.conf.release feeds.conf
./scripts/feeds update -a
./scripts/feeds install -a
./scripts/kconfig.pl + configs/an7581-tcboot.config configs/release.config > .config
make defconfig
python3 scripts/check-release.py --config .config
make -j12
```

Outputs under `bin/targets/airoha/an7581/`:

- `*-nokia_xg-040g-md-tcboot-squashfs-factory.bin`: factory payload for an
  already-installed compatible tcboot recovery interface.
- `*-nokia_xg-040g-md-tcboot-squashfs-sysupgrade.bin`: signed upgrade tar for
  this exact tcboot profile.

The profile does not bundle, install or rewrite a bootloader. It does not alias
the separate Nokia UBI/FIP profile in image compatibility metadata. Sysupgrade
accepts its own tar layout, uses the UBI kernel volume, and refuses to proceed
if UBI or the personal-data volumes are missing. The standard NAND tar upgrader
replaces kernel/rootfs/rootfs_data while preserving the other volumes; the raw
bootloader and environment partitions are outside that operation. PON, LAN,
USB and LEDs inherit the existing MD board support.

The missing-volume guard checks the name returned by OpenWrt's UBI lookup,
because an unsuccessful search can still return status zero. This also fixes
the existing AN7581 and AN7583 UBI profiles. Regression tests reproduce that
helper behavior and verify that missing required volumes stop the upgrade before
any flash writes.
The tcboot device tree compiles with all PON references resolved and adds no
compiler warnings relative to the existing MD UBI profile.

Use production signing keys for production builds. CI-generated keys are test
keys. Source and image checks do not establish bootloader compatibility with
every tcboot variant or replace hardware validation.
