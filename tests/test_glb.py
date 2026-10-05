from pathlib import Path

import pytest

from ldraw_mechanisms.glb import bind, read, write
from ldraw_mechanisms.source import Document

ROOT = Path(__file__).resolve().parents[1]


def test_binding_existing_glb_and_preserving_metadata(tmp_path):
    p = tmp_path / "106.glb"
    p.write_bytes((ROOT / "106-1.glb").read_bytes())
    before, _ = read(p)
    manifest = Document(ROOT / "data/models-annotated/106-1.mpd").manifest()
    assert bind(p, manifest)["bound_instances"] == 72
    after, _ = read(p)
    assert len(after["nodes"]) == len(before["nodes"])
    tagged = [n for n in after["nodes"] if "mecha_id" in n.get("extras", {})]
    assert len(tagged) == 73
    assert all(n["extras"]["description"] for n in tagged)


def test_binding_missing_metadata_fails_without_rewriting(tmp_path):
    p = tmp_path / "bad.glb"
    data, chunks = read(ROOT / "106-1.glb")
    data["nodes"][2]["extras"].pop("fileName")
    write(p, data, chunks)
    before = p.read_bytes()
    with pytest.raises(ValueError, match="binding"):
        bind(p, Document(ROOT / "data/models-annotated/106-1.mpd").manifest())
    assert p.read_bytes() == before


def test_binding_wrong_transform_fails(tmp_path):
    p = tmp_path / "wrong.glb"
    data, chunks = read(ROOT / "106-1.glb")
    data["nodes"][2]["translation"] = [100, 0, 0]
    write(p, data, chunks)
    with pytest.raises(ValueError, match="binding"):
        bind(p, Document(ROOT / "data/models-annotated/106-1.mpd").manifest())


def test_exact_duplicate_placements_bind_in_source_order(tmp_path):
    import copy

    manifest = Document(ROOT / "data/models-annotated/106-1.mpd").manifest()
    tagged = tmp_path / "tagged.glb"
    tagged.write_bytes((ROOT / "106-1.glb").read_bytes())
    bind(tagged, manifest)
    data, chunks = read(tagged)
    index = {n.get("extras", {}).get("mecha_id"): i for i, n in enumerate(data["nodes"])}
    leaf = next(n for n in manifest["nodes"] if n["kind"] == "part")
    parent = next(
        i for i, n in enumerate(data["nodes"]) if index[leaf["id"]] in n.get("children", [])
    )
    data["nodes"].append(copy.deepcopy(data["nodes"][index[leaf["id"]]]))
    data["nodes"][parent]["children"].append(len(data["nodes"]) - 1)
    twin = dict(copy.deepcopy(leaf), id="dup", index=999)
    manifest["nodes"].append(twin)
    p = tmp_path / "dup.glb"
    write(p, data, chunks)
    report = bind(p, manifest)
    assert report["duplicate_placements"] == [[leaf["id"], "dup"]]
    after, _ = read(p)
    ids = [n.get("extras", {}).get("mecha_id") for n in after["nodes"]]
    assert ids.index(leaf["id"]) < ids.index("dup")  # Source order preserved.
    # A near (not exact) duplicate stays ambiguous and fails.
    twin["local"][0][3] += 0.1
    write(p, data, chunks)
    with pytest.raises(ValueError, match="binding"):
        bind(p, manifest)


def test_primitive_leaves_bind_to_merged_parent_geometry(tmp_path):
    import json

    source = tmp_path / "rope.mpd"
    source.write_text("""0 FILE main.ldr
0 Main
1 4 10 0 0 1 0 0 0 1 0 0 0 1 rope.ldr
0 FILE rope.ldr
0 Rope
1 16 0 0 0 1 0 0 0 1 0 0 0 1 4-4cyli.dat
1 16 0 1 0 1 0 0 0 1 0 0 0 1 4-4cyli.dat
1 16 0 0 20 1 0 0 0 1 0 0 0 1 3001.dat
""")
    manifest = Document(source).manifest()
    data = dict(
        asset=dict(version="2.0"),
        scene=0,
        scenes=[dict(nodes=[0])],
        nodes=[
            dict(children=[1]),
            dict(
                extras=dict(fileName="rope.ldr", colorCode="4"),
                translation=[10, 0, 0],
                children=[2, 3],
            ),
            dict(mesh=0),
            dict(extras=dict(fileName="3001.dat", colorCode="16"), translation=[0, 0, 20]),
        ],
    )
    p = tmp_path / "rope.glb"
    write(p, data, [])
    with pytest.raises(ValueError, match="0 matches"):
        bind(p, manifest)  # Without the primitive list the leaves stay unbound.
    report = bind(p, manifest, {"4-4cyli.dat"})
    assert report["merged_primitives"] == {"0": 2}
    nodes, _ = read(p)
    assert json.loads(nodes["nodes"][2]["extras"]["mecha_merged"]) == ["0/0", "0/1"]
    assert "mecha_id" not in nodes["nodes"][2]["extras"]
    assert nodes["nodes"][3]["extras"]["mecha_id"] == "0/2"
