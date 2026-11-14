# AX3000T channel survey correction, 2026-11-15

mt76 release 4 rejects an older MT7981 channel MIB sample before subtracting
its counters from the previous sample. A TX counter falling from 1000 to 100
previously added `18446744073709550716` microseconds to the accumulated survey.
Patch 962 returns `-EINVAL` for that sample, frees its reply buffer, and leaves
all four totals and their previous baseline intact.

Keeping the baseline matters: independently clamping negative deltas while
rebasing to the older sample counts an interval again when the newer snapshot
returns. The new check rejects the whole sample if TX, BSS RX, combined RX, or
busy time goes backwards. The existing `chan_switch` path still establishes a
new baseline, including after a channel change or explicit counter reset.
The guard is limited to MT7981; other chip layouts retain their behavior.

This is an additional patch after the ten AX3000T audit patches introduced in
`89f77e46`. The MCU length/offset validation and bounded retries from patch 955
remain in place. The driver pin is still official mt76
`0936617dc529ff9da0385221d3fa6de732231177`; fetching official master on
2026-11-15 found the same revision. The Wi-Fi firmware blobs are unchanged.

The [upstream investigation](https://github.com/openwrt/mt76/issues/1135)
reports both unrelated MCU replies and MT7981 firmware alternating between
band snapshots. Its band echo is not reliable, so this change does not reject
replies based on that field. Offset validation addresses the unrelated reply;
patch 962 prevents underflow and duplicate accumulation when an accepted
snapshot goes backwards. It cannot identify an incorrect but increasing
per-band snapshot, and does not repair totals already corrupted in memory.

The production-function fixture in `tests/fixtures/` comes from the pinned
source after patch 955. Its regression test applies the actual patch 962 with
zero fuzz and compiles the before/after functions with AddressSanitizer and
UndefinedBehaviorSanitizer. It covers:

- The original 1000-to-100 counter overflow as a negative control.
- Both bands and decreases in each of the four accumulated counters.
- Sixteen alternating old/new snapshot pairs without duplicate accumulation.
- Normal increments and equal samples.
- Lower baselines during channel changes/counter resets.
- Stale, reordered, short and non-linear MCU replies, bounded retries,
  transport errors, buffer release, and the legacy MT7915 layout.

Run the repository checks with:

```sh
python3 scripts/device-build.py check-source
python3 -m unittest discover -s tests -v
```

Validation on 2026-11-15 used Python 3.12, the available Ninja binary, and
AddressSanitizer/UndefinedBehaviorSanitizer. All 13 package patches applied
with zero fuzz to the pinned upstream source; the fixture matched its
pre-fix function, and the function extracted from the complete patched source
passed the same regression probe. Source checks passed for Linux 6.18.63 and
all eight profiles. The 93-test suite passed 88 tests, then four additional
signing integration tests passed using the existing native host tools. The
remaining signing flush-failure test requires Linux `/dev/full` and was
skipped on macOS. The release verification script passed its shell syntax
check. Initial failures under the system Python 3.9 were resolved by using
the repository's required newer runtime; no source changes were needed.

The 6.18.63 migration kit contains the same patch and package release, updated
checksums, and accepts the previous release 3 state. On an otherwise current
tree the update changes only the mt76 recipe and adds patch 962. The installer
still checks compatibility before writes and preserves its backup/rollback
behavior. Rebuild mt76 and the firmware on Linux after updating source:

```sh
make package/kernel/mt76/clean
make package/kernel/mt76/compile -j2 V=s
make -j2 V=s
```

Source tests do not establish that this fixes the reported disappearance of
both SSIDs or poor 2.4 GHz throughput. A full firmware cross-build and an
AX3000T hardware run remain necessary. Capture failure-time logs and compare
WM/WA recovery counts to investigate that symptom.
