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
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ldraw_mechanisms import source  # noqa: E402


def keep_ids(path):
    data = json.loads(Path(path).read_text())
    items = data["parts"] if isinstance(data, dict) else data
    return [i["id"] if isinstance(i, dict) else i for i in items]


def file_blocks(text):
    """Map normalized FILE names to their raw lines (header to the line before the next FILE)."""
    blocks, name, lines = {}, None, []
    for line in text.splitlines():
        m = re.match(r"^0\s+FILE\s+(.+?)\s*$", line)
        if m:
            if name is not None:
                blocks[source.normalized(name)] = (name, lines)
            name, lines = m.group(1), [line]
        elif name is not None:
            lines.append(line)
    if name is not None:
        blocks[source.normalized(name)] = (name, lines)
    return blocks


def references(lines):
    for line in lines:
        tokens = line.split()
        if len(tokens) >= 15 and tokens[0] == "1":
            yield " ".join(tokens[14:])


def number(v):
    s = f"{v:.10g}"
    return "0" if s in ("-0", "0") else s


def extract(model, keep, output, name=None, title=None, section=None):
    model, output = Path(model).resolve(), Path(output).resolve()
    if output == model:
        raise ValueError("Refusing to overwrite the source model")
    doc = source.Document(model)
    manifest = doc.manifest(section)
    nodes = {n["id"]: n for n in manifest["nodes"]}
    order = sorted(dict.fromkeys(keep), key=lambda s: [int(x) for x in s.split("/")])
    missing = [i for i in order if i not in nodes]
    if missing:
        raise ValueError(f"Unknown occurrences: {missing[:5]}")
    non_parts = [i for i in order if nodes[i]["kind"] != "part"]
    if non_parts:
        raise ValueError(f"Keep physical leaves only: {non_parts[:5]}")
    text = model.read_text(encoding="utf-8-sig")
    blocks = file_blocks(text)
    first = next(iter(blocks.values()))[1]
    header = {k: next((ln for ln in first if ln.startswith(p)), None)
              for k, p in (("author", "0 Author:"), ("licence", "0 !LICENSE"), ("org", "0 !LDRAW_ORG"))}
    name = name or f"{output.stem}.ldr"
    out = [
        f"0 FILE {name}",
        f"0 {title or manifest['description'] + ' - standalone extract'} ({len(order)} parts)",
        f"0 Name: {name}",
        *(v for v in (header["author"], header["org"], header["licence"]) if v),
        f"0 // Derived by ldraw-mecha scripts/extract_subsystem.py from {model.name}: the kept occurrences are "
        "written with their composed world matrices (same frame as the source selection); everything else is "
        "removed. Original occurrence IDs precede each line; see idmap.json.",
        "",
    ]
    idmap = {}
    for new, old in enumerate(order):
        n = nodes[old]
        w = n["world"]
        values = [w[0][3], w[1][3], w[2][3], *w[0][:3], *w[1][:3], *w[2][:3]]
        out.append(f"0 // from {old}")
        out.append(f"1 {n['effective_colour']} " + " ".join(number(v) for v in values) + f" {n['ref']}")
        idmap[old] = str(new)
    # Embedded FILE closure: blocks referenced by kept parts, then by those blocks.
    pending = [source.normalized(nodes[i]["ref"]) for i in order if nodes[i]["embedded"]]
    copied = []
    while pending:
        key = pending.pop(0)
        if key in copied or key not in blocks:
            continue
        copied.append(key)
        pending += [source.normalized(r) for r in references(blocks[key][1])]
    for key in copied:
        lines = blocks[key][1]
        while lines and not lines[-1].strip():
            lines = lines[:-1]
        out += ["", *lines]
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(out) + "\n")
    report = verify(nodes, output, idmap)
    report.update(source=str(model), source_sha256=source.sha256(model), output=str(output),
                  output_sha256=source.sha256(output), embedded_files=[blocks[k][0] for k in copied])
    return idmap, report


def verify(nodes, output, idmap):
    new = {n["id"]: n for n in source.Document(output).manifest()["nodes"]}
    if set(new) != set(idmap.values()):
        raise ValueError("Standalone occurrences differ from the ID map")
    worst = 0.0
    for old, i in idmap.items():
        a, b = nodes[old], new[i]
        if source.normalized(a["ref"]) != source.normalized(b["ref"]) or a["effective_colour"] != b["effective_colour"]:
            raise ValueError(f"{old} -> {i}: reference or colour changed")
        if b["kind"] != "part":
            raise ValueError(f"{old} -> {i}: not a physical leaf")
        worst = max(worst, max(abs(x - y) for ra, rb in zip(a["world"], b["world"]) for x, y in zip(ra, rb)))
    if worst > 1e-6:
        raise ValueError(f"World matrix changed by {worst}")
    return dict(kept=len(idmap), max_world_matrix_error=worst,
                coverage="Every kept leaf re-read from the written file: same reference, effective colour and "
                         "world matrix (max error reported)")


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
