"""Discovery regressions: identities, nested inventory, geometry near misses."""

from copy import deepcopy
import io
import math
from pathlib import Path
import sqlite3
from urllib.error import HTTPError

import pytest

from ldraw_mechanisms import search as discovery
from ldraw_mechanisms.cli import main
from ldraw_mechanisms.discovery import compact_inspect, submodels
from ldraw_mechanisms.geometry import axis_residual, coaxial, gear_meshes
from ldraw_mechanisms.math3d import matmul, pose, rotation_z
from ldraw_mechanisms.source import Document

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def database(tmp_path):
    path = tmp_path / "catalog.db"
    with sqlite3.connect(path) as db:
        db.execute(
            "CREATE VIRTUAL TABLE SUBMODELS_DESCRIPTIONS_FTS USING fts5(model,submodel,description)"
        )
        db.executemany(
            "INSERT INTO SUBMODELS_DESCRIPTIONS_FTS VALUES (?,?,?)",
            [
                ("car.mpd", "engine.ldr", "six piston engine"),
                ("plane.mpd", "cabin.ldr", "cockpit and engine controls"),
                ("car.mpd", "body.ldr", "cabin enclosure"),
            ],
        )
    return path


def test_fts_identities_syntax_and_readonly(database):
    before = database.read_bytes()
    result = discovery.search("submodels", '"engine" OR cabin', database=database)
    assert result["engine"] == "fts"
    assert len(result["results"]) == 3
    assert all(
        r["model"].endswith(".mpd") and r["section"].endswith(".ldr")
        for r in result["results"]
    )
    result = discovery.search(
        "submodels", "engine NOT controls", database=database, raw_fts=True
    )
    assert [r["section"] for r in result["results"]] == ["engine.ldr"]
    assert result["results"][0]["score"] > 0
    with pytest.raises(ValueError, match="fts search failed"):
        discovery.search("submodels", '"', raw_fts=True, database=database)
    assert before == database.read_bytes()


def test_jev_402_stops_before_rerank(database, monkeypatch):
    monkeypatch.setenv("TYPESAFE_API_KEY", "test-secret")
    monkeypatch.setattr(discovery.shutil, "which", lambda _: "/jev-rerank")
    calls = []

    def fail(*a, **kw):
        calls.append(1)
        raise HTTPError(
            "https://api.typesafe.ai", 402, "Credit", {}, io.BytesIO(b"test-secret")
        )

    monkeypatch.setattr(discovery, "urlopen", fail)
    monkeypatch.setattr(
        discovery.subprocess,
        "run",
        lambda *a, **kw: pytest.fail("Rerank must not start"),
    )
    with pytest.raises(ValueError, match="Insufficient credits.*--engine fts") as exc:
        discovery.search("submodels", "engine", engine="jev", database=database)
    assert "test-secret" not in str(exc.value)
    assert len(calls) == 1


def test_inventory_repeats_embedded_and_parents(tmp_path):
    p = tmp_path / "engine.mpd"
    p.write_text("""0 FILE main.ldr
0 Engine
1 16 0 0 0 1 0 0 0 1 0 0 0 1 bank.ldr
1 16 40 0 0 1 0 0 0 1 0 0 0 1 bank.ldr
0 FILE bank.ldr
0 Bank
1 16 0 0 0 1 0 0 0 1 0 0 0 1 2851.dat
1 16 0 0 0 1 0 0 0 1 0 0 0 1 custom.dat
0 FILE custom.dat
0 Custom piece
1 16 0 0 0 1 0 0 0 1 0 0 0 1 2851.dat
""")
    report = submodels(p)
    root, child = report["sections"]
    assert (root["parts"], root["pistons"]) == (4, 2)
    assert child["parts"] == 2
    assert child["parents"] == [
        dict(section="main.ldr", index=0),
        dict(section="main.ldr", index=1),
    ]
    # Extraction resolves dependencies and keeps occurrence-relative identities.
    target = tmp_path / "copy.mpd"
    assert (
        main(["extract", str(p), "--section", "bank.ldr", "--output", str(target)]) == 0
    )
    assert len(Document(target).manifest()["nodes"]) == 2
    assert main(["extract", str(p), "--section", "bank.ldr", "--output", str(p)]) == 2


@pytest.fixture(scope="module")
def w16():
    return Document(ROOT / "data/models-annotated/42083-1.mpd").manifest(
        "42083 - engine.ldr"
    )


def test_w16_inventory_and_compact_coordinates(w16):
    report = submodels(w16["path"], match="engine.ldr")
    engine = next(r for r in report["sections"] if r["section"] == w16["section"])
    assert (
        engine["parts"],
        engine["pistons"],
        engine["rods"],
        engine["crank_parts"],
        engine["gears"],
    ) == (223, 16, 16, 15, 5)
    assert engine["parents"] == [dict(section="42083 - chassisrear.ldr", index=157)]
    compact = compact_inspect(w16, refs=["24505.dat"], limit=2)
    assert compact["truncated"] and compact["total"] == 3
    assert compact["instances"][0]["position"] == [0, 50, 200]
    assert compact["instances"][0]["axes"]["z"] == [0, 0, -1]
    assert (
        len(compact_inspect(w16, refs=["24505.dat"], limit=2, offset=2)["instances"])
        == 1
    )


