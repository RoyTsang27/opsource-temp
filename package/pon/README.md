# Integrated PON packages

These are maintained copies of the two pbs05 PON repositories, at the commits
recorded in `upstream.json`, with the local changes described in
[the PON audit](../../docs/PON-SECURITY-AUDIT.md). Original licenses, source
headers, firmware, documentation and Cargo lockfiles are retained.

The package sources live here, rather than in external feeds. Feed updates
cannot replace the audited copies. AN7581 and AN7583 select the frontend core,
xPON driver, control utility, protocol daemon, diagnostic tools and both LuCI
apps by default. Optical frontend modules are still selected by each device.
Packet capture and IPTV configuration remain disabled until the administrator
enables them. EN7523 does not support these drivers.

When updating, compare both upstream trees against `upstream.json`, preserve
local security changes, update the recorded commits and package releases, and
run the security checks and both Airoha kernel/PON package builds. Never add
these repositories back as feeds alongside these built-in packages.

Existing PON feed symlinks are ignored by the package scanner, so an older
checkout cannot override these copies. For housekeeping, run `./scripts/feeds
uninstall -a` followed by the normal feed update/install steps after switching
to this branch. Use the new `feeds.conf.release` or `feeds.conf.default`; a
previously copied `feeds.conf` may still list the removed external PON feeds.
