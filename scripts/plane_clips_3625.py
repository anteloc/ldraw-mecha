"""Pure-Python timeline for the 3625 plane: take off, cruise and land without leaving the spot.

Channels (one value per frame, 1-based frames at 24 fps):

    joints   prop, wheel, head, arm_l, arm_r        plan controls, radians (see scripts/build_plane_3625.py)
    staging  climb (+ nose up, rad), bank (+ left side down, rad), lift (+ up, LDU)

The plane never translates sideways or forwards; `lift` is the only translation. Staging is a root transform
about PIVOT, not part of the plan (see scripts/blender/animate_plane_3625.py). Every channel finishes at its rest
value; `prop` finishes on a whole number of blade periods (three identical blades).
"""

import math

FPS = 24
END = 570
LDU = 0.0004  # metres per LDU in the converted GLB
PIVOT = (0.0, -56.0, -30.0)  # LDraw frame: roughly the plane's centre of mass, between wing and cockpit
BLADE_PERIOD = 2 * math.pi / 3
JOINTS = ("prop", "wheel", "head", "arm_l", "arm_r")
STAGING = ("climb", "bank", "lift")
CHANNELS = JOINTS + STAGING


def smooth(u):
    u = min(max(u, 0.0), 1.0)
    return u * u * (3 - 2 * u)


def ramp(f, f0, f1, a, b):
    return a + (b - a) * smooth((f - f0) / (f1 - f0))


def piece(f, knots):
    """Smoothly interpolate (frame, value) knots; flat outside the first and last."""
    if f <= knots[0][0]:
        return knots[0][1]
    for (f0, a), (f1, b) in zip(knots, knots[1:]):
        if f <= f1:
            return ramp(f, f0, f1, a, b)
    return knots[-1][1]


def window(f, f0, f1, fade):
    """1 between f0 and f1, faded in/out over `fade` frames."""
    return smooth((f - f0) / fade) * smooth((f1 - f) / fade)


# Propeller speed (rad/frame): idle, full power for take-off and flight, throttle back, stop.
PROP_SPEED = [(1, 0.0), (24, 0.0), (72, 0.30), (132, 0.85), (440, 0.85), (500, 0.30), (560, 0.0)]
# Wheel speed (rad/frame): take-off roll, coast down in the air, spin up before touchdown, roll out.
WHEEL_SPEED = [(1, 0.0), (96, 0.0), (150, 0.40), (200, 0.0), (396, 0.0), (440, 0.40), (540, 0.0)]
STOP_FROM = 500  # the final prop slow-down, stretched so the blades stop on a whole period
CRUISE = (230, 350)


def climb(f):
    base = piece(f, [(1, 0.0), (132, 0.0), (168, 0.20), (230, 0.06), (350, 0.03), (390, -0.07), (410, -0.07),
                     (432, 0.14), (452, 0.10), (480, 0.0), (570, 0.0)])
    w = window(f, *CRUISE, 24)
    return base + 0.03 * w * math.sin(2 * math.pi * (f - CRUISE[0]) / 80 + 1.0)


def bank(f):
    w = window(f, *CRUISE, 36)
    return 0.28 * w * math.sin(2 * math.pi * (f - CRUISE[0]) / 120)


def lift(f):
    base = piece(f, [(1, 0.0), (150, 0.0), (186, 60.0), (230, 130.0), (350, 130.0), (410, 45.0), (440, 8.0),
                     (452, 0.0), (570, 0.0)])
    w = window(f, *CRUISE, 24)
    bounce = 3.0 * math.sin(math.pi * min(max((f - 452) / 12, 0.0), 1.0))  # one shallow rebound after touchdown
    return base + 8.0 * w * math.sin(2 * math.pi * (f - CRUISE[0]) / 80) + bounce


def head(f):
    return 0.65 * window(f, 240, 340, 30) * math.sin(2 * math.pi * (f - 240) / 110)


def arms(f):
    """(left, right) shoulder angles: hands forward on the yoke for take-off and landing, steering in cruise."""
    forward = 0.2 * max(window(f, 120, 230, 24), window(f, 350, 480, 30))
    steer = 0.2 * bank(f) / 0.28
    return forward - steer, forward + steer


