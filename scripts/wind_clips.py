"""Plant wind catalog: twenty plant cases, one shared wind field and 60 clips (pure Python, Blender-safe).

Imported by scripts/build_plants.py (MPDs, plans and catalog export), scripts/blender/animate_plants.py (actions,
NLA tracks and the scene), scripts/blender/check_plants_*.py and the tests. This module is the single source of the
controls, their wind-response recipes and the clip values; the exported JSON and the Blender actions come from it.

Wind model (a reusable approximation, not aerodynamics or a multibody simulation):
- One wind field blows toward +X (LDraw/Blender X, left to right in the overview). Its speed U(tau) and cross
  component V(tau) are normalised (storm gusts reach about 1). Gusts and turbulence are frozen into the air and
  travel along +X at GUST_SPEED LDU/frame, so a joint at x feels the field at tau = t - (x - X0) / GUST_SPEED.
- Each control (one plan joint) has a recipe. `osc` is a damped second-order response
  x'' + 2*zeta*w*x' + w^2*x = w^2*g(t), with g = gain * drag; drag is |W| * (W . swing) where `swing` is the
  horizontal motion of the joint's tip per radian (so the shared direction decides who leans, folds or flattens), or
  `asym` * |W|^2 for twist joints driven by asymmetric drag. `spin` is a rotor (w' = k*max(|W| - u0, 0) - b*w) and
  `vane` turns a leaf toward the downwind heading. Optional flutter adds sines whose amplitude grows with |W|^2.
- Breeze (A) is the exact periodic steady state (spectrum of the forcing times the transfer function), so frames
  25..217 hold two identical 96-frame periods (a seamless loop); it fades in over frames 1..25 and out over
  217..240. Gusty (B) and storm (C) are integrated from rest with RK4 (8 substeps per frame); the wind picks up,
  gusts, dies away, and a final fade (frames 220..240) returns every control to rest.
- Outputs are soft-limited (tanh) to the control range; spins end on a multiple of 2*pi/symmetry (an identical pose
  for a flower with that many petals).

Keys: one LINEAR key per integer clip frame, so `value_at` (linear interpolation) equals what Blender plays.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np

PI = math.pi
TAU = 2 * PI
FPS = 24
CLIP_FRAMES = 240
WINDOWS = {"A": (1, 240), "B": (257, 496), "C": (513, 752)}
FRAMES = 752
REGIMES = {"A": "breeze", "B": "gusty", "C": "storm"}
PERIOD = 96  # breeze period (frames)
LOOP = (25, 217)  # breeze loop range: two periods, value(217) == value(25)
SUB = 8  # integration substeps per frame
FADE = (220, 240)  # final fade of gusty/storm clips
GUST_SPEED = 48.0  # LDU per frame: gusts travel along +X
WIND_DIR = (1.0, 0.0, 0.0)
COLUMNS, ROWS = 5, 4
PITCH_X, PITCH_Z = 520.0, 500.0
X0 = -(COLUMNS - 1) / 2 * PITCH_X - 240.0  # gust front origin (left edge of the field)
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "output/plants"
LDU = 0.0004  # metres per LDU in the converted GLB
FLEX_LIMIT = 0.17  # rad, maximum range of a flex_approx joint


def slot_xz(row, col):
    """Case origin in the field (LDU): columns along +X (the wind), row 0 in front (-Z), row 3 at the back."""
    return ((col - (COLUMNS - 1) / 2) * PITCH_X, (row - (ROWS - 1) / 2) * PITCH_Z)


# --------------------------------------------------------------------------- recipes
def osc(f, zeta, gain, x, swing=(1.0, 0.0), lag=0.0, drive="drag", asym=0.0, asym_v=0.0, threshold=0.0,
        flutter=(), lift=0.0):
    """Damped response: natural frequency f (Hz), damping ratio zeta, gain (rad per unit drive).

    drive="drag": |W| * (u*swing_x + v*swing_z), swing = horizontal tip motion per radian (LDraw x, z);
    drive="speed": asym*|W|^2 + asym_v*|W|*v (twist from asymmetric drag). `lag` delays the drive (frames);
    `threshold` ignores drive below it (sheltered parts); `lift` adds lift*|W|^2 (a flat leaf or branch rising
    in stronger wind); flutter = [(amp rad at |W|=1, f Hz, phase rad)]."""
    return dict(kind="osc", f=f, zeta=zeta, gain=gain, x=x, swing=list(swing), lag=lag, drive=drive, asym=asym,
                asym_v=asym_v, threshold=threshold, lift=lift, flutter=[list(t) for t in flutter])


def spin(k, u0, damping, x, steps=1, symmetry=1, sign=1.0, flutter=()):
    """Free rotor: w' = k*max(|W| - u0, 0) - damping*w (rad/frame); the breeze advances `steps` symmetric steps
    (2*pi/symmetry each) per period; clips end on a multiple of 2*pi/symmetry."""
    return dict(kind="spin", k=k, u0=u0, damping=damping, x=x, steps=steps, symmetry=symmetry, sign=sign,
                flutter=[list(t) for t in flutter])


def vane(stiffness, damping, heading, x, flutter=()):
    """Weathervane yaw (+ = right-hand about up, -Y): theta'' = -K*|W|^2*sin(heading + theta - wind heading)
    - c*theta'. `heading` = rest direction of the leaf tip, atan2(z, x) in the case frame."""
    return dict(kind="vane", stiffness=stiffness, damping=damping, heading=heading, x=x,
                flutter=[list(t) for t in flutter])


def control(unit, lo, hi, description, recipe, joint="real", symmetry=None):
    if joint not in ("real", "flex_approx"):
        raise ValueError(joint)
    return dict(unit=unit, min=lo, max=hi, description=description, recipe=recipe, joint=joint,
                periodic=recipe["kind"] == "spin", symmetry=symmetry or recipe.get("symmetry"))


