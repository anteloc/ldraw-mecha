import copy
import math
from pathlib import Path

import pytest

from ldraw_mechanisms import plan
from ldraw_mechanisms.math3d import inverse, point, signed_gear_ratio
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
    ["__import__('os').system('true')", "x[0]", "(lambda: 1)()", "[x for x in y]", "1+"],
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
