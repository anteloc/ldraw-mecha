"""42083 (Bugatti Chiron) standalone mechanisms: saved plans, timelines and the gearbox reconstruction.

These read the generated plans under output/42083-mechanisms (skipped when absent) and check the
claims recorded in their notes with the portable evaluator only (no Blender, no pyldraw3).
"""

import json
import math
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from ldraw_mechanisms import plan as contract  # noqa: E402
import timeline_42083 as tl  # noqa: E402

OUT = ROOT / "output/42083-mechanisms"
PI = math.pi


def load(name):
    path = OUT / name / "plan.json"
    if not path.exists():
        pytest.skip(f"{path} not generated")
    return contract.load(path)


def kin(name):
    return json.loads((OUT / name / "kinematics.json").read_text())


def angle_about(t, axis):
    """Rotation angle of a 4x4 transform about a unit axis (for revolute bodies about that axis)."""
    a = axis
    v = [0.0, 1.0, 0.0] if abs(a[1]) < 0.9 else [1.0, 0.0, 0.0]
    w = [sum(t[i][j] * v[j] for j in range(3)) for i in range(3)]
    c = [v[1] * w[2] - v[2] * w[1], v[2] * w[0] - v[0] * w[2], v[0] * w[1] - v[1] * w[0]]
    return math.atan2(sum(c[i] * a[i] for i in range(3)), sum(v[i] * w[i] for i in range(3)))


@pytest.mark.parametrize("name", ["drivetrain", "gearbox", "dnr", "doors", "wing"])
def test_plans_are_ready_valid_and_reviewed(name):
    p = load(name)
    assert p["status"] == "ready"
    contract.validate(p)
    assert all(v["disposition"] in ("planned", "static") for v in p["mechanisms"].values())
    assert contract.sweep(p, steps=9)["passed"]


def test_drivetrain_differentials_and_straight_running():
    p = load("drivetrain")
    for drive, df, dr in ((0.37, 0.0, 0.0), (-2.9, 0.4, -0.25), (7.3, -1.1, 0.9)):
        s = contract.evaluate(p, dict(drive=drive, diff_front=df, diff_rear=dr))["signals"]
        assert abs((s["side_fl"] + s["side_fr"]) / 2 - drive) < 1e-12
        assert abs((s["side_rl"] + s["side_rr"]) / 2 - drive) < 1e-12
    # No centre differential: one road-wheel angle fixes the main shaft and both pinions consistently.
    s = contract.evaluate(p, dict(drive=1.0))["signals"]
    assert abs(s["main"] + 1.4) < 1e-9  # 28T ring / 20T pinion
    assert abs(s["front_pinion"] - 1.4) < 1e-9  # through the 16:16 mesh
    for w in ("wheel_fl", "wheel_fr"):
        assert abs(s[w] - 1.0) < 1e-9  # straight front half shafts
    for w in ("wheel_rl", "wheel_rr"):
        assert abs(s[w] - 1.0) < 0.05  # 20.3 deg cardan: up to ~0.036 rad lead/lag within a turn
    full = contract.evaluate(p, dict(drive=2 * PI))["signals"]
    assert abs(full["wheel_rl"] - 2 * PI) < 1e-9 and abs(full["wheel_rr"] - 2 * PI) < 1e-9


def test_gearbox_has_eight_decreasing_ratios_and_one_ring_per_catch():
    p = load("gearbox")
    ratios = {}
    for c2 in range(4):
        for c1 in range(4):
            psi = (4 * c2 + c1) * PI / 2
            e0 = contract.evaluate(p, dict(shift=psi, input=0.5))["signals"]
            e1 = contract.evaluate(p, dict(shift=psi, input=0.6))["signals"]
            gear = (c2 % 2) * 4 + c1 + 1
            r = (e1["s2"] - e0["s2"]) / (e1["s1"] - e0["s1"])
            ratios.setdefault(gear, set()).add(round(r, 9))
            engaged = [k for k in ("ring_r1_abs", "ring_r2", "ring_r3", "ring_r4_abs") if abs(e0[k]) > 9.99]
            assert len(engaged) == 2 and len({k[:7] for k in engaged}) == 2
    assert all(len(v) == 1 for v in ratios.values())
    seq = [next(iter(ratios[g])) for g in range(1, 9)]
    assert seq == sorted(seq, reverse=True) and len(set(seq)) == 8
    assert [round(x, 4) for x in seq] == [1.6667, 1.25, 1.0, 0.8, 0.6, 0.45, 0.36, 0.288]


def test_gearbox_carry_happens_on_the_fourth_to_fifth_shift_only():
    p = load("gearbox")
    psi2 = lambda s: contract.evaluate(p, dict(shift=s))["signals"]["psi2"]  # noqa: E731
    assert psi2(0) == psi2(3 * PI / 2) == 0
    assert abs(psi2(2 * PI) - PI / 2) < 1e-12
    assert 0 < psi2(1.75 * PI) < PI / 2
    assert abs(psi2(3.5 * PI) - PI / 2) < 1e-12  # gears 5-8 keep catch 2
    assert abs(psi2(4 * PI) - PI) < 1e-12  # the next carry (8th -> 9th = 1st again) completes at 4 pi


