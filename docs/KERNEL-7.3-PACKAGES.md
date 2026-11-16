# Linux 7.3 package compatibility audit

## Scope

The audit used the pinned Linux 7.3.4 archive, the prepared generic/Filogic and
generic/MT76x8 patch stacks, Linux 6.18.63 as a comparison, and the exact five
commits in `feeds.conf.release`. It inspected 380 source package Makefiles and
2,072 feed Makefiles (2,452 total), together with local sources and patches that
refer to kernel APIs. The 1,171 generic kernel package definitions were evaluated
with the real make macros and version filters: 1,000 definitions pass the source
reference audit for Filogic and 996 for MT76x8 after target restrictions.

Source reference checks establish that requested module Kconfig symbols and
source/Kbuild paths exist. They do not establish that every optional package
compiles or works. Full default device builds also exercise external wireless
packages, userspace dependencies, package installation and image generation.

## Corrections

| Area | Linux 7.3 correction |
| --- | --- |
| SHA3, BLAKE2b | Package the renamed CryptoAPI modules and their new library modules. |
| GHASH/GCM | Provide `libgf128hash` instead of the removed `ghash-generic` module. |
| RSA | Include the signature API module selected by RSA. |
| Random number generation | Filter obsolete DRBG variant choices on 7.3. |
| Crypto benchmark | Use the current `CRYPTO_BENCHMARK` option on 6.18 and newer. |
| PHY drivers | Update the MDIO bus filename; include Airoha's new shared library and Realtek's PHY package dependency. |
| Ethernet drivers | Include the PCI stmmac and Intel XDP helper modules; retain fixed-PHY and PTP dependencies. |
| RAID, polynomial, EEPROM, WMI | Follow their new source directories. |
| EEPROM configuration | Enable NVMEM sysfs, which now contains the EEPROM driver options. |
| Device-mapper encryption | Install the MD5 library now used directly by the LMK IV mode. |
| Cadence USB | Follow the combined `cdns` module; the old common module is absent on 7.3. |
| SMB and NFS | Include SMB compression and Kerberos crypto modules; update NFSv4 and removed configuration choices. |
| Firmware and optional graphics | Extend dependencies introduced in 6.18 to 7.3. |
| Autoload | Replace literal `LINUX_6_18:module` strings with actual version filters. |
| Removed kernel subsystems | Hide obsolete AppleTalk, mISDN, IPoA, ATM-over-TCP and CryptoAPI FCRYPT/PCBC/Michael packages on 7.3. |
| Wireless backports | Remove 7.3 dependencies on the old Michael CryptoAPI module; the pinned backports contain the replacement implementation. |
| Wireless configuration | Recognize numeric kernel versions beyond 6.x when generating backport compatibility symbols. |
| Wireless MAC parsing | Include `linux/hex.h` explicitly for the downstream sysfs setter and MT7615 debug controls after the kernel stopped including it indirectly. |
| MediaTek WED integration | Match the pinned mt76 driver with the upstream mac80211 SCS/MSCS series and kernel flow-priority, flush and idle interfaces. Keep matching flow-layout assertions on both sides. |
| RTSP connection tracking | Retain the helper copies allocated by the new registration API, unregister only successful registrations and let the kernel release them. |
| DAHDI PPP | Use the PPP error callback without its removed error-code argument on 7.3. |
| libbpf and bpftool | Add the aligned 128-bit integer types to their bundled headers for current ARM64 ptrace UAPI. |
| Old vendor Wi-Fi | Keep the already unsupported rtl8812au-ct driver restricted to its supported 6.12 selection. |
| Hasivo PSE | Restrict this driver to Realtek, which supplies its kernel patch. |

ReiserFS is restricted to 6.12 because it was already absent from the 6.18
comparison kernel. Version guards preserve the older supported module layouts.

## ATM and PPP

