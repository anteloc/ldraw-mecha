#!/bin/sh
# Set up ldraw-mecha on Linux (x86_64), self-contained in this project:
# portable tools in bin/, the LDraw library in data/ldraw, Python in .venv.
# Nothing is installed system-wide and no shell profile is edited.
#   ./setup-linux.sh [--yes]   (--yes: install without asking for approval)
# Needs: the system packages checked in step 1 (Debian/Ubuntu names), Python 3.12+.
# Safe to re-run: up-to-date items are skipped. To bump a tool, change its
# version below and re-run. Windows: run ./setup-win-wsl.sh inside WSL2. See docs/setup.md.
set -eu

# --- Versions -----------------------------------------------------------------
UV_VERSION=0.9.3
LDRAW_XRAY_VERSION=0.5.0
JEV_RERANK_VERSION=0.5.0
LDRAW_ANNOTATOR_VERSION=0.5.0
BUN_VERSION=1.4.4
MPD2GLB_VERSION=0.9.1
BLENDER_VERSION=5.2.3
LEOCAD_VERSION=26.09
LDRAWORG_REF=a38efc7aca5b1171e888687939d77b6c0b228c7f   # 3D viewer (ldbi), as in ldraw-nova-docker

# --- System packages: Blender and LeoCAD are portable but use these libraries --
TOOL_PACKAGES="ca-certificates curl unzip xz-utils git git-lfs"
BLENDER_PACKAGES="libgl1 libegl1 libxrender1 libxi6 libxfixes3 libxkbcommon0 libsm6
  libice6 libxxf86vm1 libdbus-1-3 libgomp1 libglx-mesa0 libgl1-mesa-dri"
LEOCAD_PACKAGES="libosmesa6 libxkbcommon-x11-0 libxcb-cursor0 libxcb-icccm4 libxcb-image0
  libxcb-keysyms1 libxcb-randr0 libxcb-render-util0 libxcb-shape0 libxcb-xinerama0
  libnss3 fontconfig"

# --- Options ------------------------------------------------------------------
yes=0
case "${1:-}" in
  -y | --yes) yes=1 ;;   # approve without asking (e.g. no terminal)
  "") ;;
  *) echo "usage: ./setup-linux.sh [--yes]" >&2; exit 2 ;;
esac

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
die() { printf 'setup-linux: %s\n' "$*" >&2; exit 2; }
fetch() { # URL FILE, with a progress bar on a terminal only
  if [ -t 2 ]; then curl -fL --progress-bar "$1" -o "$2"; else curl -fsSL "$1" -o "$2"; fi
}
is_version() { # DIR VERSION: was bin/DIR installed at that version?
  [ "$(cat "$bin/$1/.version" 2>/dev/null)" = "$2" ]
}

# --- 1. Checks ----------------------------------------------------------------
step "Checks"
[ "$(uname -s)" = Linux ] || die "this script is for Linux; see docs/setup.md"
[ "$(uname -m)" = x86_64 ] || die "this script needs x86_64: LeoCAD ships x86_64 Linux builds only"
if have dpkg-query; then
  missing=
  for p in $TOOL_PACKAGES $BLENDER_PACKAGES $LEOCAD_PACKAGES; do
    # shellcheck disable=SC2016 # dpkg's own ${Status} field
    dpkg-query -W -f='${Status}' "$p" 2>/dev/null | grep -q 'ok installed' || missing="$missing $p"
  done
  [ -z "$missing" ] || die "missing system packages:$missing
curl, unzip and xz-utils fetch and unpack the downloads; git-lfs fetches the parts
database (data/ldraw-info.db) and the reference and sample assets, which are
otherwise only small pointer files; the lib* packages are the graphics and X11
libraries that the portable Blender and LeoCAD load from the system. Install them with
    sudo apt-get update && sudo apt-get install -y --no-install-recommends$missing
then re-run ./setup-linux.sh."
else
  echo "No dpkg: make sure your distribution's equivalents of these are installed:"
  echo "  $TOOL_PACKAGES $BLENDER_PACKAGES $LEOCAD_PACKAGES" | tr -s ' \n' ' '
  echo
  have git-lfs || die "git-lfs is missing: install it with your package manager, then re-run"
fi
echo ok

# --- Summary and approval: nothing has been changed so far ----------------------
row() { printf '  %-26s %s\n' "$1" "$2"; }
cat <<EOF

This will install ldraw-mecha's tools for Linux (x86_64), all inside
  $root

