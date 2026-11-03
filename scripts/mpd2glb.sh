#!/bin/bash

script_dir="$(dirname "$0")"
script_dir="$(realpath "$script_dir")"
bin_dir="$(dirname "$script_dir")/bin"

mjs="$bin_dir/mpd2glb.mjs"
[ -f "$mjs" ] || { echo "mpd2glb: $mjs not found: run ./setup-macos.sh" >&2; exit 2; }

# bun from bin/, else PATH.
bun="$bin_dir/bun"
[ -x "$bun" ] || bun="$(command -v bun)" || { echo "mpd2glb: bun not found: run ./setup-macos.sh" >&2; exit 2; }

# exec: bun takes this process's place, so stopping it (e.g. the web app's
# time limit) stops the conversion too.
exec "$bun" "$mjs" "$@"
