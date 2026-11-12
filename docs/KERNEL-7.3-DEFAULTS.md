# Linux 7.3 router defaults

Reviewed on 2026-11-12 for the six Device Build profiles. The goal is a
general-purpose Wi-Fi router with bounded memory and image size. These are
source defaults; throughput and latency still need measurement on the devices.

## Scope and inventory

The review covers the 6.19, 7.0, 7.1, 7.2 and 7.3 release feature groups and
compares the actual upstream Linux 6.18.63 and 7.3.4 Kconfig declarations.
[kernel-7.3-new-options.csv](kernel-7.3-new-options.csv) lists **all 849 added
symbols**, their source paths, types and prompts. The comparison excludes
`scripts/` and `tools/` test fixtures, deduplicates symbol names across
architectures, and includes architecture-specific drivers and kernel samples.
An empty prompt denotes an internal symbol or an unprompted default.

This is a configuration inventory, not a claim that every kernel change has a
switch. Fixes and implementation improvements arrive with the pinned kernel;
many new interfaces require applications to use them. Existing symbols can
also acquire new implementations, such as NTFS, without appearing in this list.

The input archive SHA-256 values are:

| Archive | SHA-256 |
| --- | --- |
| linux-6.18.63.tar.xz | `81764a545072d160748beff4d9de2e7d95aa9f16e8261110288f067a2cc61d71` |
| linux-7.3.4.tar.xz | `b11b6df8295e8e991ff040b71aaa4994a8b55caa23b6b092907f195b5840fd1f` |

