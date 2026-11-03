#!/bin/sh
# Set up this machine for ldraw-mecha, once: the tools, parts library and shell
# variables that ./setup.sh (the Python environment, run last) does not install.
#   ./bootstrap.sh          macOS (Homebrew) or Linux x86_64 (apt); Windows: inside WSL2
# Safe to re-run: whatever is already installed is kept. See docs/setup.md.
set -eu

# --- Versions: keep in sync with the ARGs in ../ldraw-mecha-docker/Dockerfile ----
: "${BLENDER_VERSION:=5.2.2}"
: "${BLENDER_SHA256:=84098912789dc450e95697c4184fb8a90acbe5111c2ba4aede3fecb57806a168}" # linux-x64
: "${LEOCAD_VERSION:=25.09}"
: "${LEOCAD_APPIMAGE_SHA256:=135140a17cd5d701a5d758907d88bff59e28d1f35277ef3fcac4d0a82e0ca467}"
: "${LEOCAD_DMG_SHA256:=6e4664f6d5a9c2ffe3855c2bfcdffc32f666efe759076d976818b28a911eb9d8}"
: "${BUN_VERSION:=1.4.2}"
: "${LDRAW_XRAY_VERSION:=0.5.0}"
: "${JEV_RERANK_VERSION:=0.5.0}"

# --- Where downloads go ---------------------------------------------------------
: "${OPT_DIR:=$HOME/.local/opt}"  # Linux: Blender and LeoCAD
: "${LDRAW_LIB:=$HOME/ldraw-lib}" # the LDraw parts library, unpacked as $LDRAW_LIB/ldraw

task_dir=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)
cd "$task_dir"
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT

step() { printf '\n==> %s\n' "$*"; }
have() { command -v "$1" >/dev/null 2>&1; }
die() { echo "bootstrap: $*" >&2; exit 2; }
fetch() { # URL FILE, with a progress bar on a terminal only
  if [ -t 2 ]; then curl -fL --progress-bar "$1" -o "$2"; else curl -fsSL "$1" -o "$2"; fi
}
verify() { # FILE SHA256
  if have sha256sum; then echo "$2  $1" | sha256sum -c -; else echo "$2  $1" | shasum -a 256 -c -; fi
}
as_root() { if [ "$(id -u)" -eq 0 ]; then "$@"; else sudo "$@"; fi; }

os=$(uname -s)
case "$os" in
  Darwin) ;;
  Linux) [ "$(uname -m)" = x86_64 ] || die "Linux needs x86_64: LeoCAD and Blender's pinned build are x86_64-only" ;;
  *) die "unsupported system $os; on Windows, run this inside WSL2 (docs/setup.md)" ;;
esac

# --- 1. System packages ---------------------------------------------------------
step "System packages"
if [ "$os" = Darwin ]; then
  have brew || die "install Homebrew first (https://brew.sh), then re-run"
  have git-lfs || brew install git-lfs