# --------------------------------------------------------------------------- wind field
REGIME_SPECS = {
    # mean speed, turbulence [(amp, cycles per frame, phase)], cross wind, gusts [(centre, amp, width)], envelope
    "A": dict(mean=0.42, turb=[(0.07, 1 / 96, 0.3), (0.04, 3 / 96, 1.1), (0.025, 5 / 96, 2.0), (0.012, 11 / 96, 0.5)],
              cross=[(0.06, 2 / 96, 0.7), (0.03, 7 / 96, 1.9)], gusts=[], ramp=None),
    "B": dict(mean=0.45, turb=[(0.05, 1 / 37, 0.4), (0.03, 1 / 17.3, 1.3), (0.015, 1 / 7.1, 2.2)],
              cross=[(0.08, 1 / 41, 0.2), (0.05, 1 / 13.7, 1.0)],
              gusts=[(48, 0.33, 12), (104, 0.42, 9), (150, 0.3, 13)], ramp=(0, 30, 145, 175)),
    "C": dict(mean=0.8, turb=[(0.08, 1 / 29, 0.9), (0.05, 1 / 11.3, 2.1), (0.03, 1 / 5.3, 0.3)],
              cross=[(0.15, 1 / 33, 1.4), (0.09, 1 / 9.7, 0.2), (0.04, 1 / 4.9, 2.6)],
              gusts=[(40, 0.22, 11), (88, 0.3, 8), (126, 0.2, 12), (158, 0.28, 8)], ramp=(0, 36, 150, 180)),
}
REGIME_TEXT = {
    "A": "Gentle breeze (mean speed 0.42, 4 s swell; frames 25-217 loop seamlessly).",
    "B": "Gusty wind: picks up, three gusts sweep across the field from the left, then dies away.",
    "C": "Storm: strong steady push with four hard gusts and cross-wind turbulence, then calm.",
}


def smoothstep(a):
    a = min(max(a, 0.0), 1.0)
    return a * a * (3 - 2 * a)


def envelope(regime, tau):
    ramp = REGIME_SPECS[regime]["ramp"]
    if ramp is None:
        return 1.0
    a, b, c, d = ramp
    return smoothstep((tau - a) / (b - a)) * (1 - smoothstep((tau - c) / (d - c)))


def _sines(tau, terms):
    return sum(a * math.sin(TAU * f * tau + p) for a, f, p in terms)


def wind(regime, t, x):
    """(u, v): wind along +X and +Z felt at case-frame-independent field position x (LDU) at clip time t (frames,
    0 at clip frame 1)."""
    spec = REGIME_SPECS[regime]
    tau = t - (x - X0) / GUST_SPEED
    env = envelope(regime, tau)
    gust = sum(a * math.exp(-((tau - c) / w) ** 2) for c, a, w in spec["gusts"])
    u = env * (spec["mean"] + gust + _sines(tau, spec["turb"]))
    v = env * _sines(tau, spec["cross"])
    return u, v


def delay(x):
    return (x - X0) / GUST_SPEED


# --------------------------------------------------------------------------- responses
def _drive(recipe, regime, t, x):
    u, v = wind(regime, t - recipe.get("lag", 0.0), x)
    s = math.hypot(u, v)
    if recipe["drive"] == "drag":
        g = s * (u * recipe["swing"][0] + v * recipe["swing"][1]) + recipe.get("lift", 0.0) * s * s
    else:
        g = recipe["asym"] * s * s + recipe["asym_v"] * s * v
    th = recipe["threshold"]
    if th:
        g = math.copysign(max(abs(g) - th, 0.0), g)
    return recipe["gain"] * g


def _flutter(recipe, regime, t, x):
    if not recipe["flutter"]:
        return 0.0
    u, v = wind(regime, t, x)
    s2 = u * u + v * v
    # Frequencies snap to harmonics of the breeze period so that the breeze stays periodic.
    return s2 * sum(a * math.sin(TAU * round(4 * f) / PERIOD * t + p) for a, f, p in recipe["flutter"])


def _rk4(deriv, state, t0, steps, h):
    out = [state]
    t = t0
    for _ in range(steps):
        k1 = deriv(t, state)
        k2 = deriv(t + h / 2, [s + h / 2 * k for s, k in zip(state, k1)])
        k3 = deriv(t + h / 2, [s + h / 2 * k for s, k in zip(state, k2)])
        k4 = deriv(t + h, [s + h * k for s, k in zip(state, k3)])
        state = [s + h / 6 * (a + 2 * b + 2 * c + d) for s, a, b, c, d in zip(state, k1, k2, k3, k4)]
        t += h
        out.append(state)
    return out


def _periodic_linear(samples, transfer):
    """Steady state of a linear system for periodic forcing sampled over one period at SUB per frame."""
    n = len(samples)
    spectrum = np.fft.fft(np.asarray(samples, float))
    omega = TAU * np.fft.fftfreq(n, d=1.0 / SUB)  # rad per frame
    return np.real(np.fft.ifft(spectrum * transfer(omega)))


def _osc_transfer(recipe):
    w = TAU * recipe["f"] / FPS
    z = recipe["zeta"]
    return lambda om: w * w / (w * w - om * om + 2j * z * w * om)


def _osc_ode(recipe, regime, x):
    w = TAU * recipe["f"] / FPS
    z = recipe["zeta"]

    def deriv(t, s):
        return [s[1], -2 * z * w * s[1] - w * w * (s[0] - _drive(recipe, regime, t, x))]

    return deriv


def _window(f):
    """Breeze fade-in/out over clip frames 1..25 and 217..240 (1 inside the loop range)."""
    if f <= LOOP[0]:
        return smoothstep((f - 1) / (LOOP[0] - 1))
    if f >= LOOP[1]:
        return 1 - smoothstep((f - LOOP[1]) / (CLIP_FRAMES - LOOP[1]))
    return 1.0


def _fade(f):
    return 1 - smoothstep((f - FADE[0]) / (FADE[1] - FADE[0]))


def soft_limit(value, lo, hi):
    if value >= 0:
        return hi * math.tanh(value / hi) if hi > 0 else 0.0
    return lo * math.tanh(value / lo) if lo < 0 else 0.0


