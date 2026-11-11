# Easy Linux 6.18.60 → 6.18.63 update kit

One kit supports **op-source (OpenWrt)** and **official ImmortalWrt**. It detects
the source automatically, checks compatibility, backs up the files it changes,
and applies the matching patches. Python 3.8+ is required; Git is optional.

## Quick start

Stop any running build and extract `op-source-kernel-6.18.63-update.tar.gz`.
From your existing source/build root, run **one command**:

```sh
cd /home/ubuntu_2604/op
sh /path/to/kernel-6.18.63-update/update.sh
```

Replace `/path/to/` with the directory where you extracted the kit. The build
root contains `rules.mk`; do not run inside the generated
`build_dir/.../linux-6.18.60` directory. A separate check command is unnecessary:
preflight runs automatically before any source changes.

To update **and build firmware** on Linux instead:

```sh
sh /path/to/kernel-6.18.63-update/update.sh --build
```

`--build` runs `make defconfig`, cleans the selected kernel and mac80211/mt76
build outputs, prepares Linux 6.18.63, and builds firmware with two jobs. It
stops at the first failed command. If memory is limited, use `--build --jobs 1`.
Firmware output is under `bin/targets/`. Use an existing device `.config`,
with feeds and build prerequisites already installed.

Inside the source repository, use `sh updates/kernel-6.18.63/update.sh`.
You can also pass the build root explicitly from any directory:

```sh
sh kernel-6.18.63-update/update.sh /home/ubuntu_2604/op --build
```

## Supported source trees

| Source | Tested starting point |
| --- | --- |
| op-source / OpenWrt | Linux 6.18.60, commit `a8854f0e`; also the published 6.18.62 tree `485f4439` |
| Official ImmortalWrt | Linux 6.18.60 bump `5fb9d9cd`; also master snapshot `4765b657` |

The ImmortalWrt profile retains its branding, feeds, device definitions,
wireless package recipes, and additional patches. It removes eight duplicate
stable backports where present, refreshes five kernel patches, and corrects
the mac80211 `sockaddr_unsized` compatibility guard for Linux 6.18.61+.
Both tested ImmortalWrt snapshots already select the kit's mt76 revision;
the updater checks that revision and preserves their driver customizations.

This kit updates the **6.18 kernel series**. It does not migrate a 5.15, 6.6,
or 6.12 build to 6.18. Changed files must match a recorded starting state or
the final state; unknown local edits are listed and the update stops before
writing source files. Do not bypass conflicts by overwriting your own patches.

`.config`, feeds, toolchains, download caches and device definitions are
preserved. Source backups and a journal are saved in `.kernel-update-backups/`.
Source write failures trigger rollback. Running the source update again is a
no-op; `--build` explicitly cleans and rebuilds even if source is current.

Optional flags:

- `--check`: compatibility check only; no writes.
- `--download`: fetch the checksum-verified kernel archive into `dl/` before
  applying changes. Normally the build downloads its own sources.
- `--build --jobs N`: update and build on Linux using N jobs (default: 2).

The original `python3 update.py /path/to/op` interface still works.

## Pinned sources and patches

- Linux **6.18.63**, kernel.org archive SHA-256:
  `81764a545072d160748beff4d9de2e7d95aa9f16e8261110288f067a2cc61d71`.
- mt76 **0936617dc529ff9da0385221d3fa6de732231177** (2026-10-28), latest official
  upstream HEAD verified on 2026-11-11. Archive SHA-256:
  `3a3844097e66021f21f0ec8508cb740ef6536a2243f74c47fd5a898edb26839f`.
- op-source includes matching mac80211 and MediaTek WED/PPE APIs and both
  official mt76x02/mt76x2u fixes. ImmortalWrt retains its matching integration.

Readable deltas and integrity manifests are included:

- `patches/op-source-6.18.60-to-6.18.63.patch`
- `profiles/immortalwrt/patches/immortalwrt-6.18.60-to-6.18.63.patch`
- `profiles/immortalwrt/patches/immortalwrt-4765b657-to-6.18.63.patch`

The ImmortalWrt baselines are recorded in the [official repository](https://github.com/immortalwrt/immortalwrt):
[6.18.60 bump](https://github.com/immortalwrt/immortalwrt/commit/5fb9d9cd90ca751b5066a37517caa9fbc158ded7),
[master snapshot](https://github.com/immortalwrt/immortalwrt/commit/4765b657625ec5bbda74b44400465fe043802b30).

## Local validation

The op-source preflight passed all 42 kernel stacks, 247 mac80211 patches and
two mt76 patches. For each ImmortalWrt snapshot, all 41 kernel patch stacks
were checked with zero fuzz and no rejects; 250/256 mac80211 patches and
2/3 mt76 patches passed. AArch64 socket compatibility compiler probes cover
6.18.60, .61, .62 and .63. Migration tests cover automatic detection, backup,
preservation of build settings, conflicts, rollback, repeated updates and
the extracted delivery archive.

A complete firmware compilation and hardware boot have **not** been verified.
