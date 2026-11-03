# Model selector

Browse the annotated models in `data/models-annotated/`, read their descriptions,
look at one in 3D and copy its path for the animation agent.

```sh
python3 model-selector/serve.py            # opens http://127.0.0.1:8770/
python3 model-selector/serve.py --port 9000 --no-open
```

Python 3.10+ standard library only. It needs `data/ldraw` and `bin/ldbi-viewer/`,
both installed by your system's `setup-*.sh` script ([docs/setup.md](../docs/setup.md)).

## What it does

1. **Index.** Every start rewrites `output/model-selector/models-annotated.json`
   with one `{name, path, url, description}` entry per `data/models-annotated/*.mpd`.
   If a file starts with `0 FILE`, its description is the second line.
   Otherwise the description is the first line. The leading `0 ` is removed.
2. **Serve.** It listens on `127.0.0.1` only.

| URL | Served from |
| --- | --- |
| `/` | `model-selector/model-selector.html`: the table |
| `/viewer.html` | `model-selector/viewer.html`: the 3D viewer |
| `/models-annotated.json` | the index above |
| `/models/<name>` | `data/models-annotated/` |
| `/ldraw/<path>` | `data/ldraw/` (`LDConfig.ldr`, textures) |
| `/ldraw-id/<id>` | `data/ldraw/parts/`, then `p/`, then `models/`: one request per part reference |
| `/vendor/<path>` | `bin/ldbi-viewer/` (ldbi + three.js r139 from ldraworg-library) |

## Pages

- **Table**: Name, Description (wrapped), **View 3D** and **Copy path**. Copy
  path puts the model's repository-relative path (for example
  `data/models-annotated/42000-1.mpd`) on the clipboard.
- **3D viewer** opens in a modal (✕, Esc or a click outside closes it). It is
  ldraw-nova's viewer, trimmed:
  - Rendering: Normal, High and Poly.
  - Camera: Inspect and Walk, plus Reset view.
  - Buttons: `.mpd` download and Copy path.
  - Removed: GLB loading, `.glb` download and animation playback. The header
    comment in `viewer.html` lists these changes.

## Continuing

- To change the description rule, edit `description()` in `serve.py`.
- To add a route, add an entry to `Handler.ROUTES`, or a special case in
  `Handler.translate_path`.
- To update the viewer from ldraw-nova, compare it with
  `../ldraw-nova-docker/web/viewer/viewer.html`, keep the trims listed above,
  and keep `/vendor/` in the script paths.
