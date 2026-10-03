#!/bin/bash

script_dir="$(dirname "$0")"
script_dir="$(realpath "$script_dir")"
bin_dir="$(dirname "$script_dir")/bin"

mjs="$bin_dir/mpd2glb.mjs"

# exec: bun takes this process's place, so stopping it (e.g. the web app's
# time limit) stops the conversion too.
exec bun "$mjs" "$@"
