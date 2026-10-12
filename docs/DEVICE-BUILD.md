# Device Build source provenance and validation

## Imported snapshot

| Item | Source |
| --- | --- |
| Project | Device Build (`RoyTsang27/Device-Build`) |
| Reference | `https://github.com/RoyTsang27/ponwrt-test-build` |
| Branch | `codex/security-audit` |
| Commit | `a80feaf1764000fa9ebd1f49ce27fcc6c0b5cb09` |
| Import date | 2026-10-13, Asia/Shanghai |
| Kernel | Linux 6.18.56 |
| Archive SHA256 | `4633bbda2ab95eaf2a7af4041236451d6759c72e6946265531af4b3aacefbf89` |

The complete tracked source snapshot is imported into an independent source
repository. Upstream history is available at the recorded reference commit;
copyright notices, licenses, source pins, and the original PonWrt README are
retained. `config/device-build.json` records the base and all device selectors.

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
Existing distribution branding stays ImmortalWrt; Device Build is the project.

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
