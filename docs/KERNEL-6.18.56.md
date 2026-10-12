# Linux 6.18.56 update

Updated the 6.18 kernel version and source SHA256 to
`4633bbda2ab95eaf2a7af4041236451d6759c72e6946265531af4b3aacefbf89`.
The downloaded archive matches the [official checksum list](https://cdn.kernel.org/pub/linux/kernel/v6.x/sha256sums.asc).
The OpenWrt Airoha snapshot checked at commit
`1daf1410c575360bc4ec4896281f0140d528d34d` still selects 6.18.55; this update
follows the owner's explicit request for 6.18.56. The existing updater refuses
downgrades if OpenWrt temporarily trails the local version.

Linux 6.18.56 already includes Quectel EG060W USB serial support, so the duplicate
`782-v7.3-USB-serial-option-add-Quectel-EG060W.patch` is removed. The LoongArch vDSO
prefix-map patch is retained and refreshed around the new
`CONFIG_CC_OPT_INLINE_MEMSET` line. No downstream functionality is discarded.

All 609 active generic/Airoha patches apply to a fresh, checksum-verified source
tree. Prepared-source checks confirm the UART, MediaTek phylink/MAC operations,
Realtek entry, flowtable RCU teardown and Airoha shutdown invariants. BBRv3 remains
an inactive experiment; upstream BBR remains selected.

The signing fixes and audited built-in PON packages previously published on
`codex/signing-append-fix` are carried into `codex/security-audit`. Their existing
licenses, source pins, private runtime paths and default selections are retained.

Linux CI compiles both Airoha kernels and PON packages. The AN7581 job selects
the new single-device tcboot profile, builds complete factory and sysupgrade
images, validates the FIT/load address and UBI volume layout, and verifies the
sysupgrade signature. CI uses disposable build keys and does not publish a
production firmware release. Compilation and test results will be recorded when
CI finishes. Hardware boot, optical registration and physical upgrade/recovery
still require device testing.
