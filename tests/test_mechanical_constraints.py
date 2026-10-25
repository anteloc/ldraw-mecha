"""Failures which a signal-only animation check cannot detect."""

import copy
import math

import pytest

from ldraw_mechanisms import plan
from ldraw_mechanisms.constraints import coverage
from ldraw_mechanisms.linkages import differential, double_cardan, gear_pair
from ldraw_mechanisms.math3d import identity


def machine():
    p = plan.draft(
        dict(
            nodes=[
                dict(id=i, kind="part", world=identity())
                for i in ("shaft", "gear", "bearing", "carrier")
            ]
        ),
        "fixture",
    )
    p["controls"] = {
        k: dict(unit="radian", default=0, min=-4 * math.pi, max=4 * math.pi)
        for k in ("drive", "orbit")
    }
    p["signals"] = {
        k: dict(expression="x", variables={"x": "control:" + k}) for k in p["controls"]
    }
    for i in ("shaft", "gear"):
        p["bodies"][i] = dict(
            kind="revolute",
            instances=[i],
            origin=[0, 0, 0],
            axis=[0, 0, 1],
            signal="drive",
        )
    p["checks"] = [
        dict(
            kind="rigid",
            name="keyed",
            a="shaft",
            b="gear",
            tolerance_ldu=1e-6,
            tolerance_degrees=1e-5,
        )
    ]
    return p


def test_spinning_gear_on_fixed_axle_is_rejected():
    p = machine()
    plan.validate(p)
    assert all(c["passed"] for c in plan.evaluate(p, {"drive": 0.731})["checks"])
    del p["bodies"]["shaft"]  # Unowned parts are fixed, not ignored.
    plan.validate(p)  # Rest pose alone cannot catch this.
    c = plan.evaluate(p, {"drive": 0.731})["checks"][0]
    assert not c["passed"] and c["rotation_degrees"] > 40
    assert not plan.sweep(p, 18)["passed"]


def test_wrong_pivot_preserves_spin_but_breaks_keyed_assembly():
    p = machine()
    p["bodies"]["gear"]["origin"] = [8, 0, 0]
    c = plan.evaluate(p, {"drive": 0.731})["checks"][0]
    assert not c["passed"] and c["displacement_ldu"] > 5


def coaxial():
    return dict(
        kind="coaxial",
        name="shaft bearing",
        a=dict(instance="shaft", point=[0, 0, 0], axis=[0, 0, 1], span=[-20, 20]),
        b=dict(instance="bearing", point=[0, 0, 0], axis=[0, 0, -1], span=[-5, 5]),
        tolerance_ldu=0.01,
        tolerance_degrees=0.01,
        axial_tolerance_ldu=0.01,
        min_overlap_ldu=9.9,
    )


def test_bearing_allows_spin_but_rejects_wrong_axis_and_axial_escape():
    p = machine()
    p["checks"] = [coaxial()]
    plan.validate(p)
    assert plan.evaluate(p, {"drive": 0.731})["checks"][0]["passed"]
    p["bodies"]["shaft"]["axis"] = [1, 0, 0]
    assert not plan.evaluate(p, {"drive": 0.731})["checks"][0]["passed"]
    p["bodies"]["shaft"].update(kind="prismatic", axis=[0, 0, 1])
    assert not plan.evaluate(p, {"drive": 1.2})["checks"][0]["passed"]
    del p["checks"][0][
        "axial_tolerance_ldu"
    ]  # Sliding is allowed, but engagement is finite.
    p["bodies"]["shaft"]["origin"] = [0, 0, 0]
    p["controls"]["drive"].update(max=50)
    c = plan.evaluate(p, {"drive": 40})["checks"][0]
    assert not c["passed"] and c["overlap_ldu"] == 0


def test_parented_carrier_and_relative_gear_rotation():
    p = machine()
    p["bodies"]["carrier"] = dict(
        kind="revolute",
        instances=["carrier"],
        origin=[0, 0, 0],
        axis=[1, 0, 0],
        signal="orbit",
    )
    for b in ("shaft", "gear"):
        p["bodies"][b]["parent"] = "carrier"
    p["signals"]["reverse"] = dict(expression="-a/3", variables={"a": "control:drive"})
    p["bodies"]["gear"]["signal"] = "reverse"
    p["checks"] = [
        dict(
            kind="rotation",
            carrier="carrier",
            terms=[
                dict(instance="shaft", axis=[0, 0, 1], coefficient=8),
                dict(instance="gear", axis=[0, 0, 1], coefficient=24),
            ],
            tolerance_radians=1e-8,
            axis_tolerance_degrees=1e-5,
        )
    ]
    plan.validate(p)
    for drive, orbit in ((0.731, -0.38), (-4.4, 0.61), (7.37, -1.02)):
        assert plan.evaluate(p, dict(drive=drive, orbit=orbit))["checks"][0]["passed"]
    p["signals"]["reverse"]["expression"] = "a/3"
    assert not plan.evaluate(p, dict(drive=0.731, orbit=-0.38))["checks"][0]["passed"]
    p["signals"]["reverse"]["expression"] = "-a/3"
    del p["checks"][0]["carrier"]
    assert not plan.evaluate(p, dict(drive=0.731, orbit=-0.38))["checks"][0]["passed"]