def test_gearbox_pawl_tips_stay_on_the_roller_circle_while_driving():
    p = load("gearbox")
    k = kin("gearbox")
    rho = 24.65
    up = k["paddle"]["up_stroke"]
    for side, stroke in (("l", -0.6), ("r", 0.6)):
        for f in (0.25, 0.5, 1.0):
            s = contract.evaluate(p, dict(paddle=stroke * f))["signals"]
            d = math.hypot(s[f"pw{side}_tx"] - 140.0, s[f"pw{side}_tz"] + 360.0)
            assert abs(d - rho) < 0.01
    assert up in (-0.6, 0.6)


def test_dnr_reverse_turns_the_engine_the_other_way_and_neutral_disconnects():
    p = load("dnr")
    rate = {}
    for sel in (-1.0, 0.0, 1.0):
        a = contract.evaluate(p, dict(selector=sel, input=0.2))["signals"]["engine_in"]
        b = contract.evaluate(p, dict(selector=sel, input=0.3))["signals"]["engine_in"]
        rate[sel] = (b - a) / 0.1
    assert rate[0.0] == 0.0
    assert rate[1.0] * rate[-1.0] < 0
    assert abs(rate[1.0] + 1.2) < 1e-9 and abs(rate[-1.0] - 3.0) < 1e-9


def test_doors_open_outwards_about_their_pillars():
    p = load("doors")
    e = contract.evaluate(p, dict(door_left=1.0, door_right=1.0))
    for side, sign in (("left", 1), ("right", -1)):
        b = p["bodies"][f"door_{side}"]
        assert abs(abs(b["axis"][1]) - 1) < 1e-9
        t = e["transforms"][f"door_{side}"]
        rear = [b["origin"][0], b["origin"][1], b["origin"][2] + 200.0]
        moved = [sum(t[i][j] * rear[j] for j in range(3)) + t[i][3] for i in range(3)]
        assert sign * (moved[0] - rear[0]) > 100  # the rear edge swings outwards
    assert p["controls"]["door_left"]["max"] == tl.DOOR_MAX


def test_wing_lifts_straight_up_and_its_links_close():
    p = load("wing")
    hi = p["controls"]["wing"]["max"]
    assert hi == tl.WING_RANGE[1]
    e = contract.evaluate(p, dict(wing=hi))
    assert all(c["passed"] for c in e["checks"])
    lift = e["transforms"]["wing_lift"]
    dy, dz = lift[1][3], lift[2][3]
    assert dy < -10 and abs(dz) < 3  # -Y is up: a near-vertical lift
    assert abs(angle_about(lift, [1.0, 0.0, 0.0])) < 1e-9  # the wing does not tilt


@pytest.mark.parametrize("name", ["drivetrain", "gearbox", "dnr", "doors", "wing"])
def test_timelines_are_continuous_and_end_at_rest(name):
    p = load(name)
    up = (kin(name).get("paddle") or {}).get("up_stroke", -0.6)
    rows = tl.timeline(name, p, paddle_up_stroke=up)
    assert len(rows) == tl.FRAMES
    assert tl.continuity(p, rows)["passed"]
    last = rows[-1]["controls"]
    if name == "gearbox":
        gears = {round(r["controls"]["shift"] / (PI / 2), 6) for r in rows}
        assert set(range(8)) <= gears and abs(last["shift"]) < 1e-9
    if name == "dnr":
        assert {r["state"] for r in rows} >= {(1.0, 0.0), (0.0, 1.0), (0.0, 0.0)} and last["selector"] == 0
    if name == "doors":
        assert last["door_left"] == last["door_right"] == 0
    if name == "wing":
        assert last["wing"] == 0


def test_gearbox_reconstruction_is_confined_to_the_extract():
    idmap = OUT / "gearbox/source/idmap.json"
    if not idmap.exists():
        pytest.skip("gearbox extract not generated")
    doc = json.loads(idmap.read_text())
    rec = doc["report"]["reconstructed"]
    assert set(rec) == {"R/S6_12T", "R/S5_12T"}
    text = (OUT / "gearbox/source/42083-gearbox.mpd").read_text().splitlines()
    added = [ln for ln in text if ln.startswith("1 ") and ln.endswith(" 32270.dat")
             and ("80 0 40 " in ln or "-80 -40 160 " in ln)]
    assert len(added) == 2
    from ldraw_mechanisms.source import sha256
    plan = load("drivetrain")
    src = ROOT / "data/models-annotated/42083-1.mpd"
    assert doc["report"]["source_sha256"] == sha256(src)
    assert "32270" not in {r["id"] for r in json.loads((OUT / "gearbox/keep.json").read_text())["parts"]}
    assert plan["source"]["sha256"]  # standalone sources carry their own hashes