else
  # The Docker image's runtime set: tools, then Blender's libraries, then LeoCAD's
  # (Qt, X11, GL). xvfb gives LeoCAD a display on headless machines.
  packages="ca-certificates curl unzip xz-utils squashfs-tools python3 git git-lfs xvfb
    libgl1 libegl1 libxrender1 libxi6 libxfixes3 libxkbcommon0 libsm6 libice6 libxxf86vm1
    libdbus-1-3 libgomp1 libglx-mesa0 libgl1-mesa-dri libosmesa6 libxkbcommon-x11-0
    libxcb-cursor0 libxcb-icccm4 libxcb-image0 libxcb-keysyms1 libxcb-randr0
    libxcb-render-util0 libxcb-shape0 libxcb-xinerama0 libnss3 fontconfig"
  if have apt-get; then
    set --
    for p in $packages; do
      # shellcheck disable=SC2016 # dpkg's own ${Status} field
      dpkg-query -W -f='${Status}' "$p" 2>/dev/null | grep -q 'ok installed' || set -- "$@" "$p"
    done
    if [ $# -gt 0 ]; then
      as_root apt-get update
      as_root env DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends "$@"
    fi
  else
    echo "No apt-get: install your distribution's equivalents of: $packages"
  fi
fi

# --- 2. Git LFS objects (the parts database, reference assets) ------------------
if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  step "Git LFS objects"
  git lfs install
  git lfs pull
fi

# --- 3. uv and Bun: official installers, only when missing ----------------------
step "uv and Bun"
PATH="$HOME/.local/bin:$HOME/.bun/bin:$PATH"
if ! have uv; then
  fetch https://astral.sh/uv/install.sh "$tmp/uv.sh"
  sh "$tmp/uv.sh"
fi
if ! have bun; then
  fetch https://bun.sh/install "$tmp/bun.sh"
  bash "$tmp/bun.sh" "bun-v$BUN_VERSION"
fi
uv --version
echo "bun $(bun --version)"

# --- 4. LDraw parts library -----------------------------------------------------
step "LDraw parts library"
LDRAW_DIR=${LDRAW_DIR:-${LDRAWDIR:-$LDRAW_LIB/ldraw}}
if [ ! -d "$LDRAW_DIR/parts" ]; then
  [ "$LDRAW_DIR" = "$LDRAW_LIB/ldraw" ] || die "LDRAW_DIR=$LDRAW_DIR has no parts/ folder"
  fetch https://library.ldraw.org/library/updates/complete.zip "$tmp/complete.zip"
  mkdir -p "$LDRAW_LIB"
  unzip -q "$tmp/complete.zip" -d "$LDRAW_LIB"
fi
echo "LDRAW_DIR=$LDRAW_DIR"

# --- 5. Blender (rigging, animation, checks) ------------------------------------
step "Blender"
if [ -z "${BLENDER_BIN:-}" ]; then
  if [ "$os" = Darwin ]; then
    BLENDER_BIN=/Applications/Blender.app/Contents/MacOS/Blender
    [ -x "$BLENDER_BIN" ] || brew install --cask blender@lts
  else
    BLENDER_BIN=$OPT_DIR/blender-$BLENDER_VERSION/blender
    if [ ! -x "$BLENDER_BIN" ]; then
      fetch "https://download.blender.org/release/Blender${BLENDER_VERSION%.*}/blender-$BLENDER_VERSION-linux-x64.tar.xz" "$tmp/blender.tar.xz"
      verify "$tmp/blender.tar.xz" "$BLENDER_SHA256"
      mkdir -p "${BLENDER_BIN%/*}"
      tar -xJf "$tmp/blender.tar.xz" -C "${BLENDER_BIN%/*}" --strip-components=1
    fi
  fi
fi
[ -x "$BLENDER_BIN" ] || die "BLENDER_BIN=$BLENDER_BIN is not executable"
blender_version=$("$BLENDER_BIN" --version | head -n 1)
echo "$blender_version"
case "$blender_version" in
  "Blender 5.2"*) ;;
  *) echo "warning: ldraw-mecha is tested with Blender 5.2 LTS" ;;
esac

# --- 6. LeoCAD (ldraw-xray renders with it) -------------------------------------
step "LeoCAD"
LEOCAD=${LEOCAD:-}
if [ -z "$LEOCAD" ] && [ "$os" = Darwin ]; then
  # Homebrew's cask is disabled (Gatekeeper), so use the release's disk image.
  # ldraw-xray finds /Applications/LeoCAD.app by itself.
  if [ ! -d /Applications/LeoCAD.app ]; then
    fetch "https://github.com/leozide/leocad/releases/download/v$LEOCAD_VERSION/LeoCAD-macOS-$LEOCAD_VERSION.dmg" "$tmp/LeoCAD.dmg"
    verify "$tmp/LeoCAD.dmg" "$LEOCAD_DMG_SHA256"
    hdiutil attach -quiet -nobrowse -readonly -mountpoint "$tmp/dmg" "$tmp/LeoCAD.dmg"
    cp -R "$tmp/dmg/LeoCAD.app" /Applications/
    hdiutil detach -quiet "$tmp/dmg"
  fi
  echo "/Applications/LeoCAD.app"
