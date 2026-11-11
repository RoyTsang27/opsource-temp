#!/bin/sh
# Load stable keys only after all source downloads and host-tool builds finish.
set -eu
umask 077

: "${PONWRT_APK_PRIVATE_KEY:?Set PONWRT_APK_PRIVATE_KEY in the release environment}"
: "${PONWRT_USIGN_PRIVATE_KEY:?Set PONWRT_USIGN_PRIVATE_KEY in the release environment}"
: "${PONWRT_USIGN_PUBLIC_KEY:?Set PONWRT_USIGN_PUBLIC_KEY in the release environment}"

printf '%s\n' "$PONWRT_APK_PRIVATE_KEY" > private-key.pem
openssl pkey -in private-key.pem -check -noout
openssl pkey -in private-key.pem -pubout -out public-key.pem
printf '%s\n' "$PONWRT_USIGN_PRIVATE_KEY" > key-build
printf '%s\n' "$PONWRT_USIGN_PUBLIC_KEY" > key-build.pub

key_test_dir=$(mktemp -d "${RUNNER_TEMP:-/tmp}/ponwrt-key-test.XXXXXX")
trap 'rm -rf "$key_test_dir"' EXIT HUP INT TERM
printf '%s\n' 'PonWrt release key pair validation' > "$key_test_dir/message"
staging_dir/host/bin/usign -S -m "$key_test_dir/message" -s key-build -x "$key_test_dir/signature"
staging_dir/host/bin/usign -V -m "$key_test_dir/message" -p key-build.pub -x "$key_test_dir/signature"
staging_dir/host/bin/ucert -I -c key-build.ucert -p key-build.pub -s key-build