def respond(spec, regime, slot_x):
    """Values at clip frames 1..CLIP_FRAMES for one control spec in one regime (case placed at slot_x)."""
    r = spec["recipe"]
    x = slot_x + r["x"]
    frames = range(1, CLIP_FRAMES + 1)
    n_steps = (CLIP_FRAMES - 1) * SUB
    h = 1.0 / SUB
    if r["kind"] == "osc":
        if regime == "A":
            n = PERIOD * SUB
            g = [_drive(r, regime, j * h, x) for j in range(n)]
            xs = _periodic_linear(g, _osc_transfer(r))
            raw = [xs[((f - 1) * SUB) % n] for f in frames]
        else:
            states = _rk4(_osc_ode(r, regime, x), [0.0, 0.0], 0.0, n_steps, h)
            raw = [states[(f - 1) * SUB][0] for f in frames]
        out = []
        for f, value in zip(frames, raw):
            value = soft_limit(value + _flutter(r, regime, f - 1, x), spec["min"], spec["max"])
            out.append(value * (_window(f) if regime == "A" else _fade(f)))
        return out
    if r["kind"] == "spin":
        step = TAU / (r["symmetry"] or 1)
        torque = [r["k"] * max(math.hypot(*wind(regime, j * h, x)) - r["u0"], 0.0)
                  for j in range((PERIOD if regime == "A" else CLIP_FRAMES) * SUB)]
        if regime == "A":
            omega = _periodic_linear(torque, lambda om: 1.0 / (r["damping"] + 1j * om))
            omega *= r["steps"] * step / (float(np.mean(omega)) * PERIOD)  # whole steps per period
            n = len(omega)
            w = [omega[j % n] * _window(1 + j * h) for j in range(n_steps + 1)]
        else:
            states = _rk4(lambda t, s: [torque[min(int(round(t * SUB)), len(torque) - 1)] - r["damping"] * s[0]],
                          [0.0], 0.0, n_steps, h)
            w = [s[0] * _fade(1 + j * h) for j, s in enumerate(states)]
        theta = [0.0]
        for a, b in zip(w, w[1:]):
            theta.append(theta[-1] + (a + b) * h / 2)
        raw = [theta[(f - 1) * SUB] for f in frames]
        if regime == "A":
            end = raw[-1]
            target = step * math.ceil(end / step - 1e-9)
            raw = [v + (target - end) * (smoothstep((f - LOOP[1]) / (CLIP_FRAMES - LOOP[1])) if f > LOOP[1] else 0)
                   for f, v in zip(frames, raw)]
        else:
            end = raw[-1]
            target = step * max(1, round(end / step))
            raw = [v * target / end for v in raw]
        return [r["sign"] * v for v in raw]
    if r["kind"] == "vane":
        k, c = r["stiffness"], r["damping"]

        def deriv(t, s):
            u, v = wind(regime, t, x)
            return [s[1], -k * (u * u + v * v) * math.sin(r["heading"] + s[0] - math.atan2(v, u)) - c * s[1]]

        if regime == "A":
            warm = 10 * PERIOD * SUB
            states = _rk4(deriv, [0.0, 0.0], -10.0 * PERIOD, warm + PERIOD * SUB, h)[warm:]
            period = [s[0] for s in states[:PERIOD * SUB]]
            raw = [period[((f - 1) * SUB) % len(period)] for f in frames]
        else:
            states = _rk4(deriv, [0.0, 0.0], 0.0, n_steps, h)
            raw = [states[(f - 1) * SUB][0] for f in frames]
        out = []
        for f, value in zip(frames, raw):
            value = soft_limit(value + _flutter(r, regime, f - 1, x), spec["min"], spec["max"])
            out.append(value * (_window(f) if regime == "A" else _fade(f)))
        return out
    raise ValueError(r["kind"])


# --------------------------------------------------------------------------- roster
STYLES = {
    "whip_chain": "Segmented trunk or vine: each joint lags the one below and swings further, so a bend travels "
                  "to the tip like a whip",
    "crown_twist": "A crown or head turns back and forth about its stem from asymmetric drag",
    "leaf_flex": "Large leaves lift and droop at their roots; upwind leaves are lifted, downwind leaves flattened",
    "frond_flap": "Clip-hinged fronds flap about their bars, staggered in time",
    "cane_sway": "Tall rigid canes lean on ball joints, each at its own (height-dependent) frequency",
    "rustle": "Small leaf pieces jiggle about their bar or stud, fast and out of phase",
    "stem_lean": "A thin stem leans downwind and springs back (flex_approx)",
    "twirl": "Flower heads turn back and forth on their pins",
    "heavy_nod": "A heavy head on a hinge: slow, lightly damped nod with overshoot",
    "pinwheel_spin": "Free spin about a bar facing the wind, speed following the gusts",
    "ripple_wave": "A field of identical stems: the gust front makes a visible wave cross it",
    "lean_recover": "Well damped lean with the gusts and recovery, no lingering oscillation",
    "two_level": "A slow stalk carries fast leaves (two natural frequencies in one plant)",
    "hanging_chain": "A hanging flexible chain: the bottom swings most and lags the top",
    "domino_gust": "A row along the wind: each element starts later (gust front plus shelter lag)",
    "branch_bounce": "Hinged branches bounce springily (low damping, higher frequency)",
    "shiver": "Pendant leaves tremble fast with small amplitude (aspen)",
    "directional": "Identical leaves react by their facing: upwind fold over, downwind flatten, cross-wind flutter",
    "bouquet_jiggle": "Several stems and heads in one vase, each with its own small motion",
    "tier_cascade": "Tiers stacked on one bar twist one after another (helical lag up the stack)",
    "rope_rock": "A vine strung between two clips rocks about the line through them",
    "pendulum_swing": "Identical hanging pendulums: the passing gust sets their phase",
    "sheltered_flicker": "Ground plants ignore the breeze and only flick in gusts (drive threshold)",
    "weathervane": "Leaves free to turn about a vertical bar swing round to point downwind and hunt there",
    "torsion_wave": "Stacked crowns on one axle twist with a lag between them",
    "breeze_loop": "Breeze clip: seamless 4 s loop (frames 25-217)",
    "gust_response": "Gusty clip: rest, three gusts, rest",
    "storm_push": "Storm clip: strong mean push (soft-limited at the range ends) with hard gusts",
}


def lean(desc, lo, hi, f, zeta, gain, x=0.0, swing=(1.0, 0.0), lag=0.0, flutter=(), joint="real", threshold=0.0,
         lift=0.0):
    """Joint driven by drag along its tip's horizontal motion (lean, bend, flap, nod, swing); x and swing are
    filled from GEOMETRY below."""
    return control("radian", lo, hi, desc, osc(f, zeta, gain, x, swing, lag, threshold=threshold,
                                               flutter=flutter, lift=lift), joint)


def twist(desc, lo, hi, f, zeta, gain, asym, x=0.0, lag=0.0, asym_v=0.0, threshold=0.0, flutter=(),
          joint="real"):
    """Joint about a stem/bar/stud axis driven by asymmetric drag (twist, twirl, rustle, flicker)."""
    return control("radian", lo, hi, desc, osc(f, zeta, gain, x, (0.0, 0.0), lag, drive="speed", asym=asym,
                                               asym_v=asym_v, threshold=threshold, flutter=flutter), joint)