EOF
row "uv $UV_VERSION" "bin/uv, bin/uvx"
row "Python environment" ".venv (any Python uv downloads: bin/python)"
row "ldraw-xray $LDRAW_XRAY_VERSION" "bin/ldraw-xray (environment in bin/uv-tools/)"
row "jev-rerank $JEV_RERANK_VERSION" "bin/jev-rerank"
row "ldraw-annotator $LDRAW_ANNOTATOR_VERSION" "bin/ldraw-annotator"
row "Bun $BUN_VERSION" "bin/bun"
row "mpd2glb $MPD2GLB_VERSION" "bin/mpd2glb.mjs"
row "LDraw web viewer" "bin/ldbi-viewer/"
row "Blender $BLENDER_VERSION" "bin/blender/"
row "LeoCAD $LEOCAD_VERSION" "bin/leocad/ (unpacked AppImage)"
row "LDraw parts library" "data/ldraw (latest complete.zip)"
row "Git LFS files" "data/ldraw-info.db, reference and sample assets"
row "Download cache" ".cache/uv"
cat <<EOF

About 2 GB in total. Nothing is installed anywhere else: no sudo, no package
manager, nothing in /usr, /opt or ~/.local, and your shell profile is not
edited. Git LFS is enabled for this repository only (git lfs install --local).
Items already at these versions are skipped.

Afterwards:
  1. add the export lines printed at the end (LDRAW_DIR, BLENDER_BIN, ...) to
     ~/.bashrc and ~/.profile (bash), or ~/.zshenv (zsh);
  2. close VS Code, open a new terminal and start VS Code from it
     (code .), so your shell and agents (Claude Code, Codex) see them.
Uninstall: see docs/setup.md.

EOF
if [ "$yes" = 1 ]; then
  echo "Approved with --yes."
elif [ -t 0 ]; then
  printf 'Install? [y/N] '
  read -r answer || answer=
  case "$answer" in
    [yY] | [yY][eE][sS]) ;;
    *) echo "Cancelled: nothing was installed."; exit 1 ;;
  esac
else
  die "no terminal to ask for approval; re-run with --yes to install without asking"
fi

# --- 2. Git LFS objects (this repository's config only) ------------------------
step "Git LFS objects"
git lfs install --local
git lfs pull

# --- 3. uv --------------------------------------------------------------------
step "uv $UV_VERSION"
case "$("$bin/uv" --version 2>/dev/null)" in
  "uv $UV_VERSION "* | "uv $UV_VERSION") echo "already installed" ;;
  *)
    fetch "https://github.com/astral-sh/uv/releases/download/$UV_VERSION/uv-x86_64-unknown-linux-gnu.tar.gz" "$tmp/uv.tar.gz"
    tar -xzf "$tmp/uv.tar.gz" --strip-components=1 -C "$bin"
    ;;
esac
command -v uv

# --- 4. Python environment (.venv) --------------------------------------------
step "Python environment"
./setup.sh

# --- 5. ldraw-xray, jev-rerank, ldraw-annotator: isolated uv tools in bin/ -------
step "ldraw-xray $LDRAW_XRAY_VERSION, jev-rerank $JEV_RERANK_VERSION, ldraw-annotator $LDRAW_ANNOTATOR_VERSION"
uv tool install --reinstall "https://github.com/anteloc/ldraw-xray/releases/download/v$LDRAW_XRAY_VERSION/ldraw_xray-$LDRAW_XRAY_VERSION-py3-none-any.whl"
uv tool install --reinstall "https://github.com/anteloc/jev-rerank/releases/download/v$JEV_RERANK_VERSION/jev_rerank-$JEV_RERANK_VERSION-py3-none-any.whl"
uv tool install --reinstall "https://github.com/anteloc/ldraw-annotator-nova/releases/download/v$LDRAW_ANNOTATOR_VERSION/ldraw_annotator_nova-$LDRAW_ANNOTATOR_VERSION-py3-none-any.whl"

# --- 6. Bun (runs mpd2glb.mjs) ------------------------------------------------
step "Bun $BUN_VERSION"
if [ "$("$bin/bun" --version 2>/dev/null)" = "$BUN_VERSION" ]; then
  echo "already installed"
else
  fetch "https://github.com/oven-sh/bun/releases/download/bun-v$BUN_VERSION/bun-linux-x64.zip" "$tmp/bun.zip"
  unzip -q -o -j "$tmp/bun.zip" 'bun-linux-x64/bun' -d "$bin"
fi

