# Model selector

Find an annotated model in `data/models-annotated/` by set number or description,
look at it in 3D and copy its path for the animation agent.

```sh
python3 model-selector/serve.py            # opens http://127.0.0.1:8770/
python3 model-selector/serve.py --port 9000 --no-open
```

Python 3.10+ standard library only. It needs `data/ldraw` and `bin/ldbi-viewer/`,
both installed by your system's `setup-*.sh` script ([docs/setup.md](../docs/setup.md)).

## What it does

1. **Index.** Every start rewrites `output/model-selector/models-annotated.json`
   with one `{name, path, url, description, parts}` entry per `data/models-annotated/*.mpd`
   (about 1 s for 1,821 models).
   - **description:** if a file starts with `0 FILE`, the second line; otherwise the
     first line. The leading `0 ` is removed.
   - **parts:** the parts in the built model, counted the way the 3D viewer does. It
     starts from the first model with references, and counts each submodel once per
     use. A library part, or a part defined in the file (`0 FILE x.dat`), counts as one.
     Very large models can differ from the viewer by a few parts.
2. **Serve.** It listens on `127.0.0.1` only.

| URL | Served from |
| --- | --- |
| `/` | `model-selector/model-selector.html`: search and results |
| `/search.js` | `model-selector/search.js`: the fuzzy matcher |
| `/viewer.html` | `model-selector/viewer.html`: the 3D viewer |
| `/models-annotated.json` | the index above |
| `/models/<name>` | `data/models-annotated/` |
| `/ldraw/<path>` | `data/ldraw/` (`LDConfig.ldr`, textures) |
| `/ldraw-id/<id>` | `data/ldraw/parts/`, then `p/`, then `models/`: one request per part reference |
| `/vendor/<path>` | `bin/ldbi-viewer/` (ldbi + three.js r139 from ldraworg-library) |

## Pages

- **Search**: one box filters as you type. Matches are highlighted.
  - Every word must match the name or the description, in any order.
  - Case and accents are ignored.
  - A misspelled word (4+ letters, no digits) finds near matches (`defnder` finds
    Defender), but only when it matches nothing exactly.
  - Esc clears it. `/` jumps to it from anywhere on the page; this shortcut has no
    on-screen hint.
- **Sort by**:
  - **Best match** (the default): name matches first, then description words
    starting with the query, then the description containing it, then typo matches.
  - **Fewest parts (simplest)** and **Most parts (most complex)**: the part count is
    a rough guide to how complex a model is.
  - **Name**: natural order, so `2531-1` comes before `10001-1`.
  - Ties and an empty search are listed by name.
- The query and the sort are kept in `?q=` and `?sort=`, so a reload or a shared link
  keeps them.
- **Results**: one card per model with its name, part count, full description,
  **View 3D** and **Copy prompt**. Copy prompt puts
  `Animate the following model: data/models-annotated/42000-1.mpd` (the model's
  repository-relative path) on the clipboard and shows "Prompt copied to clipboard".
- **3D viewer** opens in a modal (✕, Esc or a click outside closes it). It is
  ldraw-nova's viewer, trimmed:
  - Rendering: Normal, High and Poly.
  - Camera: Inspect and Walk, plus Reset view.
  - Buttons: `.mpd` download and Copy prompt. Copy prompt asks the selector page, through
    `postMessage`, to show the same message. When the viewer is opened on its own, its
    status line shows it.
  - Removed: GLB loading, `.glb` download and animation playback. The header
    comment in `viewer.html` lists these changes.

## Continuing

- To change the description rule or the part count, edit `describe()` or
  `count_parts()` in `serve.py`.
- To change matching or ranking, edit the scores in `match()` in `search.js`. Its
  header comment lists them. It has no DOM code, so it can be tried with
  `bin/bun` on the index.
- To add a route, add an entry to `Handler.ROUTES`, or a special case in
  `Handler.translate_path`.
- To update the viewer from ldraw-nova, compare it with
  `../ldraw-nova-docker/web/viewer/viewer.html`, keep the trims listed above,
  and keep `/vendor/` in the script paths.
