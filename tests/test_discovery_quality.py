"""Rounded placements, finite worm meshes and omissions must stay observable."""

from copy import deepcopy
import math
import os
from pathlib import Path

import numpy as np
import pytest

from ldraw_mechanisms import mechanisms, plan
from ldraw_mechanisms.analysis import contacts, connectors
from ldraw_mechanisms.audit import audit
from ldraw_mechanisms.cli import main
from ldraw_mechanisms.geometry import gear_meshes
from ldraw_mechanisms.math3d import matmul, pose, rotation_z
from ldraw_mechanisms.placements import analysis_placement
from ldraw_mechanisms.prepare import adopt_motion, discover
from ldraw_mechanisms.source import Document

ROOT = Path(__file__).resolve().parents[1]
LIBRARY = bool(os.getenv("LDRAW_DIR") or os.getenv("LDRAWDIR"))


@pytest.fixture(scope="module")
def mustang():
    return Document(ROOT / "data/models-annotated/10265-1_B-Model.mpd").manifest()


@pytest.mark.parametrize(
    "angle,reflected", [(0.052, False), (0.33, False), (0.731, True)]
)
def test_near_rigid_projection_preserves_source_translation_and_handedness(
    angle, reflected
):
    c, s = round(math.cos(angle), 3), round(math.sin(angle), 3)
    matrix = pose(
        [137, -48, 291], [[-1 if reflected else 1, 0, 0], [0, c, -s], [0, s, c]]
    )
    n = dict(id="0", world=matrix)
    original = deepcopy(n)
    fixed, report = analysis_placement(n)
    r = np.array(fixed)[:3, :3]
    assert r.T @ r == pytest.approx(np.eye(3), abs=1e-12)
    assert np.linalg.det(r) == pytest.approx(-1 if reflected else 1)
    assert [row[3] for row in fixed] == [row[3] for row in matrix]
    assert report["status"] == "normalized" and report["reflected"] == reflected
    assert analysis_placement(n, normalize=False)[0] == matrix
    assert n == original


@pytest.mark.parametrize(
    "rotation",
    [
        [[1.02, 0, 0], [0, 1, 0], [0, 0, 1]],
        [[1, 0.03, 0], [0, 1, 0], [0, 0, 1]],
        [[0, 0, 0], [0, 1, 0], [0, 0, 1]],
    ],
)
def test_real_scale_shear_and_singular_frames_are_not_repaired(rotation):
    n = dict(id="0", world=pose([4, 5, 6], rotation))
    fixed, report = analysis_placement(n)
    assert fixed == n["world"]
    assert report["status"] == "unsupported"


@pytest.mark.skipif(not LIBRARY, reason="Needs official parts and shadow library")
@pytest.mark.parametrize(
    "ids,minimum",
    [
        (["0/104/34", "0/104/41"], 3),
        (["0/104/34", "0/104/10"], 1),
        (["0/104/35", "0/104/37"], 3),
        (["0/91/7", "0/91/8"], 1),
    ],
)
def test_real_rounded_root_recovers_hidden_contacts(mustang, ids, minimum):
    before = deepcopy(mustang)
    raw = contacts(mustang, ids, normalize=False)
    fixed = contacts(mustang, ids)
    assert not raw["contacts"]
    assert "zero_axle_contacts" in {w["code"] for w in raw["warnings"]}
    assert len(fixed["contacts"]) >= minimum
    assert fixed["summary"]["axles"]["with_axle_hole_contact"] == 1
    assert fixed["placements"]["counts"] == {"normalized": 2}
    report = connectors(mustang, ids[0])
    assert report["placement"]["status"] == "normalized"
    assert np.linalg.norm(report["features"][0]["world_axis"]) == pytest.approx(1)
    assert mustang == before


@pytest.mark.skipif(not LIBRARY, reason="Needs official parts and shadow library")
def test_nested_rounded_frame_recovers_rear_axles(mustang):
    ids = [
        n["id"]
        for n in mustang["nodes"]
        if n["kind"] == "part" and n["id"].startswith("0/88/")
    ]
    fixed = contacts(mustang, ids)
    assert fixed["summary"]["axles"]["total"] == 4
    assert fixed["summary"]["axles"]["with_axle_hole_contact"] == 4
    assert not contacts(mustang, ids, normalize=False)["summary"]["axles"][
        "with_axle_hole_contact"
    ]


@pytest.mark.parametrize("transformed", [False, True])
def test_worm_found_in_rotated_model_without_inventing_direction(mustang, transformed):
    m = deepcopy(mustang)
    if transformed:
        transform = matmul(
            pose(
                [137, -57, 48],
                [
                    [1, 0, 0],
                    [0, math.cos(0.37), -math.sin(0.37)],
                    [0, math.sin(0.37), math.cos(0.37)],
                ],
            ),
            rotation_z(0.731),
        )
        for n in m["nodes"]:
            n["world"] = matmul(transform, n["world"])
    report = gear_meshes(m)
    worms = [r for r in report["meshes"] if r["kind"] == "worm_mesh"]
    assert len(worms) == 1
    mesh = worms[0]
    assert (mesh["a"], mesh["b"]) == ("0/104/37", "0/104/41")
    assert mesh["distance_error_ldu"] < 0.01
    assert mesh["wheel_per_worm_magnitude"] == 0.125
    assert mesh["direction_requires_review"] and "b_per_a" not in mesh
    # Bevel-only wheels remain unsupported; brackets are no longer false racks.
    assert {r["ref"] for r in report["unsupported"]} == {"32198.dat"}


