#!/usr/bin/env python3
"""Write a standalone MPD holding only chosen occurrences, in the source's own frame.

Each kept physical occurrence becomes one type-1 line in a single main FILE,
with its composed world matrix and effective colour, preceded by a comment
naming its original occurrence ID. Embedded `.dat` FILE blocks those parts use
(and their own sub-files) are copied verbatim. Everything else is left out.
Because the root is the identity, coordinates equal the source selection's, so
a motion plan authored on the source can be reused after remapping IDs.

    .venv/bin/python scripts/extract_subsystem.py \
        output/42110-suspension/source/42110-1-shocks-split.mpd \
        --keep output/42110-suspension-standalone/keep.json \
        --output output/42110-suspension-standalone/source/42110-suspension-standalone.mpd

`--keep` is a JSON list of IDs or an object with a `parts` list of IDs or of
`{"id": ...}` records. The ID map and a verification report are written next
to the output (`idmap.json`). The source file is never written.
Use `--section 'exact FILE name'` when the keep IDs were measured in that section;
both the coordinates and the recorded source_section refer to that selection.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ldraw_mechanisms import source  # noqa: E402


def keep_ids(path):
    data = json.loads(Path(path).read_text())
    items = data["parts"] if isinstance(data, dict) else data
    return [i["id"] if isinstance(i, dict) else i for i in items]


def extract(model, keep, output, name=None, title=None, section=None):
    model = Path(model).resolve()
    idmap, _, report = source.flatten(
        model,
        keep,
        output,
        section=section,
        name=name,
        title=title,
        note=f"Derived by ldraw-mecha scripts/extract_subsystem.py from {model.name}: the kept occurrences are "
        "written with their composed world matrices (same frame as the source selection); everything else is "
        "removed. Original occurrence IDs precede each line; see idmap.json.",
    )
    return idmap, report


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("model")
    ap.add_argument("--keep", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--name", help="Main FILE name (default: output stem + .ldr)")
    ap.add_argument("--title", help="Description line of the main FILE (default: source description)")
    ap.add_argument("--section", help="Select this FILE as the root (IDs and frame of that section, as in prepare --section)")
    a = ap.parse_args()
    idmap, report = extract(a.model, keep_ids(a.keep), a.output, a.name, a.title, a.section)
    path = Path(a.output).with_name("idmap.json")
    path.write_text(json.dumps(dict(idmap=idmap, report=report), indent=1) + "\n")
    print(json.dumps(dict(output=a.output, idmap=str(path), kept=report["kept"],
                          max_world_matrix_error=report["max_world_matrix_error"],
                          embedded_files=report["embedded_files"])))


if __name__ == "__main__":
    main()
