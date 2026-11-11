# LLVM-BPF builds on hosts with limited RAM

The reported LLVM 22.1.3 build stopped after Clang Sema compilations. The pasted
tail contains `#include_next` warnings and Ninja's final failure, but no failed
command or fatal diagnostic. The warnings are not fatal with the shown flags.
Reported high memory use and the large amount of system CPU time suggest memory
pressure; an out-of-memory kill has not been confirmed.

## Use OpenWrt's prebuilt tools on Linux x86-64

The setup helper installs the official OpenWrt LLVM-BPF archive matching
`tools/llvm-bpf/Makefile`. These host tools compile eBPF objects; the firmware
source and Linux kernel version stay selected by the existing configuration.

From the existing build tree, after the failed build has exited:

```sh
git pull --ff-only
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

`tools/llvm-bpf/Makefile` now passes an explicit `-j1` to Ninja, limiting LLVM
compilation and installation independently of the parent make jobserver.
This prevents an unusable jobserver from causing Ninja to use every CPU.
It also bounds LLVM resource use during a normal parallel firmware build.
One large compilation can still require substantial RAM.

On hosts with sufficient RAM, the owner can explicitly increase the limit:

```sh
make tools/llvm-bpf/compile LLVM_BPF_JOBS=2 V=s
```

## Local preflight on 2026-10-17

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
The change uses `[skip ci]` to keep cloud builds stopped as requested.