@pytest.fixture
def worm_pair():
    return dict(
        section="test",
        coordinate_space="ldu",
        nodes=[
            dict(
                id="a",
                kind="part",
                ref="4716.dat",
                description="Technic Worm Gear 2L",
                world=pose([0, 0, 0], [[1, 0, 0], [0, 1, 0], [0, 0, 1]]),
            ),
            dict(
                id="b",
                kind="part",
                ref="10928.dat",
                description="Technic Gear 8 Tooth",
                world=pose([0, -20, -10], [[0, 0, 1], [0, 1, 0], [-1, 0, 0]]),
            ),
        ],
    )


@pytest.mark.parametrize(
    "change",
    [
        "distance",
        "wheel_plane",
        "worm_end",
        "parallel",
        "oblique",
        "scale",
        "unknown",
        "embedded",
    ],
)
def test_worm_near_misses_rejected(worm_pair, change):
    assert len(gear_meshes(worm_pair)["meshes"]) == 1
    a, b = worm_pair["nodes"]
    if change == "distance":
        b["world"][1][3] -= 1
    elif change == "wheel_plane":
        b["world"][0][3] += 2
    elif change == "worm_end":
        b["world"][2][3] = 30
    elif change == "parallel":
        b["world"] = pose([0, -20, -10], [[1, 0, 0], [0, 1, 0], [0, 0, 1]])
    elif change == "oblique":
        b["world"] = matmul(
            b["world"],
            pose(
                [0, 0, 0],
                [
                    [math.cos(0.1), 0, math.sin(0.1)],
                    [0, 1, 0],
                    [-math.sin(0.1), 0, math.cos(0.1)],
                ],
            ),
        )
    elif change == "scale":
        a["world"][0][0] = 1.1
    elif change == "unknown":
        a["ref"] = "32905.dat"  # A different worm cannot inherit 4716's start count.
    else:
        a["embedded"] = True
    assert not gear_meshes(worm_pair)["meshes"]


def test_worm_evidence_enters_prepare_and_diagram(mustang, monkeypatch):
    monkeypatch.delenv("LDRAW_DIR", raising=False)
    monkeypatch.delenv("LDRAWDIR", raising=False)
    p = plan.draft(mustang)
    p.update(discover(mustang))
    edge = next(e for e in p["connections"].values() if e["kind"] == "worm_mesh")
    view = next(
        k
        for k, m in p["mechanisms"].items()
        if {edge["a"], edge["b"]} <= set(m["parts"])
    )
    text = mechanisms.diagram(p, view)
    assert "worm_mesh (candidate)" in text and "direction unreviewed" in text
    assert "contacts_not_run" in {w["code"] for w in audit(p)["warnings"]}


def test_audit_and_adoption_keep_deferred_and_missing_work_visible(tmp_path):
    source = tmp_path / "simple.ldr"
    source.write_text(
        "0 Example\n1 16 0 0 0 1 0 0 0 1 0 0 0 1 3001.dat\n1 16 20 0 0 1 0 0 0 1 0 0 0 1 3001.dat\n"
    )
    study = plan.draft(Document(source).manifest())
    study["connections"] = {}
    study["mechanisms"] = {
        "ride_height": dict(
            label="Rear ride height",
            parts=["0"],
            bodies=[],
            inputs=["part:0"],
            outputs=[],
            notes=[],
        ),
        "door": dict(
            label="Door", parts=["1"], bodies=[], inputs=[], outputs=[], notes=[]
        ),
    }
    study["discovery"] = dict(mechanical_parts=["0", "1"])
    motion = mechanisms.add_joint(
        study,
        mechanism="door",
        name="door_angle",
        instances=["1"],
        origin=[20, 0, 0],
        axis=[0, 1, 0],
        minimum=-0.2,
        maximum=0.7,
    )
    motion["status"] = "ready"
    adopted = adopt_motion(study, motion)
    assert adopted["mechanisms"]["ride_height"] == study["mechanisms"]["ride_height"]
    assert "ride_height" in audit(adopted)["unresolved"]
    assert plan.evaluate(adopted, {"door_angle": 0.43}) == plan.evaluate(
        motion, {"door_angle": 0.43}
    )
    path = tmp_path / "plan.json"
    plan.save(path, adopted)
    assert main(["audit", str(path), "--require-reviewed"]) == 1
    adopted["mechanisms"]["ride_height"].update(
        disposition="deferred", review="Crank-to-beam surface coupling not verified"
    )
    adopted["mechanisms"]["door"].update(
        disposition="planned",
        bodies=["door_angle"],
        review="Door declared by door_angle; clearance still pending",
    )
    report = audit(adopted)
    assert report["review_complete"] and report["deferred"] == ["ride_height"]
    assert (
        adopt_motion(adopted, motion)["mechanisms"]["ride_height"]["disposition"]
        == "deferred"
    )
    plan.save(path, adopted)
    assert main(["audit", str(path), "--require-reviewed"]) == 0
    del adopted["mechanisms"]["ride_height"]
    assert audit(adopted)["unaccounted_mechanical_parts"] == ["0"]
    assert not audit(adopted)["review_complete"]


def test_bracket_not_classified_as_rack(tmp_path):
    p = tmp_path / "bracket.ldr"
    p.write_text("0 Bracket\n1 16 0 0 0 1 0 0 0 1 0 0 0 1 99207.dat\n")
    from ldraw_mechanisms.analysis import inspect

    assert not inspect(p)["candidates"]
