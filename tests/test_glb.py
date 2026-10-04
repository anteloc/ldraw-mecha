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
