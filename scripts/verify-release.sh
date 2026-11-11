#!/bin/bash
# Verify every sysupgrade image before making it a release artifact.
set -euo pipefail
target_dir=${1:?Supply the target output directory}
verify_dir=$(mktemp -d "${RUNNER_TEMP:-/tmp}/ponwrt-verify.XXXXXX")
trap 'rm -rf "$verify_dir"' EXIT HUP INT TERM
mkdir "$verify_dir/keys"
cp key-build.pub "$verify_dir/keys/$(staging_dir/host/bin/usign -F -p key-build.pub)"

count=0
while IFS= read -r -d '' image; do
    staging_dir/host/bin/fwtool -q -i "$verify_dir/metadata" "$image"
    staging_dir/host/bin/fwtool -q -s "$verify_dir/certificate" "$image"
    staging_dir/host/bin/fwtool -q -T -s /dev/null "$image" |
        staging_dir/host/bin/ucert -V -m - -c "$verify_dir/certificate" -P "$verify_dir/keys"
    count=$((count + 1))
done < <(find "$target_dir" -type f \( -name '*-sysupgrade.bin' -o -name '*-sysupgrade.itb' \) -print0)

if [ "$count" -eq 0 ]; then
    echo 'No sysupgrade images were produced' >&2
    exit 1
fi
printf 'Verified %s signed sysupgrade images\n' "$count"