def test_mechanical_constraint_validation_and_tautological_coverage():
    p = machine()
    assert coverage(p)["complete"]
    p["bodies"]["shaft"]["instances"].append("gear")
    del p["bodies"]["gear"]
    assert coverage(p)["unchecked_bodies"] == ["shaft"]
    for update in (
        dict(tolerance_ldu=float("nan")),
        dict(a="missing"),
        dict(b="shaft"),
    ):
        q = copy.deepcopy(p)
        q["checks"][0].update(update)
        with pytest.raises(ValueError):
            plan.validate(q)


def test_rod_is_covered_by_its_explicit_endpoint_length_check():
    p = machine()
    p["anchors"] = dict(
        a=dict(body="shaft", point=[0, 0, 0]), b=dict(body="gear", point=[0, 10, 0])
    )
    p["bodies"]["link"] = dict(
        kind="rod",
        instances=["bearing"],
        origin=[0, 0, 0],
        axis=[0, 0, 1],
        x_hint=[1, 0, 0],
        start="a",
        end="b",
    )
    p["checks"] = [dict(kind="distance", a="a", b="b", length=10, tolerance=0.01)]
    plan.validate(p)
    assert coverage(p)["complete"]


def test_differential_and_moving_carrier_helpers():
    p = machine()
    carrier, planet = differential(
        p["signals"],
        "diff",
        "control:drive",
        "control:orbit",
        side_teeth=24,
        planet_teeth=12,
    )
    follower = gear_pair(p["signals"], "mesh", "control:drive", carrier, -2)
    for a, b in ((0.9, -0.3), (1.3, 1.3), (-7.2, 3.8)):
        s = plan.evaluate(p, dict(drive=a, orbit=b))["signals"]
        assert s[carrier] == pytest.approx((a + b) / 2)
        assert s[planet] == pytest.approx(a - b)
        assert (s[follower] - s[carrier]) == pytest.approx(-2 * (a - s[carrier]))
    assert plan.evaluate(p, dict(drive=0.9, orbit=0.9))["signals"][planet] == 0


def test_rotation_relation_catches_differential_average_violation():
    p = machine()
    p["bodies"]["carrier"] = dict(
        kind="revolute",
        instances=["carrier"],
        origin=[0, 0, 0],
        axis=[0, 0, 1],
        signal="mean",
    )
    p["bodies"]["gear"]["signal"] = "orbit"
    p["signals"]["mean"] = dict(
        expression="(a+b)/2", variables={"a": "control:drive", "b": "control:orbit"}
    )
    p["checks"] = [
        dict(
            kind="rotation",
            terms=[
                dict(instance=i, axis=[0, 0, 1], coefficient=k)
                for i, k in [("shaft", 1), ("gear", 1), ("carrier", -2)]
            ],
            tolerance_radians=1e-8,
            axis_tolerance_degrees=1e-5,
        )
    ]
    plan.validate(p)
    assert plan.evaluate(p, dict(drive=1.13, orbit=-0.37))["checks"][0]["passed"]
    p["signals"]["mean"]["expression"] = "a"
    assert not plan.evaluate(p, dict(drive=1.13, orbit=-0.37))["checks"][0]["passed"]


@pytest.mark.parametrize("bend", [0, 0.17, -0.43, math.pi / 4])
def test_phased_double_cardan_is_cv_but_intermediate_shaft_is_not(bend):
    p = machine()
    result = double_cardan(
        p["signals"],
        "cv",
        "control:drive",
        [0, 1, 0],
        [0, math.cos(bend), math.sin(bend)],
        [1, 0, 0],
    )
    for phase in (0.371, 1.13, -2.27, 7.31, -9.47):
        s = plan.evaluate(p, dict(drive=phase))["signals"]
        assert s[result["output"]] == pytest.approx(phase, abs=1e-10)
        if bend:
            assert abs(s[result["middle"]] - phase) > 1e-4
