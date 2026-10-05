#!/usr/bin/env python3
"""Write a derived MPD whose chosen library shortcuts become embedded assemblies.

An LDraw shortcut such as a complete shock absorber is one physical leaf, so the
converter merges its piston rod, cylinder and spring into one mesh. This copies
the shortcut's own official sub-part lines into an embedded `.ldr` FILE and
repoints only the matching type-1 lines at it. Line counts per section do not
change, so every other occurrence ID stays valid; a replaced occurrence becomes
an assembly whose children are `ID/0`, `ID/1`, ... in the shortcut's line order.

The source file is never written. The report records both hashes, the ID map
and a check that each sub-part's composed world matrix equals the original
placement composed with its shortcut line.

    .venv/bin/python scripts/split_shortcuts.py data/models-annotated/42110-1.mpd \
        --parts 76537.dat 41838.dat \
        --output output/42110-suspension/source/42110-1-shocks-split.mpd
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ldraw_mechanisms import source  # noqa: E402
from ldraw_mechanisms.math3d import matmul  # noqa: E402


def shortcut_lines(library, part):
    path = library / "parts" / part
    lines = path.read_text(encoding="utf-8-sig").splitlines()
    header = [ln for ln in lines if ln.startswith("0 ")]
    if not any("!LDRAW_ORG" in ln and "Shortcut" in ln for ln in header):
        raise ValueError(f"{part} is not an LDraw shortcut")
    title = header[0][2:].strip()
    author = next(
        (ln[len("0 Author:") :].strip() for ln in header if ln.startswith("0 Author:")),
        "unknown",
    )
    licence = next(
        (ln[2:].strip() for ln in header if ln.startswith("0 !LICENSE")), None
    )
    body = [ln.strip() for ln in lines if ln.strip().startswith("1 ")]
    if not body:
        raise ValueError(f"{part} has no sub-part lines")
    return title, author, licence, body


def split(model, parts, output, library=None):
    model, output = Path(model).resolve(), Path(output).resolve()
    if output == model:
        raise ValueError("Refusing to overwrite the source model")
    lib = source.library_path(library)
    wanted = {source.normalized(p): p for p in parts}
    files = {}
    for key, part in wanted.items():
        title, author, licence, body = shortcut_lines(lib, part)
        files[key] = dict(
            part=part,
            name=f"{Path(part).stem}-split.ldr",
            title=title,
            author=author,
            licence=licence,
            lines=body,
        )
    text = model.read_text(encoding="utf-8-sig")
    newline = "\r\n" if "\r\n" in text else "\n"
    out, replaced = [], 0
    for line in text.splitlines():
        tokens = line.split()
        if (
            len(tokens) >= 15
            and tokens[0] == "1"
            and source.normalized(" ".join(tokens[14:])) in files
        ):
            key = source.normalized(" ".join(tokens[14:]))
            line = " ".join(tokens[:14] + [files[key]["name"]])
            replaced += 1
        out.append(line)
    if not replaced:
        raise ValueError(f"No type-1 references to {sorted(wanted.values())}")
    # Derivation note inside the first FILE header: a comment, not a placement,
    # so no type-1 index moves.
    author_at = next(i for i, ln in enumerate(out) if ln.startswith("0 Author:"))
    out.insert(
        author_at + 1,
        "0 // Derived by ldraw-mecha scripts/split_shortcuts.py from "
        f"{model.name}: shortcuts {', '.join(sorted(wanted.values()))} expanded "
        "into their official sub-parts; nothing else changed.",
    )
    for f in files.values():
        out += [
            "",
            f"0 FILE {f['name']}",
            f"0 {f['title']} - sub-parts of {f['part']}",
            f"0 Name: {f['name']}",
            f"0 Author: {f['author']} (LDraw shortcut {f['part']})",
        ]
        if f["licence"]:
            out.append(f"0 {f['licence']}")
        out += ["", *f["lines"], "0 NOFILE"]
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(newline.join(out) + newline)
    return check(model, output, files)


def check(model, derived, files):
    before = {n["id"]: n for n in source.Document(model).manifest()["nodes"]}
    after = {n["id"]: n for n in source.Document(derived).manifest()["nodes"]}
    names = {source.normalized(f["name"]): f for f in files.values()}
    mapping, worst = {}, 0.0
    for node_id, old in before.items():
        new = after.get(node_id)
        if new is None:
            raise ValueError(f"Occurrence vanished: {node_id}")
        err = max(
            abs(a - b) for ra, rb in zip(old["world"], new["world"]) for a, b in zip(ra, rb)
        )
        if err > 1e-9:
            raise ValueError(f"Occurrence moved: {node_id} ({err})")
        if source.normalized(new["ref"]) in names:
            f = names[source.normalized(new["ref"])]
            if new["kind"] != "assembly":
                raise ValueError(f"Split occurrence is not an assembly: {node_id}")
            children = []
            for i, line in enumerate(f["lines"]):
                child = after[f"{node_id}/{i}"]
                t = [float(v) for v in line.split()[2:14]]
                local = [t[3:6] + [t[0]], t[6:9] + [t[1]], t[9:12] + [t[2]], [0, 0, 0, 1]]
                expected = matmul(old["world"], local)
                worst = max(
                    worst,
                    max(
                        abs(a - b)
                        for ra, rb in zip(expected, child["world"])
                        for a, b in zip(ra, rb)
                    ),
                )
                children.append(dict(id=child["id"], ref=child["ref"], colour=child["effective_colour"]))
            mapping[node_id] = dict(shortcut=f["part"], section=old["section"], children=children)
        elif new["ref"] != old["ref"] or new["kind"] != old["kind"]:
            raise ValueError(f"Occurrence changed: {node_id}")
    extra = sorted(set(after) - set(before) - {c["id"] for m in mapping.values() for c in m["children"]})
    if extra:
        raise ValueError(f"Unexpected new occurrences: {extra[:5]}")
    if worst > 1e-9:
        raise ValueError(f"Sub-part placement mismatch {worst}")
    return dict(
        source=str(model),
        source_sha256=source.sha256(model),
        derived=str(derived),
        derived_sha256=source.sha256(derived),
        shortcuts={f["part"]: dict(file=f["name"], title=f["title"], author=f["author"], lines=f["lines"]) for f in files.values()},
        split_occurrences=mapping,
        unchanged_occurrences=len(before) - len(mapping),
        max_subpart_matrix_error=worst,
        note="Only the listed occurrences changed (part -> assembly of its official sub-parts); all other IDs, references and world matrices are identical.",
    )


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("model")
    ap.add_argument("--parts", nargs="+", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--report", help="Default: split.json next to the output")
    ap.add_argument("--library")
    a = ap.parse_args()
    report = split(a.model, a.parts, a.output, a.library)
    path = Path(a.report or Path(a.output).with_name("split.json"))
    path.write_text(json.dumps(report, indent=1) + "\n")
    print(json.dumps(dict(output=a.output, report=str(path), split=len(report["split_occurrences"]), unchanged=report["unchanged_occurrences"])))


if __name__ == "__main__":
    main()
