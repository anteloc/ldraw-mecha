"""Movable-element catalog: twenty scenarios, their controls and 60 clips (pure Python, Blender-safe).

Imported by scripts/build_movables.py (MPDs, plans and catalog export), scripts/blender/animate_movables.py
(actions, NLA tracks and scenes), scripts/blender/check_movables_*.py and the tests. This module is the single
source of the controls and the clip keyframes; the exported JSON and the Blender actions are generated from it.

Each scenario has its own controller with one custom property per plan control (radians or LDU). Keys are sparse;
each key's interpolation applies to the segment that starts at it and uses Blender's own easing formulas (Penner
equations, as in BLI_easing.c), so `value_at` reproduces what Blender evaluates. BACK keys use Blender's default
`back` factor 1.70158; BOUNCE uses Blender's fixed bounce curve.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

PI = math.pi
TAU = 2 * PI
FPS = 24
FRAMES = 480
WINDOWS = {"A": (1, 144), "B": (161, 304), "C": (321, 464)}
MAX_CLIP_FRAMES = 144
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "output/movables"
LDU = 0.0004  # metres per LDU in the converted GLB
BACK = 1.70158  # Blender's default keyframe `back` factor


def control(unit, lo, hi, description, periodic=False):
    return dict(unit=unit, min=lo, max=hi, description=description, periodic=periodic)


# Scenario roster. `controls` become the plan controls (default 0 = the built pose) and the controller's custom
# properties; ranges are catalog choices narrowed by clearance against the mock context (see REPORT.md).
SCENARIOS = [
    dict(key="S01_house_door", title="House front door", plan="movable_01_house_door",
         element="Door 1x4x6 (60616b) in door frame 60596",
         controls=dict(door=control("radian", 0.0, 1.75, "Door leaf about its frame hinge; + swings the door "
                                    "open toward the front (-Z)"))),
    dict(key="S02_casement_window", title="Casement window", plan="movable_02_casement_window",
         element="Two panes 60608 in window 1x4x3 60594",
         controls=dict(pane_l=control("radian", 0.0, 1.4, "Left pane (viewer's left) about its side hinge; + "
                                      "opens it toward the viewer (-Z)"),
                       pane_r=control("radian", 0.0, 1.4, "Right pane (viewer's right) about its side hinge; + "
                                      "opens it toward the viewer (-Z)"))),
    dict(key="S03_shuttered_window", title="Shuttered window", plan="movable_03_shuttered_window",
         element="Two shutters 3856 on classic window 1x4x3 3853",
         controls=dict(shutter_l=control("radian", 0.0, 3.0, "Left shutter; 0 = closed over the glass, + folds it "
                                         "open outward toward the wall"),
                       shutter_r=control("radian", 0.0, 3.0, "Right shutter; 0 = closed over the glass, + folds it "
                                         "open outward toward the wall"))),
    dict(key="S04_garden_gate", title="Garden gate", plan="movable_04_garden_gate",
         element="Gate 1x4x2 3186 on gate base 3187 between fences",
         controls=dict(gate=control("radian", -1.6, 1.6, "Gate about its post; + swings it outward (-Z), - "
                                    "inward (+Z)"))),
    dict(key="S05_kitchen_cupboard", title="Kitchen cupboard", plan="movable_05_kitchen_cupboard",
         element="Cupboard 2x3x2 4532 with door 4533 and two drawers 4536",
         controls=dict(door=control("radian", 0.0, 1.9, "Lower cupboard door; + opens outward (-Z)"),
                       drawer_top=control("ldu", 0.0, 30.0, "Upper drawer; + pulls it out (-Z)"),
                       drawer_low=control("ldu", 0.0, 30.0, "Lower drawer of the upper cupboard; + pulls it out"))),
    dict(key="S06_double_cabinet", title="Double-door cabinet", plan="movable_06_double_cabinet",
         element="Cupboard 2x6x7 2042 with two doors 2043",
         controls=dict(door_l=control("radian", 0.0, 1.9, "Left door; + opens outward (-Z)"),
                       door_r=control("radian", 0.0, 1.9, "Right door; + opens outward (-Z)"))),
    dict(key="S07_treasure_chest", title="Treasure chest", plan="movable_07_treasure_chest",
         element="Treasure chest 4738a with lid 4739a",
         controls=dict(lid=control("radian", 0.0, 1.9, "Lid about the rear hinge; + lifts the front edge"))),
    dict(key="S08_mailbox", title="Mailbox", plan="movable_08_mailbox",
         element="Container box 2x2x2 4345a with slot door 4346 on a post",
         controls=dict(door=control("radian", 0.0, 1.6, "Front door about its bottom hinge; + drops it open "
                                    "forward and down"))),
    dict(key="S09_trap_door", title="Floor trap door", plan="movable_09_trap_door",
         element="Trap door 30042 in trap door frame 30041 on pillars",
         controls=dict(trap=control("radian", 0.0, 1.95, "Trap door about its edge pins; + drops the free end "
                                    "down into the pit"))),
    dict(key="S10_car_doors", title="Town car doors", plan="movable_10_car_doors",
         element="Car doors 1x3x1 3822 (left) / 3821 (right) on a mock town car",
         controls=dict(door_l=control("radian", 0.0, 1.3, "Left door (-Z side); + swings the rear edge out"),
                       door_r=control("radian", 0.0, 1.3, "Right door (+Z side); + swings the rear edge out"))),
    dict(key="S11_car_roof", title="Car roof hatch", plan="movable_11_car_roof",
         element="Hinge car roof 4x4 4213 on roof holder 4214",
         controls=dict(roof=control("radian", 0.0, 1.3, "Roof about the rear holder hinge; + lifts the front "
                                    "edge"))),
    dict(key="S12_canopy", title="Spaceship canopy", plan="movable_12_canopy",
         element="Windscreen 4x4x3 with hinge 2620 on hinge plate 4315",
         controls=dict(canopy=control("radian", 0.0, 1.6, "Canopy about the rear hinge; + lifts the front"))),
    dict(key="S13_forklift", title="Forklift mast", plan="movable_13_forklift",
         element="Forklift 2x7: rails 3430, forks 3431, spring u9529",
         controls=dict(lift=control("ldu", 0.0, 100.0, "Forks along the rails; + raises them (0 = lowered, 100 "
                                    "= raised, as shortcuts 3430c00-f2 / -f1)"))),
    dict(key="S14_sliding_door", title="Sliding shed door", plan="movable_14_sliding_door",
         element="Sliding door 6.5x5 4511 in door-rail plates 4510",
         controls=dict(slide=control("ldu", 0.0, 150.0, "Door along the rails; + slides it open to the right "
                                     "(+X)"))),
    dict(key="S15_radar", title="Rotating radar", plan="movable_15_radar",
         element="Dish 4x4 3960 on turntable 2x2 3680/3679",
         controls=dict(spin=control("radian", -8 * PI, 8 * PI, "Turntable top; + turns counter-clockwise seen "
                                    "from above", periodic=True))),
    dict(key="S16_crane", title="Mini crane", plan="movable_16_crane",
         element="Turntable 4x4 3403/3404 slew, hinge 3937/6134 luffing boom, plumb hook 3136",
         controls=dict(slew=control("radian", -PI, PI, "Superstructure on the turntable; + turns counter-"
                                    "clockwise seen from above"),
                       luff=control("radian", 0.0, 1.1, "Boom about its hinge; + raises the tip"))),
    dict(key="S17_tipper", title="Dump truck tipper", plan="movable_17_tipper",
         element="Tipper bucket 4080 on hinge plates 4275b / hinge tiles 4531",
         controls=dict(tip=control("radian", 0.0, 1.0, "Bucket about the rear hinge; + raises the front"))),
    dict(key="S18_barrier", title="Parking barrier", plan="movable_18_barrier",
         element="Boom on hinge 1x2 3937/3938",
         controls=dict(boom=control("radian", 0.0, 1.5, "Boom about its post hinge; + raises the tip"))),
    dict(key="S19_drawbridge", title="Drawbridge", plan="movable_19_drawbridge",
         element="Bridge deck on two hinge 1x2 pairs 3937/3938",
         controls=dict(bridge=control("radian", 0.0, 1.55, "Bridge deck about the threshold hinges; + raises it "
                                      "(0 = lowered across the moat)"))),
    dict(key="S20_levers", title="Control levers", plan="movable_20_levers",
         element="Two control sticks 4593 in bases 4592",
         controls=dict(lever_l=control("radian", -0.7, 0.7, "Left stick; + tilts it forward (-Z)"),
                       lever_r=control("radian", -0.7, 0.7, "Right stick; + tilts it forward (-Z)"))),
]
BY_KEY = {s["key"]: s for s in SCENARIOS}
STYLES = {
    "ease_cycle": "Open, hold, close with sine ease-in/out; starts and ends at rest with zero speed (loops cleanly)",
    "slam_bounce": "Fast close into a stop with Blender's BOUNCE ease-out: accelerates, hits, rebounds twice, settles",
    "hesitant": "Small stepped openings with pauses (a creaking or cautious opening)",
    "mirrored_pair": "Two elements move together with identical values (mirrored by their axes)",
    "staggered_pair": "Two elements move one after the other, overlapping in time",
    "damped_swing": "Released element swings through its rest position with decaying sine half-cycles",
    "flutter": "Small irregular oscillations about a partly open position (wind)",
    "peek": "Partial opening (a crack), hold, close; repeated or single",
    "gravity_drop": "Falls open under gravity: QUAD ease-in or BOUNCE ease-out onto a stop",
    "winch_linear": "Constant-speed (LINEAR) movement, like a winch or motor",
    "overshoot_settle": "Moves past the target and settles back with Blender's BACK ease-out (gas strut, spring)",
    "stepped": "Equal steps with holds (chain hoist, ratchet, hydraulic stages)",
    "continuous_spin": "Constant angular speed over whole turns (loops cleanly)",
    "spin_up_down": "Accelerates (QUAD in), cruises (LINEAR), decelerates (QUAD out) to a whole number of turns",
    "sweep": "Back-and-forth sine oscillation about the rest position (scanning)",
    "slide_bounce": "Slides into an end stop with a BOUNCE ease-out",
    "sequence": "Several channels in a scripted order (open, use, close)",
    "shake": "Fast small oscillation around a held pose (shaking out a load)",
    "toggle": "Snap between positions with very short QUAD moves and holds",
}

INTERPOLATIONS = {
    # name: (Blender interpolation, Blender easing)
    "CONSTANT": ("CONSTANT", "AUTO"),
    "LINEAR": ("LINEAR", "AUTO"),
    "SINE_IN": ("SINE", "EASE_IN"),
    "SINE_OUT": ("SINE", "EASE_OUT"),
    "SINE_IN_OUT": ("SINE", "EASE_IN_OUT"),
    "QUAD_IN": ("QUAD", "EASE_IN"),
    "QUAD_OUT": ("QUAD", "EASE_OUT"),
    "QUAD_IN_OUT": ("QUAD", "EASE_IN_OUT"),
    "CUBIC_IN_OUT": ("CUBIC", "EASE_IN_OUT"),
    "BACK_OUT": ("BACK", "EASE_OUT"),
    "BOUNCE_OUT": ("BOUNCE", "EASE_OUT"),
}


def ease(kind, t, b, c, d):
    """Blender's easing equations (BLI_easing.c): time t of duration d, start b, change c."""
    if kind == "CONSTANT":
        return b
    if kind == "LINEAR":
        return b + c * t / d
    if kind == "SINE_IN":
        return -c * math.cos(t / d * (PI / 2)) + c + b
    if kind == "SINE_OUT":
        return c * math.sin(t / d * (PI / 2)) + b
    if kind == "SINE_IN_OUT":
        return -c / 2 * (math.cos(PI * t / d) - 1) + b
    if kind == "QUAD_IN":
        t /= d
        return c * t * t + b
    if kind == "QUAD_OUT":
        t /= d
        return -c * t * (t - 2) + b
    if kind == "QUAD_IN_OUT":
        t /= d / 2
        if t < 1:
            return c / 2 * t * t + b
        t -= 1
        return -c / 2 * (t * (t - 2) - 1) + b
    if kind == "CUBIC_IN_OUT":
        t /= d / 2
        if t < 1:
            return c / 2 * t * t * t + b
        t -= 2
        return c / 2 * (t * t * t + 2) + b
    if kind == "BACK_OUT":
        t = t / d - 1
        return c * (t * t * ((BACK + 1) * t + BACK) + 1) + b
    if kind == "BOUNCE_OUT":
        t /= d
        if t < 1 / 2.75:
            return c * (7.5625 * t * t) + b
        if t < 2 / 2.75:
            t -= 1.5 / 2.75
            return c * (7.5625 * t * t + 0.75) + b
        if t < 2.5 / 2.75:
            t -= 2.25 / 2.75
            return c * (7.5625 * t * t + 0.9375) + b
        t -= 2.625 / 2.75
        return c * (7.5625 * t * t + 0.984375) + b
    raise ValueError(f"Unknown interpolation {kind}")