FLEX = "flex_approx"
DOWN = "+ leans it downwind (+X)"
RISE = "+ lifts the tip"
TWIST_UP = "right-hand about up (-Y): + turns +X toward +Z"
FL = ((0.04, 3.2, 0.0), (0.02, 4.7, 1.3))  # leaf flutter (rad at |W| = 1)

CASES = [
    dict(key="P01_palm_tree", title="Ball-chain palm", plan="plant_01_palm_tree", slot=(3, 0),
         element="Palm 2518c01 taken apart: base 2563a, six 2536a ball-jointed trunk segments, top 2566b, four "
                 "2518 leaves",
         how="The trunk bends as a whip through six ball joints (each lagging the one below), the crown twists "
             "on its spike and the four big leaves lift or flatten by their facing.",
         styles=["whip_chain", "crown_twist", "leaf_flex"],
         controls=dict(
             **{f"bend_{k}": lean(f"Trunk segment {k} on its ball joint (real, 1 of 2 tilts); {DOWN}", -0.2, 0.2,
                                  0.5, 0.1, 0.07 + 0.012 * k, lag=1.5 * k) for k in range(1, 7)},
             crown_twist=twist(f"Crown on the top segment's spike (real); {TWIST_UP} about the trunk", -0.6, 0.6,
                               0.7, 0.15, 1.0, 0.3, asym_v=0.4, flutter=((0.03, 1.9, 0.4),)),
             **{f"leaf_{n}": lean(f"Leaf {n} at its root (flex_approx); {RISE}", -FLEX_LIMIT, FLEX_LIMIT, 1.4,
                                  0.12, 0.3, flutter=FL, joint=FLEX)
                for n in ("front", "upwind", "back", "downwind")})),
    dict(key="P02_swordleaf_palm", title="Swordleaf palm", plan="plant_02_swordleaf_palm", slot=(3, 1),
         element="Four 10884 swordleaf fronds clipped on 60478 handle bars on a round-brick trunk",
         how="Each frond flaps about its handle bar; fronds respond by facing and are staggered in time.",
         styles=["frond_flap", "directional"],
         controls={f"frond_{n}": lean(f"Frond {n} on its clip (real); {RISE}", -0.38, 0.45, 1.1, 0.12, 0.7, lag=lag,
                                      flutter=FL)
                   for n, lag in (("downwind", 0), ("upwind", 3), ("back", 6), ("front", 9))}),
    dict(key="P03_bamboo", title="Bamboo clump", plan="plant_03_bamboo", slot=(3, 2),
         element="Four 10315 bamboo stalks on 22484 ball joints in 14418 friction sockets, splayed",
         how="Each cane sways on its ball joint at its own frequency (taller = slower); the top leaf bricks "
             "rustle about the cane's bar.",
         styles=["cane_sway", "rustle"],
         controls=dict(
             **{f"cane_{k}": lean(f"Cane {k} on its ball joint (real, 1 of 2 tilts); {DOWN}", -0.14, 0.14, f, 0.07,
                                  0.16) for k, f in zip(range(1, 5), (0.42, 0.5, 0.62, 0.75))},
             **{f"rustle_{k}{s}": twist(f"Leaf brick {s} of cane {k} on the bar (real); {TWIST_UP} about the cane",
                                        -0.5, 0.5, 2.2, 0.15, 1.0, a, asym_v=0.3, flutter=((0.05, 3.6, ph),))
                for k in range(1, 5) for s, a, ph in (("a", 0.3, 0.2), ("b", -0.25, 1.7))})),
    dict(key="P04_flower_bed", title="Flower bed", plan="plant_04_flower_bed", slot=(0, 1),
         element="Three 3741a flower stems with nine 3742 flowers in round-brick pots",
         how="The stems lean downwind (flex_approx) and the flower heads twirl on their pins.",
         styles=["stem_lean", "twirl"],
         controls=dict(
             **{f"stem_{k}": lean(f"Stem {k} at its pot (flex_approx); {DOWN}", -FLEX_LIMIT, FLEX_LIMIT, 1.4, 0.2,
                                  0.3, joint=FLEX) for k in range(1, 4)},
             **{f"head_{k}{s}": twist(f"Flower {k}{s} on its pin (real); right-hand about the pin", -0.8, 0.8, 1.8,
                                      0.12, 1.0, a, asym_v=0.3, flutter=((0.06, 2.6, ph),))
                for k in range(1, 4) for s, a, ph in (("a", 0.4, 0.0), ("b", -0.35, 1.1), ("c", 0.3, 2.3))})),
    dict(key="P05_sunflower", title="Sunflower", plan="plant_05_sunflower", slot=(1, 3),
         element="Flower 4x4 35473 on a 2540 handle plate clipped in a 61252 clip atop a round-brick stem",
         how="A heavy head nods slowly on its clip hinge with overshoot while the stalk leans a little.",
         styles=["heavy_nod", "stem_lean"],
         controls=dict(
             stem_lean=lean(f"Stalk at the base (flex_approx); {DOWN}", -0.12, 0.12, 0.9, 0.15, 0.12, joint=FLEX),
             nod=lean(f"Head about the clip (real); {DOWN}", -0.5, 0.6, 0.45, 0.05, 0.9))),
    dict(key="P06_pinwheel_daisies", title="Pinwheel daisies", plan="plant_06_pinwheel_daisies", slot=(0, 3),
         element="Flowers with bar 32606 / 95831 / 4367 in 63868 clips on a post, facing the wind",
         how="Each flower spins about its bar like a pinwheel, speed following the gusts (artistic: a real flower "
             "has no blade pitch).",
         styles=["pinwheel_spin"],
         controls={f"spin_{k}": control("radian", -80.0, 80.0, f"Daisy {k} about its bar (real); right-hand about "
                                        "+X", spin(kk, 0.3, 0.03, 0.0, steps=st, symmetry=sym, sign=sg), symmetry=sym)
                   for k, kk, st, sym, sg in ((1, 0.012, 7, 7, 1.0), (2, 0.010, 6, 6, -1.0),
                                              (3, 0.014, 14, 7, 1.0))}),
    dict(key="P07_grass_meadow", title="Grass meadow", plan="plant_07_grass_meadow", slot=(0, 2),
         element="Ten 15279 grass stems on a base plate",
         how="Every blade leans with the wind and recovers; the gust front crosses the meadow as a wave.",
         styles=["ripple_wave", "lean_recover"],
         controls={f"blade_{k}": lean(f"Blade {k} at its stud (flex_approx); {DOWN}", -FLEX_LIMIT, FLEX_LIMIT,
                                      1.2 + 0.07 * (k % 5), 0.35, 0.25, joint=FLEX) for k in range(1, 11)}),
    dict(key="P08_reeds", title="Reeds", plan="plant_08_reeds", slot=(2, 0),
         element="Two 30093 sea-grass reeds in cones, each with a 30239 swordleaf clipped on its top bar",
         how="The reeds lean slowly (flex_approx) while their clipped leaves swing fast about the top bars like flags.",
         styles=["two_level", "frond_flap"],
         controls=dict(
             **{f"stalk_{k}": lean(f"Reed {k} at its cone (flex_approx); {DOWN}", -0.15, 0.15, 0.7, 0.12, 0.2,
                                   joint=FLEX) for k in (1, 2)},
             **{f"leaf_{k}": lean(f"Leaf {k} about the reed's top bar (real); {TWIST_UP}", -0.6, 0.6, 2.0, 0.15, 0.8,
                                  flutter=FL) for k in (1, 2)})),
    dict(key="P09_hanging_vine", title="Hanging leafy vine", plan="plant_09_hanging_vine", slot=(3, 3),
         element="Vine 16981 rebuilt from its segment subfiles as five links, hung by its end bar in a 60897 clip",
         how="The vine twists in its clip and swings as a chain: the lower links lag and swing further.",
         styles=["hanging_chain", "whip_chain"],
         controls=dict(
             twist=twist(f"Top end bar in the clip (real); {TWIST_UP}", -0.8, 0.8, 0.4, 0.1, 1.0, 0.35,
                         asym_v=0.5),
             **{f"bend_{k}": lean(f"Vine bend {k} (flex_approx); {DOWN} (lower part)", -FLEX_LIMIT, FLEX_LIMIT,
                                  0.55, 0.06, 0.12 + 0.03 * k, lag=3 * k, joint=FLEX) for k in range(1, 5)})),
    dict(key="P10_rushes", title="Rushes row", plan="plant_10_rushes", slot=(2, 1),
         element="Four short stalks (as 10315 bamboo-stalk-3, with 32607 leaf plates) on 22484 ball joints in a "
                 "row along the wind",
         how="The rushes lean in turn as the gust passes along the row (front delay plus a shelter lag).",
         styles=["domino_gust", "cane_sway"],
         controls={f"rush_{k}": lean(f"Rush {k} on its ball joint (real, 1 of 2 tilts); {DOWN}", -0.12, 0.24, 0.9,
                                     0.1, 0.24, lag=3 * (k - 1)) for k in range(1, 5)}),
    dict(key="P11_hinged_oak", title="Oak with hinged branches", plan="plant_11_hinged_oak", slot=(2, 2),
         element="Four 2540 branch plates with 2423 leaves clipped in 61252 clips on a round-brick trunk",
         how="The branches bounce on their clip hinges: springy, lightly damped, by facing.",
         styles=["branch_bounce", "directional"],
         controls={f"branch_{n}": lean(f"Branch {n} on its clip (real); {RISE}", -0.3, 0.3, 1.3, 0.05, 0.9,
                                       lift=0.2) for n in ("front", "downwind", "back", "upwind")}),
    dict(key="P12_aspen", title="Shivering aspen", plan="plant_12_aspen", slot=(1, 4),
         element="Five 2423 leaves on the side studs of 4733 bricks and the top of a round-brick trunk",
         how="Pendant leaves shiver about their studs: fast, small, mostly flutter.",
         styles=["shiver"],
         controls=dict(
             leaf_top=twist(f"Top leaf on its stud (real); {TWIST_UP}", -0.4, 0.4, 2.5, 0.12, 1.0, 0.2,
                            flutter=((0.06, 3.8, 0.3),)),
             **{f"leaf_{n}": lean(f"Leaf {n} hanging from a side stud (real); "
                                  + (DOWN if n in ("front", "back") else "right-hand about the stud axis"),
                                  -0.4, 0.4, 2.5, 0.12, 0.4, flutter=((0.08, 3.6 + 0.2 * i, i),))
                for i, n in enumerate(("front", "back", "upwind", "downwind"))})),
    dict(key="P13_fern", title="Fern bush", plan="plant_13_fern", slot=(1, 2),
         element="Four 30239 swordleaves clipped on 60478 handle bars over a round brick",
         how="Identical fronds react by facing: the upwind frond is lifted over, the downwind one flattened, "
             "the cross-wind ones flutter.",
         styles=["directional", "frond_flap"],
         controls={f"frond_{n}": lean(f"Frond {n} on its clip (real); {RISE}", -0.28, 0.5, 1.5, 0.12, 1.4,
                                      flutter=FL) for n in ("downwind", "upwind", "back", "front")}),
    dict(key="P14_bouquet", title="Vase bouquet", plan="plant_14_bouquet", slot=(1, 0),
         element="10297 vase with 24855 and three 32606 flowers, and a second vase with 19119 and six 3742",
         how="One stem leans (flex_approx), the other twists in its vase, and every head spins a little on its pin.",
         styles=["bouquet_jiggle", "twirl"],
         controls=dict(
             stem_a=lean(f"Stem A in its vase (flex_approx); {DOWN}", -0.14, 0.14, 1.2, 0.15, 0.25, joint=FLEX),
             **{f"head_a{k}": twist(f"Flower A{k} on its pin (real); right-hand about the pin", -0.7, 0.7, 1.6, 0.12,
                                    1.0, a, flutter=((0.05, 2.4, k),)) for k, a in zip((1, 2, 3), (0.3, -0.35, 0.25))},
             stem_b=twist(f"Stem B in its vase (real); {TWIST_UP}", -0.5, 0.5, 0.9, 0.12, 1.0, 0.3, asym_v=0.3),
             **{f"head_b{k}": twist(f"Flower B{k} on its pin (real); right-hand about the pin", -0.7, 0.7, 1.8, 0.12,
                                    1.0, a, flutter=((0.05, 2.8, k),))
                for k, a in zip(range(1, 7), (0.3, -0.25, 0.35, -0.3, 0.2, -0.35))})),
    dict(key="P15_tiered_shrub", title="Tiered shrub", plan="plant_15_tiered_shrub", slot=(0, 4),
         element="Four 1566 plant tiers threaded on a 6L bar",
         how="The tiers twist one after another up the bar (a helical cascade).",
         styles=["tier_cascade"],
         controls={f"tier_{k}": twist(f"Tier {k} on the bar (real); {TWIST_UP}", -0.7, 0.7, 0.8, 0.12, 1.0, 0.45,
                                      lag=5 * (k - 1), asym_v=0.3) for k in range(1, 5)}),
    dict(key="P16_liana", title="Lianas", plan="plant_16_liana", slot=(2, 3),
         element="Thorny vine 73828 and leafy vine 16981 strung across the wind between clips on posts",
         how="Each vine rocks about the line through its two clips; its thorns or leaves swing downwind.",
         styles=["rope_rock"],
         controls=dict(rock_thorny=lean(f"Thorny vine about its end bars (real); {DOWN} (hanging thorns)", -0.6,
                                        0.6, 0.6, 0.08, 0.7),
                       rock_leafy=lean(f"Leafy vine about its end bars (real); {DOWN} (lower leaves)", -0.6, 0.6,
                                       0.5, 0.08, 0.7))),
    dict(key="P17_tendrils", title="Hanging tendrils", plan="plant_17_tendrils", slot=(2, 4),
         element="Three 28870 curved stems hung by their bars in 61252 clips under an arch, and a 1997 curl",
         how="Identical tendrils swing as pendulums, phased by the passing gust; the curl can only twist in its "
             "vertical clip.",
         styles=["pendulum_swing"],
         controls=dict(
             **{f"swing_{k}": lean(f"Tendril {k} about its clip (real); {DOWN}", -0.3, 0.45, 0.75, 0.06, 0.6)
                for k in (1, 2, 3)},
             twist_curl=twist(f"Curl 1997 about its bar (real); {TWIST_UP}", -0.8, 0.8, 0.5, 0.1, 1.0, 0.35,
                              asym_v=0.4))),
    dict(key="P18_ground_cover", title="Ground cover", plan="plant_18_ground_cover", slot=(0, 0),
         element="Six low plants (6255, 7264, 32607, 4728, 98262, 2682a) on studs",
         how="Sheltered plants ignore the breeze and only flick round on their studs in gusts.",
         styles=["sheltered_flicker"],
         controls={f"turn_{k}": twist(f"Plant {k} on its stud (real); {TWIST_UP}", -0.5, 0.5, 2.4, 0.18, 1.5, a,
                                      threshold=0.15)
                   for k, a in zip(range(1, 7), (0.4, -0.35, 0.45, -0.4, 0.35, -0.45))}),
    dict(key="P19_leaf_vanes", title="Leaf weathervanes", plan="plant_19_leaf_vanes", slot=(1, 1),
         element="Palm leaves 2518 / 6148 each turning on a vertical bar through one of its holes, poles in a "
                 "row along the wind (tallest upwind)",
         how="Each leaf swings round to point downwind and hunts about that heading.",
         styles=["weathervane"],
         controls={f"vane_{k}": control("radian", lo, hi, f"Leaf {k} about its bar (real); {TWIST_UP}",
                                        vane(0.085, 0.08, h, 0.0, flutter=((0.04, 2.2, k),)))
                   for k, h, lo, hi in ((1, 3 * PI / 4, -2.8, 0.6), (2, -PI / 2, -0.9, 2.2),
                                        (3, PI / 2, -2.2, 0.9))}),
    dict(key="P20_friends_palm", title="Palm crowns on an axle", plan="plant_20_friends_palm", slot=(3, 4),
         element="Curved palm trunk 30338 with two 30339 quadruple leaves turning on its top axle",
         how="The two crowns twist on the axle, the upper one lagging (a torsion wave).",
         styles=["torsion_wave", "crown_twist"],
         controls={f"crown_{k}": twist(f"Crown {k} on the axle (real); right-hand about the axle's up direction",
                                       -0.45, 0.45, 0.5, 0.1, 1.0, a, lag=lag, asym_v=0.4)
                   for k, a, lag in ((1, 0.35, 0.0), (2, 0.3, 6.0))}),
]

