# Setting up a machine

On macOS (Apple silicon), one script installs everything ldraw-mecha needs
**inside this project**: portable tools in `bin/`, the LDraw parts library in
`data/ldraw`, the Python environment in `.venv`. Nothing goes to
`/Applications`, `~/.local` or your shell profile.

```sh
git clone https://github.com/anteloc/ldraw-mecha.git
cd ldraw-mecha
./setup-macos.sh
```

It ends by printing a few `export` lines. Add them to `~/.zshrc` yourself, then
open a new terminal, or restart VS Code, so your shell and agents (Claude Code,
Codex) see them.

Linux (`setup-linux.sh`) and Windows through WSL2 (`setup-win-wsl.sh`) are
planned. They will follow the same layout.

## Before you run it

- **Python 3.12+**, used through `.venv`.
- **git-lfs**: the parts database (`data/ldraw-info.db`) and the reference and
  sample assets are stored in Git LFS. The script stops if `git-lfs` is missing
  and asks you to run `brew install git-lfs`.

The script also downloads its own uv, so it doesn't depend on a global one.

## What it installs

| Item | Version | Location | Used for |
| --- | --- | --- | --- |
| uv | 0.9.3 | `bin/uv` | `.venv` and the two tools below |
| Python environment | | `.venv` (via `./setup.sh`) | `./ldraw-mecha`, tests |
| ldraw-xray | 0.5.0 | `bin/ldraw-xray` (uv tool, env in `bin/uv-tools/`) | `./ldraw-mecha xray` look boards |
| jev-rerank | 0.5.0 | `bin/jev-rerank` (uv tool) | Optional semantic search; needs `TYPESAFE_API_KEY` |
| Bun | 1.4.4 | `bin/bun` | Runs `bin/mpd2glb.mjs` |
| mpd2glb | 0.9.1 | `bin/mpd2glb.mjs` | GLB conversion (`scripts/mpd2glb.sh`) |
| Blender | 5.2.3 | `bin/Blender.app` | `rig`, animation, Blender checks |
| LeoCAD | 26.09 | `bin/LeoCAD.app` | ldraw-xray renders |
| LDraw parts library | latest `complete.zip` | `data/ldraw` | Everything |

It also runs `git lfs install --local` (this repository only) and
`git lfs pull`. uv's cache goes to `.cache/uv`, and any Python that uv
downloads goes to `bin/python`. Git ignores everything in `bin/` except
`bin/.gitkeep`, and it ignores `data/ldraw`.

## Re-running and upgrading

It's safe to re-run. Blender, LeoCAD, Bun and uv are skipped when they already
match their pinned version. ldraw-xray and jev-rerank are reinstalled from uv's
cache, and `mpd2glb.mjs` (1 MB) is always fetched again.

- **Bump a tool**: change its `*_VERSION` at the top of `setup-macos.sh`, then
  re-run.
- **Refresh the LDraw library**: `rm -rf data/ldraw`, then re-run.

## Configuration

Add the block that the script prints to `~/.zshrc`, for example:

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

`bin/` is deliberately left off `PATH`, so its uv and bun don't shadow your own.
ldraw-mecha finds each tool in this order, and fails if none of them has it:

1. an explicit option (`--blender`) or variable (`BLENDER_BIN`, `LEOCAD`);
2. `bin/` (`bin/Blender.app`, `bin/LeoCAD.app`, `bin/ldraw-xray`, `bin/jev-rerank`, `bin/bun`);
3. `PATH`.

To call a tool by hand, use its path, for example `bin/ldraw-xray doctor`.
ldraw-xray 0.5.0 is tested with LeoCAD 25.09, so `doctor` may warn that 26.09
is untested.

## Optional extras (not installed)

- `ffmpeg`: required only by `./add-sample.sh`. The plant catalog script also
  uses it, when present, to write an overview video (`brew install ffmpeg`).
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

Blender and LeoCAD save their preferences in `~/Library` when you open them,
like any macOS app.

## Uninstall

```sh
rm -rf bin/* data/ldraw .venv .cache/uv .cache/ldraw-xray   # keeps bin/.gitkeep
```

Then delete the `ldraw-mecha` block from `~/.zshrc`.
