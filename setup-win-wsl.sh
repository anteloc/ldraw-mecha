#!/bin/sh
# Set up ldraw-mecha on Windows, inside WSL2 (Ubuntu): WSL-specific checks, then
# the Linux setup, which installs everything inside this project (see setup-linux.sh).
#   ./setup-win-wsl.sh [--yes]   (passed on to setup-linux.sh)
# Run it in the Ubuntu terminal, from a clone in your Linux home (not /mnt/c).
# See docs/setup.md (Windows: WSL2).
set -eu

root=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)

die() { printf 'setup-win-wsl: %s\n' "$*" >&2; exit 2; }

# --- 1. Inside WSL2? -------------------------------------------------------------
# WSL2 kernels report e.g. "5.15.167.4-microsoft-standard-WSL2"; WSL1 has no "WSL2".
grep -q WSL2 /proc/sys/kernel/osrelease 2>/dev/null || die "run this inside WSL2.
In PowerShell, once:  wsl --install -d Ubuntu-24.04
then, in the Ubuntu terminal, clone the project into your Linux home and re-run."

# --- 2. In the Linux file system? ------------------------------------------------
# Windows drives (/mnt/c, ...) are slow from WSL and lose Linux file permissions.
case "$root" in
  /mnt/*) die "this clone is on a Windows drive ($root).
Clone it into your Linux home instead, e.g.
    git clone https://github.com/anteloc/ldraw-mecha.git ~/ldraw-mecha
then run ~/ldraw-mecha/setup-win-wsl.sh." ;;
esac

# --- 3. WSLg display (LeoCAD needs one; Blender does not) ------------------------
[ -n "${DISPLAY:-}${WAYLAND_DISPLAY:-}" ] ||
  echo "warning: no WSLg display; update WSL (wsl --update in PowerShell) so LeoCAD can render"

# --- 4. The Linux setup --------------------------------------------------------
exec "$root/setup-linux.sh" "$@"