def value_at(keys, frame):
    """Evaluate sparse keys [(frame, value, interpolation)] with constant extrapolation."""
    if frame <= keys[0][0]:
        return keys[0][1]
    for (f0, v0, kind), (f1, v1, _) in zip(keys, keys[1:]):
        if f0 <= frame <= f1:
            return ease(kind, frame - f0, v0, v1 - v0, f1 - f0) if f1 > f0 else v1
    return keys[-1][1]


class Clip:
    """Sparse keyframes per control channel of one scenario; frames are clip-local, starting at 1."""

    def __init__(self, scenario, name, title, description, styles, frames=MAX_CLIP_FRAMES, loop=None):
        if not 1 < frames <= MAX_CLIP_FRAMES:
            raise ValueError(f"{scenario}.{name}: clip length must be 2..{MAX_CLIP_FRAMES} frames")
        unknown = set(styles) - set(STYLES)
        if unknown:
            raise ValueError(f"{scenario}.{name}: unknown styles {unknown}")
        self.scenario, self.name, self.title, self.description = scenario, name, title, description
        self.styles, self.frames, self.loop = list(styles), frames, loop
        self.channels = list(BY_KEY[scenario]["controls"])
        self._keys = {c: {} for c in self.channels}

    @property
    def id(self):
        return f"{self.scenario}.{self.name}"

    def key(self, channel, frame, value, interp="SINE_IN_OUT"):
        if channel not in self._keys:
            raise ValueError(f"{self.id}: unknown channel {channel}")
        if interp not in INTERPOLATIONS:
            raise ValueError(f"Unknown interpolation {interp}")
        if not 1 <= frame <= self.frames:
            raise ValueError(f"{self.id}: key at frame {frame} outside 1..{self.frames}")
        self._keys[channel][round(float(frame), 4)] = (float(value), interp)
        return self

    def seq(self, channel, points, interp="SINE_IN_OUT"):
        """Add (frame, value[, interpolation]) points; the interpolation applies to the segment after the key."""
        for p in points:
            self.key(channel, p[0], p[1], p[2] if len(p) > 2 else interp)
        return self

    def keys(self, channel):
        """Sorted keys of a channel, always bracketing the clip with keys at 1 and at the last frame."""
        k = dict(self._keys[channel])
        if 1 not in k:
            k[1] = (0.0, "SINE_IN_OUT")
        last = float(self.frames)
        if last not in k:
            k[last] = (k[max(k)][0], "SINE_IN_OUT")
        return [(f, v, i) for f, (v, i) in sorted(k.items())]

    def value(self, channel, frame):
        return value_at(self.keys(channel), frame)

    def values(self, frame):
        return {c: self.value(c, frame) for c in self.channels}


