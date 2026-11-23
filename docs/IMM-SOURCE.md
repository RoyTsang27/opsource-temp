# op-source: ImmortalWrt source (`imm`)

This branch is an independent root snapshot of official
[ImmortalWrt master at `6003f6b8c3278a27712f4fdaaa8d1e5faa2b1f54`](https://github.com/immortalwrt/immortalwrt/tree/6003f6b8c3278a27712f4fdaaa8d1e5faa2b1f54),
created on 2026-11-20. It retains ImmortalWrt's distribution defaults,
package sources, feeds, device definitions and license notices. Its source
history is separate from the OpenWrt-based
[`op-source` reference](https://github.com/tdsafgen1888asd/op-source/tree/main).
The destination repository is [`RoyTsang27/op-source`](https://github.com/RoyTsang27/op-source).

## Linux 6.18.65 update, 2026-11-24

The current kernel is **Linux 6.18.65**. The generic kernel selector uses
the official `linux-6.18.65.tar.xz` archive SHA256 from the
[kernel.org checksum list](https://cdn.kernel.org/pub/linux/kernel/v6.x/sha256sums.asc):

```text
c92606f956f09dc50b5a0e2af9e86763fce27ada1647de97f8d1ac8cfc95801d
```

The [official changelog](https://cdn.kernel.org/pub/linux/kernel/v6.x/ChangeLog-6.18.65)
records the release on 2026-11-23. Remove 23 obsolete carried patches:
two ksmbd listener fixes, VLAN-ID masking in flowtable keys, ST1202
hardware blinking, the Armada 38x errata selection, the Rockchip PCIe
RX-termination workaround, 15 Rockchip USB/DisplayPort PHY fixes,
the Gemini TVE200 interrupt-trigger fix and the earlier module metadata
extraction workaround. The fixes and updated module metadata handling are supplied
by the stable kernel.

Rebase the retained Rockchip USB/DisplayPort PHY cleanup patches around
the stable reinitialization flag rename, USB3 port delay and USB/DP
mode handling. Preserve the downstream clock-preserving reinitialization,
orientation handling and lane-mapping helpers.

Update the BPDU-filter patch to use its own bridge enum flag at bit 25.
The stable kernel now uses bit 24 for gratuitous-neighbour forwarding;
the two controls must remain independent. Port atomic bridge flag reads
to the carried patch as well.

Refresh EcoNet, i.MX, Raspberry Pi and StarFive patch contexts. Retain the
stable kernel's clock reference cleanup, disabled display defaults,
VC4 component cleanup, bounded DMA descriptor dumps and length-minus-one
DMA burst encoding. Broadcom Ethernet coalescing defaults use the
driver's per-ring fields, preserving user-selected ethtool settings
when rings are reinitialized.

Local kernel preparation uses the verified Linux 6.18.64 archive and
kernel.org's checksum-verified
[6.18.64-to-6.18.65 incremental patch](https://cdn.kernel.org/pub/linux/kernel/v6.x/incr/patch-6.18.64-65.xz).
The complete 6.18.65 archive has not been downloaded for these local
checks. The normal build downloads it using the published archive hash
above. Detailed checks are in the
[6.18.65 validation record](validation/imm-kernel-6.18.65.json).

All 46 kernel patch stacks (generic plus the 45 targets selecting Linux
6.18) and all 324 mac80211 patches apply with zero fuzz and no rejects.
This includes the four targets without a separate platform patch directory.
Focused compiler checks cover wireless socket compatibility, forwarding
interfaces, independent bridge flags, Rockchip OTP error cleanup and
Rockchip USB/DisplayPort reset pairing and power-state failures.

## Linux 6.18.60 to 6.18.64

The initial branch selected Linux **6.18.64** and the SHA256 of
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

See [the current validation record](validation/imm-kernel-6.18.65.json) for the
kernel-source checksums, per-platform kernel patch results and wireless
checks. The [initial 6.18.64 record](validation/imm-kernel-6.18.64.json)
records the branch's creation. Patches are applied in build-system order
after generic and platform file overlays, using GNU patch with zero fuzz.
Validation uses native kernel contents for every file referenced by a patch.

Local checks establish patch compatibility and focused compiler behavior.
Full firmware compilation and hardware boot have not been verified on
the macOS host.
