# Security and robustness audit

Date: 2026-10-07 (Asia/Shanghai).
Baseline: `04986da1e6` on `RoyTsang27/ponwrt-test-build`.

## Scope

Reviewed release automation, download and cache handling, APK/firmware signing,
sysupgrade verification, supplied AN7581/AN7583 configurations, service defaults,
and the Airoha upgrade/initialization path. This is a focused source audit, not
a claim that the complete OpenWrt tree or every external dependency is secure.
The later [PON audit](PON-SECURITY-AUDIT.md) expands this review to the integrated
PON sources. Proprietary firmware blobs and the entire kernel driver patch stack
have not received a complete memory-safety audit.

## Findings and patches

| Priority | Finding and consequence | Patch |
| --- | --- | --- |
| High | `dl_github_archive.py` disables certificate verification. An intercepted API/archive request is accepted before the repacked source hash is checked. | Default verified TLS context, bounded request timeout, closed HTTP responses, strict SHA256 validation. |
| High | Archive content is extracted before its repacked hash is checked, without validating archive paths and links. Predictable scratch paths also allow local interference. | Validate the complete member graph before invoking tar; reject traversal, absolute paths, symlink pivots/chains, duplicate members, device nodes and invalid hard links. Use a private temporary workspace and refuse unsafe scratch directories and cache files. Unusual archives fall back to the existing Git download path. |
| High | APK builds enable `SIGN_FIRMWARE` but the certificate generation and firmware trust-key installation are inside the OPKG branch. The image recipe silently skips signing when those files are absent. The shipped profiles also omit `ucert`. | Generate firmware keys/certificates for both package formats, install the firmware trust anchor for APK, provide a signature-enforcement build option, and include `ucert` in releases. Fail the image recipes when signing material is absent or a signing command fails; verify every `.bin` and `.itb` sysupgrade artifact before upload. |
| Reliability / security | The pinned `ucert -A` returns a boolean write result as its process status: successful appends report failure, while failed writes can report success. Buffered close errors are also ignored. | Convert append success to exit status zero and failures to nonzero, check `fclose`, retain fail-closed image signing, and identify the failing signing stage. Exercise the real pinned tools in CI. |
| High | Missing APK signing secrets silently produce new per-build keys, while firmware releases have no stable signing-key contract. | Require stable APK and firmware keys, validate key pairing, load private keys after downloads and host-tool preparation, and remove working key files with an `always()` step. Build code remains within the signing trust boundary. |
| Medium | Actions and release feeds follow mutable refs. The checkout retains credentials for later build steps. | Pin action commits and release feed commits, disable checkout credential persistence, and add Dependabot updates for actions. Development feeds continue to track upstream. |
| Medium | Both device profiles omit the LuCI HTTPS collection and use regular stack protection and conservative fortification. | Select `luci-ssl-openssl`, strong userspace/kernel stack protection and FORTIFY level 2. Keep existing full RELRO and seccomp. |
| Medium | Root-local information leaks and privileged process dumps assist exploit development or expose credentials after crashes. | Airoha-specific sysctls restrict kernel pointers, dmesg and unprivileged BPF, hide JIT symbols and disable privileged core dumps. Diagnostic restrictions can be changed by administrators; re-enabling unprivileged BPF requires changing the policy and rebooting. |
| Medium | Release tags are quoted but not constrained; a leading dash can be interpreted as a CLI option. An existing tag can identify a commit different from the firmware source. | Validate Git ref syntax and a conservative tag alphabet; only release the default branch; require a fresh tag and create it at the build SHA, then publish using `--verify-tag`. |
| Reliability | Timestamp cache corruption aborts downloads; eviction keeps the oldest entries and can retain stale in-memory entries. | Ignore malformed cache lines, refresh in-memory state from the locked file and retain newest entries. Reject symlinked, non-regular or writable-by-others cache files. |
| Reliability | The fork trails OpenWrt's current Airoha kernel patch level. | Update Linux 6.18.52 to 6.18.55 with upstream's source checksum, and add weekly draft update PRs plus AN7581/AN7583 kernel compilation checks. |
| Reliability | The old 8250 `UPIO_AU` patch overlaps a new stable-kernel case, so it applies without rejects but compilation fails with a duplicate case value. | Remove the redundant patch, retain the stable-kernel handling, and require exactly one `UPIO_AU` case in the prepared source. |
| Reliability | An Airoha phylink hunk has stale, ambiguous context and can apply to the MAC-address setter instead of device shutdown. | Anchor the hunk to `airoha_dev_stop` and refresh the downstream shutdown patch context; verify the resulting functions after applying the full stack. |
| Medium | Both READMEs recommend piping an unpinned network script into a root shell. | Remove that shortcut; retain the explicit package-manager dependency installation instructions. |

Action pins were resolved directly from the action repositories. Release feed
commits were resolved from their upstream heads on the audit date. These pins
provide immutability, not proof that each dependency is free of vulnerabilities.

