# Linux 6.18.59 CVE fixes

Checked on 2026-10-28. Linux 6.18.59 was released on 2026-10-26.
The Linux security team's published database maps seven CVE fixes to this
release. Every listed stable fix commit also appears in the
[official 6.18.59 changelog](https://www.kernel.org/pub/linux/kernel/v6.x/ChangeLog-6.18.59).
This is a dated list of assigned CVEs, not a claim that every security-related
change already has an assigned CVE.

## Issues affecting earlier released 6.18 kernels

| CVE | Fix | 6.18 branch detail |
| --- | --- | --- |
| [CVE-2026-99077](https://www.cve.org/CVERecord?id=CVE-2026-99077) | IPv4 UDP exception-cache side channel could reveal a connected socket's ephemeral source port, weakening DNS cache-poisoning resistance. | [ecd7ead4bf05](https://git.kernel.org/stable/c/ecd7ead4bf05e221e90f18a29aec570a50fd1592); introduced in 3.6. |
| [CVE-2026-99100](https://www.cve.org/CVERecord?id=CVE-2026-99100) | p54 Wi-Fi firmware records lacked length and RX-range validation, allowing reads beyond malformed records. | [f641066b0ddc](https://git.kernel.org/stable/c/f641066b0ddcd1b0cf007c0d04f9c966f6e888ae); fixed in 6.18.59. |
| [CVE-2026-98166](https://www.cve.org/CVERecord?id=CVE-2026-98166) | DRM/TTM swapout left stale bulk-move pointers, causing use-after-free and crashes. | [b48ebe399b4e](https://git.kernel.org/stable/c/b48ebe399b4e72baa323462580fdd83ebda561e1); affects 6.18.57–6.18.58. |
| [CVE-2026-31775](https://www.cve.org/CVERecord?id=CVE-2026-31775) | Creative X-Fi audio initialization enumerated an unsupported SPDIF entry, causing a kernel crash. | [7fca3600e79e](https://git.kernel.org/stable/c/7fca3600e79e9f8bac1ebc10af9ff20a35d6cccb); affects 6.18.57–6.18.58. |

## Paired backports in this release

For these three records the security database identifies both the introducing
commit and its fix in 6.18.59. They are included security fixes, but do not show
that the corresponding defect affected the released 6.18.58 kernel.

| CVE | Fix | Stable fix commit |
| --- | --- | --- |
| [CVE-2025-71312](https://www.cve.org/CVERecord?id=CVE-2025-71312) | NTFS3 mount-option memory leak. | [d977b979081e](https://git.kernel.org/stable/c/d977b979081ef2585a15453f309a6311c95ede02) |
| [CVE-2026-23353](https://www.cve.org/CVERecord?id=CVE-2026-23353) | Intel ice Ethernet offline loopback self-test NULL-pointer crash. | [a4c584ea79d9](https://git.kernel.org/stable/c/a4c584ea79d958ea1cadc9ce056f6df58a363342) |
| [CVE-2026-72453](https://www.cve.org/CVERecord?id=CVE-2026-72453) | regcache initialization overwrote an error code, permitting later NULL-pointer dereferences. | [bae057687f61](https://git.kernel.org/stable/c/bae057687f61580dd897411cd749da22a7740647) |

## Relevance to op-source

The IPv4/UDP fix is relevant to router networking. The other defects depend on
the drivers and filesystems selected in a particular firmware configuration.
The published MediaTek/Ralink presets do not use Creative X-Fi, Intel ice or
DRM/TTM graphics.

OpenWrt builds wireless drivers from backports 7.2 instead of the kernel's
in-tree wireless source. Updating the kernel alone does not update that copy
of p54. This update therefore includes the same upstream p54 validation change
in `package/kernel/mac80211/patches/subsys/380-p54-validate-firmware-record-lengths.patch`
and raises the mac80211 package release to 7. The migration kit includes it.

The comparison scanned all 18,048 published `.dyad` records from the
[Linux security team's repository mirror](https://kernel.googlesource.com/pub/scm/linux/security/vulns/)
and checked the matched commits against the release changelog. Machine-readable
provenance is recorded in `docs/validation/kernel-6.18.59-cves.json`.