# --------------------------------------------------------------------------- helpers
def cycle(c, ch, f0, f1, f2, f3, value, interp="SINE_IN_OUT"):
    """Rest until f0, move to `value` by f1, hold to f2, back to rest by f3."""
    c.seq(ch, [(f0, 0.0, interp), (f1, value, "CONSTANT" if f2 > f1 else interp), (f2, value, interp), (f3, 0.0)])


def damped(c, ch, f0, centre, start, amps, half, end=None, end_frame=None):
    """From `start` at f0, sine half-swings through `centre` with amplitudes `amps` (alternating sides), each
    `half` frames long, then settle at `centre` (or `end` by end_frame)."""
    c.key(ch, f0, start)
    f = f0
    sign = -1.0 if start > centre else 1.0
    for a in amps:
        f += half
        c.key(ch, f, centre + sign * a)
        sign = -sign
        half = max(4, half * 0.85)
    f += half
    c.key(ch, f, centre)
    if end is not None:
        c.key(ch, end_frame, end)
    return f


def wave(c, ch, f0, period, half_cycles, amps, centre=0.0, sign=1.0):
    """Sine wave starting and ending on centre crossings: extremes alternate at quarter periods."""
    q = period / 4
    amps = [amps] * half_cycles if isinstance(amps, (int, float)) else list(amps)
    c.key(ch, f0, centre, "SINE_OUT")
    for k in range(half_cycles):
        s = sign if k % 2 == 0 else -sign
        c.key(ch, f0 + q + 2 * q * k, centre + s * amps[k], "SINE_IN_OUT" if k < half_cycles - 1 else "SINE_IN")
    f1 = f0 + 2 * q * half_cycles
    c.key(ch, f1, centre)
    return f1


