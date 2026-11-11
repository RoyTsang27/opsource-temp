# LLVM-BPF builds on hosts with limited RAM

LLVM's large C++ files need substantially more memory per worker than most
OpenWrt packages. On the reported Ryzen 9 7900 with 16 GB RAM, running 24 LLVM
workers exhausts memory. The recipe now chooses a smaller LLVM worker count
independently of the firmware's `make -j` setting. Prebuilt tools avoid this
source compilation entirely on a supported host.

If your Linux copy still has `LLVM_BPF_JOBS ?= 1`, use the portable
[LLVM-BPF speed update](../updates/llvm-bpf-speed/README.md). It installs the
automatic-worker recipe and both helpers without cleaning the build. The kit
also supports the original recipe without a dedicated LLVM worker limit.
Raising the firmware's `make -j` alone does not override an explicit LLVM limit.

## Use OpenWrt's prebuilt tools on Linux x86-64

The setup helper installs the official OpenWrt LLVM-BPF archive matching
`tools/llvm-bpf/Makefile`. These host tools compile eBPF objects; the firmware
source and Linux kernel version stay selected by the existing configuration.

From the existing build tree, after the failed build has exited:

```sh
python3 scripts/setup-llvm-bpf.py
make -j2 V=s
```

The helper requires Linux x86-64, Python with tarfile's safe data filter
(Python 3.12 or a patched Python 3.11), and `zstd`. It uses the staged OpenWrt
`zstd` when available. It does not need root access. It:

- Fetches the checksum list and matching archive from the official OpenWrt
  HTTPS download server, then verifies SHA256 before extracting it. Snapshot
  archives rotate; the checksum is obtained for the current snapshot rather
  than assuming a rolling filename always has the same content.
- Rejects unsafe archive paths and links, checks the recorded LLVM version,
  and verifies the required tools can run on the host.
- Exercises the clang, opt, llvm-dis, llc and llvm-strip pipeline and checks
  that its result is a BPF ELF object before selecting the toolchain.
- Installs the toolchain under `llvm-bpf-<version>.Linux-x86_64` and selects it
  through the buildroot's `llvm-bpf` link and supported Kconfig settings.
- Saves `.config.llvm-bpf.backup`, preserves device/package selections, and
  restores the original configuration and toolchain link if configuration
  resolution fails. Existing source-build objects are retained.

The helper refuses buildbot/all-host-tools configurations and existing
toolchains with different provenance rather than silently changing or removing
them. It fails without selecting a new configuration if the required archive
is unavailable or cannot pass its checks. Resume the normal firmware build
after setup; explicitly requesting `tools/llvm-bpf/compile` still requests a
source build even when prebuilt tools are selected.

## Continue building LLVM from source

`LLVM_BPF_JOBS=auto` is the default. `scripts/llvm-bpf-jobs.py` reads Linux
`MemAvailable` and the current process's cgroup v1/v2 memory limits, including
visible parent groups. It takes the smallest available headroom, reserves the
larger of 2 GiB or 25% of the effective memory capacity, and budgets 3 GiB per
worker. CPU affinity also caps the result. Swap is excluded. Unknown memory
availability and unsupported hosts fall back to one worker.

For example, 16 GiB total with 14 GiB available selects three workers; the same
machine with 10 GiB available selects two. This is a conservative estimate,
not a measured peak for every LLVM file. The count is sampled when the LLVM
recipe starts and does not throttle other packages or react to later changes
in memory pressure. An individual compiler or linker can still exceed its
budget. On a busy host, use two workers or choose the prebuilt tools.

The recipe passes the selected count as an explicit Ninja `-jN`, including
when a parent `make -j24` supplies a jobserver. Linking remains limited to one
job with `LLVM_PARALLEL_LINK_JOBS=1`. Compilation and installation both use the
Ninja limit. The compile log prints the selected worker count. Numeric overrides
must be positive; zero is rejected because Ninja interprets it as unlimited.

Inspect the automatic selection on the build host:

```sh
python3 scripts/llvm-bpf-jobs.py --explain
```

Resume the LLVM source build on its own to avoid competing with other packages:

```sh
make tools/llvm-bpf/compile V=s
```

Or choose a fixed, smaller count:

```sh
make tools/llvm-bpf/compile LLVM_BPF_JOBS=2 V=s
```

No clean step is needed to change the job count. Ninja retains completed object
files. After LLVM finishes, resume the firmware build with the usual `make`
command. The LLVM limit does not guarantee that 24 concurrent jobs are suitable
for every other package on a 16 GB host.

LLVM's own [CMake options](https://github.com/llvm/llvm-project/blob/llvmorg-22.1.3/llvm/cmake/modules/HandleLLVMOptions.cmake)
provide the serial link pool. An explicit job count also avoids depending on
the Ninja version or the parent's jobserver protocol; see the
[Ninja manual](https://ninja-build.org/manual.html#ref_jobserver).

## Memory-policy preflight on 2026-10-25

All 27 LLVM tests passed. A real Ninja 1.13.2 workload, invoked through the
actual recipe under `make -j24`, peaked at three workers for simulated Linux
16 GiB / 14 GiB available memory, and at one or two for the explicit overrides.
Tests also cover busy hosts, cgroup v1/v2 parent limits and missing memory data.
The full Python suite passed 92 tests with 11 platform/tool-dependent skips,
and source checks passed for all 31 device profiles.

The official 22.1.3 archive returned HTTP 200 and a matching entry in OpenWrt's
current checksum manifest. This availability check did not download the archive
or run its Linux binaries. The current manifest observation and test details
are recorded in `docs/validation/llvm-bpf-preflight.json`. A full LLVM source
compilation and firmware build on the reported Ryzen machine remain unverified.

## Historical preflight on 2026-10-17

- Built Ninja 1.13.2 on Apple Silicon and ran the actual LLVM recipe with a
  parallel test workload and an unusable parent jobserver. The default peak
  was one worker; `LLVM_BPF_JOBS=2` allowed two workers.
- Built OpenWrt's configuration parser and verified the actual toolchain
  Kconfig selects prebuilt LLVM and disables LLVM source compilation with
  developer options both enabled and disabled.
- Downloaded and SHA256-verified the official 22.1.3 archive (53,056,544 bytes),
  safely extracted it, and checked its version marker and required Linux
  x86-64 ELF tools. The observed archive checksum is recorded in
  `docs/validation/llvm-bpf-preflight.json`.
- Passed 55 tests, including 14 new LLVM setup/concurrency tests, and source
  checks for Linux 6.18.57 and all six device profiles. Five signing integration
  tests were skipped because their native tool directory was unavailable.

The Linux executables cannot run natively on this macOS host. Their BPF smoke
test runs on the owner's Linux host as a mandatory setup check before changing
the active configuration. A complete firmware build remains unverified here.
