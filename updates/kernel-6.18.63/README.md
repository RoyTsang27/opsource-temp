# Update a 6.18.60 OpenWrt build directory to Linux 6.18.63 and latest mt76

This kit updates the op-source 6.18.60 snapshot at commit
`a8854f0e7dcacd2b21ccbccaf0dd9d2fd93f4ae1` and accepts the published op-source
6.18.62 file states. It includes a standalone Python 3.8+ script, the cumulative
source patch, checksums and replacement files. Git is not required to use the
script. Local changes to files in the update are reported for review before
any source files are changed.

Stop running firmware builds and extract the kit. Pass the OpenWrt build root
containing `rules.mk`, such as `/home/ubuntu_2604/op`:

```sh
python3 kernel-6.18.63-update/update.py /home/ubuntu_2604/op --check
python3 kernel-6.18.63-update/update.py /home/ubuntu_2604/op --download
```

Inside the source repository, the script is `updates/kernel-6.18.63/update.py`.
Do not point it at the generated `build_dir/.../linux-6.18.60` subdirectory.
The script updates the source recipes and patches; OpenWrt then prepares a
fresh 6.18.63 kernel build directory.

`--download` is optional. It places the checksum-verified kernel archive in
`dl/`; the normal OpenWrt build fetches the pinned mt76 source. Without this
option the normal build fetches both sources. The updater backs up changed
files and a journal under `.kernel-update-backups/`, preserves `.config`,
feeds, device definitions, toolchains and caches, and prints the rebuild
commands. It handles write errors by rolling back files already changed.

Rebuild from your existing OpenWrt build root on a supported Linux host:

```sh
cd /home/ubuntu_2604/op
make defconfig
make target/linux/clean
make package/kernel/mac80211/clean
make package/kernel/mt76/clean
make target/linux/prepare -j1 V=s
make -j2 V=s
```

The clean commands remove the selected target's kernel and wireless build
outputs while retaining the host/cross toolchains and download cache. Kernel
modules must be rebuilt together with the new kernel.

## Default wireless source

The default mt76 package uses official upstream HEAD as checked on 2026-11-11:

- Commit: `0936617dc529ff9da0385221d3fa6de732231177` (2026-10-28).
- Source archive SHA-256:
  `3a3844097e66021f21f0ec8508cb740ef6536a2243f74c47fd5a898edb26839f`.
- Both current OpenWrt mt76x02/mt76x2u fixes are included.
- Matching mac80211 and MediaTek WED/PPE interfaces are included so the driver
  builds against the expected flow and priority APIs.

The driver is pinned to this revision for reproducible builds. The existing
MediaTek device presets select the mt76 modules appropriate to each device.

Linux 6.18.63 is pinned to the kernel.org archive SHA-256:

```text
81764a545072d160748beff4d9de2e7d95aa9f16e8261110288f067a2cc61d71
```

## Source patch and validation

`patches/op-source-6.18.60-to-6.18.63.patch` is the readable source delta from
the recorded op-source 6.18.60 snapshot. You can use `git apply --check` and
`git apply` on that baseline. The Python updater additionally validates
recognised file versions, writes backups, and updates the optional
`config/device-build.json` kernel version/hash while preserving its other
settings.

Local preflight passed all 42 kernel patch stacks, 247 mac80211 patches,
two mt76 patches, AArch64 socket and flow-layout compiler probes, a MIPS
flow-layout syntax check, and update preservation, conflict and rollback
tests. The extracted delivery kit was tested on the actual 6.18.60 and
6.18.62 source files. A full firmware build and hardware boot were not tested.
