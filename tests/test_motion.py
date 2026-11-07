import copy
import math
from pathlib import Path

import pytest

from ldraw_mechanisms import plan
from ldraw_mechanisms.math3d import inverse, matmul, point, signed_gear_ratio
from ldraw_mechanisms.recipes import create

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def f1():
    return create(ROOT / "data/models-annotated/42000-1.mpd", "42000")


def test_f1_transmission_and_link_closure(f1):
    p = plan.evaluate(f1, dict(spin_rl=1.4, spin_rr=-0.2, steering=0.7))
    assert p["signals"]["diff"] == pytest.approx(0.6)
    assert abs(p["signals"]["planet"]) == pytest.approx(0.8)
    assert abs(p["signals"]["crank"]) == pytest.approx(0.6 * 28 / 12)
    assert all(c["passed"] for c in p["checks"])
    assert len(p["checks"]) == 10
    assert plan.sweep(f1, 49)["passed"]


def test_pistons_move_and_equal_wheels_do_not_spin_planets(f1):
    p = plan.evaluate(f1, dict(spin_rl=0.4, spin_rr=0.4))
    assert p["signals"]["planet"] == 0
    assert any(abs(p["signals"][f"piston{i}"]) > 0.1 for i in range(8))


def test_sources_and_controls_are_checked(f1, tmp_path):
    p = copy.deepcopy(f1)
    p["source"]["dependencies"] = {str(tmp_path / "missing.mpd"): "bad"}
    with pytest.raises(OSError):
        plan.validate(p, check_source=True)
    with pytest.raises(ValueError, match="Unknown controls"):
        plan.evaluate(f1, {"steer_typo": 1})
    with pytest.raises(ValueError, match="Nonfinite"):
        plan.evaluate(f1, {"steering": float("nan")})
    assert (
        plan.evaluate(f1, {"steering": 100})["controls"]["steering"]
        == f1["controls"]["steering"]["max"]
    )


def test_dependency_cycles_and_double_ownership(f1):
    p = copy.deepcopy(f1)
    p["signals"]["yoke"]["variables"]["s"] = "signal:column"
    with pytest.raises(ValueError, match="cycle"):
        plan.validate(p)
    p = copy.deepcopy(f1)
    p["bodies"]["wheel_fl"]["instances"] += p["bodies"]["wheel_fr"]["instances"]
    with pytest.raises(ValueError, match="two rigid bodies"):
        plan.validate(p)


@pytest.mark.parametrize(
    "expr",
    [
        "__import__('os').system('true')",
        "x[0]",
        "(lambda: 1)()",
        "[x for x in y]",
        "1+",
    ],
)
def test_unsafe_expressions_rejected(expr):
    with pytest.raises(ValueError):
        plan.expression(expr, {"x", "y"})


def test_gear_sign_and_degenerate_contact():
    assert signed_gear_ratio(
        [0, 0, 1], [0, 0, 0], 8, [0, 0, 1], [40, 0, 0], 24
    ) == pytest.approx(-1 / 3)
    assert signed_gear_ratio(
        [0, 0, 1], [0, 0, 0], 8, [0, 0, -1], [40, 0, 0], 24
    ) == pytest.approx(1 / 3)
    with pytest.raises(ValueError):
        signed_gear_ratio([0, 0, 1], [0, 0, 0], 8, [0, 0, 1], [0, 0, 10], 24)


def test_standalone_hatch():
    p = create(
        ROOT / "data/models-annotated/928-1.mpd",
        "928",
        "928 - Space Ship - Cargo Hatchway.ldr",
    )
    assert len(p["source"]["nodes"]) == 2
    assert len(p["bodies"]["hatch"]["instances"]) == 2
    assert plan.sweep(p)["passed"]


@pytest.fixture(scope="module")
def w16():
    return create(
        ROOT / "data/models-annotated/42083-1.mpd", "42083", "42083 - engine.ldr"
    )


