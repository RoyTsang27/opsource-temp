# Update an existing OpenWrt build folder to Linux 6.18.59

This kit upgrades the OpenWrt source/build root used for firmware compilation,
for example `/home/ubuntu_2604/op`. It supports the original official OpenWrt
6.18.55 snapshot recorded by op-source, plus the compatible op-source 6.18.56,
6.18.57 and 6.18.58 states. The baseline is official OpenWrt commit
`0ad1348fb2a7f49c9c5941d4d8c98f88b6974e8d`.

The kit contains `update.py`, a readable unified patch, hash metadata and the
replacement source files. It does not require a Git checkout or network access
to apply the update. Python 3.8 or newer is required.

## Apply the update

Let any running firmware build exit first. Extract the kit, then run:

```sh
python3 kernel-6.18.59-update/update.py /home/ubuntu_2604/op --check
python3 kernel-6.18.59-update/update.py /home/ubuntu_2604/op
```

If using these files inside a current op-source checkout, the script path is
`updates/kernel-6.18.59/update.py` instead. Point the script at the build root
containing `rules.mk` and `target/linux/`, rather than an extracted
`build_dir/.../linux-6.18.55` directory.

The check verifies every payload and every source file it would change. The
updater applies only recognised originals, skips files already updated and
stops before changing source if a file has unexpected local modifications.
Review any reported conflicts instead of overwriting custom patches.

Original files and a journal are saved under
`.kernel-update-backups/6.18.59-<UTC timestamp>-<suffix>/` in the build root.
An interrupted write handled by the script restores the files already changed.
The journal records which files existed before the update; new files do not
have an original copy. Keep this backup until the new firmware is verified.

The updater preserves `.config`, feeds, custom device definitions, downloads,
host tools, staging and existing build objects. When present, op-source's
`config/device-build.json` receives the new kernel version/hash while retaining
its device definitions. No build or cleanup command runs automatically.

Optionally pre-download and verify the new kernel archive in `dl/`:

```sh
python3 kernel-6.18.59-update/update.py /home/ubuntu_2604/op --download
```

The download uses kernel.org over HTTPS and the pinned SHA256:

```text
53a55ac9863a5547e292b8e381d4e4c2240dd1127d5428a7c44dbc550be23963
```

Without `--download`, the normal OpenWrt build downloads and verifies the
archive when preparing the kernel. A custom download location or a symlinked
`dl/` can continue to be used by the normal build; the helper's optional download
mode operates only on a regular `dl/` directory inside the selected root.

## Rebuild the kernel and firmware

Run the commands printed by the updater, from the existing OpenWrt build root:

```sh
cd /home/ubuntu_2604/op
make defconfig
make target/linux/clean
make package/kernel/mac80211/clean
make target/linux/prepare -j1 V=s
make -j2 V=s
```

These clean only the selected target's kernel outputs and mac80211 objects.
Downloaded sources and the compiled host/cross toolchains are retained.
The new kernel and kernel modules must be rebuilt together; existing 6.18.55
module binaries cannot be carried into the 6.18.59 firmware.

## Included source adjustments

- Select Linux 6.18.59 and its verified archive checksum.
- Drop four OpenWrt patches whose SPI-NAND, Quectel and cgroup fixes are already
  in the stable kernel, and retain the refreshed LoongArch vDSO patch from 6.18.56.
- Retain the bridge ARP suppression refresh for the neighbour MAC-address snapshot
  introduced in 6.18.58.
- Refresh the small-device FQ-CoDel memory-limit patch around the stable
  kernel's updated MTU handling, retaining the 4 MiB router default.
- Include mac80211's `sockaddr_unsized` compatibility fix for 6.18.57 and later.
- Carry the p54 firmware record bounds fix (CVE-2026-99100) into the separately
  built backports 7.2 wireless package, increasing its package release to 7.

`patches/openwrt-6.18.55-to-6.18.59.patch` is the reviewable source delta from
the original 6.18.55 files. It can be checked with `git apply --check` on that
baseline. The Python updater also handles already-updated files and supported
6.18.56/57/58 kernel metadata, using exact content hashes rather than fuzzy patch
application.

Local preflight verified the 591 MediaTek and 497 Ralink kernel patches with
zero fuzz and no rejects, all 192 mac80211 patches, an AArch64 compiler probe
against the native 6.18.59 socket type, and update/backup/recovery tests.
These checks do not establish a completed firmware build or hardware boot.
