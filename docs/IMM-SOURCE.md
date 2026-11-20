# op-source: ImmortalWrt source (`imm`)

This branch is an independent root snapshot of official
[ImmortalWrt master at `6003f6b8c3278a27712f4fdaaa8d1e5faa2b1f54`](https://github.com/immortalwrt/immortalwrt/tree/6003f6b8c3278a27712f4fdaaa8d1e5faa2b1f54),
created on 2026-11-20. It retains ImmortalWrt's distribution defaults,
package sources, feeds, device definitions and license notices. Its source
history is separate from the OpenWrt-based
[`op-source` reference](https://github.com/tdsafgen1888asd/op-source/tree/main).
The destination repository is [`RoyTsang27/op-source`](https://github.com/RoyTsang27/op-source).

## Linux 6.18.60 to 6.18.64

The generic kernel selector now uses Linux **6.18.64** and the SHA256 of
the official `linux-6.18.64.tar.xz` archive:

```text
020d45510c539972e6f14c5c71566878d3b7ef56fb082b3e09134f2ebaade562
```

The archive matches the
[kernel.org checksum list](https://cdn.kernel.org/pub/linux/kernel/v6.x/sha256sums.asc).
The release changes are in the
[official changelog](https://cdn.kernel.org/pub/linux/kernel/v6.x/ChangeLog-6.18.64).

Twelve backports are removed because their implementations are present in
the stable kernel: Airoha cpufreq error handling, BCM2712 HDMI PHY disable,
Macronix fallback flash parameters, Qualcomm SPI NAND ECC context lifetime,
ksmbd TCP keepalive, MediaTek WED reserved buffers, the HORACO SFP quirk,
xHCI root-port recovery, the MT7986 timer frequency, two Atmel QSPI
initialization prerequisites and the IPQ5018 critical clock flag.

Refresh the Raspberry Pi HID, HDMI, camera, framebuffer and DMA patches
around stable changes. Preserve the new Rockchip OTP read mutex and its
unlock path when applying the word-size backport. Preserve the MediaTek
Lynxi PCS register-read error checks when moving its get-state function.
Adapt StarFive's PMU identification patch to the stable probe lifecycle,
using managed sysfs cleanup and the existing unregister error path.

Linux 6.18.61 reverted the `sockaddr_unsized` backport present in
6.18.57 through 6.18.60. Update mac80211's compatibility guard to provide
the type again for 6.18.61 through 6.18.x and increase its package release
to 16. The backports source version and checksum remain those selected
by ImmortalWrt.

## Build

Use a supported Linux build host with a case-sensitive filesystem and
the dependencies listed in the upstream README.

```sh
git clone --branch imm --single-branch https://github.com/RoyTsang27/op-source.git op-source-imm
cd op-source-imm
./scripts/feeds update -a
./scripts/feeds install -a
make menuconfig
make download -j8
make -j2 V=s
```

For an existing build directory on this branch, retain its configuration
and rebuild the kernel and wireless modules together after pulling an
update:

```sh
make defconfig
make target/linux/clean
make package/kernel/mac80211/clean
make package/kernel/mt76/clean
make target/linux/prepare -j1 V=s
make -j2 V=s
```

## Validation

See [the validation record](validation/imm-kernel-6.18.64.json) for the
verified archive hash, per-platform kernel patch results and wireless
checks. Patches are applied in build-system order after generic and
platform file overlays, using GNU patch with zero fuzz. Validation uses
the original archive contents for every file referenced by the patches.

Local checks establish patch compatibility and focused compiler behavior.
Full firmware compilation and hardware boot have not been verified on
the macOS host.
