# LLVM-BPF build parallelism

LLVM-BPF source builds now use **16 Ninja workers** by default. The build owner
reports that 16 workers succeed on the 24-thread Linux host, while using all
24 fails. The previous single-worker default serialized compilation even when
the surrounding firmware build used `make -j24`.

The limit is specific to LLVM-BPF and applies to compilation and installation.
LLVM's separate link pool remains limited to one job.

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

`tools/llvm-bpf/Makefile` passes an explicit `-j16` to Ninja. This overrides the
buildroot's serial fallback and is independent of the parent make jobserver,
so `make -j24` still limits LLVM to 16 concurrent commands. The build log prints
the selected worker count. Compilation can use up to 16 workers when enough
independent files are ready; linking remains serial with
`LLVM_PARALLEL_LINK_JOBS=1`.

Stop any running build, pull the updated `main`, then resume without cleaning:

```sh
git pull --ff-only origin main
make tools/llvm-bpf/compile V=s
make -j24 V=s
```

Completed LLVM objects are retained. A numeric `LLVM_BPF_JOBS` override remains
available, for example `make tools/llvm-bpf/compile LLVM_BPF_JOBS=16 V=s`.

## Concurrency preflight on 2026-11-12

The regression workload contains 24 independent jobs and runs through the
actual LLVM recipe, buildroot Ninja wrapper, and CMake compile/install
commands. It checks that the default peaks at 16 workers under `make -j24`
with an unusable parent jobserver, under serial make with no jobserver, and
when installation has pending build work. A two-worker override is also tested.
The old recipe reproduced a peak of one worker under the same `make -j24` test.

These checks verify scheduling, not a full LLVM compilation or firmware build
on the Linux machine. The one-job link pool uses LLVM's
[Ninja job-pool support](https://github.com/llvm/llvm-project/blob/llvmorg-22.1.3/llvm/cmake/modules/HandleLLVMOptions.cmake).

## Missing prebuilt compiler when building bpf-headers

If `bpf-headers` reports that `llvm-bpf/bin/clang` does not exist, the
configuration has selected prebuilt LLVM but the toolchain has not been
installed in this build tree. A blank compiler version does not mean an old
LLVM version was found. The build now reports a missing compiler or a failed
version query separately from an unsupported version.

From the existing build root, install the toolchain and retry the package:

```sh
python3 scripts/setup-llvm-bpf.py
make package/kernel/bpf-headers/compile -j1 V=s
make -j2 V=s
```

The helper verifies and tests the tools before resolving `.config` with
`make defconfig`. Completed firmware build objects are retained. Compiler
validation remains disabled for metadata, download and refresh operations,
which must work before a toolchain is installed.

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