def steps(c, ch, f0, values, move, hold, interp="QUAD_IN_OUT"):
    """Move through `values` one after another: `move` frames each, `hold` frames between."""
    f = f0
    c.key(ch, f, 0.0 if not c._keys[ch] else c.value(ch, f), interp)
    for v in values:
        c.key(ch, f + move, v, "CONSTANT")
        c.key(ch, f + move + hold, v, interp)
        f += move + hold
    return f


# --------------------------------------------------------------------------- clips (three per scenario)
def s01():
    k = "S01_house_door"
    a = Clip(k, "open_close", "Open and close", "The door swings open to about 92 deg, waits, and closes.",
             ["ease_cycle"], loop=(1, 144))
    cycle(a, "door", 8, 44, 96, 136, 1.6)
    b = Clip(k, "slam", "Slam shut", "Opens calmly, then is let go: it slams shut and bounces twice off the frame.",
             ["slam_bounce"])
    b.seq("door", [(8, 0.0), (40, 1.5, "CONSTANT"), (70, 1.5, "BOUNCE_OUT"), (100, 0.0)])
    c = Clip(k, "creak", "Creaking open", "Opens in small hesitant pushes with pauses, then swings shut.",
             ["hesitant", "gravity_drop"])
    c.seq("door", [(6, 0.0), (16, 0.18, "CONSTANT"), (26, 0.18), (36, 0.4, "CONSTANT"), (48, 0.4), (56, 0.55, "CONSTANT"),
                   (70, 0.55), (86, 1.0, "CONSTANT"), (104, 1.0, "QUAD_IN"), (124, 0.0)])
    return [a, b, c]


def s02():
    k = "S02_casement_window"
    a = Clip(k, "open_both", "Open both panes", "Both panes open together toward the viewer, wait, and close.",
             ["mirrored_pair", "ease_cycle"], loop=(1, 144))
    for ch in ("pane_l", "pane_r"):
        cycle(a, ch, 10, 46, 98, 134, 1.3)
    b = Clip(k, "one_by_one", "One pane after the other", "Left pane opens, then the right; they close in reverse "
             "order.", ["staggered_pair"])
    cycle(b, "pane_l", 8, 40, 104, 134, 1.25)
    cycle(b, "pane_r", 30, 62, 86, 116, 1.25)
    c = Clip(k, "wind_flutter", "Wind flutter", "Both panes stand ajar and flutter in gusts, then are pulled shut.",
             ["flutter"])
    c.seq("pane_l", [(4, 0.0), (24, 0.55)])
    damped(c, "pane_l", 24, 0.55, 0.55, [0.28, 0.2, 0.14, 0.24, 0.12, 0.06], 10)
    c.seq("pane_l", [(118, 0.55), (138, 0.0)])
    c.seq("pane_r", [(10, 0.0), (30, 0.6)])
    damped(c, "pane_r", 30, 0.6, 0.6, [0.22, 0.3, 0.16, 0.1, 0.18, 0.08], 9)
    c.seq("pane_r", [(112, 0.6), (134, 0.0)])
    return [a, b, c]


def s03():
    k = "S03_shuttered_window"
    a = Clip(k, "fold_open", "Fold open", "Both shutters fold all the way back against the wall and close again.",
             ["mirrored_pair", "ease_cycle"], loop=(1, 144))
    for ch in ("shutter_l", "shutter_r"):
        cycle(a, ch, 10, 54, 96, 136, 2.95)
    b = Clip(k, "one_at_a_time", "One at a time", "Left shutter opens, then the right; left closes first.",
             ["staggered_pair"])
    cycle(b, "shutter_l", 6, 44, 92, 122, 2.9)
    cycle(b, "shutter_r", 34, 72, 106, 138, 2.9)
    c = Clip(k, "storm", "Storm banging", "Unlatched shutters are blown open and bang shut again and again.",
             ["flutter", "slam_bounce"])
    for ch, f0, peaks in (("shutter_l", 4, (1.1, 1.7, 0.8)), ("shutter_r", 18, (1.4, 0.9, 1.9))):
        f = f0
        for p in peaks:
            c.seq(ch, [(f, 0.0, "QUAD_OUT"), (f + 12, p, "CONSTANT"), (f + 16, p, "BOUNCE_OUT"), (f + 34, 0.0)])
            f += 40
    return [a, b, c]


def s04():
    k = "S04_garden_gate"
    a = Clip(k, "push_through", "Push through and swing back", "Pushed open outward, released: the gate swings back "
             "through closed and oscillates to rest.", ["damped_swing"])
    a.seq("gate", [(6, 0.0), (34, 1.45)])
    damped(a, "gate", 34, 0.0, 1.45, [0.95, 0.6, 0.36, 0.2, 0.1], 14)
    b = Clip(k, "open_latch", "Open and latch", "Opens outward, waits, swings shut and rattles on the latch.",
             ["slam_bounce", "ease_cycle"])
    b.seq("gate", [(10, 0.0), (46, 1.5, "CONSTANT"), (90, 1.5, "BOUNCE_OUT"), (120, 0.0)])
    c = Clip(k, "in_and_out", "Inward then outward", "Opens outward and closes, then opens inward and closes.",
             ["sequence", "ease_cycle"])
    c.seq("gate", [(8, 0.0), (36, 1.4, "CONSTANT"), (50, 1.4), (72, 0.0, "CONSTANT"), (80, 0.0), (108, -1.4, "CONSTANT"),
                   (118, -1.4), (140, 0.0)])
    return [a, b, c]


