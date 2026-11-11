# PON userspace and driver security audit

## Scope and integration

Reviewed `pbs05/openwrt-pon-userspace` at
`cce9d756742487b378749c606b30e13ee9b0f093` and
`pbs05/openwrt-pon-drivers` at
`e5194d2dfd169eef8f4a944fdc3f929e0287b680`. Standalone patches apply to those exact upstream commits:
[userspace](patches/pon-userspace-security.patch) and
[drivers](patches/pon-drivers-security.patch). They have been checked with
`git apply --check`. The reviewed copies and local fixes
are part of `package/pon`, with original licenses and provenance retained.
The external PON feed entries were removed to avoid duplicate package names
and prevent feed updates from discarding the fixes.

Both supported Airoha subtargets select the core stack, diagnostics and LuCI
PON/IPTV apps by default. Optical modules and calibration remain board-specific.
Packet capture and IPTV remain disabled in their shipped runtime configuration.
The control package explicitly depends on `coreutils-stat` because the shipped
BusyBox profiles omit the stat applet used by the runtime ownership checks.
Release validation also requires the resolved core package selections. The
package scanner prevents stale external PON feed links from overriding the
audited built-in sources.

The review covered OMCI/OAM framing, authentication, kernel control attributes,
netlink authorization, firmware loading, frontend lifetimes, Rust parsing and
configuration/control handlers, LuCI access rules and root-run shell helpers.
It does not prove the absence of all defects, and does not reverse-engineer
the EN7572 firmware blobs or test live optical hardware.

## Findings and changes

| Finding | Effect and correction |
| --- | --- |
| OMCI extended TX length narrows a 16-bit length plus a 10-byte header back to `u16`. | Values near 65535 wrap and can accept inconsistent frames, including trimming a ten-byte packet to six bytes. Use an unsigned integer wide enough for the addition, retaining the existing size limit. This is a local raw-socket TX path requiring `CAP_NET_RAW`; remote code execution was not demonstrated. |
| Board-image upload and recovery backups use predictable paths in shared `/tmp`. | Pre-created symlinks can redirect privileged file access; backup copies can be readable to other users. Put uploads, locks, work files and backups in checked root-owned 0700 directories; use umask 077 and exclusive temporary names. Give each upload its own token, reject symlinks, hardlinks, non-root owners and invalid lengths before flash access, and retain verified private backups for recovery. |
| Diagnostic state and archive paths are predictable in shared `/tmp`, and archive permissions are tightened only after creation. | Pre-created directories/symlinks can redirect root writes and expose configuration or captured credentials. Check ownership and permissions before using runtime directories, create archives with private permissions from the beginning, use unique staging directories and atomic publication, and serialize collection. |
| A read-only LuCI PON role can read the diagnostic archive. | Archives may contain registration credentials, raw packets and configuration. Restrict the archive path to the write role while retaining ordinary status access. |
| Enhanced-security authentication compares tags with ordinary slice equality. | Replace the potentially early-exiting comparison with `subtle::ConstantTimeEq`. This reduces timing leakage; an exploitable timing attack was not demonstrated. |
| Control sockets read unlimited request lines and serve clients serially without a timeout. | A local client can consume memory or stall status handling. Limit requests to 128 bytes with a two-second whole-request deadline and bounded response writes; reject incomplete/invalid input. Refuse to delete regular files or symlinks at the configured socket path. Control socket permissions remain 0600. |
| OMCI Create/Set/Set-table can grow entity and table maps without an allocation budget. | An OLT can exhaust daemon memory by repeatedly adding unique instances or rows. Cap entities at 4096, rows per table at 4096 and aggregate rows at 16384; preserve replacement/deletion/retry behavior, reject exhausted budgets with Processing Error, and stage batches atomically. Check MIB-upload record counts before narrowing to 16 bits. |
| Raw packet descriptors lack close-on-exec. | Set `SOCK_CLOEXEC` when opening the daemon packet socket to avoid accidental inheritance by future child processes. |

The fixed authentication PSK in upstream class 332 is preserved for protocol
compatibility. This review does not establish that it provides an operator-specific
trust boundary. Debug archives still contain sensitive data for administrator
troubleshooting, and RAM backups do not survive reboot. Save needed backups
securely before rebooting. Root privileges remain necessary for the current
netlink, sysfs and network configuration backend.

## Advisories and validation

Checked the locked Rust dependency names against the official RustSec advisory
database snapshot `550efd3d587a29b2e2c2b21b17a440da4fede999`.
The one matching package advisory, [RUSTSEC-2020-0146 / CVE-2020-36465](https://rustsec.org/advisories/RUSTSEC-2020-0146.html), affects
older generic-array releases; the locked 0.14.7 version is in its patched range
(`>= 0.13.3`). No applicable assigned CVE was confirmed by that check. The new
code findings above have no assigned CVE IDs. CI runs cargo-audit 0.22.2 against
the current advisory database for both Cargo lockfiles; there is no blanket
claim that the firmware or kernel is free of CVEs.

Regression coverage exercises all 65536 declared OMCI content lengths against
the actual C normalizer, valid baseline/extended frames, symlink and ownership
attacks, unique uploads, private backups, flash readback using a fake storage
file, constant-time tag matching bounded Unix-socket requests and MIB resource exhaustion/recovery. Linux CI runs
ownership tests as root; no test writes router flash. It also runs the existing
Rust suites and cross-compiles integrated packages with Linux 6.18.55 on AN7581
and AN7583. Final Linux security checks passed in
[run 37812990875](https://github.com/RoyTsang27/ponwrt-test-build/actions/runs/37812990875):
41 daemon tests, 2 control-utility tests, 9 PON filesystem/length/access/feed
checks, 44 existing security tests and 5 real signing tests. Both cargo-audit
scans found no applicable vulnerabilities. Cross-build results will be recorded
after CI completes.

The branch still matches OpenWrt Airoha Linux 6.18.55 at upstream commit
`8d0fa6b2903f1abe57c6dc3320e75a18d353b880`, checked on 2026-10-09.

## Updating an existing checkout

Switch to `codex/signing-append-fix` and pull its current commits. Replace any
old `feeds.conf` with the checked-in `feeds.conf.release`, then update and install
feeds normally. The package scanner ignores stale PON feed links automatically;
`./scripts/feeds uninstall -a` before reinstalling feeds also removes the obsolete
package links, while keeping the downloaded feed sources.

Fresh target configurations select the seven core packages automatically. The
supplied `configs/an7581.config` and `configs/an7583.config` explicitly select
them too. Existing custom `.config` files may retain explicit deselections:
select `kmod-airoha-xpon`, `kmod-airoha-pon-frontend`, `airoha-ponctl`,
`airoha-pond`, `airoha-pon-debug`, `luci-app-pon` and `luci-app-iptv`, run
`make defconfig`,
and check `python3 scripts/check-release.py --pon-config .config` before building.
This preserves the remaining custom device and package selections.

Recovery backups on this branch are private files named
`/tmp/ponwrt/board/backup-*`, rather than the old paths in the preserved upstream
identity documentation. The flash helpers print the exact recovery path after a
successful update. No test in this review writes physical router flash.
