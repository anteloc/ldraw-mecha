# Setting up a machine

One command installs what ldraw-mecha needs on macOS or Linux, and on Windows
through WSL2:

```sh
git clone https://github.com/anteloc/ldraw-mecha.git
cd ldraw-mecha
./bootstrap.sh
```

Then open a new terminal, or restart VS Code, so your shell and agents (Claude
Code, Codex) see the new variables. `bootstrap.sh` is safe to re-run: it keeps
whatever is already installed, re-runs `./setup.sh` (the Python environment) and
rewrites its block in your shell profile. It finishes with `ldraw-xray doctor`;
you're ready when it prints `ldraw-xray: renders`.

## What it installs

| Tool | Version | macOS | Linux | Used for |
| --- | --- | --- | --- | --- |
| Git LFS | current | Homebrew | apt | Parts database (`data/ldraw-info.db`), reference assets |
| uv | current | official installer, if missing | same | Python environment and the tools below |
| Bun | 1.4.2 | official installer, if missing | same | `scripts/mpd2glb.sh` (GLB conversion) |
| LDraw parts library | `complete.zip` | `~/ldraw-lib/ldraw` | same | Everything |
| Blender | 5.2 LTS | Homebrew `blender@lts` | 5.2.2 in `~/.local/opt/` | `rig`, animation, Blender checks |
| LeoCAD | 25.09 | release DMG, `/Applications` | release AppImage, unpacked in `~/.local/opt/` | ldraw-xray renders |
| ldraw-xray | 0.5.0 | uv tool | same | `./ldraw-mecha xray` look boards |
| jev-rerank | 0.5.0 | uv tool | same | Optional semantic search; needs `TYPESAFE_API_KEY` |
| Python 3.12 venv | | `./setup.sh` → `.venv` | same | `./ldraw-mecha`, tests |

On Linux it also installs, with `apt` and `sudo`, the libraries Blender and
LeoCAD need, plus `xvfb`. Other distributions get the package list to install
themselves. Linux needs x86_64: LeoCAD only ships x86_64 builds.

Not installed: `ffmpeg` (only for `./add-sample.sh`; `brew install ffmpeg` or
`sudo apt install ffmpeg`) and the Blender MCP server (see [Agents](#agents)).

## Windows: WSL2

The toolkit's scripts are POSIX shell, so on Windows it runs in WSL2's Ubuntu,
which is the Linux setup above. In PowerShell, once:

```powershell
wsl --install -d Ubuntu-24.04   # reboot if asked, then create your Linux user
```

In the Ubuntu terminal, clone into your Linux home (not `/mnt/c`, which is slow
and loses file permissions) and run the bootstrap:

```sh
git clone https://github.com/anteloc/ldraw-mecha.git ~/ldraw-mecha
cd ~/ldraw-mecha && ./bootstrap.sh
code .
```

`code .` opens VS Code connected to WSL (it installs the **WSL** extension).
Install Claude Code or Codex in that window, so agents run inside Ubuntu.
WSLg, in Windows 11 and current Windows 10 WSL, gives LeoCAD its display;
without it, follow the next section.

## Headless Linux

LeoCAD needs an X display. On a server, or WSL without WSLg, start a virtual
one, as the Docker image does:

```sh
Xvfb :99 -screen 0 1920x1080x24 &
export DISPLAY=:99
./bootstrap.sh                  # its last check renders a brick: "ldraw-xray: renders"
```

Start Xvfb again after each reboot, and keep `DISPLAY` set for agents.
`ldraw-xray doctor` alone reports `"renders": true` even without a display.

## Configuration

`bootstrap.sh` writes this block to `~/.zshenv` (zsh), or `~/.bashrc` and
`~/.profile` (bash), and replaces it on every run:

```sh
# >>> ldraw-mecha >>> (written by /home/me/ldraw-mecha/bootstrap.sh; re-run it to update)
export LDRAW_DIR="/home/me/ldraw-lib/ldraw"
export BLENDER_BIN="/home/me/.local/opt/blender-5.2.2/blender"
export LEOCAD="/home/me/.local/opt/leocad-25.09/AppRun"     # Linux only
case ":$PATH:" in ... PATH="/home/me/.local/bin:$PATH" ;; esac  # uv tools
case ":$PATH:" in ... PATH="/home/me/.bun/bin:$PATH" ;; esac    # bun
# <<< ldraw-mecha <<<
```

To use your own installs, set the variable for the first run, for example
`BLENDER_BIN=/path/to/blender LDRAW_DIR=/path/to/ldraw ./bootstrap.sh`.
`OPT_DIR` and `LDRAW_LIB` change where downloads go. Versions and checksums are
the variables at the top of `bootstrap.sh`.

**Upgrading** a pinned tool: change its version (and checksum) there, then
remove the old one so the next run installs the new one: `uv tool uninstall
ldraw-xray`, or `BLENDER_BIN= LEOCAD= ./bootstrap.sh` for Blender and LeoCAD on
Linux.

## Agents

Agents read `AGENTS.md` and `instructions.md` and use the variables above, so
start them after the bootstrap (restart VS Code). The workflow runs Blender in
the background and needs no Blender add-on. For live Blender inspection
([API guide](discovery-and-blender.md)), you can add the Blender Lab MCP add-on
and server by hand (<https://projects.blender.org/lab/blender_mcp>; the Docker
image uses 1.0.3) and register the server with `claude mcp add` or `codex mcp add`.

## Docker

The versions at the top of `bootstrap.sh` mirror the ARGs in
`ldraw-mecha-docker/Dockerfile`; change both together. The variables are the
ones the image sets as `ENV`. The script asks no questions and skips `sudo` as
root, so it also runs unattended in an Ubuntu container.

## Uninstall

Delete the `ldraw-mecha` block from your shell profile, then remove
`~/.local/opt/blender-*` and `~/.local/opt/leocad-*` (Linux), `~/ldraw-lib`,
`.venv`, and the tools: `uv tool uninstall ldraw-xray jev-rerank`. On macOS,
Blender and LeoCAD are in `/Applications` (`brew uninstall --cask blender@lts`).