def s05():
    k = "S05_kitchen_cupboard"
    a = Clip(k, "door_cycle", "Door open and close", "The lower cupboard door opens wide, waits, and closes.",
             ["ease_cycle"], loop=(1, 144))
    cycle(a, "door", 10, 44, 96, 134, 1.8)
    b = Clip(k, "drawer_pull", "Drawers pulled and pushed", "Top drawer pulled out and pushed back so it bumps on "
             "its stop; then the lower drawer.", ["slide_bounce", "staggered_pair"])
    b.seq("drawer_top", [(10, 0.0), (32, 26.0, "CONSTANT"), (60, 26.0, "BOUNCE_OUT"), (80, 0.0)])
    b.seq("drawer_low", [(52, 0.0), (74, 24.0, "CONSTANT"), (104, 24.0, "BOUNCE_OUT"), (124, 0.0)])
    c = Clip(k, "kitchen_sequence", "Fetch something", "Door opens, top drawer slides out and back, door closes.",
             ["sequence"])
    cycle(c, "door", 6, 28, 108, 134, 1.75)
    cycle(c, "drawer_top", 36, 56, 78, 96, 28.0)
    return [a, b, c]


def s06():
    k = "S06_double_cabinet"
    a = Clip(k, "open_both", "Open both doors", "Both doors open together, wait, and close.",
             ["mirrored_pair", "ease_cycle"], loop=(1, 144))
    for ch in ("door_l", "door_r"):
        cycle(a, ch, 10, 48, 96, 134, 1.75)
    b = Clip(k, "left_then_right", "Left then right", "Left door opens, then the right; right closes first.",
             ["staggered_pair"])
    cycle(b, "door_l", 6, 40, 104, 136, 1.7)
    cycle(b, "door_r", 30, 64, 80, 112, 1.7)
    c = Clip(k, "peek", "Peek inside", "The right door opens a crack twice; then the left door opens halfway and "
             "closes.", ["peek", "hesitant"])
    c.seq("door_r", [(6, 0.0), (18, 0.35, "CONSTANT"), (34, 0.35), (44, 0.0, "CONSTANT"), (54, 0.0), (64, 0.5, "CONSTANT"),
                     (80, 0.5), (92, 0.0)])
    cycle(c, "door_l", 96, 112, 124, 140, 0.9)
    return [a, b, c]


def s07():
    k = "S07_treasure_chest"
    a = Clip(k, "slow_reveal", "Slow reveal", "The lid rises slowly and smoothly to fully open, waits, and closes.",
             ["ease_cycle"], loop=(1, 144))
    a.seq("lid", [(10, 0.0, "SINE_OUT"), (70, 1.75, "CONSTANT"), (100, 1.75), (134, 0.0)])
    b = Clip(k, "snap_shut", "Snap shut", "Flipped open, then dropped: the lid bangs shut and bounces.",
             ["slam_bounce"])
    b.seq("lid", [(10, 0.0, "QUAD_OUT"), (28, 1.7, "CONSTANT"), (70, 1.7, "BOUNCE_OUT"), (96, 0.0)])
    c = Clip(k, "peek_twice", "Peek twice", "The lid is lifted a crack twice, the second time a little more.",
             ["peek"])
    c.seq("lid", [(10, 0.0), (24, 0.3, "CONSTANT"), (40, 0.3), (50, 0.0, "CONSTANT"), (70, 0.0), (84, 0.55, "CONSTANT"),
                  (104, 0.55), (116, 0.0)])
    return [a, b, c]


def s08():
    k = "S08_mailbox"
    a = Clip(k, "gravity_drop", "Drop open, lift shut", "Released, the door drops open onto its stop and bounces; "
             "later it is lifted shut.", ["gravity_drop"])
    a.seq("door", [(12, 0.0, "BOUNCE_OUT"), (40, 1.5, "CONSTANT"), (90, 1.5), (122, 0.0)])
    b = Clip(k, "eased_loop", "Open and close", "The door folds down, waits, and folds up again.",
             ["ease_cycle"], loop=(1, 144))
    cycle(b, "door", 10, 50, 90, 130, 1.45)
    c = Clip(k, "flap_rattle", "Flap rattle", "The door flaps a few times as letters are pushed in, then opens to "
             "take them out.", ["flutter", "peek"])
    f = 6
    for p in (0.22, 0.3, 0.18, 0.26):
        c.seq("door", [(f, 0.0, "QUAD_OUT"), (f + 5, p, "QUAD_IN"), (f + 10, 0.0)])
        f += 14
    cycle(c, "door", 80, 100, 116, 136, 1.1)
    return [a, b, c]


def s09():
    k = "S09_trap_door"
    a = Clip(k, "drop_and_winch", "Drop and winch up", "The trap falls open, swings like a pendulum about hanging "
             "straight down, then is winched closed at constant speed.", ["gravity_drop", "damped_swing",
                                                                       "winch_linear"])
    a.seq("trap", [(10, 0.0, "QUAD_IN"), (24, 1.85)])
    damped(a, "trap", 24, PI / 2, 1.85, [0.22, 0.13, 0.07, 0.03], 9)
    a.seq("trap", [(86, PI / 2, "LINEAR"), (134, 0.0)])
    b = Clip(k, "quick_trap", "Snap open", "Snaps open to hanging, waits, and closes with an ease.",
             ["toggle", "ease_cycle"])
    b.seq("trap", [(10, 0.0, "QUAD_OUT"), (18, PI / 2, "CONSTANT"), (70, PI / 2), (110, 0.0)])
    c = Clip(k, "test_wiggle", "Test wiggle", "The trap is tested with small quick openings, then dropped open "
             "briefly.", ["shake", "peek"])
    f = 8
    for p in (0.18, 0.25, 0.15):
        c.seq("trap", [(f, 0.0, "QUAD_OUT"), (f + 6, p, "QUAD_IN"), (f + 12, 0.0)])
        f += 18
    cycle(c, "trap", 76, 92, 112, 136, 1.2, "QUAD_IN_OUT")
    return [a, b, c]