# Measured by `scripts/build_plants.py geometry` (joint x in the case frame; horizontal motion of the body's
# tip per radian of + rotation). build_plants.py plan re-measures and refuses a mismatch.
GEOMETRY = {
    'P01_palm_tree': {
        'bend_1': (0, (1, 0)), 'bend_2': (0, (1, 0)), 'bend_3': (0, (1, 0)), 'bend_4': (0, (1, 0)),
        'bend_5': (0, (1, 0)), 'bend_6': (0, (1, 0)), 'crown_twist': (0, (0, 0.906)),
        'leaf_front': (-10, (0, -0.517)), 'leaf_upwind': (0, (-0.106, -0.421)), 'leaf_back': (10, (0, -0.325)),
        'leaf_downwind': (0, (0.106, -0.421)),
    },
    'P02_swordleaf_palm': {
        'frond_downwind': (50, (0.53, 0)), 'frond_upwind': (-50, (-0.53, 0)), 'frond_back': (10, (0, 0.309)),
        'frond_front': (10, (0, -0.309)),
    },
    'P03_bamboo': {
        'cane_1': (-10, (0.954, 0)), 'rustle_1a': (-69.5, (-0.043, 0.957)), 'rustle_1b': (-78.7, (0.043, -0.957)),
        'cane_2': (10, (0.968, 0)), 'rustle_2a': (52.3, (-0.901, -0.303)), 'rustle_2b': (60.1, (0.901, 0.303)),
        'cane_3': (10, (0.936, 0)), 'rustle_3a': (57.8, (0.56, -0.684)), 'rustle_3b': (65.8, (-0.759, -0.65)),
        'cane_4': (-10, (0.926, 0)), 'rustle_4a': (-49.6, (-0.525, -0.842)), 'rustle_4b': (-58.1, (-0.775, 0.408)),
    },
    'P04_flower_bed': {
        'stem_1': (-60, (1, 0)), 'head_1a': (-50.7, (0.034, -0.98)), 'head_1b': (-75.5, (-0.011, -0.999)),
        'head_1c': (-54.2, (-0.022, -0.97)), 'stem_2': (0, (1, 0)), 'head_2a': (14.2, (0.011, -0.999)),
        'head_2b': (-10.1, (-0.034, -0.98)), 'head_2c': (-5.8, (0.022, -0.97)), 'stem_3': (60, (1, 0)),
        'head_3a': (72.5, (-0.029, -0.992)), 'head_3b': (60, (0, -0.966)), 'head_3c': (45.2, (0.029, -0.992)),
    },
    'P05_sunflower': {
        'stem_lean': (0, (1, 0)), 'nod': (-20, (0.581, 0)),
    },
    'P06_pinwheel_daisies': {
        'spin_1': (0, (0, -1)), 'spin_2': (0, (0, -1)), 'spin_3': (0, (0, -1)),
    },
    'P07_grass_meadow': {
        'blade_1': (-70, (1, 0)), 'blade_2': (-50, (1, 0)), 'blade_3': (-30, (1, 0)), 'blade_4': (-30, (1, 0)),
        'blade_5': (-10, (1, 0)), 'blade_6': (10, (1, 0)), 'blade_7': (30, (1, 0)), 'blade_8': (30, (1, 0)),
        'blade_9': (50, (1, 0)), 'blade_10': (70, (1, 0)),
    },
    'P08_reeds': {
        'stalk_1': (-40, (0.995, 0)), 'leaf_1': (-30, (1, 0)), 'stalk_2': (40, (0.995, 0)), 'leaf_2': (30, (-1, 0)),
    },
    'P09_hanging_vine': {
        'twist': (20, (0, 1)), 'bend_1': (20, (1, 0)), 'bend_2': (20, (1, 0)), 'bend_3': (20, (1, 0)),
        'bend_4': (20, (1, 0)),
    },
    'P10_rushes': {
        'rush_1': (-120, (1, 0)), 'rush_2': (-40, (1, 0)), 'rush_3': (40, (1, 0)), 'rush_4': (120, (1, 0)),
    },
    'P11_hinged_oak': {
        'branch_front': (-10, (0, 0.124)), 'branch_downwind': (30, (-0.124, 0)), 'branch_back': (10, (0, -0.124)),
        'branch_upwind': (-30, (0.124, 0)),
    },
    'P12_aspen': {
        'leaf_top': (0, (0.94, -0.342)), 'leaf_front': (0, (1, 0)), 'leaf_back': (0, (1, 0)),
        'leaf_upwind': (-10, (0, -1)), 'leaf_downwind': (10, (0, 1)),
    },
    'P13_fern': {
        'frond_downwind': (50, (-0.208, 0)), 'frond_upwind': (-50, (0.208, 0)), 'frond_back': (10, (0, -0.469)),
        'frond_front': (10, (0, 0.469)),
    },
    'P14_bouquet': {
        'stem_a': (-40, (1, 0)), 'head_a1': (-32.4, (0.078, -0.955)), 'head_a2': (-47.6, (-0.334, -0.934)),
        'head_a3': (-40, (-0.987, 0.131)), 'stem_b': (40, (0.5, 0.866)), 'head_b1': (26.6, (-0.112, -0.968)),
        'head_b2': (53.4, (0.112, -0.968)), 'head_b3': (19.7, (0.433, -0.883)), 'head_b4': (40, (0, -0.866)),
        'head_b5': (40, (0, -0.342)), 'head_b6': (60.3, (-0.433, -0.883)),
    },
    'P15_tiered_shrub': {
        'tier_1': (0, (0.5, 0.866)), 'tier_2': (0, (0.766, -0.643)), 'tier_3': (0, (-0.766, -0.643)),
        'tier_4': (0, (-0.5, 0.866)),
    },
    'P16_liana': {
        'rock_thorny': (-30, (1, 0)), 'rock_leafy': (30, (1, 0)),
    },
    'P17_tendrils': {
        'swing_1': (-50, (1, 0)), 'swing_2': (-10, (1, 0)), 'swing_3': (30, (1, 0)), 'twist_curl': (-10, (1, 0)),
    },
    'P18_ground_cover': {
        'turn_1': (-50, (0.766, 0.643)), 'turn_2': (50, (0.985, -0.174)), 'turn_3': (-10, (0.5, -0.866)),
        'turn_4': (-50, (-0.342, -0.94)), 'turn_5': (50, (-0.94, -0.342)), 'turn_6': (10, (-0.866, 0.5)),
    },
    'P19_leaf_vanes': {
        'vane_1': (-50, (-0.707, -0.707)), 'vane_2': (10, (1, 0)), 'vane_3': (70, (-1, 0)),
    },
    'P20_friends_palm': {
        'crown_1': (-7.7, (0, -1)), 'crown_2': (-7.7, (0.683, -0.707)),
    },
}
for _case in CASES:
    for _name, _spec in _case["controls"].items():
        # A control missing here (while authoring) keeps x = 0 and a +X swing; build_plants.py plan refuses it.
        _x, _swing = GEOMETRY.get(_case["key"], {}).get(_name, (0.0, (1.0, 0.0)))
        _spec["recipe"]["x"] = _x
        if _spec["recipe"]["kind"] == "osc" and _spec["recipe"]["drive"] == "drag":
            _spec["recipe"]["swing"] = list(_swing)

