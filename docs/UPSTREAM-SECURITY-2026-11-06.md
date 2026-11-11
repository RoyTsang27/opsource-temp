# OpenWrt upstream security audit, 2026-11-06

The review screened 919 commits between the original OpenWrt source snapshot
`0ad1348fb` and [OpenWrt main at `031659df`](https://github.com/openwrt/openwrt/tree/031659df7f07c53d29743009c2c8fbc8eb2a05f8),
plus 40 commits on [OpenWrt 25.12](https://github.com/openwrt/openwrt/tree/69af20612b6405a35042c4bca17765c4f7c07137)
since October 13. It examined relevant security advisories, patch contents,
source pins and follow-up fixes. The comparison started from op-source
`0e720319`. The scope covers core OpenWrt sources, the two kernel lines in this
tree and the six published device profiles.

## Integrated security fixes

| Area | Reason for taking the change | Upstream source |
| --- | --- | --- |
| dnsmasq 2.93 | Fixes DNS and DHCPv6 bounds errors, TFTP cache handling and connection exhaustion. Includes the ubus reconnect fixes that prevent a stale object type and a use-after-free during ubusd restarts. | [Parser and resource fixes](https://github.com/openwrt/openwrt/commit/6db25ee835eb55af521125c84b12ffd0495f671b), [ubus lifetime fix](https://github.com/openwrt/openwrt/commit/ceb87102) |
| musl 1.2.6 | Prevents integer overflows while compiling a regex supplied by an application. Applications passing untrusted regex patterns are the relevant exposure. | [CVE-2026-107891 advisory](https://www.openwall.com/lists/musl/2026/10/21/1), [OpenWrt backport](https://github.com/openwrt/openwrt/commit/f1d43d52) |
| uhttpd | Rejects non-string ubus list parameters. | [Updated source pin](https://github.com/openwrt/openwrt/commit/20c44f41) |
| rpcd and ubus | Enforces session ACLs for non-root ubus callers. The rpcd change uses a new libubus pre-invoke callback, so both pins move together. | [rpcd](https://github.com/openwrt/openwrt/commit/8ac5e011), [ubus](https://github.com/openwrt/openwrt/commit/f79894ab) |
| odhcpd | Drops relay packets without an encapsulated client message, checks the type of DHCPv6 IA sub-options and exits the receive loop on errors. | [Updated source pin](https://github.com/openwrt/openwrt/commit/2778c373) |
| libubox and json-c | Avoids out-of-bounds reads when converting malformed blob attributes, plus leaks and double-free risks in JSON object cleanup. | [libubox](https://github.com/openwrt/openwrt/commit/3119b579), [json-c leak](https://github.com/openwrt/openwrt/commit/e95288dc), [json-c cleanup](https://github.com/openwrt/openwrt/commit/102f4eeb) |
| CA certificates | Removes the emSign ECC Root CA G3 trust anchor after intermediates were issued with trivially guessable private keys. | [OpenWrt blacklist change](https://github.com/openwrt/openwrt/commit/63f702f1) |
| GNU patch and osafeloader | Updates the host patch tool for CVE-2026-56288, CVE-2026-56289 and CVE-2026-115207. Bounds the partition name scans used to inspect or extract firmware images. | [GNU patch update](https://github.com/openwrt/openwrt/commit/1356b3ab), [image parser](https://github.com/openwrt/openwrt/commit/d13ba979) |
| Block NVMEM | Saves the registration error before freeing its backing allocation. | [OpenWrt use-after-free fix](https://github.com/openwrt/openwrt/commit/5b3efb65) |

OpenWrt's dnsmasq commit lists CVE-2026-93006 through CVE-2026-93009 and
CVE-2026-93011 as possible mappings. The listed parser and resource fixes are
present in the patched source. The upstream CVE labels remain provisional.

## Kernel decisions

- Linux **6.18.60** follows [OpenWrt's stable bump](https://github.com/openwrt/openwrt/commit/5fb9d9cd).
  Earlier OpenWrt bump commits supplied the compatible patch refreshes for
  BCM27xx, Microchip, Qualcomm and Rockchip. The 6.18.60 changelog matched 28
  published Linux security records in the downloaded CVE repository snapshot.
  Relevant examples include [recursive IP-in-IP GSO segmentation](https://www.cve.org/CVERecord?id=CVE-2026-98853),
  [a coredump thread lifetime race](https://www.cve.org/CVERecord?id=CVE-2026-99218)
  and [a PID namespace teardown hang](https://www.cve.org/CVERecord?id=CVE-2026-99244).
- Linux **6.12.115** updates the seven retained targets using 6.12. It includes
  the three stable releases after 6.12.112, whose fix commits matched 917 unique
  published Linux CVE records in the same snapshot. Exposure depends on kernel
  configuration and installed modules. Patch refreshes preserve the existing
  ARP suppression, LoongArch vDSO flags, GSO features and FQ-CoDel defaults.
  The 6.12.114 update includes the WED `hif2` field, so the duplicate patch is removed.
- Both kernel lines receive the upstream [bridge VLAN deletion fix](https://github.com/torvalds/linux/commit/2842ce397dd09882530b42f7fdb0c855767eb24e)
  for [CVE-2026-98285](https://www.cve.org/CVERecord?id=CVE-2026-98285).
  Switchdev errors are logged while software VLAN deletion completes, avoiding
  inconsistent state and crashes during a flush.

Kernel archive SHA256 values were checked against [kernel.org's checksum list](https://cdn.kernel.org/pub/linux/kernel/v6.x/sha256sums.asc).
The CVE mapping uses the [Linux security database](https://kernel.googlesource.com/pub/scm/linux/security/vulns/)
and verifies each selected stable fix commit against the official changelogs.

## Deferred changes

- The dnsmasq capability reduction can break DNS and DHCP startup on MediaTek
  snapshots. [OpenWrt issue #26419](https://github.com/openwrt/openwrt/issues/26419)
- The PPP jail series changes credentials, hook privileges and device access.
  It needs Linux PPPoE and upgrade testing before adoption. [OpenWrt PPP jail series](https://github.com/openwrt/openwrt/pull/25537)
- The broader Wi-Fi, flow-offload and firewall feature series change runtime
  behavior across interacting packages. They need integration testing beyond
  the patch and build checks used here. The OpenWrt 6.12 removal would also
  require migrating the retained 6.12 targets as a separate update.

## Validation

GNU patch 2.8.1 applied all 50 kernel patch stacks with zero fuzz, including
592 MediaTek and 498 Ralink patches. All 192 wireless patches applied. The
patched p54 parser matches Linux 6.18.60, and the socket wrapper compiled for
AArch64 in the existing focused probe.

The selected package source archives matched their recipe hashes. dnsmasq
compiled natively and passed its configuration check with ubus disabled. The
patched musl `regcomp` compiled to an AArch64 ELF object. The json-c suite passed
all 28 tests after replacing `echo -n` with `printf` in the temporary macOS test
fixture. GNU patch passed 45 tests, with two skips and two expected failures.

All six device source checks passed. Repository tests passed 70 of 74, including
four tests with natively built signing tools. The four skips cover the historical
kernel kit comparison, two Ninja checks and Linux `/dev/full`. The previous
6.18.59 migration kit remains a historical artifact. Firmware compilation,
Linux service integration and hardware boot remain unverified.