def s10():
    k = "S10_car_doors"
    a = Clip(k, "driver_door", "Driver's door", "The left door opens, waits, and closes.", ["ease_cycle"],
             loop=(1, 144))
    cycle(a, "door_l", 10, 44, 96, 134, 1.2)
    b = Clip(k, "both_doors", "Both doors", "Both doors open together and close.", ["mirrored_pair"],
             loop=(1, 144))
    for ch in ("door_l", "door_r"):
        cycle(b, ch, 10, 44, 96, 134, 1.2)
    c = Clip(k, "slam", "Slam both", "Doors open one after the other, then both slam shut with a bounce.",
             ["staggered_pair", "slam_bounce"])
    c.seq("door_l", [(6, 0.0), (32, 1.15, "CONSTANT"), (80, 1.15, "BOUNCE_OUT"), (104, 0.0)])
    c.seq("door_r", [(22, 0.0), (48, 1.15, "CONSTANT"), (92, 1.15, "BOUNCE_OUT"), (116, 0.0)])
    return [a, b, c]


def s11():
    k = "S11_car_roof"
    a = Clip(k, "lift_close", "Lift and close", "The roof hatch lifts at the front, waits, and closes.",
             ["ease_cycle"], loop=(1, 144))
    cycle(a, "roof", 10, 48, 96, 134, 1.2)
    b = Clip(k, "gas_strut", "Gas strut", "Pops up past its open position and settles back, like a gas strut; "
             "closes slowly.", ["overshoot_settle"])
    b.seq("roof", [(10, 0.0, "BACK_OUT"), (40, 1.12, "CONSTANT"), (92, 1.12), (136, 0.0)])
    c = Clip(k, "slam", "Slam", "Lifted, then dropped shut with a bounce.", ["slam_bounce"])
    c.seq("roof", [(10, 0.0), (40, 1.2, "CONSTANT"), (76, 1.2, "BOUNCE_OUT"), (102, 0.0)])
    return [a, b, c]


def s12():
    k = "S12_canopy"
    a = Clip(k, "flip_open", "Flip open", "The canopy flips up past its open angle and settles, then closes.",
             ["overshoot_settle"])
    a.seq("canopy", [(12, 0.0, "BACK_OUT"), (46, 1.35, "CONSTANT"), (96, 1.35), (134, 0.0)])
    b = Clip(k, "slow_seal", "Slow seal", "Opens and closes slowly with cubic easing (a motorised seal).",
             ["ease_cycle"], loop=(1, 144))
    b.seq("canopy", [(4, 0.0, "CUBIC_IN_OUT"), (64, 1.4, "CONSTANT"), (80, 1.4, "CUBIC_IN_OUT"), (140, 0.0)])
    c = Clip(k, "pop_open", "Emergency pop", "Pops open fast, waits, and lowers at a constant speed.",
             ["toggle", "winch_linear"])
    c.seq("canopy", [(10, 0.0, "QUAD_OUT"), (18, 1.5, "CONSTANT"), (70, 1.5, "LINEAR"), (130, 0.0)])
    return [a, b, c]


def s13():
    k = "S13_forklift"
    a = Clip(k, "raise_lower", "Raise and lower", "Forks rise to the top, wait, and come down (the spring "
             "compresses and extends with them).", ["ease_cycle"], loop=(1, 144))
    cycle(a, "lift", 12, 56, 92, 136, 95.0)
    b = Clip(k, "chain_hoist", "Stepped hoist", "Forks rise in five equal steps with pauses, then come down "
             "smoothly.", ["stepped"])
    f = steps(b, "lift", 6, [20.0, 40.0, 60.0, 80.0, 100.0], 8, 10)
    b.seq("lift", [(f + 10, 100.0), (f + 46, 0.0)])
    c = Clip(k, "drop", "Drop", "Forks are raised high, then released: they drop and bounce on the bottom stop.",
             ["gravity_drop", "slide_bounce"])
    c.seq("lift", [(10, 0.0), (50, 90.0, "CONSTANT"), (80, 90.0, "BOUNCE_OUT"), (104, 0.0)])
    return [a, b, c]


def s14():
    k = "S14_sliding_door"
    a = Clip(k, "slide_cycle", "Slide open and closed", "The door slides fully open along its rails, waits, and "
             "closes.", ["ease_cycle"], loop=(1, 144))
    cycle(a, "slide", 10, 54, 94, 136, 145.0)
    b = Clip(k, "shove", "Shove", "Shoved open, it runs into the end stop and bounces; shoved shut the same way.",
             ["slide_bounce"])
    b.seq("slide", [(10, 0.0, "BOUNCE_OUT"), (40, 145.0, "CONSTANT"), (80, 145.0, "BOUNCE_OUT"), (110, 0.0)])
    c = Clip(k, "crack_open", "Crack open", "Slides open a little, waits, opens a bit more, then closes.",
             ["peek", "hesitant"])
    c.seq("slide", [(10, 0.0), (34, 35.0, "CONSTANT"), (60, 35.0), (76, 60.0, "CONSTANT"), (104, 60.0), (134, 0.0)])
    return [a, b, c]


def s15():
    k = "S15_radar"
    a = Clip(k, "constant_spin", "Constant spin", "Two full turns at constant speed (loops seamlessly).",
             ["continuous_spin", "winch_linear"], loop=(1, 144))
    a.seq("spin", [(1, 0.0, "LINEAR"), (144, 2 * TAU)])
    b = Clip(k, "spin_up_down", "Spin up and down", "Speeds up, cruises and slows down to stop after three turns.",
             ["spin_up_down"])
    d1, d2 = 35.0, 72.0
    v = 3 * TAU / (d1 / 2 + d2 + d1 / 2)
    b.seq("spin", [(1, 0.0, "QUAD_IN"), (1 + d1, v * d1 / 2, "LINEAR"), (1 + d1 + d2, v * (d1 / 2 + d2), "QUAD_OUT"),
                   (144, 3 * TAU)])
    c = Clip(k, "sweep_scan", "Sweep scan", "Scans back and forth over 120 deg, three times.", ["sweep"])
    wave(c, "spin", 6, 44, 6, 1.05)
    return [a, b, c]