BY_KEY = {c["key"]: c for c in CASES}


def case_slot(case):
    return slot_xz(*case["slot"])


# --------------------------------------------------------------------------- clips
def value_at(values, frame):
    """Linear interpolation of per-frame values (index 0 = clip frame 1), held outside the clip."""
    if frame <= 1:
        return values[0]
    if frame >= len(values):
        return values[-1]
    i = int(math.floor(frame)) - 1
    a = frame - (i + 1)
    return values[i] + (values[i + 1] - values[i]) * a if a else values[i]


class Clip:
    """Dense per-frame values of every control of one case in one wind regime (clip-local frames from 1)."""

    def __init__(self, case, window):
        self.case, self.window = case, window
        self.regime = REGIMES[window]
        c = BY_KEY[case]
        self.name = self.regime
        self.title = f"{c['title']}: {self.regime}"
        self.description = f"{REGIME_TEXT[window]} {c['how']}"
        self.styles = list(c["styles"]) + [{"A": "breeze_loop", "B": "gust_response", "C": "storm_push"}[window]]
        self.frames = CLIP_FRAMES
        self.loop = list(LOOP) if window == "A" else None
        self.channels = list(c["controls"])
        sx, _ = case_slot(c)
        self.slot_x = sx
        self._values = {ch: [float(v) for v in respond(spec, window, sx)] for ch, spec in c["controls"].items()}

    @property
    def id(self):
        return f"{self.case}.{self.name}"

    def series(self, channel):
        return self._values[channel]

    def value(self, channel, frame):
        return value_at(self._values[channel], frame)

    def values(self, frame):
        return {c: self.value(c, frame) for c in self.channels}


