#!/usr/bin/env python3
"""LDraw annotated model selector: index data/models-annotated, then serve it.

    python3 model-selector/serve.py [--port 8770] [--no-open]

1. Writes output/model-selector/models-annotated.json (name, path, url, description).
2. Serves model-selector.html (table) and viewer.html (3D) on 127.0.0.1 only.

Standard library only. See model-selector/README.md.
"""

import argparse
import json
import webbrowser
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

HERE = Path(__file__).resolve().parent              # model-selector/
ROOT = HERE.parent                                  # the repository
MODELS = ROOT / "data" / "models-annotated"
LDRAW = ROOT / "data" / "ldraw"
VENDOR = ROOT / "bin" / "ldbi-viewer"               # fetched by setup-*.sh
INDEX = ROOT / "output" / "model-selector" / "models-annotated.json"


def description(mpd: Path) -> str:
    """The description is the line after "0 FILE"; without a "0 FILE" line it is the first line.
    Leading blank lines are skipped (e.g. 4906-1.mpd starts with one)."""
    with mpd.open(encoding="utf-8", errors="replace") as f:
        lines = (line for line in f if line.strip())
        first, second = next(lines, ""), next(lines, "")
    line = second if first.startswith("0 FILE") else first
    line = line.strip()
    return line[2:].strip() if line.startswith("0 ") else line


def build_index() -> list[dict]:
    models = [
        {
            "name": mpd.name,
            "path": mpd.relative_to(ROOT).as_posix(),     # what the user gives the agent
            "url": f"/models/{mpd.name}",                 # what the viewer loads
            "description": description(mpd),
        }
        for mpd in sorted(MODELS.glob("*.mpd"))
    ]
    INDEX.parent.mkdir(parents=True, exist_ok=True)
    INDEX.write_text(json.dumps(models, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    return models


def inside(root: Path, rel: str) -> Path | None:
    """root/rel, or None when it would leave root (../ tricks)."""
    path = (root / rel).resolve()
    return path if path.is_relative_to(root.resolve()) else None


def ldraw_by_id(part_id: str) -> Path | None:
    """A type-1 reference as LDraw resolves it: parts/, then p/, then models/.
    Same as ldraw-nova's /ldraw-id/ endpoint: one request per part, no 404 probing."""
    for sub in ("parts", "p", "models"):
        for name in (part_id, part_id.lower()):   # the library's file names are lowercase
            path = inside(LDRAW / sub, name)
            if path and path.is_file():
                return path
    return None


class Handler(SimpleHTTPRequestHandler):
    # URL prefix -> folder. Everything else comes from model-selector/ itself.
    ROUTES = {"/models/": MODELS, "/ldraw/": LDRAW, "/vendor/": VENDOR}
    extensions_map = {**SimpleHTTPRequestHandler.extensions_map,
                      ".mpd": "text/plain; charset=utf-8", ".ldr": "text/plain; charset=utf-8",
                      ".dat": "text/plain; charset=utf-8"}

    def translate_path(self, path: str) -> str:
        url = unquote(urlsplit(path).path)
        if url == "/":
            return str(HERE / "model-selector.html")
        if url == "/models-annotated.json":
            return str(INDEX)
        if url.startswith("/ldraw-id/"):
            found = ldraw_by_id(url[len("/ldraw-id/"):])
            return str(found or HERE / "missing")      # missing -> plain 404
        for prefix, root in self.ROUTES.items():
            if url.startswith(prefix):
                found = inside(root, url[len(prefix):])
                return str(found or HERE / "missing")
        found = inside(HERE, url.lstrip("/"))
        return str(found or HERE / "missing")

    def end_headers(self):
        self.send_header("Cache-Control", "no-cache")  # always the newest index and pages
        super().end_headers()

    def log_message(self, format, *args):           # quiet: only report errors
        if args and str(args[1])[:1] in "45":
            super().log_message(format, *args)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--port", type=int, default=8770)
    parser.add_argument("--no-open", action="store_true", help="don't open the browser")
    args = parser.parse_args()

    missing = [p for p in (LDRAW / "LDConfig.ldr", VENDOR / "js" / "ldraworgscene.js") if not p.is_file()]
    if missing:
        raise SystemExit(f"Missing {', '.join(str(p.relative_to(ROOT)) for p in missing)}: "
                         "run your system's setup-*.sh script (docs/setup.md).")

    models = build_index()
    print(f"Indexed {len(models)} models -> {INDEX.relative_to(ROOT)}")

    server = ThreadingHTTPServer(("127.0.0.1", args.port), partial(Handler, directory=str(HERE)))
    url = f"http://127.0.0.1:{args.port}/"
    print(f"Model selector at {url}  (Ctrl+C to stop)")
    if not args.no_open:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
