"""Demonstration timelines of the five 42083 mechanism extracts (pure Python, Blender-safe).

Imported by scripts/build_42083_mechanisms.py (continuity check at plan time), by
scripts/blender/animate_42083_mechanisms.py (keys) and by the tests. Only plan controls are
produced; the portable evaluator gives every body signal. Opening limits live here as the
single source shared by the plans and the animation.
"""

from __future__ import annotations

import math
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ldraw_mechanisms import plan as contract  # noqa: E402

PI = math.pi
FPS = 24
FRAMES = 480
OUT = Path(__file__).resolve().parents[1] / "output/42083-mechanisms"
DOOR_MAX = 1.2  # radians (69 deg); clearance-context study: no new crossings up to 1.65 rad with the bodywork
WING_RANGE = (0.0, 0.4)  # radians of the lower cranks; clearance-context study clear to 0.40, rods touch at 0.45


def smooth(u):
    u = min(max(u, 0.0), 1.0)
    return u * u * (3 - 2 * u)


def ramp(f, f0, f1, a_, b_):
    return a_ + (b_ - a_) * smooth((f - f0) / (f1 - f0))


def speed_profile(f, points):
    for (f0, v0), (f1, v1) in zip(points, points[1:]):
        if f0 <= f <= f1:
            return v0 + (v1 - v0) * smooth((f - f0) / (f1 - f0))
    return 0.0


GEARBOX_SHIFTS = [40 + 28 * k for k in range(7)] + [262 + 28 * k for k in range(7)]  # 7 up, 7 down
SHIFT_FRAMES = 16


def controls_at(name, plan, f, up_stroke=-0.6):
    """Selector/opening controls per frame (rotations of shafts are integrated in `timeline`)."""
    if name == "gearbox":
        psi, paddle = 0.0, 0.0
        for k, f0 in enumerate(GEARBOX_SHIFTS):
            sgn = 1 if k < 7 else -1
            stroke = up_stroke if sgn > 0 else -up_stroke
            target = (k + 1 if sgn > 0 else 13 - k) * PI / 2
            start = target - sgn * PI / 2
            if f >= f0:
                psi = ramp(f, f0 + 1, f0 + SHIFT_FRAMES - 1, start, target)
            if f0 <= f <= f0 + SHIFT_FRAMES:
                u = (f - f0) / SHIFT_FRAMES
                paddle = stroke * math.sin(PI * min(1.0, u * 1.15)) if u < 0.87 else 0.0
        return dict(shift=psi, paddle=paddle)
    if name == "dnr":
        sel = 0.0
        for f0, f1, val in ((50, 66, 1.0), (196, 212, 0.0), (236, 252, -1.0), (400, 416, 0.0)):
            if f >= f0:
                sel = ramp(f, f0, f1, sel_prev(f0), val)
        return dict(selector=sel)
    if name == "doors":
        return dict(door_right=ramp(f, 40, 130, 0, DOOR_MAX) if f < 300 else ramp(f, 330, 420, DOOR_MAX, 0),
                    door_left=ramp(f, 90, 180, 0, DOOR_MAX) if f < 260 else ramp(f, 280, 370, DOOR_MAX, 0))
    if name == "wing":
        hi = WING_RANGE[1]
        return dict(wing=ramp(f, 60, 170, 0, hi) if f < 300 else ramp(f, 300, 410, hi, 0))
    return {}


def sel_prev(f0):
    return {50: 0.0, 196: 1.0, 236: 0.0, 400: -1.0}[f0]


SPEEDS = dict(
    drivetrain=[(1, 0.0), (40, 0.16), (420, 0.16), (470, 0.0), (480, 0.0)],
    gearbox=[(1, 0.0), (30, 0.42), (450, 0.42), (475, 0.0), (480, 0.0)],
    dnr=[(1, 0.0), (70, 0.0), (100, 0.3), (180, 0.3), (196, 0.0), (256, 0.0), (290, -0.2), (380, -0.2), (400, 0.0), (480, 0.0)],
)
CARRIES = dict(gearbox=(("s6", "phase_stage1", ("e1", "i1")), ("s2", "phase_stage2", ("e2", "i2"))),
               dnr=(("ring_shaft", "phase_ring_shaft", ("fwd", "rev")),))
STATE = dict(gearbox=("e1", "i1", "e2", "i2"), dnr=("fwd", "rev"))


def timeline(name, plan, paddle_up_stroke=-0.6, frames=FRAMES):
    """Per-frame control values; carries keep shafts continuous when engagement changes."""
    rows, previous = [], None
    shaft = 0.0
    split = dict(diff_front=0.0, diff_rear=0.0)
    carry = {c: 0.0 for _, c, _ in CARRIES.get(name, ())}
    for f in range(1, frames + 1):
        values = controls_at(name, plan, f, paddle_up_stroke)
        if name in SPEEDS:
            if f > 1:
                shaft += speed_profile(f, SPEEDS[name])
            if name == "drivetrain":
                v = speed_profile(f, SPEEDS[name])
                corner = smooth((f - 150) / 30) * smooth((340 - f) / 30)
                if f > 1:
                    split["diff_front"] += 0.16 * corner * v * (1 if f < 245 else -1)
                    split["diff_rear"] += 0.12 * corner * v * (1 if f < 245 else -1)
                values.update(drive=shaft, **split)
            else:
                values.update(input=shaft)
        values.update(carry)
        result = contract.evaluate(plan, values)
        if name in STATE:
            state = tuple(result["signals"][k] for k in STATE[name])
            if previous and state != previous["state"]:
                for sig, ctrl, _ in CARRIES[name]:
                    probe = contract.evaluate(plan, dict(values, **{ctrl: 0.0}))
                    carry[ctrl] = previous["signals"][sig] - probe["signals"][sig]
                    values[ctrl] = carry[ctrl]
                result = contract.evaluate(plan, values)
                state = tuple(result["signals"][k] for k in STATE[name])
        else:
            state = ()
        rows.append(dict(frame=f, controls=values, state=state, signals=result["signals"]))
        previous = rows[-1]
    return rows


def continuity(plan, rows, radians=0.8, ldu=6.0):
    kinds = {b["signal"]: b["kind"] for b in plan["bodies"].values() if b.get("signal")}
    worst = {}
    for a_, b_ in zip(rows, rows[1:]):
        for n in kinds:
            dv = abs(b_["signals"][n] - a_["signals"][n])
            if dv > worst.get(n, (0, 0))[0]:
                worst[n] = (dv, b_["frame"])
    lim = {n: radians if k == "revolute" else ldu for n, k in kinds.items()}
    bad = {n: v for n, v in worst.items() if v[0] > lim[n]}
    top = sorted(((v[0], n, kinds[n], v[1]) for n, v in worst.items()), reverse=True)[:8]
    return dict(limit_radians_per_frame=radians, limit_ldu_per_frame=ldu, worst=top, violations=bad, passed=not bad)