_LIBRARY = None


def library():
    """All clips in case order, three per case (windows A, B, C). Cached: the clips are deterministic."""
    global _LIBRARY
    if _LIBRARY is None:
        _LIBRARY = [Clip(c["key"], w) for c in CASES for w in "ABC"]
    return list(_LIBRARY)


def wind_series(window, x=0.0):
    """Wind (u, v) at field position x for every clip frame: the shared input every case responds to."""
    return [wind(window, f - 1, x) for f in range(1, CLIP_FRAMES + 1)]


# --------------------------------------------------------------------------- checks and export
def check(clip, tolerance=1e-9):
    """Clip rules: rest at start and end (spins may end on a symmetric step), ranges, step size, breeze loop."""
    problems = []
    controls = BY_KEY[clip.case]["controls"]
    for ch in clip.channels:
        spec = controls[ch]
        values = clip.series(ch)
        if abs(values[0]) > tolerance:
            problems.append(f"{ch} starts at {values[0]}")
        step = TAU / (spec["symmetry"] or 1)
        end = values[-1]
        if spec["periodic"]:
            if abs(end / step - round(end / step)) > 1e-6:
                problems.append(f"{ch} ends at {end}, not a multiple of 2*pi/{spec['symmetry']}")
        elif abs(end) > tolerance:
            problems.append(f"{ch} ends at {end}")
        if not spec["periodic"] and (min(values) < spec["min"] - tolerance or max(values) > spec["max"] + tolerance):
            problems.append(f"{ch} leaves [{spec['min']}, {spec['max']}]: {min(values):.4f}..{max(values):.4f}")
        if spec["periodic"] and max(abs(v) for v in values) > max(abs(spec["min"]), spec["max"]):
            problems.append(f"{ch} exceeds its spin range")
        jump = max((abs(b - a) for a, b in zip(values, values[1:])), default=0.0)
        if jump > 0.35:
            problems.append(f"{ch} jumps {jump:.3f} rad in one frame")
        if clip.loop:
            a, b = clip.loop
            d = values[b - 1] - values[a - 1]
            if spec["periodic"]:
                d -= 2 * spec["recipe"]["steps"] * step * spec["recipe"]["sign"]
            if abs(d) > 1e-9:
                problems.append(f"{ch} breeze loop mismatch {d:.3g}")
        if spec["joint"] == "flex_approx" and max(abs(spec["min"]), abs(spec["max"])) > FLEX_LIMIT + 1e-9:
            problems.append(f"{ch} flex_approx range exceeds {FLEX_LIMIT} rad")
    return problems