Linux 7.3 retains PVC ATM, including PPPoA and br2684 bridging, while the headers
for SVC signalling, CLIP, LANE, MPOA and ATM-over-TCP are gone. Building all
linux-atm 2.5.2 tools therefore fails on `linux/atmsvc.h`.

The package now detects the signalling header and builds libatm, br2684ctl and
PVC diagnostics without the removed tools. Its 7.3 configure check cannot fall
back to stale signalling headers in a compiler sysroot. Unsupported individual
tool packages are hidden; the aggregate debug package installs the supported
subset. PPP requests libatm only when its PPPoA plugin is selected.

## Pinned feeds

`scripts/feeds update` applies `config/feeds-patches/<feed>/*.patch` before
generating the feed index. Application is idempotent and checks the whole patch
before writing; a mismatched patch stops indexing instead of partially editing
the feed. Source pins remain unchanged.

The packages feed fixes cover:

- Open vSwitch: the old GRE/VXLAN/Geneve vport modules and Kconfig options are
  absent on 7.3. Keep their packages as dependency packages for the corresponding
  tunnel drivers; use the supported netdev tunnel interfaces. Restrict the old
  `libcrc32c` dependency to 6.12 and resolve version filters before autoload names.
- Libreswan: stop requiring the removed PCBC CryptoAPI module on 7.3.
- Netatalk: disable AppleTalk choices on 7.3 while retaining AFP over TCP. Let
  the optional AppleTalk setting select its module directly, retaining the
  package's runtime dependency without a circular parent configuration constraint.

## Verification

`scripts/kernel-package-audit.py` can be rerun against a prepared kernel tree.
It evaluates package make definitions, applies version filters, follows target
restrictions through kmod dependencies, and checks Kconfig/Kbuild references.
It also rejects unresolved autoload conditions. The Linux compile workflow runs
this audit for both architectures and cross-compiles the local button, GPIO,
relay, U-Boot NVRAM and applicable LED modules, plus the patched ATM library and
PVC tools against exported 7.3 headers.
It also compiles libbpf's and bpftool's bundled types with the exported BPF/ptrace headers,
including a check of the 128-bit integer size and alignment where supported.

Local tests cover actual package expansion on 6.12, 6.18 and 7.3, dependency
expressions, feed patch idempotency, and rejection without partial writes. The
existing source, kernel configuration, signing and build regression suite also
passes. Firmware build outcomes are tracked in the repository's Device Build
workflow. Optional packages beyond those built by CI and hardware boot still
require their own compilation and runtime testing.

The source review also fetched all 18 external-module archives referenced by
the pinned feeds, verified their declared hashes and applied their package
patches without fuzz. Alongside the two feed-local modules, their code was
checked for header and function removals since 6.18. The remaining trace event
reference to `page_is_file_lru` is guarded to kernels before 5.18. PF_RING's
unbuilt vendor driver trees and Open vSwitch's source datapath capped at 5.5
were excluded from the 7.3 module review. This remains a source audit of those
optional modules, not a successful compilation claim.

The signature review compares 1,330 called header functions in 6.18 with 1,318
in 7.3, including parameter types and argument counts. It found the RTSP helper
and DAHDI PPP changes above. OpenVPN backports already guard the UDP tunnel
socket-type change; parameter-name edits and compatible integer-to-boolean
changes need no source change.

The matching wireless integration comes from OpenWrt commit
`d068e4608f83361fb4a6ae8a8cc4b46d81219bbe`; its downloaded patch files were
checked against their official Git blob hashes. The MediaTek flow API patches
are carried on 6.18 as well as 7.3, since the same mt76 source is shared by both.
The explicit MAC-address parser include and existing mt76 safety patches remain.

The compile workflow additionally builds the pinned mac80211 backports and
MT7603/MT7615 drivers on both architectures, plus MT7915 and MT7996 with WED on
Filogic. It also builds both RTSP helper modules and the DAHDI core with its
optional PPP code enabled, using the pinned feed recipes and patched sources.
