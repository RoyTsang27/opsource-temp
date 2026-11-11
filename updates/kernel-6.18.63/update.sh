#!/bin/sh
# Run from the OpenWrt/ImmortalWrt build root, or pass its path as an argument.
set -eu
kit_dir=$(CDPATH= cd "$(dirname "$0")" && pwd)
if ! command -v python3 >/dev/null 2>&1; then
    echo 'Python 3.8 or newer is required. Install python3 and run this command again.' >&2
    exit 1
fi
export PYTHONDONTWRITEBYTECODE=1
exec python3 "$kit_dir/update.py" "$@"
