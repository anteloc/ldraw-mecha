"""Use mpd2glb unchanged; add verified source identities to its existing extras."""

from __future__ import annotations

import json
from pathlib import Path
import struct
import subprocess
import tempfile

from .math3d import pose
from .source import Document, ROOT, library_path, normalized, verify_source


def read(path):
    raw = Path(path).read_bytes()
    magic, version, size = struct.unpack_from("<4sII", raw)
    if magic != b"glTF" or version != 2 or size != len(raw):
        raise ValueError("Invalid GLB 2.0 header")
    chunks, pos = [], 12
    while pos < size:
        length, kind = struct.unpack_from("<I4s", raw, pos)
        chunks.append((kind, raw[pos + 8 : pos + 8 + length]))
        pos += 8 + length
    if pos != size or chunks[0][0] != b"JSON":
        raise ValueError("Invalid GLB chunks")
    return json.loads(chunks[0][1]), chunks[1:]


def write(path, data, chunks):
    raw = json.dumps(
        data, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode()
    raw += b" " * (-len(raw) % 4)
    chunks = [(b"JSON", raw), *chunks]
    payload = b"".join(
        struct.pack("<I4s", len(raw), kind) + raw for kind, raw in chunks
    )
    Path(path).write_bytes(
        struct.pack("<4sII", b"glTF", 2, len(payload) + 12) + payload
    )


def matrix(node):
    if "matrix" in node:
        return [[node["matrix"][j * 4 + i] for j in range(4)] for i in range(4)]
    x, y, z, w = node.get("rotation", [0, 0, 0, 1])
    sx, sy, sz = node.get("scale", [1, 1, 1])
    rows = [
        [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
        [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
        [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
    ]
    return pose(
        node.get("translation", [0, 0, 0]),
        [[r[0] * sx, r[1] * sy, r[2] * sz] for r in rows],
    )


def bind(path, manifest):
    data, chunks = read(path)
    nodes = data["nodes"]
    roots = data["scenes"][data.get("scene", 0)]["nodes"]
    if len(roots) != 1:
        raise ValueError("Expected one mpd2glb model root")
    bound = {"root": roots[0]}
    expected_by_parent = {}
    for n in manifest["nodes"]:
        expected_by_parent.setdefault(n["parent"], []).append(n)
    used = set()
    for n in manifest["nodes"]:
        candidates = []
        for idx in nodes[bound[n["parent"]]].get("children", []):
            obj = nodes[idx]
            extras = obj.get("extras", {})
            if idx in used or normalized(extras.get("fileName", "")) != normalized(
                n["ref"]
            ):
                continue
            m = matrix(obj)
            if any(
                abs(m[i][j] - n["local"][i][j]) > (0.5 if j == 3 else 0.002)
                for i in range(3)
                for j in range(4)
            ):
                continue
            # Exporter resolves colour 16 against parent; either representation is valid.
            if str(extras.get("colorCode")) not in (n["colour"], n["effective_colour"]):
                continue
            candidates.append(idx)
        if len(candidates) != 1:
            raise ValueError(
                f"GLB binding for {n['id']} {n['ref']}: {len(candidates)} matches"
            )
        idx = candidates[0]
        bound[n["id"]] = idx
        used.add(idx)
    # Missing or additional metadata-bearing siblings imply an incomplete conversion.
    for parent, expected in expected_by_parent.items():
        actual = [
            i
            for i in nodes[bound[parent]].get("children", [])
            if nodes[i].get("extras", {}).get("fileName")
        ]
        if set(actual) != {bound[n["id"]] for n in expected}:
            raise ValueError(f"Unexpected GLB children under {parent}")
    for name, idx in bound.items():
        nodes[idx].setdefault("extras", {}).update(
            mecha_id=name,
            mecha_source=manifest["sha256"],
            mecha_section=manifest["section"],
        )
    write(path, data, chunks)
    return dict(
        bound_instances=len(bound) - 1,
        source_sha256=manifest["sha256"],
        section=manifest["section"],
    )


def convert(manifest, output, library=None):
    verify_source(manifest)
    output = Path(output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="ldraw-mecha-") as temp:
        source = Path(manifest["path"])
        doc = Document(source)
        if (
            normalized(doc.root.name) != normalized(manifest["section"])
            or len(manifest["dependencies"]) > 1
        ):
            source = Path(temp) / "selection.mpd"
            doc.manifest(
                manifest["section"]
            )  # resolve any external assembly dependencies
            doc.export_section(manifest["section"], source)
        converted = Path(temp) / "model.glb"
        command = [
            str(ROOT / "scripts/mpd2glb.sh"),
            "-l",
            str(library_path(library)),
            "--descriptions",
            str(ROOT / "data/part-descriptions-full.tsv"),
            "-o",
            str(converted),
            str(source),
        ]
        result = subprocess.run(command, capture_output=True, text=True, timeout=600)
        if result.returncode:
            raise ValueError(f"mpd2glb failed: {result.stderr[-3000:]}")
        if (
            "could not be resolved" in result.stderr
            or "Failed to preload materials" in result.stderr
        ):
            raise ValueError(f"Incomplete conversion: {result.stderr[-3000:]}")
        report = bind(converted, manifest)
        # Publish only after all bindings succeed; leave earlier artifacts intact on failure.
        output.write_bytes(converted.read_bytes())
    return dict(path=str(output), **report)
