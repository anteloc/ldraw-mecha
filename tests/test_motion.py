import copy
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


def test_general_affine_inverse():
    m = [[1, 0.2, 0, 1], [0, 1, 0.1, -4], [0, 0, -1, 8], [0, 0, 0, 1]]
    p = [3, 7, 11]
    assert point(inverse(m), point(m, p)) == pytest.approx(p)
