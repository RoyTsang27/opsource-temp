# Complete package menu on test-flight

Run the normal interactive configuration command from the source root:

```sh
make menuconfig
```

`menuconfig`, `nconfig`, `xconfig` and the interactive `config` frontend now
prepare every configured feed before generating their package menus. The first
run downloads missing feeds, applies this branch's Linux 7.3 compatibility
patches, builds the indexes and installs all package recipes. Later runs reuse
the catalog without fetching upstream changes. Changed recipes, compatibility
patches, indexes or removed package links trigger preparation again.

Installing a recipe exposes its configuration options. Firmware contents still
follow the selected device profile and package selections in `.config`.

## Available feeds

| Feed | Menu content |
| --- | --- |
| `packages` | Utilities, Administration, Network, Languages, Libraries, Filesystems, Multimedia and other package categories. Examples include nano, vim, tmux, screen, coreutils, htop, curl, wget, iperf3, rsync and OpenSSH. |
| `luci` | LuCI collections, applications, protocols, themes, translations and supporting libraries. |
| `routing` | Routing protocols and mesh networking packages. |
| `telephony` | Telephony, VoIP and their libraries and drivers. |
| `video` | Video applications and supporting packages. |

Use `/` inside menuconfig to search for a package. Kconfig applies the selected
architecture, kernel, library and feature dependencies. Packages requiring
kernel facilities removed in Linux 7.3 remain restricted to supported kernels.

`feeds.conf.default` and `feeds.conf.release` now use the same five immutable
snapshots. The carried compatibility patches are written for those snapshots;
changing only a feed to its current upstream branch can prevent it from being
patched and indexed. Update both pin files and the associated patches together.

## Existing checkouts and custom feeds

To prepare or repair the package catalog without opening a frontend:

```sh
make prepare-feeds
```

Existing feed sources are indexed in place. Preparation does not fetch over
them or reset their local edits. The patch updater records applied patch
versions under `feeds/<name>.tmp/applied-patches/`. When the project revises a
patch, the updater stages the old-to-new change and applies it only after the
whole replacement passes a check. For older checkouts without receipts, it can
recognize earlier patch versions from this source repository's Git history.
Conflicting local edits produce an error instead of being overwritten.

An existing `feeds.conf` takes precedence over `feeds.conf.default`, including
custom `src-link` and `src-include` entries. Review that file if a standard feed
is missing or a patch does not match. Preserve custom entries and local changes
when bringing standard feed URLs and revisions into line with the defaults.
Automatic preparation intentionally respects the configured feed list.

The explicit upstream feed workflow remains available:

```sh
./scripts/feeds update -a
./scripts/feeds install -a
make defconfig
```

Non-interactive builds retain this explicit workflow. Feed fetch, metadata scan
and compatibility patch failures now stop preparation, with the failing command
or recipe reported, instead of opening an incomplete package menu. Recipe dump
errors are saved under `logs/<recipe-path>/dump.txt`.

## Device defaults and validation

MediaTek and Airoha kernel, wireless, network and security defaults remain
device-specific. Exposing the full catalog does not set `ALL`, `ALL_KMODS` or
`ALL_NONSHARED`, or add every package to small flash images. Enable only the
applications needed for the chosen hardware and available flash space.

Focused regression checks cover first-run installation, offline reuse, local
recipe changes, removed package links, failed feed scans and patch upgrades
with local edits. Generated virtual-provider dependencies are resolved with the
real OpenWrt Kconfig tool, including default and alternative provider choices.
The dependency fix follows
[OpenWrt PR 25091](https://github.com/openwrt/openwrt/pull/25091).

Full feed metadata generation and firmware builds require the normal supported
OpenWrt build environment, including GNU Make 4.1 or newer and GNU awk. This
change does not establish that every optional package builds on Linux 7.3.
