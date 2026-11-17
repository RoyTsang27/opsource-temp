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
| Firmware device trees | Pass the legacy `graph_child_address` warning option only when the kernel device-tree compiler supports it. |
| Autoload | Replace literal `LINUX_6_18:module` strings with actual version filters. |
| Removed kernel subsystems | Hide obsolete AppleTalk, mISDN, IPoA, ATM-over-TCP and CryptoAPI FCRYPT/PCBC/Michael packages on 7.3. |
| Wireless backports | Remove 7.3 dependencies on the old Michael CryptoAPI module; the pinned backports contain the replacement implementation. |
| Wireless configuration | Recognize numeric kernel versions beyond 6.x when generating backport compatibility symbols. |
| Wireless MAC parsing | Include `linux/hex.h` explicitly for the downstream sysfs setter and MT7615 debug controls after the kernel stopped including it indirectly. |
| MediaTek WED integration | Match the pinned mt76 driver with the upstream mac80211 SCS/MSCS series and kernel flow-priority, flush and idle interfaces. Keep matching flow-layout assertions on both sides. |
| RTSP connection tracking | Use the kernel initializer for the protocol fields and inline expectation policy; retain allocated helper copies and unregister only successful registrations. |
| DAHDI PPP and NAPI | Use the PPP error callback without its removed error-code argument; include kernel NAPI declarations before defining the legacy compatibility alias. |
| LTTng tracing | Use detached-safe names where the kernel may clear the fence callback table after signaling; keep the original callback class at the protected call sites. Match the const packet-drop socket and Btrfs transaction-handle arguments. |
| RTPengine build flags | Preserve external module definitions through current Kbuild `ccflags-y`. |
| PF_RING sockets | Match the current variable-size socket-address type in the bind callback. |
| Kernel string copies | Replace removed `strncpy` calls in LTTng, Xtables addons (including kernel Lua), OpenAppFilter and Netatop. Preserve bounded-copy padding and truncation; use `memmove` for overlapping trim buffers. |
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
this audit for MediaTek ARM64/MIPS and Airoha ARM64/ARM32 and cross-compiles the local button, GPIO,
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
Filogic. The PCIe, USB and SDIO variants of MT76x0/MT76x2, MT7663, MT7921 and
MT7925 are compiled as well. It also builds both RTSP helper modules and the
DAHDI core with its optional PPP code enabled, using the pinned feed recipes
and patched sources.
It additionally compiles PF_RING's kernel module. Reviewing initialized kernel
callback tables found its bind signature mismatch; V4L2's changed callback
parameter names do not change their types.

The standalone test configuration enables the Netfilter, NAT, PPP, USB and MMC
dependencies normally selected by these packages, and checks that configuration
resolution retained them before compiling.

RTSP retains its named helpers for explicit firewall assignment; the kernel
initializer copies the expectation policy and sets the protocol and callbacks.
DAHDI also supports enabling PPP without its separate HDLC networking option: its
NAPI compatibility alias no longer rewrites declarations in a later include.

Direct-member review covered 2,046 referenced structure types, with 443 header
matches in 6.18 and 441 in 7.3. RTSP now guards the removed tuple and changed
expectation policy. LTTng already guards the inode layout changes; its DMA fence
probe needed the accessor update above. The compile workflow also builds LTTng
with kernel tracing and DMA-buffer support enabled, and checks its fence probe.

The trace prototype review compared 486 LTTng event interfaces against the
common kernel trace headers. It found the packet-drop and Btrfs transaction
changes. The compile configuration enables Btrfs and checks that its LTTng
probe is built, alongside the DMA-fence probe.

The string API review distinguishes module code from userspace libc callers.
LTTng's cleared syscall-event record uses `strscpy`; fixed-width and substring
copies use `memcpy_and_pad` with a bounded source length to retain their original
byte contents. The compile workflow builds all enabled Xtables addon extensions,
OpenAppFilter and Netatop, with Xtables and text-search dependencies enabled.
The old DAHDI Blackfin-only mmap drivers are outside the supported targets.

The feed compile checks also cover B.A.T.M.A.N. Advanced (including its optional
algorithm, bridge, multicast and trace code), CoovaChilli's module, Jool's three
modules, RTPengine, DMX USB, Quectel and Fibocom QMI, V4L2 loopback, MDIO netlink,
MTD write enablement and OpenVPN backports. Feed-local SIIT and OSLEC are built
too. Open vSwitch uses the in-tree datapath on 7.3; its old external datapath is
outside this matrix. These checks build module code, rather than every associated
userspace daemon or every possible package configuration.

The image warning-option change was tested with the actual DTC sources from
Linux 7.3.4 and the pinned 6.18.56. Both DTB and overlay generation work; the
legacy option remains enabled on the older compiler. All six repository device
trees also compile with the prepared 7.3 bindings and the new flags.


## Airoha Linux 7.3 port

The Airoha target now selects Linux 7.3.4 for AN7581, AN7583 and EN7523.
The target series contains 61 rebased patches. Backports already included in
7.3 are omitted; the native QDMA migration, BQL flushing and typed DMA mapping
implementations are retained. The AN7583 FE port ordering correction is carried
explicitly. The moved PCIe PHY source was compared with the native 7.3 source.

The port retains the custom clock/reset, USB/PCIe PHY, PCS line modes, NAND,
Ethernet PON control/data paths and PPE metadata needed by the integrated PON
packages. It preserves the compatible-gated ESMT NAND override and current
SPI-NAND declarations. Clock changes retain the native active-low PCIe reset
handling and EN751221 implementation while adding AN7583 support.

ARM64 uses scheduler-controlled lazy preemption and Cortex-A53 errata handling;
ARM32 uses voluntary preemption. Standard software GRO remains available. The
experimental downstream hardware GRO patch is omitted because it depended on
the superseded QDMA user-count and receive-buffer model. This avoids replacing
the native migration and buffer lifetime fixes.

Local verification applied all 61 patches with zero fuzz to the pinned generic
7.3.4 tree and compiled all 25 Airoha board device trees. The Linux compile
workflow now checks all three Airoha subtargets and builds the frontend and
XPON modules on AN7581 and AN7583. EN7523 remains a source-only target and gets
a kernel build rather than an installable firmware claim. The full Airoha
workflow additionally builds the OpenWrt toolchain, PON userspace and signed
AN7581 tcboot images. Successful hardware boot, optical registration and
line-rate forwarding require testing on the actual devices.