def window_of(clip):
    return clip.window


def blender_names(clip):
    c = BY_KEY[clip.case]
    return dict(action=clip.id, action_slot="OBplant_controller", nla_track=f"{clip.window} {clip.name}",
                controller=f"CTRL_{c['plan']}", collection=f"{c['key']} {c['title']}", scene="Wind",
                strip_start=WINDOWS[clip.window][0], camera=f"CAM_{c['key'][:3]}")


def clip_document(clip):
    c = BY_KEY[clip.case]
    sx, sz = case_slot(c)
    return dict(
        id=clip.id, case=clip.case, clip=clip.name, regime=clip.regime, title=clip.title,
        description=clip.description, styles=clip.styles, window=clip.window,
        timeline_start=WINDOWS[clip.window][0], frames=clip.frames, fps=FPS,
        duration_seconds=round(clip.frames / FPS, 3), loop_range=clip.loop,
        blender=blender_names(clip),
        wind=dict(regime=REGIME_SPECS[clip.window], direction=WIND_DIR, gust_speed_ldu_per_frame=GUST_SPEED,
                  field_origin_x=X0, slot=[sx, sz], case_delay_frames=round(delay(sx), 3)),
        channels={ch: dict(unit=spec["unit"], min=spec["min"], max=spec["max"], meaning=spec["description"],
                           joint=spec["joint"], recipe=spec["recipe"], symmetry=spec["symmetry"],
                           interpolation="LINEAR", wind_delay_frames=round(delay(sx + spec["recipe"]["x"]), 3))
                  for ch, spec in c["controls"].items()},
        baked={ch: [round(v, 6) for v in clip.series(ch)] for ch in clip.channels},
        notes="Clip-local frames start at 1; one LINEAR key per frame ('baked'). Values are the case's plan "
              "controls in radians. Regenerate with scripts/wind_clips.py (respond(spec, window, slot_x)) to move "
              "a case elsewhere in the field: the wind delay depends on x.",
    )


def conventions():
    return dict(
        case_frame="LDraw LDU per case: -Y up, the case front faces -Z (towards the overview camera), ground (top of "
                   "the base) at y = 0. Each control's default 0 is the built pose.",
        wind="Blows toward +X (LDraw and Blender). Gusts travel along +X at GUST_SPEED LDU/frame from X0; a joint at "
             "field x feels the wind (x - X0)/GUST_SPEED frames after the field origin.",
        signs="+ = downwind (tip moves +X) for lean/bend joints; + = tip rises (-Y) for hinged leaves and fronds; "
              "twist/spin joints turn right-handed about the axis stated in each control's description.",
        joints="real = a LEGO connection that allows this rotation (ball socket, clip on bar, bar or pin in a hole, "
               "stud); flex_approx = a rigid-part tilt standing in for bending plastic, at most "
               f"{FLEX_LIMIT} rad.",
        rules="Every clip starts at rest and ends at rest (spins on a symmetric step); breeze clips loop seamlessly "
              f"over frames {LOOP[0]}-{LOOP[1]}.",
        windows=WINDOWS, fps=FPS, frames=FRAMES, regimes=REGIMES, regime_specs=REGIME_SPECS,
        gust_speed_ldu_per_frame=GUST_SPEED, field_origin_x=X0, grid=dict(columns=COLUMNS, rows=ROWS,
                                                                          pitch_x=PITCH_X, pitch_z=PITCH_Z),
        styles=STYLES,
    )


def export(directory=OUT):
    directory = Path(directory)
    (directory / "clips").mkdir(parents=True, exist_ok=True)
    docs = []
    for clip in library():
        problems = check(clip)
        if problems:
            raise ValueError(f"{clip.id}: {problems}")
        doc = clip_document(clip)
        (directory / "clips" / f"{clip.id}.json").write_text(json.dumps(doc, indent=1) + "\n")
        docs.append(doc)
    wind_doc = {REGIMES[w]: dict(window=w, start=WINDOWS[w][0],
                                 u=[round(u, 6) for u, _ in wind_series(w)], v=[round(v, 6) for _, v in wind_series(w)])
                for w in "ABC"}
    (directory / "clips" / "WIND.json").write_text(json.dumps(dict(
        note="Shared wind at field x = 0 (the centre column); a case at x feels it (x - X0)/GUST_SPEED - "
             "(0 - X0)/GUST_SPEED frames later.", **wind_doc), indent=1) + "\n")
    return docs
