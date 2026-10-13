# Device Build

ImmortalWrt source for compiling Xiaomi AX3000T, Cudy TR3000, and Cudy TR1200
firmware with **Linux 6.18.56**. The GitHub repository name is `Device-Build`;
the project display name is **Device Build**.

This repository contains the complete build system, kernel patches, device
trees, drivers, and image recipes. Its base is
[RoyTsang27/ponwrt-test-build](https://github.com/RoyTsang27/ponwrt-test-build/tree/a80feaf1764000fa9ebd1f49ce27fcc6c0b5cb09),
commit `a80feaf1764000fa9ebd1f49ce27fcc6c0b5cb09` on `codex/security-audit`.
That branch carries the requested kernel bump and audited PonWrt integration;
the reference's `master` was still using 6.18.52 when imported.

## Devices

| Build selector | Device / layout | Target | Image profile |
| --- | --- | --- | --- |
| `ax3000t` | Xiaomi Mi Router AX3000T, stock layout | `mediatek/filogic` | `xiaomi_mi-router-ax3000t` |
| `tr3000` | Cudy TR3000 v1, stock layout | `mediatek/filogic` | `cudy_tr3000-v1` |
| `tr1200` | Cudy TR1200 v1 | `ramips/mt76x8` | `cudy_tr1200-v1` |
| `ax3000t-ubootmod` | AX3000T, OpenWrt U-Boot layout | `mediatek/filogic` | `xiaomi_mi-router-ax3000t-ubootmod` |
| `tr3000-256mb` | TR3000 256MB v1, stock layout | `mediatek/filogic` | `cudy_tr3000-256mb-v1` |
| `tr3000-ubootmod` | TR3000 v1, OpenWrt U-Boot layout | `mediatek/filogic` | `cudy_tr3000-v1-ubootmod` |

The first three profiles form the default build set. Optional variants must be
selected explicitly. Match the hardware revision and installed flash/bootloader
layout before choosing an image. The 256MB selector describes the upstream
TR3000 flash variant; it is a separate profile.

AX3000T and TR3000 retain their MT7981/MT7915 Wi-Fi drivers and firmware.
TR1200 retains MT7603 and MT7663 Wi-Fi, USB, and its switch configuration.
Each preset builds one device, with LuCI HTTPS and firmware/package signing.
TR1200 uses the smaller LuCI TLS variant for its 16MB flash. The workflow
requires a produced sysupgrade image before uploading firmware.

## Compile locally

Use Ubuntu 24.04 or an equivalent Linux host with a case-sensitive filesystem,
GNU make 4.1+, and at least 40GB of free space for one build. The dependency list
is in the [Device Build workflow](.github/workflows/device-build.yml).

```sh
git clone https://github.com/tdsafgen1888asd/Device-Build.git
cd Device-Build
cp feeds.conf.release feeds.conf
./scripts/feeds update -a
./scripts/feeds install -a

python3 scripts/device-build.py list
python3 scripts/device-build.py configure ax3000t
make download -j4
make -j"$(nproc)" V=s
python3 scripts/device-build.py check-images ax3000t bin/targets/mediatek/filogic
```

Use `configure tr3000` or `configure tr1200` for the other devices.
TR1200 images go to `bin/targets/ramips/mt76x8/`; AX3000T and TR3000 images
go to `bin/targets/mediatek/filogic/`. For simultaneous builds or a change of
target architecture, use a separate checkout/worktree for each device. The
helper saves an existing `.config` as `.config.device-build.backup`.

Presets live in `configs/devices/`; shared settings are in `common.config`.
For custom packages, run `make menuconfig` after configuring, then run
`python3 scripts/device-build.py check-config DEVICE` before compiling.
Without a local `feeds.conf`, `feeds.conf.default` follows development feeds;
the documented procedure and CI use `feeds.conf.release` to pin them.

## GitHub Actions

The **Device Build** workflow compiles all three default devices on pushes to
`main` and relevant pull requests. In **Actions → Device Build → Run workflow**,
choose `all` or one of the six selectors. Each device has a fresh runner,
independent configuration/toolchain/build directories, source-download caching,
and its own firmware and diagnostic artifacts.

Firmware archives contain `profiles.json`, image checksums, the resolved build
configuration, pinned feeds, source commit, and device manifest. Upload checks
verify the target, Linux version, profile, image files, sizes, and SHA256 hashes.

```sh
python3 scripts/device-build.py check-source
python3 -m unittest discover -s tests -p test_device_build.py -v
```

Builds generate local signing keys. Use stable, owner-managed keys for a firmware
distribution; CI-generated keys differ between runs. This workflow uploads build
artifacts. The inherited **Release PonWrt** workflow remains a separate manual
workflow for the original Airoha devices, with its documented key requirements.
The Airoha kernel and kernel update proposal workflows also run manually;
scheduled upstream tracking is disabled here.

## Source and validation

Both MediaTek and Ralink targets select kernel 6.18 and resolve to 6.18.56.
The kernel archive SHA256 is
`4633bbda2ab95eaf2a7af4041236451d6759c72e6946265531af4b3aacefbf89`,
matching [kernel.org](https://cdn.kernel.org/pub/linux/kernel/v6.x/sha256sums.asc).

The import preserves ImmortalWrt/OpenWrt/PonWrt licenses, original package
sources, and the reference's 6.18.56 generic kernel fixes. Device Build removes
a Ralink PWM patch already incorporated in 6.18.56 and fixes the TR1200 backup
partition address. See [source provenance and validation](docs/DEVICE-BUILD.md).

Inherited Airoha/PON devices remain available through the original profiles.
Their documentation is preserved in [README.PonWrt.md](README.PonWrt.md),
[README.ImmortalWrt.md](README.ImmortalWrt.md), and
[package/pon/README.md](package/pon/README.md).

Full firmware compilation and boot/upgrade tests on physical devices are
separate validation stages. Preserve factory calibration and use images
matching the existing bootloader layout when testing hardware.

## License

The inherited build system is distributed under GPL-2.0; individual files and
packages retain their original licenses and copyright notices. See
[COPYING](COPYING), [LICENSES](LICENSES), and package-specific license files.
