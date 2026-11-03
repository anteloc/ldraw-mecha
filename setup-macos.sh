#!/bin/sh
# Set up ldraw-mecha on macOS (Apple silicon), self-contained in this project:
# portable tools in bin/, the LDraw library in data/ldraw, Python in .venv.
# Nothing is installed system-wide and no shell profile is edited.
#   ./setup-macos.sh
# Needs: git-lfs, Python 3.12+. Safe to re-run: up-to-date items are skipped.
# To bump a tool, change its version below and re-run. See docs/setup.md.
set -eu

# --- Versions -----------------------------------------------------------------
UV_VERSION=0.9.3
LDRAW_XRAY_VERSION=0.5.0
JEV_RERANK_VERSION=0.5.0
BUN_VERSION=1.4.4
MPD2GLB_VERSION=0.9.1
BLENDER_VERSION=5.2.3
LEOCAD_VERSION=26.09

root=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)
cd "$root"
bin=$root/bin
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT

# Keep everything uv writes inside the project, and use bin/ first while we run.
export UV_CACHE_DIR="$root/.cache/uv"
export UV_PYTHON_INSTALL_DIR="$bin/python"
export UV_TOOL_DIR="$bin/uv-tools"
export UV_TOOL_BIN_DIR="$bin"
export PATH="$bin:$PATH"

step() { printf '\n==> %s\n' "$*"; }
have() { command -v "$1" >/dev/null 2>&1; }
die() { printf 'setup-macos: %s\n' "$*" >&2; exit 2; }
fetch() { # URL FILE, with a progress bar on a terminal only
  if [ -t 2 ]; then curl -fL --progress-bar "$1" -o "$2"; else curl -fsSL "$1" -o "$2"; fi
}
app_is() { # NAME VERSION: is bin/NAME.app that version? (LeoCAD says 26.09.0)
  case "$(plutil -extract CFBundleVersion raw "$bin/$1.app/Contents/Info.plist" 2>/dev/null)" in
    "$2" | "$2".*) ;;
    *) return 1 ;;
  esac
}
install_app() { # NAME DMG_URL: copy NAME.app out of the disk image into bin/
  fetch "$2" "$tmp/$1.dmg"
  hdiutil attach -quiet -nobrowse -readonly -mountpoint "$tmp/mnt" "$tmp/$1.dmg"
  rm -rf "$bin/$1.app"
  ditto "$tmp/mnt/$1.app" "$bin/$1.app"
  hdiutil detach -quiet "$tmp/mnt"
}

# --- 1. Checks ----------------------------------------------------------------
step "Checks"
[ "$(uname -s)" = Darwin ] || die "this script is for macOS; see docs/setup.md"
[ "$(uname -m)" = arm64 ] || die "this script needs Apple silicon (arm64)"
have git-lfs || die "git-lfs is missing.
The parts database (data/ldraw-info.db) and the reference and sample assets are
stored with Git LFS; without it they are only small pointer files. Install it with
    brew install git-lfs
then re-run ./setup-macos.sh."
echo ok

# --- 2. Git LFS objects (this repository's config only) ------------------------
step "Git LFS objects"
git lfs install --local
git lfs pull

# --- 3. uv --------------------------------------------------------------------
step "uv $UV_VERSION"
case "$("$bin/uv" --version 2>/dev/null)" in
  "uv $UV_VERSION "* | "uv $UV_VERSION") echo "already installed" ;;
  *)
    fetch "https://github.com/astral-sh/uv/releases/download/$UV_VERSION/uv-aarch64-apple-darwin.tar.gz" "$tmp/uv.tar.gz"
    tar -xzf "$tmp/uv.tar.gz" --strip-components=1 -C "$bin"
    ;;
esac
command -v uv

# --- 4. Python environment (.venv) --------------------------------------------
step "Python environment"
./setup.sh

# --- 5. ldraw-xray and jev-rerank: isolated uv tools in bin/ --------------------
step "ldraw-xray $LDRAW_XRAY_VERSION and jev-rerank $JEV_RERANK_VERSION"
uv tool install --reinstall "https://github.com/anteloc/ldraw-xray/releases/download/v$LDRAW_XRAY_VERSION/ldraw_xray-$LDRAW_XRAY_VERSION-py3-none-any.whl"
uv tool install --reinstall "https://github.com/anteloc/jev-rerank/releases/download/v$JEV_RERANK_VERSION/jev_rerank-$JEV_RERANK_VERSION-py3-none-any.whl"

# --- 6. Bun (runs mpd2glb.mjs) ------------------------------------------------
step "Bun $BUN_VERSION"
if [ "$("$bin/bun" --version 2>/dev/null)" = "$BUN_VERSION" ]; then
  echo "already installed"
else
  fetch "https://github.com/oven-sh/bun/releases/download/bun-v$BUN_VERSION/bun-darwin-aarch64.zip" "$tmp/bun.zip"
  unzip -q -o -j "$tmp/bun.zip" 'bun-darwin-aarch64/bun' -d "$bin"
fi

# --- 7. mpd2glb (always fetched: it is small) ---------------------------------
step "mpd2glb $MPD2GLB_VERSION"
fetch "https://github.com/anteloc/mpd2glb/releases/download/v$MPD2GLB_VERSION/mpd2glb-$MPD2GLB_VERSION.zip" "$tmp/mpd2glb.zip"
unzip -q -o -j "$tmp/mpd2glb.zip" '*/mpd2glb.mjs' -d "$bin"

# --- 8. Blender (rigging, animation, checks) ----------------------------------
step "Blender $BLENDER_VERSION"
if app_is Blender "$BLENDER_VERSION"; then
  echo "already installed"
else
  install_app Blender "https://download.blender.org/release/Blender${BLENDER_VERSION%.*}/blender-$BLENDER_VERSION-macos-arm64.dmg"
fi

# --- 9. LeoCAD (ldraw-xray renders with it) -----------------------------------
step "LeoCAD $LEOCAD_VERSION"
if app_is LeoCAD "$LEOCAD_VERSION"; then
  echo "already installed"
else
  install_app LeoCAD "https://github.com/leozide/leocad/releases/download/v$LEOCAD_VERSION/LeoCAD-macOS-$LEOCAD_VERSION.dmg"
fi

# --- 10. LDraw parts library (delete data/ldraw to refresh it) -----------------
step "LDraw parts library"
if [ -d data/ldraw/parts ]; then
  echo "already installed"
else
  fetch https://library.ldraw.org/library/updates/complete.zip "$tmp/complete.zip"
  rm -rf data/ldraw
  unzip -q "$tmp/complete.zip" -d data
fi

# --- 11. Shell variables: printed for the user to add by hand -----------------
cat <<EOF

Done. Add these lines to ~/.zshrc, then open a new terminal (or restart VS Code)
so your shell and agents see them:

# >>> ldraw-mecha (from setup-macos.sh) >>>
export LDRAW_DIR="$root/data/ldraw"
export LDRAWDIR="\$LDRAW_DIR"
export BLENDER_BIN="$bin/Blender.app/Contents/MacOS/Blender"
export LEOCAD="$bin/LeoCAD.app/Contents/MacOS/LeoCAD"
export LDRAW_XRAY_CACHE="$root/.cache/ldraw-xray"
# export TYPESAFE_API_KEY=...   # optional: Jev semantic search (jev-rerank)
# <<< ldraw-mecha <<<

Then try:
  ./ldraw-mecha prepare data/models-annotated/106-1.mpd --recipe 106 --output output/study
  ./ldraw-mecha check output/study
  ./ldraw-mecha rig output/study --animate --reopen
EOF