def prop_angles():
    """Cumulative propeller angle per frame; the last slow-down is scaled so it stops on a blade period."""
    def total(k):
        angle, out = 0.0, [0.0]
        for f in range(2, END + 1):
            v = piece(f, PROP_SPEED)
            if f > STOP_FROM:
                v *= k
            angle += v
            out.append(angle)
        return out

    pre = total(0.0)[STOP_FROM - 1]  # angle accumulated before the stop phase begins (k=0 freezes it)
    unit = total(1.0)[-1] - pre
    target = math.ceil((pre + unit) / BLADE_PERIOD) * BLADE_PERIOD
    return total((target - pre) / unit)


def wheel_angles():
    angle, out = 0.0, [0.0]
    for f in range(2, END + 1):
        angle += piece(f, WHEEL_SPEED)
        out.append(angle)
    return out


def timeline():
    prop, wheel = prop_angles(), wheel_angles()
    rows = []
    for f in range(1, END + 1):
        left, right = arms(f)
        rows.append(dict(frame=f, prop=prop[f - 1], wheel=wheel[f - 1], head=head(f), arm_l=left, arm_r=right,
                         climb=climb(f), bank=bank(f), lift=lift(f)))
    return rows


def staging_matrix(climb_, bank_, lift_):
    """4x4 (rows) LDU transform of the airframe in the LDraw frame: lift, then pitch, then bank about PIVOT.

    Forward is -Z, left +X, up -Y. Nose up rotates -Z towards -Y; left side down rotates +X towards +Y.
    """
    ca, sa = math.cos(-climb_), math.sin(-climb_)  # about the left axis
    cb, sb = math.cos(bank_), math.sin(bank_)  # about the back axis
    rx = [[1, 0, 0], [0, ca, -sa], [0, sa, ca]]
    rz = [[cb, -sb, 0], [sb, cb, 0], [0, 0, 1]]
    r = [[sum(rx[i][k] * rz[k][j] for k in range(3)) for j in range(3)] for i in range(3)]
    p = PIVOT
    t = [p[i] - sum(r[i][j] * p[j] for j in range(3)) for i in range(3)]
    t[1] -= lift_
    return [r[0] + [t[0]], r[1] + [t[1]], r[2] + [t[2]], [0, 0, 0, 1]]


def check(rows, tolerance=1e-9):
    """Rest at both ends, joint ranges respected, no per-frame jumps, no sideways/forward travel."""
    errors = []
    first, last = rows[0], rows[-1]
    for c in CHANNELS:
        if abs(first[c]) > tolerance:
            errors.append(f"{c} starts at {first[c]}")
        if c != "prop" and c != "wheel" and abs(last[c]) > tolerance:
            errors.append(f"{c} ends at {last[c]}")
    if abs(last["prop"] / BLADE_PERIOD - round(last["prop"] / BLADE_PERIOD)) > 1e-9:
        errors.append("prop does not stop on a blade period")
    limits = dict(head=1.2, arm_l=0.6, arm_r=0.6)
    for r in rows:
        for c, lim in limits.items():
            if abs(r[c]) > lim:
                errors.append(f"{c} out of range at {r['frame']}")
    jump = dict(prop=0.9, wheel=0.5, head=0.06, arm_l=0.04, arm_r=0.04, climb=0.02, bank=0.02, lift=4.0)
    for a, b in zip(rows, rows[1:]):
        for c, lim in jump.items():
            if abs(b[c] - a[c]) > lim:
                errors.append(f"{c} jumps {abs(b[c] - a[c]):.3f} at {b['frame']}")
    return errors


if __name__ == "__main__":
    rows = timeline()
    problems = check(rows)
    print("frames", len(rows), "problems", problems or "none")
    for c in CHANNELS:
        vals = [r[c] for r in rows]
        print(f"{c:6s} min {min(vals):9.3f} max {max(vals):9.3f} end {vals[-1]:9.3f}")