def test_w16_gear_train_and_link_closure(w16):
    kinds = [b["kind"] for b in w16["bodies"].values()]
    assert (kinds.count("revolute"), kinds.count("prismatic"), kinds.count("rod")) == (
        4,
        16,
        16,
    )
    for drive in (0.37, -2.9, 7.3):
        p = plan.evaluate(w16, dict(drive=drive))
        s = p["signals"]
        assert s["crank_c"] == pytest.approx(-5 / 3 * drive)
        assert s["crank_l"] == s["crank_r"] == pytest.approx(5 / 3 * drive)
        assert len(p["checks"]) == 16 and all(c["passed"] for c in p["checks"])
        assert all(abs(s[f"piston{i}"]) > 0.1 for i in range(16))
    assert plan.sweep(w16, 49)["passed"]


def test_w16_stroke_is_twice_the_throw(w16):
    strokes = []
    for i in range(16):
        x = [
            plan.evaluate(w16, dict(drive=k * 1.2 * math.pi / 60))["signals"][
                f"piston{i}"
            ]
            for k in range(61)
        ]
        strokes.append(max(x) - min(x))
    assert strokes == pytest.approx([20] * 16, abs=0.05)


def test_general_affine_inverse():
    m = [[1, 0.2, 0, 1], [0, 1, 0.1, -4], [0, 0, -1, 8], [0, 0, 0, 1]]
    p = [3, 7, 11]
    assert point(inverse(m), point(m, p)) == pytest.approx(p)


def test_combined_sample_is_nonzero_mixed_and_within_ranges():
    p = dict(
        controls={
            "a": dict(min=-1.0, max=2.0, default=0.0),
            "b": dict(min=-1.0, max=2.0, default=0.0),
            "c": dict(min=0.0, max=3.0, default=0.0),
            "d": dict(min=-5.0, max=5.0, default=0.0),
        }
    )
    s = plan.combined_sample(p)
    assert s == pytest.approx(dict(a=0.8, b=-0.4, c=1.2, d=-2.0))
    for name, c in p["controls"].items():
        assert c["min"] <= s[name] <= c["max"]


def test_combined_sample_handles_offset_ranges_and_nonzero_defaults():
    p = dict(
        controls={
            "negative": dict(min=-2, max=0, default=0),
            "positive": dict(min=10, max=20, default=15),
            "offset_negative": dict(min=-20, max=-10, default=-15),
            "at_maximum": dict(min=1, max=3, default=3),
            "fixed": dict(min=2, max=2, default=2),
        }
    )
    sample = plan.combined_sample(p)
    assert sample == pytest.approx(
        dict(negative=-0.8, positive=17, offset_negative=-13, at_maximum=2.2, fixed=2)
    )
    for name, c in p["controls"].items():
        assert c["min"] <= sample[name] <= c["max"]
        if c["min"] != c["max"]:
            assert sample[name] != c["default"]
    for fraction in (-0.1, 1.1, float("nan")):
        with pytest.raises(ValueError, match="fraction"):
            plan.combined_sample(p, fraction)


def _spring_plan():
    """928 hatch split into a hinge and a coil-spring child scaled along +Y."""
    p = create(
        ROOT / "data/models-annotated/928-1.mpd",
        "928",
        "928 - Space Ship - Cargo Hatchway.ldr",
    )
    hinge, spring = p["bodies"]["hatch"]["instances"]
    p["bodies"]["hatch"]["instances"] = [hinge]
    p["controls"]["squeeze"] = dict(
        default=0.0, min=-10.0, max=10.0, unit="ldu", description="Spring length change"
    )
    p["signals"]["spring_k"] = dict(
        expression="(40+d)/40", variables=dict(d="control:squeeze")
    )
    p["bodies"]["spring"] = dict(
        instances=[spring],
        kind="stretch",
        origin=[5.0, 2.0, 3.0],
        axis=[0.0, 1.0, 0.0],
        signal="spring_k",
        parent="hatch",
    )
    return p


def test_stretch_scales_along_axis_about_origin():
    p = _spring_plan()
    assert plan.validate(p)["bodies"] == 2
    e = plan.evaluate(p, dict(squeeze=-10.0))
    m = e["transforms"]["spring"]
    hinge = e["transforms"]["hatch"]
    local = matmul(inverse(hinge), m)
    # Points on the axis line scale about the origin; perpendicular offsets stay.
    assert point(local, [5.0, 2.0 + 40.0, 3.0]) == pytest.approx([5.0, 2.0 + 30.0, 3.0])
    assert point(local, [9.0, 2.0, 3.0]) == pytest.approx([9.0, 2.0, 3.0])
    rest = plan.evaluate(p)["transforms"]
    flat = sum(matmul(inverse(rest["hatch"]), rest["spring"]), [])
    assert flat == pytest.approx([1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1])