def test_w16_meshes_and_arbitrary_global_rotation(w16):
    expected = {("68", "84/16"), ("68", "85/16"), ("82", "83")}
    for manifest in (w16, deepcopy(w16)):
        if manifest is not w16:
            transform = matmul(
                pose(
                    [137, -40, 81],
                    [
                        [1, 0, 0],
                        [0, math.cos(0.61), -math.sin(0.61)],
                        [0, math.sin(0.61), math.cos(0.61)],
                    ],
                ),
                rotation_z(0.37),
            )
            for n in manifest["nodes"]:
                n["world"] = matmul(transform, n["world"])
        meshes = gear_meshes(manifest)["meshes"]
        assert {(r["a"], r["b"]) for r in meshes} == expected
        assert next(r for r in meshes if r["a"] == "82")["b_per_a"] == pytest.approx(
            -0.6
        )


@pytest.mark.parametrize("change", ["distance", "plane", "tilt", "scale", "embedded"])
def test_mesh_near_misses(w16, change):
    manifest = deepcopy(w16)
    manifest["nodes"] = [n for n in manifest["nodes"] if n["id"] in {"82", "83"}]
    n = manifest["nodes"][1]
    if change == "distance":
        n["world"][1][3] += 1
    elif change == "plane":
        n["world"][2][3] += 1
    elif change == "tilt":
        n["world"] = matmul(
            n["world"],
            pose([0, 0, 0], [[1, 0, 0], [0, 0.9, -0.43589], [0, 0.43589, 0.9]]),
        )
    elif change == "scale":
        n["world"][0][0] *= 2
    else:
        n["embedded"] = True
    assert not gear_meshes(manifest)["meshes"]


def test_axis_offsets_not_unitless():
    a = [0, math.sin(0.2618), math.cos(0.2618)]
    p = [v * 40 for v in a]
    evidence = axis_residual([0, 0, 0], a, p, [-v * 0.9999 for v in a])
    assert evidence["radial_offset_ldu"] == pytest.approx(0, abs=1e-10)
    assert evidence["axial_separation_ldu"] == pytest.approx(40)
    assert axis_residual([0, 0, 0], a, [p[0] + 0.7, p[1], p[2]], a)[
        "radial_offset_ldu"
    ] == pytest.approx(0.7)


def test_rotated_crank_connector_evidence(w16):
    import os

    if not (os.getenv("LDRAW_DIR") or os.getenv("LDRAWDIR")):
        pytest.skip("Needs official LDraw library and shadow")
    result = coaxial(w16, ["38", "67", "68"])
    assert all(r["status"] == "candidate" for r in result["pairs"])
    assert result["pairs"][0]["evidence"]["axial_separation_ldu"] == 20
    changed = deepcopy(w16)
    next(n for n in changed["nodes"] if n["id"] == "67")["world"][0][3] += 3
    assert coaxial(changed, ["67", "68"])["pairs"][0]["status"] == "not_coaxial"


@pytest.mark.parametrize(
    "first,second,distance",
    [
        ("3647.dat", "3649.dat", 60),
        ("4019.dat", "94925.dat", 40),
        ("32270.dat", "32498.dat", 60),
    ],
)
def test_additional_reviewed_gear_profiles(first, second, distance):
    def gear(i, ref, x):
        return dict(
            id=i,
            kind="part",
            ref=ref,
            description="Technic Gear",
            world=pose([x, 0, 0], [[1, 0, 0], [0, 1, 0], [0, 0, 1]]),
        )

    result = gear_meshes(
        dict(
            section="test",
            coordinate_space="LDU",
            nodes=[gear("a", first, 0), gear("b", second, distance)],
        )
    )
    assert len(result["meshes"]) == 1
    assert result["meshes"][0]["distance_error_ldu"] == 0


def test_compact_cli_table_and_external_inventory(tmp_path, capsys):
    child = tmp_path / "child.ldr"
    child.write_text("0 Piston\n1 16 0 10 0 1 0 0 0 1 0 0 0 1 2851.dat\n")
    parent = tmp_path / "parent.ldr"
    parent.write_text("0 Bank\n1 16 0 0 0 1 0 0 0 1 0 0 0 1 child.ldr\n")
    report = submodels(parent)
    assert report["total"] == 2
    assert report["sections"][0]["pistons"] == 1
    assert (
        main(["inspect", str(parent), "--format", "table", "--instances", "0/0"]) == 0
    )
    text = capsys.readouterr().out
    assert "0/0\t0\t2851.dat\t0,10,0" in text
