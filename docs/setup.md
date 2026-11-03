# Setting up a machine

One script per system installs everything ldraw-mecha needs **inside this
project**: portable tools in `bin/`, the LDraw parts library in `data/ldraw`, the
Python environment in `.venv`. Nothing goes to `/Applications`, `~/.local`,
`/opt` or your shell profile.

| System | Script | Needs beforehand |
| --- | --- | --- |
| macOS, Apple silicon | `./setup-macos.sh` | git-lfs (`brew install git-lfs`) |
| Linux, x86_64 | `./setup-linux.sh` | git-lfs and the graphics libraries Blender and LeoCAD load (it prints the `apt-get` command) |
| Windows | `./setup-win-wsl.sh`, inside WSL2 | WSL2 with Ubuntu; then as Linux |

All three also need **Python 3.12+**, used through `.venv`. Each downloads its
own uv, so none of them depends on a global one.

```sh
git clone https://github.com/anteloc/ldraw-mecha.git
cd ldraw-mecha
./setup-macos.sh            # or ./setup-linux.sh, ./setup-win-wsl.sh
```

The scripts never use `sudo` or a package manager. When something from the table
is missing they stop, explain why it's needed and print the command to install it;
install it and re-run. At the end they print a few `export` lines for you to add
to your shell profile (see [Configuration](#configuration)).

## What gets installed

| Item | Version | macOS location | Linux / WSL location | Used for |
| --- | --- | --- | --- | --- |
| uv | 0.9.3 | `bin/uv` | same | `.venv` and the two tools below |
| Python environment | | `.venv` (via `./setup.sh`) | same | `./ldraw-mecha`, tests |
| ldraw-xray | 0.5.0 | `bin/ldraw-xray` (uv tool, env in `bin/uv-tools/`) | same | `./ldraw-mecha xray` look boards |
| jev-rerank | 0.5.0 | `bin/jev-rerank` (uv tool) | same | Optional semantic search; needs `TYPESAFE_API_KEY` |
| Bun | 1.4.4 | `bin/bun` | same | Runs `bin/mpd2glb.mjs` |
| mpd2glb | 0.9.1 | `bin/mpd2glb.mjs` | same | GLB conversion (`scripts/mpd2glb.sh`) |
| LDraw web viewer (ldbi + three.js) | ldraworg-library `a38efc7` | `bin/ldbi-viewer/` | same | 3D view in `model-selector/` |
| Blender | 5.2.3 | `bin/Blender.app` | `bin/blender/` | `rig`, animation, Blender checks |
| LeoCAD | 26.09 | `bin/LeoCAD.app` | `bin/leocad/` (unpacked AppImage) | ldraw-xray renders |
| LDraw parts library | latest `complete.zip` | `data/ldraw` | same | Everything |

The scripts also run `git lfs install --local` (this repository only) and
`git lfs pull`. uv's cache goes to `.cache/uv`, and any Python that uv
downloads goes to `bin/python`. Git ignores everything in `bin/` except
`bin/.gitkeep`, and it ignores `data/ldraw`.

## Linux

Linux needs x86_64, because LeoCAD only ships x86_64 builds. Blender and LeoCAD
are portable, but they load graphics and X11 libraries from the system. On
Debian and Ubuntu, `setup-linux.sh` checks these with `dpkg` and prints the
`sudo apt-get install` line for any that are missing. On other distributions it
lists the Debian package names for you to translate.

LeoCAD needs a display. Blender doesn't, because the workflow runs it in the
background. A desktop session works as it is. On a headless machine, install
`xvfb` and start a virtual display before rendering:

```sh
Xvfb :99 -screen 0 1920x1080x24 &
export DISPLAY=:99
```

Start Xvfb again after each reboot, and keep `DISPLAY` set for agents.

## Windows: WSL2

The toolkit runs in WSL2's Ubuntu. In PowerShell, once:

```powershell
wsl --install -d Ubuntu-24.04   # reboot if asked, then create your Linux user
```

In the Ubuntu terminal, clone into your Linux home. Don't clone under `/mnt/c`:
it's slow and loses file permissions, so the script refuses to run there.

```sh
git clone https://github.com/anteloc/ldraw-mecha.git ~/ldraw-mecha
cd ~/ldraw-mecha && ./setup-win-wsl.sh
code .
```

`setup-win-wsl.sh` checks that it runs inside WSL2, from the Linux file system,
with a WSLg display. It then runs `setup-linux.sh`, so the
[Linux](#linux) notes apply too. `code .` opens VS Code connected to WSL (it
installs the **WSL** extension). Install Claude Code or Codex in that window, so
agents run inside Ubuntu. WSLg, in Windows 11 and current Windows 10 WSL, gives
LeoCAD its display. If it's missing, run `wsl --update`.

## Re-running and upgrading

It's safe to re-run. Blender, LeoCAD, Bun and uv are skipped when they already
match their pinned version. ldraw-xray and jev-rerank are reinstalled from uv's
cache, and `mpd2glb.mjs` (1 MB) is always fetched again.

- **Bump a tool**: change its `*_VERSION` at the top of the script, then re-run.
  The versions are repeated in `setup-macos.sh` and `setup-linux.sh`; keep them
  in step.
- **Refresh the LDraw library**: `rm -rf data/ldraw`, then re-run.
- **Refresh the web viewer**: change `LDRAWORG_REF`, `rm -rf bin/ldbi-viewer`, then re-run.

## Configuration

Add the block the script prints to your shell profile:

- **macOS (zsh):** `~/.zshrc`, or `~/.zshenv`, which non-interactive shells also
  read.
- **Linux and WSL (bash):** `~/.bashrc` and `~/.profile`.
- **Linux and WSL (zsh):** `~/.zshenv`.

Then open a new terminal, and start or restart VS Code from it, so your shell
and agents (Claude Code, Codex) see the variables. On macOS the block looks like
this:

```sh
# >>> ldraw-mecha (from setup-macos.sh) >>>
export LDRAW_DIR="/Users/me/ldraw-mecha/data/ldraw"
export LDRAWDIR="$LDRAW_DIR"
export BLENDER_BIN="/Users/me/ldraw-mecha/bin/Blender.app/Contents/MacOS/Blender"
export LEOCAD="/Users/me/ldraw-mecha/bin/LeoCAD.app/Contents/MacOS/LeoCAD"
export LDRAW_XRAY_CACHE="/Users/me/ldraw-mecha/.cache/ldraw-xray"
# export TYPESAFE_API_KEY=...   # optional: Jev semantic search (jev-rerank)
# <<< ldraw-mecha <<<
```

On Linux and WSL, `BLENDER_BIN` is `.../bin/blender/blender` and `LEOCAD` is
`.../bin/leocad/AppRun`.

`bin/` is deliberately left off `PATH`, so its uv and bun don't shadow your own.
ldraw-mecha finds each tool in this order, and fails if none of them has it:

1. an explicit option (`--blender`) or variable (`BLENDER_BIN`, `LEOCAD`);
2. `bin/`: Blender and LeoCAD at the locations in the table above, then
   `bin/ldraw-xray`, `bin/jev-rerank` and `bin/bun`;
3. `PATH`.

To call a tool by hand, use its path, for example `bin/ldraw-xray doctor`.
ldraw-xray 0.5.0 is tested with LeoCAD 25.09, so `doctor` may warn that 26.09
is untested.

## Optional extras (not installed)

- `ffmpeg`: required only by `./add-sample.sh`. The plant catalog script also
  uses it, when present, to write an overview video (`brew install ffmpeg` or
  `sudo apt install ffmpeg`).
- ImageMagick `montage`: when present, two catalog scripts use it to stitch
  3×3 contact sheets; without it they skip that step.

## Agents

Agents read `AGENTS.md` and `instructions.md` and use the variables above, so
start them after setup (restart VS Code). The workflow runs Blender in the
background and needs no Blender add-on. For live Blender inspection
([API guide](discovery-and-blender.md)), you can add the Blender Lab MCP add-on
and server by hand (<https://projects.blender.org/lab/blender_mcp>) and register
the server with `claude mcp add` or `codex mcp add`.

## What still lands outside the project

When you open Blender and LeoCAD, they save their preferences in your user
folders: `~/Library` on macOS, `~/.config` on Linux.

## Uninstall

```sh
rm -rf bin/* data/ldraw .venv .cache/uv .cache/ldraw-xray   # keeps bin/.gitkeep
```

Then delete the `ldraw-mecha` block from your shell profile. On Linux, the
system packages stay installed; remove them with `apt` if nothing else uses them.