def test_stretch_cannot_parent_anchor_or_collapse():
    p = _spring_plan()
    q = copy.deepcopy(p)
    q["bodies"]["hatch"]["parent"] = "spring"
    q["bodies"]["spring"].pop("parent")
    with pytest.raises(ValueError, match="stretched spring cannot parent"):
        plan.validate(q)
    q = copy.deepcopy(p)
    q["anchors"]["seat"] = dict(body="spring", point=[0, 0, 0])
    with pytest.raises(ValueError, match="stretched spring"):
        plan.validate(q)
    q = copy.deepcopy(p)
    q["bodies"]["spring"].pop("signal")
    with pytest.raises(ValueError, match="Missing motion signal"):
        plan.validate(q)
    q = copy.deepcopy(p)
    q["signals"]["spring_k"]["expression"] = "d/10"
    with pytest.raises(ValueError, match="positive"):
        plan.evaluate(q, dict(squeeze=-5.0))


def _path_plan():
    """928 hatch spring leaf moved along a closed square table (period 4)."""
    p = _spring_plan()
    p["bodies"]["spring"] = dict(
        instances=p["bodies"]["spring"]["instances"],
        kind="path",
        origin=[5.0, 2.0, 3.0],
        axis=[0.0, 0.0, 1.0],
        x_hint=[1.0, 0.0, 0.0],
        signal="slot",
        parent="hatch",
        path=[[0, 0, 0], [10, 0, math.pi / 2], [10, 10, math.pi], [0, 10, 1.5 * math.pi], [0, 0, 2 * math.pi]],
    )
    p["controls"]["advance"] = dict(default=0.0, min=-20.0, max=20.0, unit="scalar", description="Table position")
    p["signals"]["slot"] = dict(expression="a", variables=dict(a="control:advance"))
    return p


def test_path_interpolates_cyclic_table_in_body_frame():
    p = _path_plan()
    assert plan.validate(p)["bodies"] == 2
    o = [5.0, 2.0, 3.0]

    def local(advance):
        e = plan.evaluate(p, dict(advance=advance))
        return matmul(inverse(e["transforms"]["hatch"]), e["transforms"]["spring"])

    # Whole rows reproduce the table: translation (u, v) then a turn about the origin.
    m = local(1.0)
    assert point(m, o) == pytest.approx([15.0, 2.0, 3.0])
    assert point(m, [6.0, 2.0, 3.0]) == pytest.approx([15.0, 3.0, 3.0])
    # Halfway between rows interpolates translation and angle linearly.
    m = local(1.5)
    assert point(m, o) == pytest.approx([15.0, 7.0, 3.0])
    assert point(m, [6.0, 2.0, 3.0]) == pytest.approx([15.0 + math.cos(0.75 * math.pi), 7.0 + math.sin(0.75 * math.pi), 3.0])
    # Cyclic in both directions; whole periods return exactly to rest.
    for advance in (4.0, -4.0, 12.0):
        assert sum(local(advance), []) == pytest.approx([1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1], abs=1e-9)
    assert sum(local(-0.5), []) == pytest.approx(sum(local(3.5), []))


def test_path_table_is_validated():
    p = _path_plan()
    for rows, message in (
        ([[0, 0, 0], [1, 0, 0]], "3.."),
        ([[1, 0, 0], [2, 0, 0], [1, 0, 0]], "rest pose"),
        ([[0, 0, 0], [5, 0, 0], [1, 0, 0]], "close its loop"),
        ([[0, 0, 0], [5, 0, 1], [0, 0, 1]], "close its loop"),
        ([[0, 0, 0], [5, 0], [0, 0, 0]], "Invalid path row"),
    ):
        q = copy.deepcopy(p)
        q["bodies"]["spring"]["path"] = rows
        with pytest.raises(ValueError, match=message):
            plan.validate(q)
    q = copy.deepcopy(p)
    q["bodies"]["spring"].pop("signal")
    with pytest.raises(ValueError, match="Missing motion signal"):
        plan.validate(q)
