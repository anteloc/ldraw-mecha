import json
from pathlib import Path

from ldraw_mechanisms import plan
from ldraw_mechanisms.geometry import gear_meshes
from ldraw_mechanisms.rcvj import wrong_motion


def fixture():
    return json.loads((Path(__file__).parent / "fixtures/rcvj-shafts.json").read_text())


def test_actual_rcvj_side_gears_are_not_an_external_pair():
    p = fixture()
    gears = gear_meshes(p["source"])
    assert {"9/14", "9/16", "9/1", "9/2"} <= {g["id"] for g in gears["gears"]}
    assert not any({m["a"], m["b"]} == {"9/14", "9/16"} for m in gears["meshes"])
    assert not gears["unsupported"]


def test_actual_rcvj_wrong_axis_and_stationary_axle_fail():
    p = wrong_motion(fixture())
    plan.validate(p)
    assert all(c["passed"] for c in plan.evaluate(p)["checks"])
    for phase in (0.371, 1.13, -2.27):
        by_name = {c["name"]: c for c in plan.evaluate(p, {"input": phase})["checks"]}
        assert not by_name["left_side_keyed"]["passed"]
        assert not by_name["left_side_axis"]["passed"]
    # Correcting the gear axis alone still leaves the keyed axle behind.
    p["bodies"]["gear"]["axis"] = [1, 0, 0]
    assert not plan.evaluate(p, {"input": 0.371})["checks"][0]["passed"]


def test_measured_cam_mount_is_vertical_and_off_centre():
    p = fixture()
    c = next(c for c in p["checks"] if c["name"] == "left_cam_axis")
    assert c["a"]["instance"] == "2" and c["b"]["instance"] == "9/4"
    assert c["b"]["point"] == [0, -10, -5]
    from ldraw_mechanisms.math3d import direction

    n = next(n for n in p["source"]["nodes"] if n["id"] == "2")
    axis = direction(n["world"], c["a"]["axis"])
    assert abs(axis[1]) > 0.999 and abs(axis[0]) < 0.001


def test_carrier_can_tilt_a_keyed_cam_axis_without_spinning_it_in_its_hole():
    p = wrong_motion(fixture())
    p["bodies"] = {
        "carrier": dict(
            kind="revolute",
            instances=["2", "9/4", "32"],
            origin=[-50, -1, 0.25],
            axis=[1, 0, 0],
            signal="input",
        )
    }
    # Local Y can travel with a carrier that turns about its X bearing.
    for phase in (0.371, -0.81):
        checks = {c["name"]: c for c in plan.evaluate(p, {"input": phase})["checks"]}
        assert checks["left_cam_keyed"]["passed"]
        assert checks["left_cam_connector_axis"]["passed"]
        assert checks["left_carrier_bearing_axis"]["passed"]