def s16():
    k = "S16_crane"
    a = Clip(k, "slew_sweep", "Slew sweep", "With the boom slightly raised, the crane turns a quarter left, a "
             "quarter right and back.", ["sweep"])
    a.seq("luff", [(1, 0.0), (16, 0.4, "CONSTANT"), (128, 0.4), (144, 0.0)])
    a.seq("slew", [(16, 0.0), (48, PI / 2, "CONSTANT"), (58, PI / 2), (100, -PI / 2, "CONSTANT"), (108, -PI / 2),
                   (128, 0.0)])
    b = Clip(k, "luff_cycle", "Luff up and down", "The boom rises and lowers; the hook stays plumb.",
             ["ease_cycle"], loop=(1, 144))
    cycle(b, "luff", 10, 56, 92, 136, 1.0)
    c = Clip(k, "pick_and_place", "Pick and place", "Boom up, slew a quarter turn, down to place the load, up, "
             "slew back and park.", ["sequence"])
    c.seq("luff", [(4, 0.0), (20, 0.85, "CONSTANT"), (54, 0.85), (66, 0.35, "CONSTANT"), (78, 0.35), (90, 0.85, "CONSTANT"),
                   (120, 0.85), (140, 0.0)])
    c.seq("slew", [(24, 0.0), (50, PI / 2, "CONSTANT"), (94, PI / 2), (118, 0.0)])
    return [a, b, c]


def s17():
    k = "S17_tipper"
    a = Clip(k, "tip_return", "Tip and return", "The bucket tips up, waits for the load to slide out, and comes "
             "down.", ["ease_cycle"], loop=(1, 144))
    cycle(a, "tip", 12, 60, 96, 136, 0.95)
    b = Clip(k, "hydraulic_steps", "Hydraulic steps", "Tips in four stages with pauses, then lowers smoothly.",
             ["stepped"])
    f = steps(b, "tip", 6, [0.25, 0.5, 0.75, 0.95], 10, 10)
    b.seq("tip", [(f + 8, 0.95), (f + 44, 0.0)])
    c = Clip(k, "shake_to_empty", "Shake to empty", "Tips up, shakes quickly to free the load, and lowers.",
             ["shake"])
    c.seq("tip", [(8, 0.0), (40, 0.85)])
    wave(c, "tip", 40, 8, 10, 0.06, centre=0.85)
    c.seq("tip", [(90, 0.85), (130, 0.0)])
    return [a, b, c]


def s18():
    k = "S18_barrier"
    a = Clip(k, "raise_lower", "Raise and lower", "The boom rises to vertical, waits, and lowers.", ["ease_cycle"],
             loop=(1, 144))
    cycle(a, "boom", 10, 40, 100, 136, 1.45)
    b = Clip(k, "bounce_down", "Drop onto the rest", "Snaps up, waits, then drops onto its rest and bounces.",
             ["toggle", "slam_bounce"])
    b.seq("boom", [(8, 0.0, "QUAD_OUT"), (24, 1.45, "CONSTANT"), (90, 1.45, "BOUNCE_OUT"), (118, 0.0)])
    c = Clip(k, "quick_up_slow_down", "Quick up, slow down", "Rises fast and comes down slowly at constant speed.",
             ["winch_linear"])
    c.seq("boom", [(10, 0.0, "QUAD_OUT"), (22, 1.4, "CONSTANT"), (60, 1.4, "LINEAR"), (136, 0.0)])
    return [a, b, c]


def s19():
    k = "S19_drawbridge"
    a = Clip(k, "winch_and_drop", "Winch up, drop down", "The bridge is winched up at constant speed, held, then "
             "let go: it falls onto the far bank and bounces.", ["winch_linear", "gravity_drop", "slam_bounce"])
    a.seq("bridge", [(10, 0.0, "LINEAR"), (70, 1.5, "CONSTANT"), (100, 1.5, "BOUNCE_OUT"), (128, 0.0)])
    b = Clip(k, "eased_cycle", "Raise and lower", "The bridge rises and lowers smoothly.", ["ease_cycle"],
             loop=(1, 144))
    cycle(b, "bridge", 10, 56, 92, 136, 1.5)
    c = Clip(k, "half_raise", "Half raise", "Raised halfway twice, as if checking the chains.", ["peek", "stepped"])
    c.seq("bridge", [(8, 0.0), (36, 0.7, "CONSTANT"), (56, 0.7), (76, 0.0, "CONSTANT"), (86, 0.0), (108, 0.45, "CONSTANT"),
                     (120, 0.45), (138, 0.0)])
    return [a, b, c]


def s20():
    k = "S20_levers"
    a = Clip(k, "toggle_snap", "Toggle", "Each stick is snapped forward or back, held, and snapped home with a "
             "small bounce.", ["toggle", "slam_bounce"])
    a.seq("lever_l", [(8, 0.0, "QUAD_OUT"), (12, 0.6, "CONSTANT"), (50, 0.6, "BOUNCE_OUT"), (64, 0.0)])
    a.seq("lever_r", [(30, 0.0, "QUAD_OUT"), (34, -0.6, "CONSTANT"), (80, -0.6, "QUAD_OUT"), (84, 0.6, "CONSTANT"),
                      (110, 0.6, "BOUNCE_OUT"), (124, 0.0)])
    b = Clip(k, "throttle", "Throttle", "Both sticks are pushed slowly forward at constant speed, held, and "
             "eased back.", ["winch_linear", "mirrored_pair"])
    for ch in ("lever_l", "lever_r"):
        b.seq(ch, [(10, 0.0, "LINEAR"), (70, 0.65, "CONSTANT"), (96, 0.65), (134, 0.0)])
    c = Clip(k, "jiggle", "Jiggle", "Both sticks are jiggled quickly, out of step.", ["shake"])
    wave(c, "lever_l", 10, 12, 16, [0.12, 0.18, 0.15, 0.2, 0.12, 0.16, 0.1, 0.14, 0.12, 0.18, 0.1, 0.14, 0.08, 0.1,
                                    0.06, 0.04])
    wave(c, "lever_r", 16, 14, 14, [0.18, 0.1, 0.2, 0.12, 0.16, 0.1, 0.14, 0.08, 0.16, 0.1, 0.12, 0.06, 0.08, 0.04],
         sign=-1.0)
    return [a, b, c]


