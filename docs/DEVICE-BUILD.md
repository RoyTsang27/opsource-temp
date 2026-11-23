# Device Build source provenance and validation

## Linux 7.3 branch

The public repository is
[RoyTsang27/opsource-temp](https://github.com/RoyTsang27/opsource-temp),
with `test-flight` as its default branch.

Interactive configuration prepares the complete standard feed catalog. See
[the menuconfig guide](MENUCONFIG.md) for Utilities, LuCI, networking and other
package choices, and for preserving custom feeds in existing checkouts.

The experimental `test-flight` branch pins `mediatek/filogic` and
`ramips/mt76x8` and Airoha AN7581/AN7583/EN7523 to Linux 7.3.5. The generic 7.3 configuration and patch stack
come from [the OpenWrt development
branch](https://github.com/graysky2/openwrt/tree/30c0d891b6103695e614de575814a67016973cf7).
The target-specific stacks were rebased from the original 6.18.56 source.
The 7.3.4 update removes the carried SPI QPIC ECC-context and MT7986 timer
frequency fixes because both are included in the upstream kernel.
The 7.3.5 update also removes the carried Macronix MX25L12805D fallback
parameter fix, which is now included upstream.
The OpenWrt MTD concatenation option has its own Kconfig symbol to distinguish
the existing device-tree binding from Linux 7.3's concatenation support.

The fork's bridge-family nftables flow offload extension (patches 675-01
through 675-14) requires a separate port to Linux 7.3's forwarding-path API.
This branch uses the 7.3 stack's standard flow offload.

The default mt76 package is pinned to upstream revision
`0936617dc529ff9da0385221d3fa6de732231177` from 2026-10-28.
Its source archive SHA256 is
`3a3844097e66021f21f0ec8508cb740ef6536a2243f74c47fd5a898edb26839f`.

Local checks verified the kernel archive checksum, applied both patch stacks
to their referenced files, compiled all six device trees, and confirmed the
kernel selection through OpenWrt target metadata. The three default device
firmwares completed compilation and image checks on 7.3.4. Each workflow run
records its exact source revision and kernel version; use the corresponding
7.3.5 build results when selecting current artifacts. Device boot and upgrade
tests require the actual hardware.

## Imported snapshot

| Item | Source |
| --- | --- |
| Project | Device Build (`tdsafgen1888asd/Device-Build`) |
| Reference | `https://github.com/RoyTsang27/ponwrt-test-build` |
| Branch | `codex/security-audit` |
| Commit | `a80feaf1764000fa9ebd1f49ce27fcc6c0b5cb09` |
| Import date | 2026-10-13, Asia/Shanghai |
| Kernel | Linux 6.18.56 |
| Archive SHA256 | `4633bbda2ab95eaf2a7af4041236451d6759c72e6946265531af4b3aacefbf89` |

The complete tracked source snapshot is imported into an independent source
repository. Upstream history is available at the recorded reference commit;
copyright notices, licenses and source pins are retained. The root README
contains only the repository name as requested. `config/device-build.json` records the base and all device selectors.

The `master` snapshot inspected was
`a57faf93c6c3638ba3651690228aabaa51d3f235` (Linux 6.18.52). The requested 6.18.56
bump and subsequent fixes live on `codex/security-audit`, which is the imported
base. The import includes that branch's refreshed generic patches, signed-image
error handling, built-in PON packages, and security fixes. Its historical audit
reports describe checks on the reference and should be read in that context.

## Device integration

The reference already contains DTS files, image recipes, networking/upgrade
handlers, calibration/MAC mappings, and wireless drivers for the six listed
profiles. Device Build exposes them through small one-device presets and a
manifest-driven selector. Stock and modified U-Boot layouts stay separate.

Default CI runs AX3000T stock, TR3000 v1 stock, and TR1200 v1 in independent
Ubuntu 24.04 jobs. Optional variants are available through manual dispatch.
The helper checks source profiles/DTS/network entries and, after Linux
`make defconfig`, verifies the selected device, wireless packages, LuCI variant,
and configuration isolation. Firmware upload requires a matching target/profile,
Linux version, sysupgrade image, file sizes, and SHA256 hashes.

Feeds use the reference's `feeds.conf.release` pins. PON driver/userspace
packages are already vendored under `package/pon`; no extra PON feed is needed.
Firmware distribution and filename defaults use `opsource-temp`. Upstream
copyright notices and package source references are retained.

Explicit Airoha optical-device choices, including `XG-040G-MD(Pon)`, are
documented in [Airoha PON profiles](AIROHA-PON-PROFILES.md). They inherit their
board's drivers and flash layout and select the complete PON application stack.

## AX3000T WED boot and startup defaults

The 2026-11-22 TTL log reached OpenWrt userspace, then repeatedly panicked in
`regmap_write → wo_w32 → mtk_wed_mcu_init` while loading `mt7915e`. Its register
dump contained `ERR_PTR(-ENODEV)` as the regmap argument. The MT7981 device tree
retains a legacy `wo-boot` reserved-memory region, while the carried WED patch
also supports the newer `mediatek,wo-cpuboot` syscon reference.

Patch `947-net-ethernet-mtk_wed-fix-legacy-cpuboot-fallback.patch` uses the
optional syscon lookup: an absent reference selects the legacy mapped region,
and actual lookup errors return before firmware loading or boot-register
access. A valid syscon skips the legacy region.

Seven native regression cases compile the actual prepared kernel's firmware
loader, register-access helpers and optional syscon lookup against simulated
hardware. They cover both mappings, deferred/invalid lookup, missing legacy
region, missing firmware and firmware-load failure. The legacy case fails on
the unpatched source and passes with the correction. MediaTek device CI runs
these checks after kernel preparation. To run them separately:

```sh
WED_TEST_KERNEL=build_dir/target-aarch64_cortex-a53_musl/linux-mediatek_filogic/linux-7.3.5 \
  python3 -m unittest discover -s tests -p test_wed_boot.py -v
```

The WED patches apply to Linux 7.3.5 without fuzz. These checks do not perform
a firmware build or a physical boot test. Rebuild the AX3000T firmware from
the corrected source; already generated images do not contain this fix.

The 2026-11-23 follow-up log passes that initialization, starts both AP
interfaces and reports a WA firmware transmit failure. It ends at 22.55 seconds
with the LAN link up, without a reset or kernel panic. To bypass the suspect
offload path during startup, `PACKAGE_MT7915_WED` defaults off for both AX3000T
layouts, including multiple-device selections. Other Filogic and MT7622
profiles keep their existing default. The option can be enabled explicitly in
menuconfig. The mt76 package release and configuration dependencies ensure
that changing this option regenerates the module loader parameters.

This is a targeted stability mitigation; the follow-up capture does not
establish the actual reset cause. See [AX3000T startup troubleshooting](AX3000T-BOOT.md)
for the matching U-Boot-layout profile, an existing-device workaround and
the evidence needed if rebooting continues.

## Corrections required for TR1200

1. Removed
   `target/linux/ramips/patches-6.18/102-01-pwm-mediatek-set-mt7628-pwm45_fixup-flag-to-false.patch`.
   Linux 6.18.56 already sets `mt7628_pwm_data.pwm45_fixup = false`; reapplying
   the patch fails kernel preparation. The separate clock-source fix (`102-02`)
   still applies and is retained.
2. Corrected `partition@fe0000` in
   `target/linux/ramips/dts/mt7628an_cudy_tr1200-v1.dts` from `0xfe000` to
   `0xfe0000`, matching its unit address and end-of-flash backup partition.
   The former address was inside the firmware partition. Factory calibration,
   bdinfo, and bootloader partitions retain their original locations/flags.

## Checks performed on 2026-10-13

- Downloaded the official 154,807,564-byte `linux-6.18.56.tar.xz` and verified
  its SHA256 against the published kernel.org checksum.
- Applied all 587 active generic + MediaTek patches to kernel source extracted
  from that archive, with target file overlays, in build-system order.
- Applied all 494 active generic + Ralink patches after removing the redundant
  PWM patch. No patch application failed and no `.rej` files remained.
- Source checks passed for all six profiles; device-selection/image-validation
  regression tests passed (10 tests).
- Inherited archive/download/signing/kernel-update regression tests passed
  (44 tests).
- `actionlint` passed for all repository workflows.

Patch checks use original contents of every patch-referenced kernel file and
the target overlays. They verify applicability, without compiling a kernel or
firmware. The local host is macOS with GNU make 3.81, so compilation is delegated
to the Linux workflow. Linux `make defconfig`, full firmware compilation
(including TR1200's size limit), and physical Wi-Fi/USB/boot/sysupgrade remain
to be confirmed. Source checks alone do not establish hardware readiness.

To change the pinned kernel, update the manifest/checker together with the
generic version/hash file, refresh both target patch stacks, and rerun all
device builds. The inherited manual kernel updater proposes Airoha changes;
Device Build rejects a changed kernel until its version/checksum and device
validation have also been updated.
