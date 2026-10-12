# SPDX-License-Identifier: GPL-2.0-only
# /tmp is shared. Never chmod or write through a pre-existing untrusted path.

umask 077
PON_RUNTIME_DIR=/tmp/ponwrt

pon_private_dir() {
	local directory="$1"

	if ! mkdir -m 0700 "$directory" 2>/dev/null; then
		[ ! -L "$directory" ] && [ -d "$directory" ] &&
			[ "$(stat -c '%u:%a' "$directory")" = '0:700' ] || {
			echo "Unsafe PON runtime directory: $directory" >&2
			return 1
		}
	fi
}

pon_runtime_init() {
	pon_private_dir "$PON_RUNTIME_DIR" || return 1
	pon_private_dir "$PON_RUNTIME_DIR/$1"
}
