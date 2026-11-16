#!/usr/bin/env bash
# Compile the pinned wireless stack with the already-built target kernel.
set -euo pipefail

: "${RUNNER_TEMP:?}" "${ARCH:?}" "${CROSS_COMPILE:?}" "${SUBTARGET:?}"
kernel="$RUNNER_TEMP/kernel"
backports="$RUNNER_TEMP/backports"
mt76="$RUNNER_TEMP/mt76"

mapfile -t pins < <(python3 - <<'PY'
from pathlib import Path
import re
def value(path, key):
    text = Path(path).read_text()
    return re.search(r'^' + key + r'\s*:?=\s*(\S+)\s*$', text, re.M)[1]
for path, keys in (
    ('package/kernel/mac80211/Makefile', ('PKG_SOURCE_VERSION', 'PKG_HASH')),
    ('package/kernel/mt76/Makefile', ('PKG_SOURCE_DATE', 'PKG_SOURCE_VERSION', 'PKG_MIRROR_HASH')),
):
    for key in keys:
        print(value(path, key))
PY
)
test "${#pins[@]}" = 5
bp_version="${pins[0]}"
mt_version="${pins[2]//-/.}~${pins[3]:0:8}"

curl --fail --location --retry 3 "https://sources.openwrt.org/backports-$bp_version.tar.zst" \
  --output "$RUNNER_TEMP/backports.tar.zst"
printf '%s  %s\n' "${pins[1]}" "$RUNNER_TEMP/backports.tar.zst" | sha256sum --check --strict
mkdir "$backports"
tar --zstd -xf "$RUNNER_TEMP/backports.tar.zst" --strip-components=1 -C "$backports"
for series in build subsys ath ath5k ath9k ath10k ath11k ath12k rt2x00 mt7601u mwl brcm rtl; do
  patch_dir="package/kernel/mac80211/patches/$series"
  if [ -d "$patch_dir" ]; then
    PATCH='patch --fuzz=0' scripts/patch-kernel.sh "$backports" "$patch_dir"
  fi
done
# Match the package's preparation: use these headers from the target kernel.
rm -rf "$backports/include/linux/ssb" "$backports/include/linux/bcma" "$backports/include/net/bluetooth"
for header in cordic crc8 eeprom_93cx6 wl12xx mhi; do
  rm -f "$backports/include/linux/$header.h"
done
rm -f "$backports/include/net/ieee80211.h" "$backports/backport-include/linux/bcm47xx_nvram.h"

cat > "$backports/.config" <<'EOF'
CPTCFG_WLAN=y
CPTCFG_CFG80211=m
CPTCFG_CFG80211_CERTIFICATION_ONUS=y
CPTCFG_NL80211_TESTMODE=y
CPTCFG_CFG80211_DEBUGFS=y
CPTCFG_MAC80211=m
CPTCFG_MAC80211_RC_MINSTREL=y
CPTCFG_MAC80211_RC_MINSTREL_HT=y
CPTCFG_MAC80211_RC_DEFAULT_MINSTREL=y
CPTCFG_MAC80211_DEBUGFS=y
CPTCFG_MAC80211_MESH=y
CPTCFG_MAC80211_LEDS=y
EOF
make -C "$backports" KLIB_BUILD="$kernel" KERNEL_SUBLEVEL=3 olddefconfig
make -C "$backports" KLIB_BUILD="$kernel" KERNEL_SUBLEVEL=3 -j"$(nproc)" modules
test -f "$backports/net/wireless/cfg80211.ko"
test -f "$backports/net/mac80211/mac80211.ko"
cp "$backports/.config" logs/wireless.config

curl --fail --location --retry 3 "https://sources.openwrt.org/mt76-$mt_version.tar.zst" \
  --output "$RUNNER_TEMP/mt76.tar.zst"
printf '%s  %s\n' "${pins[4]}" "$RUNNER_TEMP/mt76.tar.zst" | sha256sum --check --strict
mkdir "$mt76"
tar --zstd -xf "$RUNNER_TEMP/mt76.tar.zst" --strip-components=1 -C "$mt76"
PATCH='patch --fuzz=0' scripts/patch-kernel.sh "$mt76" package/kernel/mt76/patches
compiler_includes="$("${CROSS_COMPILE}gcc" -print-file-name=include)"
includes="-nostdinc -isystem $compiler_includes -I$mt76 -I$backports/backport-include -I$backports/backport-include/uapi -I$backports/include -I$backports/include/uapi"
includes+=" -include backport/autoconf.h -include backport/backport.h -DCONFIG_MAC80211_MESH -DCONFIG_NL80211_TESTMODE"
drivers=(CONFIG_MT7603E=m CONFIG_MT7615_COMMON=m CONFIG_MT7615E=m CONFIG_MT76_CONNAC_LIB=m)
if [ "$SUBTARGET" = filogic ]; then
  drivers+=(CONFIG_MT7915E=m CONFIG_MT798X_WMAC=y)
  includes+=" -DCONFIG_MT798X_WMAC"
fi
make -C "$kernel" M="$mt76" -j"$(nproc)" \
  NOSTDINC_FLAGS="$includes" KBUILD_EXTRA_SYMBOLS="$backports/Module.symvers" \
  CONFIG_NL80211_TESTMODE=y "${drivers[@]}" modules
test -f "$mt76/mt7603/mt7603e.ko"
test -f "$mt76/mt7615/mt7615e.ko"
if [ "$SUBTARGET" = filogic ]; then
  test -f "$mt76/mt7915/mt7915e.ko"
fi
