#!/usr/bin/env bash
# Check every board tree and the PON modules against the prepared target kernel.
set -euo pipefail
: "${RUNNER_TEMP:?}" "${ARCH:?}" "${CROSS_COMPILE:?}" "${SUBTARGET:?}"
kernel="$RUNNER_TEMP/kernel"
output="$RUNNER_TEMP/airoha-dtbs"
mkdir -p "$output"
for source in target/linux/airoha/dts/"$SUBTARGET"-*.dts; do
  name="${source##*/}"
  "${CROSS_COMPILE}gcc" -E -nostdinc -x assembler-with-cpp -undef -D__DTS__ \
    -I"$kernel/include" -I"$kernel/arch/$ARCH/boot/dts/airoha" \
    "$source" -o "$output/$name"
  "$kernel/scripts/dtc/dtc" -@ -I dts -O dtb \
    -i target/linux/airoha/dts -o "$output/${name%.dts}.dtb" "$output/$name"
  test -s "$output/${name%.dts}.dtb"
done
if [ "$ARCH" != arm64 ]; then
  exit 0
fi
frontend="$RUNNER_TEMP/airoha-pon-frontends"
xpon="$RUNNER_TEMP/airoha-xpon"
mkdir -p "$frontend" "$xpon"
cp -a package/pon/drivers/airoha-pon-frontends/src/. "$frontend/"
cp -a package/pon/drivers/airoha-xpon/src/. "$xpon/"
make -C "$kernel" M="$frontend" -j"$(nproc)" modules
for module in airoha-pon-frontend-core airoha-en7572 airoha-paged-bosa; do
  test -s "$frontend/$module.ko"
done
make -C "$kernel" M="$xpon" AIROHA_PON_FRONTEND_INCLUDE="$frontend" \
  KBUILD_EXTRA_SYMBOLS="$frontend/Module.symvers" -j"$(nproc)" modules
test -s "$xpon/airoha-xpon.ko"