SCENARIO_CLIPS = (s01, s02, s03, s04, s05, s06, s07, s08, s09, s10, s11, s12, s13, s14, s15, s16, s17, s18, s19,
                  s20)


def library():
    """All clips in scenario order, three per scenario (windows A, B, C)."""
    clips = []
    for make in SCENARIO_CLIPS:
        made = make()
        if len(made) != 3:
            raise ValueError(f"{make.__name__}: expected 3 clips")
        clips += made
    return clips


def window_of(clip, clips=None):
    clips = clips or library()
    mine = [c for c in clips if c.scenario == clip.scenario]
    return "ABC"[[c.name for c in mine].index(clip.name)]


# --------------------------------------------------------------------------- checks and export
def check(clip, tolerance=1e-9):
    """Clip rules: rest at start and end (whole turns allowed on periodic channels), ranges, step size."""
    problems = []
    controls = BY_KEY[clip.scenario]["controls"]
    for ch in clip.channels:
        spec = controls[ch]
        keys = clip.keys(ch)
        if abs(keys[0][1]) > tolerance:
            problems.append(f"{ch} starts at {keys[0][1]}")
        end = keys[-1][1]
        if spec["periodic"]:
            turns = end / TAU
            if abs(turns - round(turns)) > tolerance:
                problems.append(f"{ch} ends at {end}, not a whole turn")
        elif abs(end) > tolerance:
            problems.append(f"{ch} ends at {end}")
        samples = [clip.value(ch, f / 4) for f in range(4, 4 * clip.frames + 1)]
        if min(samples) < spec["min"] - tolerance or max(samples) > spec["max"] + tolerance:
            problems.append(f"{ch} leaves [{spec['min']}, {spec['max']}]: {min(samples):.4f}..{max(samples):.4f}")
        jump = max((abs(b - a) for a, b in zip(samples, samples[1:])), default=0.0)
        limit = 12.0 if spec["unit"] == "ldu" else 0.35
        if jump > limit:
            problems.append(f"{ch} jumps {jump:.3f} within a quarter frame")
    if clip.loop:
        a, b = clip.loop
        if not 1 <= a < b <= clip.frames:
            problems.append(f"loop range {clip.loop} outside the clip")
    return problems


def baked(clip):
    return {ch: [round(clip.value(ch, f), 6) for f in range(1, clip.frames + 1)] for ch in clip.channels}


def blender_names(clip, clips=None):
    w = window_of(clip, clips)
    sc = BY_KEY[clip.scenario]
    return dict(action=clip.id, action_slot="OBmovable_controller", nla_track=f"{w} {clip.name}",
                controller=f"CTRL_{sc['plan']}", collection=f"{sc['key']} {sc['title']}",
                scene=f"{sc['key'][:3]} {sc['title']}", strip_start=WINDOWS[w][0])


def clip_document(clip, clips=None):
    clips = clips or library()
    w = window_of(clip, clips)
    controls = BY_KEY[clip.scenario]["controls"]
    return dict(
        id=clip.id,
        scenario=clip.scenario,
        clip=clip.name,
        title=clip.title,
        description=clip.description,
        styles=clip.styles,
        window=w,
        timeline_start=WINDOWS[w][0],
        frames=clip.frames,
        fps=FPS,
        duration_seconds=round(clip.frames / FPS, 3),
        loop_range=clip.loop,
        blender=blender_names(clip, clips),
        channels={ch: dict(unit=controls[ch]["unit"], min=controls[ch]["min"], max=controls[ch]["max"],
                           meaning=controls[ch]["description"],
                           keys=[dict(frame=f, value=round(v, 9), interpolation=INTERPOLATIONS[i][0],
                                      easing=INTERPOLATIONS[i][1]) for f, v, i in clip.keys(ch)])
                  for ch in clip.channels},
        baked=baked(clip),
        notes="Clip-local frames start at 1. Each key's interpolation/easing applies to the segment that starts at "
              "it (Blender semantics; BACK uses back = 1.70158). 'baked' holds the evaluated value at every integer "
              "frame. Channels are the scenario's plan controls: radians for hinges and turntables, LDU for slides "
              "(1 LDU = 0.4 mm = 0.0004 Blender units in the converted model).",
    )


def conventions():
    return dict(
        scenario_frame="LDraw LDU per scenario: -Y up, the scenario front faces -Z (towards the catalog camera), "
                       "ground (top of the base) at y = 0. Each control's default 0 is the built pose.",
        rules="Every clip starts at rest (all controls 0) and ends at rest; periodic channels may end on whole "
              "turns (an identical pose). Values stay inside the control ranges.",
        windows=WINDOWS,
        fps=FPS,
        frames=FRAMES,
        styles=STYLES,
        interpolations={k: dict(interpolation=v[0], easing=v[1]) for k, v in INTERPOLATIONS.items()},
        back_factor=BACK,
    )


def export(directory=OUT):
    directory = Path(directory)
    clips = library()
    (directory / "clips").mkdir(parents=True, exist_ok=True)
    docs = []
    for clip in clips:
        problems = check(clip)
        if problems:
            raise ValueError(f"{clip.id}: {problems}")
        doc = clip_document(clip, clips)
        (directory / "clips" / f"{clip.id}.json").write_text(json.dumps(doc, indent=1) + "\n")
        docs.append(doc)
    return docs
