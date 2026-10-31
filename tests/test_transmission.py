"""Supported construction and adversarial authoring, independent of Blender."""

from copy import deepcopy
import math
from pathlib import Path
import runpy

import pytest

from ldraw_mechanisms import plan
from ldraw_mechanisms.constraints import coverage
from ldraw_mechanisms.geometry import gear_meshes
from ldraw_mechanisms.math3d import matmul, pose, rotation_z
from ldraw_mechanisms.source import Document
from ldraw_mechanisms.transmission import mesh, port, shaft

motion = runpy.run_path(
    str(Path(__file__).resolve().parents[1] / "scripts/gear_drive.py")
)["motion"]


@pytest.fixture
def source():
    return Document(
        Path(__file__).resolve().parents[1] / "examples/gear-drive/gear-drive.mpd"
    ).manifest()


def test_supported_drive_has_one_input_and_both_keyed_shafts_move(source):
    p = motion(source)
    assert set(p["controls"]) == {"drive"}
    assert len([n for n in source["nodes"] if n["kind"] == "part"]) == 23
    assert len(p["bodies"]["input"]["instances"]) == 6
    assert len(p["bodies"]["output"]["instances"]) == 6
    assert coverage(p)["complete"]
    for angle in (0.731, -2.27, 7.37, -13.2):
        result = plan.evaluate(p, {"drive": angle})
        assert result["signals"]["output_angle"] == pytest.approx(-angle / 3)
        assert all(c["passed"] for c in result["checks"])
    assert plan.sweep(p, 97)["passed"]


def test_arbitrary_global_orientation_does_not_change_coupling(source):
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
    for n in source["nodes"]:
        n["world"] = matmul(transform, n["world"])
    p = motion(source)
    assert all(c["passed"] for c in plan.evaluate(p, {"drive": -2.27})["checks"])


@pytest.mark.parametrize(
    "change",
    [
        "gear_off_axis",
        "bearing_offset",
        "short_axle",
        "bad_spacing",
        "opposed_coaxial",
        "unknown_gear",
        "embedded_gear",
    ],
)
def test_bad_source_is_rejected_before_animation(source, change):
    nodes = {n["id"]: n for n in source["nodes"]}
    if change == "gear_off_axis":
        nodes["1/1"]["world"][0][3] += 5
    elif change == "bearing_offset":
        nodes["0/5"]["world"][1][3] += 2
    elif change == "short_axle":
        nodes["1/0"]["world"][2][3] += 35
    elif change in {"bad_spacing", "opposed_coaxial"}:
        delta = 2 if change == "bad_spacing" else -40
        for i in ("2/0", "2/1", "2/2", "2/3", "2/4", "2/5", "0/6", "0/8"):
            nodes[i]["world"][0][3] += delta
        if change == "opposed_coaxial":
            assert not gear_meshes(source)["meshes"]
    elif change == "unknown_gear":
        nodes["2/1"]["ref"] = (
            "3650c.dat"  # Crown teeth are not a parallel spur profile.
        )
    else:
        nodes["2/1"]["embedded"] = True
    with pytest.raises(ValueError):
        motion(source)


def reset_mesh(p):
    p["signals"]["output_angle"] = dict(expression="0", variables={})
    p["checks"] = [c for c in p["checks"] if c["kind"] != "rotation"]


def test_reversed_body_axis_uses_matching_signed_ratio(source):
    p = motion(source)
    reset_mesh(p)
    p["bodies"]["output"]["axis"] = [0, 0, -1]
    mesh(
        p,
        "input",
        "output",
        gear_a="1/1",
        gear_b="2/1",
        evidence="Same source, reversed directed output axis.",
    )
    result = plan.evaluate(p, {"drive": 0.731})
    assert result["signals"]["output_angle"] == pytest.approx(0.731 / 3)
    assert all(c["passed"] for c in result["checks"])


def test_moving_carrier_composes_once_with_both_shafts(source):
    p = motion(source)
    reset_mesh(p)
    p["controls"]["orbit"] = dict(default=0, min=-2, max=2, unit="radian")
    p["signals"]["orbit"] = dict(expression="x", variables={"x": "control:orbit"})
    p["bodies"]["carrier"] = dict(
        kind="revolute",
        instances=[f"0/{i}" for i in range(11)],
        origin=[20, -62, 0],
        axis=[1, 0, 0],
        signal="orbit",
    )
    p["mechanisms"]["frame"].update(bodies=["carrier"], disposition="planned")
    for name in ("input", "output"):
        p["bodies"][name]["parent"] = "carrier"
    mesh(
        p,
        "input",
        "output",
        gear_a="1/1",
        gear_b="2/1",
        evidence="Shared tilting carrier carries both bearing rails.",
    )
    for drive, orbit in ((0.731, -0.38), (-7.37, 0.61)):
        assert all(
            c["passed"]
            for c in plan.evaluate(p, dict(drive=drive, orbit=orbit))["checks"]
        )


def test_rejecting_second_drive_does_not_mutate_plan(source):
    p = motion(source)
    before = deepcopy(p)
    with pytest.raises(ValueError, match="already driven"):
        mesh(
            p, "input", "output", gear_a="1/1", gear_b="2/1", evidence="Duplicate drive"
        )
    assert p == before


def test_keyed_axle_omission_and_bad_gear_sign_are_detected(source):
    p = motion(source)
    p["bodies"]["input"]["instances"].remove("1/0")
    assert not all(c["passed"] for c in plan.evaluate(p, {"drive": 0.731})["checks"])
    p = motion(source)
    p["signals"]["output_angle"]["expression"] = "a/3"
    assert not all(c["passed"] for c in plan.evaluate(p, {"drive": 0.731})["checks"])


@pytest.mark.parametrize("bad_fit", [False, True])
def test_shaft_in_prepared_view_is_transactional(source, bad_fit):
    p = motion(source)
    p["bodies"] = {}
    p["checks"] = []
    view = p["mechanisms"]["transmission"]
    view.update(
        parts=[n["id"] for n in source["nodes"] if n["kind"] == "part"],
        bodies=[],
        inputs=[],
        outputs=[],
        disposition="unresolved",
    )
    if bad_fit:
        next(n for n in p["source"]["nodes"] if n["id"] == "1/0")["world"][0][0] = 2
    before = deepcopy(p)
    kwargs = dict(
        axle=port("1/0", [0, 0, 0], [1, 0, 0], [-79.5, 79.5]),
        keyed=[port("1/1", [0, 0, 0], [0, 0, 1], [-9.5, 9.5])],
        bearings=[port("0/5", [0, 10, 0], [0, 0, 1], [-10, 10])],
        signal="drive",
        mechanism="transmission",
        evidence="Measured test interfaces",
    )
    if bad_fit:
        with pytest.raises(ValueError, match="proper rotations"):
            shaft(p, "shaft", **kwargs)
        assert p == before
    else:
        shaft(p, "shaft", **kwargs)
        assert p["status"] == "draft"
        assert p["mechanisms"]["transmission"]["bodies"] == ["shaft"]
