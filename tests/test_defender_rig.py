import importlib.util
import math
from pathlib import Path

import pytest

from ldraw_mechanisms import linkages, plan
from ldraw_mechanisms.math3d import cross, dot, length, sub, unit

ROOT = Path(__file__).resolve().parents[1]
DEFENDER = ROOT / "output/42110/plan.json"


def scalar_plan(signals, controls):
    return dict(
        controls={c: dict(default=0.0, min=-1e4, max=1e4, unit="radian", description=c) for c in controls},
        signals=signals,
        bodies={},
        anchors={},
        checks=[],
    )


def evaluate(signals, **values):
    return plan.evaluate(scalar_plan(signals, values), values)["signals"]


def joint(bend, phase, prefix="uj", theta="control:t"):
    d_in = [0.0, 0.0, 1.0]
    d_out = unit([math.sin(bend), 0.0, math.cos(bend)])
    f_in = [math.cos(phase), math.sin(phase), 0.0]
    f_out = unit(cross(d_out, f_in))
    signals = {}
    out, crs = linkages.universal_joint(signals, prefix, theta, d_in, d_out, f_in, f_out)
    return signals, out, crs, (d_in, d_out, f_in, f_out)


def test_universal_joint_matches_classic_cardan_law():
    # Input fork normal to the bend plane: tan(out) = cos(beta) tan(in).
    bend = 0.5
    signals, out, _, _ = joint(bend, math.pi / 2)
    for t in (-2.9, -1.0, 0.3, 1.4, 2.8):
        expected = math.atan2(math.cos(bend) * math.sin(t), math.cos(t))
        assert evaluate(signals, t=t)[out] == pytest.approx(expected, abs=1e-12)


@pytest.mark.parametrize("phase", [0.0, 0.4, 1.1, 2.5])
def test_universal_joint_keeps_cross_arms_perpendicular_over_turns(phase):
    signals, out, crs, (d_in, d_out, f_in, f_out) = joint(0.6, phase)
    previous = 0.0
    for t in [i * 0.37 for i in range(-40, 41)]:
        s = evaluate(signals, t=t)
        arm1 = linkages.rotate(f_in, d_in, t)
        arm2 = linkages.rotate(f_out, d_out, s[out])
        assert abs(dot(arm1, arm2)) < 1e-9
        # The cross is a child of the input shaft turning about its rest fork axis.
        carried = linkages.rotate(linkages.rotate(f_out, f_in, s[crs]), d_in, t)
        assert length(sub(carried, arm2)) < 1e-9
        # Unwrapped: stays near the input angle, even after many turns.
        assert abs(s[out] - t) < 0.2
        if t > -14.8:
            assert abs(s[out] - previous) < 0.6
        previous = s[out]


def test_in_phase_double_cardan_is_constant_velocity():
    bend = 0.55
    d0, d_mid = [0.0, 0.0, 1.0], unit([math.sin(bend), 0.0, math.cos(bend)])
    f0 = [0.6, 0.8, 0.0]
    mid_fork = unit(cross(d_mid, f0))
    signals = {}
    o1, _ = linkages.universal_joint(signals, "a", "control:t", d0, d_mid, f0, mid_fork)
    o2, _ = linkages.universal_joint(signals, "b", o1, d_mid, d0, mid_fork, unit(cross(d0, mid_fork)))
    for t in (-7.0, -1.3, 0.2, 2.2, 9.9):
        s = evaluate(signals, t=t)
        assert s[o2] == pytest.approx(t, abs=1e-12)
        assert abs(s[o1] - t) > 1e-6 or abs(math.sin(2 * t)) < 1e-3  # the middle shaft is not uniform


def test_rejects_skewed_universal_joint_forks():
    with pytest.raises(ValueError, match="perpendicular|off"):
        linkages.universal_joint({}, "x", "control:t", [0, 0, 1], [0, 0.3, 1], [1, 0, 0], [1, 0, 0.0])


def test_ball_link_stays_closed():
    pivot, axis = [10.0, 0.0, 5.0], [0.0, -1.0, 0.02]
    ball = [10.0, 0.5, 45.0]
    socket = [-87.0, 18.0, 44.0]
    link = length(sub(ball, socket))
    signals = {}
    name, closed_form = linkages.ball_link(signals, "k", "control:s", pivot, axis, ball, socket, [1, 0, 0], link)
    for s in (-18.0, -7.5, 0.0, 6.0, 17.0):
        phi = evaluate(signals, s=s)[name]
        assert phi == pytest.approx(closed_form(s), abs=1e-12)
        moved = [a + b for a, b in zip(pivot, linkages.rotate(sub(ball, pivot), axis, phi))]
        assert length(sub(moved, [socket[0] + s, socket[1], socket[2]])) == pytest.approx(link, abs=1e-9)
    assert evaluate(signals, s=0.0)[name] == pytest.approx(0.0, abs=1e-9)


@pytest.mark.skipif(not DEFENDER.exists(), reason="42110 study output not generated")
def test_defender_timeline_is_continuous_across_ratio_changes():
    spec = importlib.util.spec_from_file_location("animate_defender", ROOT / "scripts/blender/animate_defender.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    p = plan.load(DEFENDER)
    rows = module.timeline(p, frames=260)
    changes = [b["frame"] for a, b in zip(rows, rows[1:]) if a["state"] != b["state"]]
    assert len(changes) >= 4  # engage, then the 1-2, 2-3 and 3-4 shifts
    for a, b in zip(rows, rows[1:]):
        for group in ("engine", "mid", "c26", "camshaft", "out"):
            assert abs(b["signals"][group] - a["signals"][group]) < 0.8
    report = module.continuity(p, rows)
    assert report["passed"], report["violations"]