# --- 7. mpd2glb (always fetched: it is small) ---------------------------------
step "mpd2glb $MPD2GLB_VERSION"
fetch "https://github.com/anteloc/mpd2glb/releases/download/v$MPD2GLB_VERSION/mpd2glb-$MPD2GLB_VERSION.zip" "$tmp/mpd2glb.zip"
unzip -q -o -j "$tmp/mpd2glb.zip" '*/mpd2glb.mjs' -d "$bin"

# --- 7b. 3D viewer for model-selector/: ldbi + three.js from ldraworg-library --
# -> bin/ldbi-viewer/{ldbi/js,ldbi/textures,js/ldraworgscene.js,js/WebGL.js}
# (delete bin/ldbi-viewer to refresh it)
step "LDraw web viewer (ldraworg-library $LDRAWORG_REF)"
if [ -f "$bin/ldbi-viewer/js/ldraworgscene.js" ]; then
  echo "already installed"
else
  fetch "https://codeload.github.com/ldraw-org/ldraworg-library/tar.gz/$LDRAWORG_REF" "$tmp/ldraworg.tar.gz"
  mkdir -p "$tmp/lor"
  tar -xzf "$tmp/ldraworg.tar.gz" -C "$tmp/lor" --strip-components=1 --wildcards '*/public/assets/*' '*/LICENSE'
  rm -rf "$bin/ldbi-viewer"
  mkdir -p "$bin/ldbi-viewer/js"
  cp -R "$tmp/lor/public/assets/ldbi" "$bin/ldbi-viewer/ldbi"
  cp "$tmp/lor/public/assets/js/ldraworgscene.js" "$tmp/lor/public/assets/js/WebGL.js" "$bin/ldbi-viewer/js/"
  cp "$tmp/lor/LICENSE" "$bin/ldbi-viewer/LICENSE-ldraworg-library.txt"
fi

# --- 8. Blender (rigging, animation, checks) ----------------------------------
step "Blender $BLENDER_VERSION"
if is_version blender "$BLENDER_VERSION"; then
  echo "already installed"
else
  fetch "https://download.blender.org/release/Blender${BLENDER_VERSION%.*}/blender-$BLENDER_VERSION-linux-x64.tar.xz" "$tmp/blender.tar.xz"
  rm -rf "$bin/blender"
  mkdir -p "$bin/blender"
  tar -xJf "$tmp/blender.tar.xz" --strip-components=1 -C "$bin/blender"
  echo "$BLENDER_VERSION" > "$bin/blender/.version"
fi

# --- 9. LeoCAD (ldraw-xray renders with it) -----------------------------------
step "LeoCAD $LEOCAD_VERSION"
if is_version leocad "$LEOCAD_VERSION"; then
  echo "already installed"
else
  fetch "https://github.com/leozide/leocad/releases/download/v$LEOCAD_VERSION/LeoCAD-Linux-$LEOCAD_VERSION-x86_64.AppImage" "$tmp/LeoCAD.AppImage"
  chmod +x "$tmp/LeoCAD.AppImage"
  # Unpack the AppImage instead of mounting it: no FUSE needed. It extracts to ./squashfs-root.
  (cd "$tmp" && ./LeoCAD.AppImage --appimage-extract >/dev/null)
  rm -rf "$bin/leocad"
  mv "$tmp/squashfs-root" "$bin/leocad"
  echo "$LEOCAD_VERSION" > "$bin/leocad/.version"
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

Done. Add these lines to ~/.bashrc and ~/.profile (bash) or ~/.zshenv (zsh), then
open a new terminal and start VS Code from it (code .) so your shell and agents see them:

# >>> ldraw-mecha (from setup-linux.sh) >>>
export LDRAW_DIR="$root/data/ldraw"
export LDRAWDIR="\$LDRAW_DIR"
export BLENDER_BIN="$bin/blender/blender"
export LEOCAD="$bin/leocad/AppRun"
export LDRAW_XRAY_CACHE="$root/.cache/ldraw-xray"
export LDRAW_ANNOTATOR_DB="$root/data/ldraw-info.db"
# export TYPESAFE_API_KEY=...   # optional: Jev semantic search (jev-rerank)
# <<< ldraw-mecha <<<
EOF
if [ -z "${DISPLAY:-}${WAYLAND_DISPLAY:-}" ]; then
  cat <<'EOF'

Note: no display found. LeoCAD (ldraw-xray renders) needs one; Blender does not.
On a headless machine, install xvfb and start a virtual display first:
  Xvfb :99 -screen 0 1920x1080x24 &
  export DISPLAY=:99
EOF
fi
