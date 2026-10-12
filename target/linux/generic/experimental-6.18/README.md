# Inactive BBRv3 experiment

This directory is not part of the OpenWrt kernel patch stack. The preserved
BBRv3 patch was written for Linux 6.18.52 and bundles stable TCP/MPTCP changes
that are already in Linux 6.18.55. It must be rebased and compiled before use.

Current builds use the upstream `tcp_bbr` implementation selected by
`CONFIG_PACKAGE_kmod-tcp-bbr`. Do not copy this patch into `hack-6.18` without
reviewing the TCP/MPTCP conflicts and testing both targets and congestion control.