Sources are the [official release archives](https://www.kernel.org/pub/linux/kernel/),
the upstream Kconfig files linked below, and kernel documentation. Release
indexes were used to locate the upstream changes; the pinned source determines
the actual configuration and runtime defaults.

## Selected defaults

| Area | Filogic / AX3000T / TR3000 | MT76x8 / TR1200 | Reason |
| --- | --- | --- | --- |
| Preemption | **Lazy**, explicitly selected | **Voluntary**, explicitly selected | Match the choices supported by Linux 7.3 on each architecture. |
| Cache-aware scheduling | **Enabled** | Unavailable without SMP | Follow the upstream SMP default; no scheduler daemon required. |
| Multi-generation LRU | Retain enabled | Retain enabled | Keep the memory-reclaim improvements supplied by the newer kernel. |
| Default queue discipline | Retain FQ-CoDel | Retain FQ-CoDel | General default without inventing WAN bandwidth or shaping parameters. |
| TCP congestion control | Retain CUBIC | Retain CUBIC | Applies to router TCP sockets; changing this does not change clients' forwarded TCP congestion control. |
| MediaTek Wi-Fi acceleration | Retain mt76 and WED support | Retain device-specific mt76 drivers | Existing device defaults already select the applicable driver and firmware. |
| Partitioned kmalloc caches | Explicitly disabled | Explicitly disabled | Avoid the additional cache copies and memory overhead in the default router image. |
| New MT7628 DSA driver | Disabled | Explicitly disabled | The TR1200 device tree and network setup still use the existing swconfig driver. A DSA conversion requires a separate board migration. |

Linux 7.3 limits `PREEMPT_NONE` to `ARCH_NO_PREEMPT`, and voluntary preemption
to architectures without lazy preemption. ARM64 selects
`ARCH_HAS_PREEMPT_LAZY`; MIPS does not select either of those architecture
flags. The previous build menu requested `PREEMPT_NONE` for both, so it could
disagree with the resolved kernel. The menu now selects lazy on ARM64 and
voluntary on MIPS, and migrates an old preset when `make defconfig` runs.
Explicit full-preemption selections remain possible. Linux 6.18 targets keep
their previous choices. See the upstream
[preemption definitions](https://github.com/torvalds/linux/blob/v7.3/kernel/Kconfig.preempt)
and [architecture definitions](https://github.com/torvalds/linux/tree/v7.3/arch).

`SCHED_CACHE` follows Linux's default on SMP systems. It tries to keep tasks
sharing a process within one last-level-cache domain. The MT7981 cores already
share a cache domain, so this selection does not imply a measured speedup on
these boards. See [the scheduler option](https://github.com/torvalds/linux/blob/v7.3/init/Kconfig).
MGLRU remains enabled as recommended by its
[upstream configuration instructions](https://docs.kernel.org/admin-guide/mm/multigen_lru.html).

The old, removed `RANDOM_KMALLOC_CACHES` entry is replaced with an explicit
`KMALLOC_PARTITION_CACHES=n`. Existing slab freelist hardening, randomization,
separate user-controlled buckets, fortified copies and hardened usercopy stay
enabled. The newer partitioning can create 16 cache copies, and its typed mode
requires Clang allocation tokens. See [the allocator choices](https://github.com/torvalds/linux/blob/v7.3/mm/Kconfig).

## Other feature decisions

| New or substantially extended feature family | Default decision |
| --- | --- |
| Accurate ECN | Keep the pinned 7.3.4 setting `tcp_ecn=2` and its fallback. Its local TCP code supports AccECN, but requesting it globally is a separate network policy. The exact source still initializes mode 2, irrespective of earlier release summaries. |
| BIG TCP for UDP tunnels, GRO/GSO improvements, network queue leasing | Inherit networking code improvements; keep normal MTU and queue sizes. No tunnel, oversized aggregation or leased queue is created by default. |
| Netfilter flowtables and MediaTek offload | Retain the existing firewall package and device policy. Kernel flowtable availability and firewall rule selection are separate settings. |
| BPF scheduler and cgroup sub-schedulers | Keep `SCHED_CLASS_EXT` unselected. These require an actual BPF scheduler and additional configuration; no such service is supplied by these profiles. |
| BPF-backed binfmt handlers, io_uring BPF, tracing and new BPF helpers | Do not add interpreters, BPF programs, profiling or BTF packages. Internal dependency symbols may still be selected by Kconfig. Existing applications can opt into the applicable interfaces. |
| io_uring filters, FUSE buffer pools and zero-copy | Keep the existing io_uring build policy. Do not install a FUSE server or filesystem module solely for these additions. |
| Swap-table and memory-reclaim improvements | Inherit the implementation where swap/reclaim is built. Preserve the small-flash target's swap policy; do not create swap on router flash. |
| userfaultfd working-set tracking, KSM, DAMON, huge pages and NUMA | Keep workload-specific parent features unselected. These profiles have no VM memory manager or tiered-memory service. Internal architecture capability symbols remain kernel-managed. |
| rseq slice extension | Leave its parent `RSEQ` unselected; enabling an application interface without a consumer provides no default routing benefit. |
| failfs, fchroot, nullfs, namespace/pidfd/openat extensions | Inherit available core APIs. Keep the existing application sandbox policy; do not change service filesystem roots automatically. |
| NTFS replacement, Btrfs/Ext4/XFS changes, new filesystem error reporting | Preserve SquashFS/overlay and device-specific writable flash support. Optional disk filesystems remain package choices. |
| SMB Time Machine, replay and encryption extensions | No SMB server is installed by these changes. Enable only with a configured storage/server use case. |
| Live Update Orchestrator, kexec handover and virtual-machine changes | Keep optional parent subsystems unselected; router sysupgrade remains the update mechanism. |
| LSM audit/logging changes, new crypto libraries and ML-DSA | Retain existing security and crypto package selections. Internal crypto dependencies resolve normally; no new LSM policy or certificate infrastructure is provisioned. |
| New Ethernet, PHY, DSA, Wi-Fi and other peripheral drivers | Select through the existing board and package definitions. Leave unrelated hardware opt-in; new upstream in-kernel mt76 drivers do not replace the separately pinned mt76 package. |
| GPU/VRAM, display, audio, x86 FRED, server accelerators, USB4 and other SoCs | No additional packages or drivers selected for these routers. |
| New KUnit, fault-injection, coverage, tracing and sample options | Keep production defaults and opt-in diagnostics. No test workload or sample driver is added to firmware. |

The [IP sysctl documentation](https://docs.kernel.org/networking/ip-sysctl.html)
describes ECN negotiation and fallback. The authoritative mode for this build
is `net/ipv4/tcp_ipv4.c` in the pinned archive. The
[flowtable documentation](https://docs.kernel.org/networking/nf_flowtable.html)
explains the firewall fast path; the
[sched_ext documentation](https://docs.kernel.org/7.3/scheduler/sched-ext.html)
explains the scheduler's userspace requirements. New filesystem sandbox
interfaces are described in the [failfs documentation](https://docs.kernel.org/filesystems/failfs.html).

## Validation and limits

The regression tests resolve the actual build-menu Kconfig using its native
`conf` program. They cover both architectures, old-preset migration, explicit
user overrides, and unchanged Linux 6.18 defaults. A separate local check used
Linux 7.3.4's own `conf` and actual preemption/scheduler Kconfig definitions,
with the merged generic/target settings and exported build-menu values. It
resolved lazy preemption plus `SCHED_CACHE=y` for Filogic and voluntary
preemption for MT76x8.

The local Python 3.12 suite completed with 97 passing tests and 15 skipped
platform/tool-dependent tests. Device Build source checks passed for all six
profiles.

These checks validate configuration selection. They are not a full firmware
compile or a hardware latency/throughput benchmark. After updating an existing
build tree, run `make defconfig` before rebuilding so the build-menu choice is
updated as well as the target kernel fragment.