The kernel bump was taken from OpenWrt commit
[`7670f36e38fce4105f96b6fdc07350ea65ac8dca`](https://github.com/openwrt/openwrt/commit/7670f36e38fce4105f96b6fdc07350ea65ac8dca).
The updater reads the Airoha target and kernel version/checksum from one immutable
upstream commit. It accepts only the expected numeric version and hash fields.
Draft proposals never merge themselves. Ten backports already present in Linux
6.18.55 were removed. The netfilter, MediaTek and Airoha patch contexts were
refreshed while preserving stable-tree fixes, including the netfilter RCU
barrier and the MT7628 MAC operations selection.

At the owner's request, the conflicting BBRv3 experiment was moved unchanged to
`target/linux/generic/experimental-6.18/`. It is inactive. Current builds use
upstream BBR through the existing `kmod-tcp-bbr` selection. Restoring BBRv3 requires
a separate TCP/MPTCP rebase, compilation and runtime testing.

## Validation

- 44 Python regression tests pass locally, covering adversarial archives,
  verified TLS configuration, private scratch paths, unsafe/corrupt caches,
  release inputs, missing keys, unsigned image rejection, `.bin`/`.itb` coverage,
  pipeline error propagation and kernel updater safety.
- A Make harness evaluates the real base-files conditionals for an APK release
  and confirms certificate generation, APK and firmware public-key installation,
  and the signature policy. The signing executables are test substitutes here.
- `actionlint` 1.7.12 validates all workflows; shell syntax checks and
  `git diff --check` pass. CI also runs ShellCheck.
- The official Linux 6.18.55 archive matches the upstream SHA256. The original 611 active
  generic/Airoha patches apply to a freshly extracted source tree with no rejects.
  Source assertions verify one MediaTek phylink allocation, correct MT7628 MAC
  operations, one RTL8367SB entry, notifier removal before the RCU barrier,
  correct Airoha PHY shutdown placement and absence of the BBRv3 TCP hooks.
- A new Ubuntu CI workflow resolves configurations, prepares kernels and checks
  the networking invariants in the patched source for both SoCs. A complete
  firmware build and real-device tests are required before release.

Follow-up, 2026-10-08: compilation reproduced a duplicate `case UPIO_AU` in
`drivers/tty/serial/8250/8250_port.c` on both Airoha targets. Linux 6.18.55 already
handles this case, while the downstream `890-serial-8250` patch added it again
under `CONFIG_HAS_IOPORT`. Removing that redundant patch leaves 610 active
generic/Airoha patches and preserves the upstream UART handling. A source check
now rejects a missing or duplicate case. Both AN7581 and AN7583 kernel/module compilations passed in
[run 37699870443](https://github.com/RoyTsang27/ponwrt-test-build/actions/runs/37699870443).

Preparation checks cannot establish that C sources and modules compile. The
two-target CI workflow now builds the host tools and cross compiler, then compiles
the kernel and modules and retains diagnostics on failure. Compilation results
are required before accepting future kernel updates.

A subsequent local build at `daeeb6d475` compiled the kernel and created the
firmware FIT, then failed at signing. The pinned upstream
[`cert_append()`](https://github.com/openwrt/ucert/blob/57270b247c91f003db6e3ba1a71d6d1fa5710fef/ucert.c#L202)
returned `write_file()`'s boolean directly as a process exit status. Successful
writes therefore exited with status 1. The strengthened signing recipe exposed
this bug; the initial substitute-tool tests missed it. The package patch corrects
the status and checks errors when buffered writes are closed. Integration tests
build the same SHA256-pinned json-c, libubox, usign, ucert and fwtool sources with
their package patches, then exercise successful signing/verification, write and
flush failures, truncated signatures and tampered firmware. Signing checks remain
mandatory, and existing private keys and trust anchors are preserved.

Local tests of signing orchestration do not establish cryptographic correctness
of the external signing tools. The release workflow uses the actual host
`fwtool`/`ucert` binaries to verify completed images and refuses publication on
failure. No production signing secrets were created or changed by this audit.

## Operational follow-up and remaining risks

1. Configure the three stable signing secrets and protect the `release`
   environment. Do not expose signing keys to pull-request builds.
2. Run a complete build for both targets, then test PON registration, VLANs,
   routing/bridging, hardware offload, recovery and signed sysupgrade on hardware.
   A patch applying successfully does not prove runtime correctness.
3. First boot still follows OpenWrt's password setup model. Root's initial
   password is empty; set a unique password before exposing the device to an
   untrusted network. Existing configurations retain their service settings.
4. `/dev/mem` and hardware debugging support remain enabled because removing
   them without auditing the external PON stack can break device support.
   Review those dependencies before reducing that access further.
5. Review upstream security advisories and intentionally refresh feed locks.
   Kernel automation tracks OpenWrt's Airoha series, not arbitrary newer kernel
   releases that the driver stack has not been ported to.
6. Rotate the GitHub credential supplied in the conversation after publication;
   it was used only for GitHub authentication, never included in source files.

The workflow hardening follows
[GitHub's secure-use guidance](https://docs.github.com/en/actions/reference/security/secure-use),
including immutable action refs and minimum token permissions.

Real signing-tool integration tests passed in [run 37703413883](https://github.com/RoyTsang27/ponwrt-test-build/actions/runs/37703413883).
The separately fetched PON feeds have since been integrated and audited; see
[the PON audit](PON-SECURITY-AUDIT.md) for the expanded scope and results.