elif [ -z "$LEOCAD" ]; then
  LEOCAD=$OPT_DIR/leocad-$LEOCAD_VERSION/AppRun
  if [ ! -x "$LEOCAD" ]; then
    fetch "https://github.com/leozide/leocad/releases/download/v$LEOCAD_VERSION/LeoCAD-Linux-$LEOCAD_VERSION-x86_64.AppImage" "$tmp/LeoCAD.AppImage"
    verify "$tmp/LeoCAD.AppImage" "$LEOCAD_APPIMAGE_SHA256"
    # An AppImage is an ELF runtime with a squashfs image appended right after its
    # section headers. Unpack that image directly, as ldraw-mecha-docker does: no
    # FUSE needed and nothing executed, so it also works under emulation.
    offset=$(python3 -c 'import struct,sys; h=open(sys.argv[1],"rb").read(64); shoff,=struct.unpack_from("<Q",h,0x28); shentsize,shnum=struct.unpack_from("<HH",h,0x3A); print(shoff+shentsize*shnum)' "$tmp/LeoCAD.AppImage")
    rm -rf "${LEOCAD%/*}"
    mkdir -p "$OPT_DIR"
    unsquashfs -q -no-progress -o "$offset" -d "${LEOCAD%/*}" "$tmp/LeoCAD.AppImage"
  fi
  echo "LEOCAD=$LEOCAD"
else
  echo "LEOCAD=$LEOCAD"
fi

# --- 7. ldraw-xray and jev-rerank: uv tools, from their release wheels ----------
step "ldraw-xray and jev-rerank"
have ldraw-xray || uv tool install "https://github.com/anteloc/ldraw-xray/releases/download/v$LDRAW_XRAY_VERSION/ldraw_xray-$LDRAW_XRAY_VERSION-py3-none-any.whl"
have jev-rerank || uv tool install "https://github.com/anteloc/jev-rerank/releases/download/v$JEV_RERANK_VERSION/jev_rerank-$JEV_RERANK_VERSION-py3-none-any.whl"
command -v ldraw-xray jev-rerank

# --- 8. Python environment ------------------------------------------------------
step "Python environment"
./setup.sh

# --- 9. Shell profile: the variables and PATH that agents and docs use ----------
step "Shell profile"
{
  echo "# >>> ldraw-mecha >>> (written by $task_dir/bootstrap.sh; re-run it to update)"
  echo "export LDRAW_DIR=\"$LDRAW_DIR\""
  echo "export BLENDER_BIN=\"$BLENDER_BIN\""
  [ -z "$LEOCAD" ] || echo "export LEOCAD=\"$LEOCAD\""
  for d in "$(uv tool dir --bin)" "$(dirname "$(command -v bun)")"; do
    # shellcheck disable=SC2016 # $PATH expands in the user's shell
    printf 'case ":$PATH:" in *":%s:"*) ;; *) PATH="%s:$PATH" ;; esac\n' "$d" "$d"
  done
  echo "# <<< ldraw-mecha <<<"
} > "$tmp/block"
# zsh reads ~/.zshenv in every shell, agents' `zsh -c` included; bash needs both.
case "${SHELL:-sh}" in
  */zsh) set -- "$HOME/.zshenv" ;;
  */bash) set -- "$HOME/.bashrc" "$HOME/.profile" ;;
  *) set -- "$HOME/.profile" ;;
esac
for f in "$@"; do
  touch "$f"
  sed '/^# >>> ldraw-mecha >>>/,/^# <<< ldraw-mecha <<</d' "$f" > "$tmp/profile"
  cat "$tmp/profile" "$tmp/block" > "$f"
  echo "updated $f"
done
cat "$tmp/block"

# --- 10. Check --------------------------------------------------------------------
step "Check"
export LDRAW_DIR BLENDER_BIN
[ -z "$LEOCAD" ] || export LEOCAD
./ldraw-mecha --help >/dev/null && echo "ldraw-mecha: ok"
# Render one brick: `ldraw-xray doctor` alone doesn't notice a missing display.
printf '0 FILE brick.ldr\n1 4 0 0 0 1 0 0 0 1 0 0 0 1 3001.dat\n' > "$tmp/brick.mpd"
if ldraw-xray render "$tmp/brick.mpd" --output "$tmp/render" > "$tmp/render.json" 2>&1; then
  echo "ldraw-xray: renders"
else
  cat "$tmp/render.json"
  echo "warning: ldraw-xray cannot render yet; see 'ldraw-xray doctor'." \
    "Without a display, see docs/setup.md (Headless Linux)."
fi

cat <<EOF

Done. Open a new terminal (or restart VS Code) so agents see these variables, then try:
  ./ldraw-mecha prepare data/models-annotated/106-1.mpd --recipe 106 --output output/study
  ./ldraw-mecha check output/study
  ./ldraw-mecha rig output/study --animate --reopen
EOF
