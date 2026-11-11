# Speed up LLVM-BPF in an existing op-source build

This kit installs three files for LLVM 22.1.3: the RAM-aware LLVM recipe,
its worker-count detector, and the verified OpenWrt prebuilt-tool setup helper.
It supports the original recipe, the older single-worker fix, and the existing
automatic-worker recipe. It checks file checksums before making changes,
backs up originals in `.llvm-bpf-backups/`, and refuses unfamiliar local edits.

Stop the running build with Ctrl-C and wait for it to exit. Extract this kit
beside the Linux build directory, then pass your actual source/build root:

```sh
tar -xzf op-source-llvm-bpf-speed-fix.tar.gz
python3 llvm-bpf-speed-fix/update.py /path/to/op-source --check
python3 llvm-bpf-speed-fix/update.py /path/to/op-source
cd /path/to/op-source
```

## Fastest option: skip LLVM source compilation

On Linux x86-64, select OpenWrt's matching prebuilt BPF toolchain:

```sh
python3 scripts/setup-llvm-bpf.py
make -j2 V=s
```

This requires `zstd` and Python 3.12 or a patched Python 3.11 providing
`tarfile.data_filter`. The helper checks the official download's SHA256,
LLVM version, executables, and a complete BPF compilation before selecting it.
It backs up `.config` and restores it and the previous toolchain link if
configuration resolution fails. Firmware device/package selections are retained.
The official matching archive was listed on 2026-11-11, but snapshots rotate.
If it becomes unavailable, use the source option below.

Resume with ordinary `make` after setup. Explicitly requesting
`tools/llvm-bpf/compile` always asks OpenWrt to compile LLVM from source,
even when prebuilt LLVM is selected.

## Source option: remove the forced one-worker limit

```sh
python3 scripts/llvm-bpf-jobs.py --explain
make tools/llvm-bpf/compile LLVM_BPF_JOBS=auto V=s
make -j2 V=s
```

The detector uses Linux available RAM, cgroup limits, and CPU affinity. It
reserves at least 2 GiB or 25% of memory capacity and budgets 3 GiB per compiler
worker. For example, 16 GiB total with 14 GiB available selects three workers;
32 GiB total with 28 GiB available selects six, subject to CPU limits. Unknown
memory falls back to one worker. Linking stays limited to one job.

Use `LLVM_BPF_JOBS=2` for an explicit override. Raising firmware `make -j`
alone does not override the LLVM-specific worker limit. Swap is excluded from
the RAM budget; more swap does not make extra compiler workers fast.

No clean command is needed. The update retains `.config`, downloads, feeds,
kernel sources, cross toolchains, and completed LLVM objects. A job-count change
resumes the existing Ninja build. This kit does not contact the Linux machine
or measure its build time; complete LLVM and firmware builds need validation
on that machine.
