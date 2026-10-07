"""Minifig movement catalog: shared joint layout, whole-figure channels and 30 clips (pure Python, Blender-safe).

Imported by scripts/build_minifigs.py (plans and catalog export), scripts/blender/animate_minifigs.py (actions
and NLA tracks), scripts/blender/check_minifigs_reopen.py and the tests. This module is the single source of
the clip keyframes; the exported JSON and the Blender actions are generated from it.

Every figure uses the same 13 channels on its controller:
- seven plan controls (radians), the minifig's real joints: neck, shoulder_l/r, wrist_l/r, hip_l/r;
- six whole-figure staging channels (LDU/radians) that move the complete figure about its hip-axis centre.

Keys are sparse. Each key's interpolation applies to the segment that starts at it and uses Blender's own
easing formulas (Penner equations, as in BLI_easing). `value_at` therefore reproduces what Blender evaluates.
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
OUT = ROOT / "output/minifigs"

# Figure frame (LDraw, LDU): torso origin at the neck, -Y up, the face looks along -Z, the figure's left is +X.
PIVOT = (0.0, 44.0, 0.0)  # centre of the hip pin axis (hips 3815b at y=32, leg pins at +12)
HIP_HEIGHT = 28.0  # hip axis above the ground (legs 3816c/3817c reach y=+28 below their pin)
SEATED_HEIGHT = 8.75  # hip axis above the ground with the legs forward (back of the legs, hips bottom)
# Floor sit: torso leaned back SIT_LEAN with the legs flat (hip = pi/2 - lean); with the legs at a full pi/2 the
# resting hands sink into the thighs. Leaning back lowers the hips' rear corner (y 8.75, z 10), which sets the height.
SIT_LEAN = 0.27
SIT_HIP = PI / 2 - SIT_LEAN
SIT_HEIGHT = SEATED_HEIGHT * math.cos(SIT_LEAN) + 10.0 * math.sin(SIT_LEAN)
# Left arm pose that holds a frying pan (4528, spin 285 in build_minifigs.ITEMS) level across the belly.
PAN_LEVEL = (0.45, -1.31)
# Pirate cutlass thrust: shoulder and wrist that keep the curved blade clear of the head and bicorne.
LUNGE_THRUST, LUNGE_WRIST = 1.45, 0.6
LDU = 0.0004  # metres per LDU in the converted GLB

JOINTS = {
    "neck": dict(min=-PI, max=PI, description="Head yaw about the neck stud; + turns the face to the figure's left"),
    "shoulder_l": dict(min=-4 * PI, max=4 * PI,
                       description="Left arm about its shoulder pin; + swings the arm forward and up (free spin)"),
    "shoulder_r": dict(min=-4 * PI, max=4 * PI,
                       description="Right arm about its shoulder pin; + swings the arm forward and up (free spin)"),
    "wrist_l": dict(min=-PI, max=PI,
                    description="Left hand about the arm socket axis; + rolls the held item's tip outward (+X)"),
    "wrist_r": dict(min=-PI, max=PI,
                    description="Right hand about the arm socket axis; + rolls the held item's tip outward (-X)"),
    "hip_l": dict(min=-PI / 2, max=PI / 2,
                  description="Left leg about the hip pin; + swings the leg forward (+pi/2 = seated)"),
    "hip_r": dict(min=-PI / 2, max=PI / 2,
                  description="Right leg about the hip pin; + swings the leg forward (+pi/2 = seated)"),
}
FIGURE = {
    "move_forward": dict(unit="ldu", min=-400.0, max=400.0,
                         description="Offset of the hip-axis centre along the home facing direction"),
    "move_left": dict(unit="ldu", min=-400.0, max=400.0,
                      description="Offset of the hip-axis centre toward the figure's home left"),
    "move_up": dict(unit="ldu", min=-200.0, max=400.0, description="Height offset of the hip-axis centre"),
    "turn": dict(unit="radian", min=-4 * PI, max=4 * PI,
                 description="Yaw about the vertical through the hip-axis centre; + turns left (counter-clockwise "
                             "seen from above)"),
    "pitch": dict(unit="radian", min=-4 * PI, max=4 * PI,
                  description="Rotation about the hip axis (figure's left-right line); + leans forward"),
    "roll": dict(unit="radian", min=-4 * PI, max=4 * PI,
                 description="Rotation about the figure's front-back line through the hip-axis centre; + leans "
                             "toward the figure's left"),
}
CHANNELS = list(JOINTS) + list(FIGURE)
# Blender MOVE_ empty drivers (figure faces -Y): (property path, index, simple expression of v, channel).
# rotation_mode 'YXZ' applies roll (Y), then pitch (X), then turn (Z, outermost).
MOVE_DRIVERS = (
    ("location", 0, f"v*{LDU}", "move_left"),
    ("location", 1, f"-v*{LDU}", "move_forward"),
    ("location", 2, f"v*{LDU}", "move_up"),
    ("rotation_euler", 0, "v", "pitch"),
    ("rotation_euler", 1, "v", "roll"),
    ("rotation_euler", 2, "v", "turn"),
)
# Channels allowed to finish on a whole number of turns (identical pose); all others must finish at 0.
PERIODIC = {"shoulder_l", "shoulder_r", "turn", "pitch", "roll"}

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
}


def ease(kind, t, b, c, d):
    """Blender's easing equations: time t of duration d, start b, change c."""
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
    """Sparse keyframes per channel; frames are clip-local, starting at 1."""

    def __init__(self, figure, name, title, description, frames, loop=None, tags=()):
        if not 1 < frames <= MAX_CLIP_FRAMES:
            raise ValueError(f"{figure}.{name}: clip length must be 2..{MAX_CLIP_FRAMES} frames")
        self.figure, self.name, self.title, self.description = figure, name, title, description
        self.frames, self.loop, self.tags = frames, loop, list(tags)
        self._keys = {c: {} for c in CHANNELS}

    @property
    def id(self):
        return f"{self.figure}.{self.name}"

    def key(self, channel, frame, value, interp="SINE_IN_OUT"):
        if channel not in self._keys:
            raise ValueError(f"Unknown channel {channel}")
        if interp not in INTERPOLATIONS:
            raise ValueError(f"Unknown interpolation {interp}")
        if not 1 <= frame <= self.frames:
            raise ValueError(f"{self.id}: key at frame {frame} outside 1..{self.frames}")
        self._keys[channel][round(float(frame), 4)] = (float(value), interp)
        return self

    def seq(self, channel, points, interp="SINE_IN_OUT"):
        """Add (frame, value[, interpolation]) points."""
        for p in points:
            self.key(channel, p[0], p[1], p[2] if len(p) > 2 else interp)
        return self

    def current(self, channel, frame):
        keys = self.keys(channel)
        return value_at(keys, frame)

    def keys(self, channel):
        """Sorted keys of a channel, always bracketing the clip with keys at 1 and at the last frame."""
        k = dict(self._keys[channel])
        if 1 not in k:
            k[1] = (0.0, "SINE_IN_OUT")
        last = float(self.frames)
        if last not in k:
            prev = max(k)
            k[last] = (k[prev][0], "SINE_IN_OUT")
        return [(f, v, i) for f, (v, i) in sorted(k.items())]

    def value(self, channel, frame):
        return value_at(self.keys(channel), frame)

    def values(self, frame):
        return {c: self.value(c, frame) for c in CHANNELS}

    def last_value(self, channel):
        k = self._keys[channel]
        return k[max(k)][0] if k else 0.0


# --------------------------------------------------------------------------- helpers
def wave(c, channel, f0, period, half_cycles, amps, center=0.0, sign=1.0, start=None, end=None):
    """Sine wave starting and ending on zero crossings (exact with SINE easing).

    Extremes alternate sign*amp, -sign*amp, ... at quarter periods; `amps` is a scalar or one amplitude per
    extreme (an envelope). `start`/`end` override the value at the first/last zero crossing (default: center).
    """
    q = period / 4
    amps = [amps] * half_cycles if isinstance(amps, (int, float)) else list(amps)
    if len(amps) != half_cycles:
        raise ValueError("One amplitude per half cycle")
    c.key(channel, f0, center if start is None else start, "SINE_OUT")
    for k in range(half_cycles):
        s = sign if k % 2 == 0 else -sign
        c.key(channel, f0 + q + 2 * q * k, center + s * amps[k],
              "SINE_IN_OUT" if k < half_cycles - 1 else "SINE_IN")
    f1 = f0 + 2 * q * half_cycles
    c.key(channel, f1, center if end is None else end)
    return f1


def heading_offsets(heading, distance):
    """Home-frame (forward, left) offsets of a move along `heading` (0 = home facing, + = turned left)."""
    return distance * math.cos(heading), distance * math.sin(heading)


def gait(c, f0, steps, period, hip, arm, *, heading=0.0, start=(0.0, 0.0), distance=None, arms="swing",
         lead="l", lean=0.0, flight=0.0, arm_bias=0.0):
    """Walk/run cycle: `steps` half cycles of `period` frames starting at f0 on a zero crossing.

    Legs swing +/-hip (lead leg forward first), arms counter-swing +/-arm about arm_bias (`arms`: swing, carry,
    none). The body dips as the straight legs split (hip axis height 28*cos), plus optional `flight` lift at the
    crossings. The hip-axis centre travels `distance` (default: the geometric step length per step) along
    `heading` with velocity-continuous ease in/out. Returns (end frame, end (forward, left)).
    """
    half = period / 2
    f1 = f0 + steps * half
    sl, sr = (1.0, -1.0) if lead == "l" else (-1.0, 1.0)
    wave(c, "hip_l", f0, period, steps, hip, sign=sl)
    wave(c, "hip_r", f0, period, steps, hip, sign=sr)
    if arms == "swing":
        wave(c, "shoulder_l", f0, period, steps, arm, center=arm_bias, sign=-sl)
        wave(c, "shoulder_r", f0, period, steps, arm, center=arm_bias, sign=-sr)
    # Height: dip at the leg extremes, back up (or lifted) at the crossings.
    drop = -HIP_HEIGHT * (1 - math.cos(hip))
    for k in range(steps):
        c.key("move_up", f0 + half * k, flight if k else 0.0)
        c.key("move_up", f0 + half * k + half / 2, drop)
    c.key("move_up", f1, 0.0)
    if lean:
        c.key("pitch", f0, c.current("pitch", f0))
        c.key("pitch", f0 + half, lean)
        c.key("pitch", f1 - half, lean)
        c.key("pitch", f1, 0.0)
    step = 2 * HIP_HEIGHT * math.sin(hip)
    if distance is None:
        distance = step * steps
    # Constant speed v in the middle steps, SINE_IN/SINE_OUT for the first/last step at matching end speed:
    # an eased step of duration d covers 2*v*d/pi.
    ease_len = 2 * half / PI
    v = distance / ((steps - 2) * half + 2 * ease_len * 1.0) if steps > 2 else distance / (2 * ease_len)
    d_ease = v * ease_len
    points = [(f0, 0.0, "SINE_IN"), (f0 + half, d_ease, "LINEAR"), (f1 - half, distance - d_ease, "SINE_OUT"),
              (f1, distance)] if steps > 2 else [(f0, 0.0, "SINE_IN_OUT"), (f1, distance)]
    fwd0, left0 = start
    for p in points:
        df, dl = heading_offsets(heading, p[1])
        interp = p[2] if len(p) > 2 else "SINE_IN_OUT"
        c.key("move_forward", p[0], fwd0 + df, interp)
        c.key("move_left", p[0], left0 + dl, interp)
    end = heading_offsets(heading, distance)
    return f1, (fwd0 + end[0], left0 + end[1])


def turn_steps(c, f0, f1, h0, h1, hip=0.18, steps=2):
    """Turn in place from heading h0 to h1 with small shuffling steps."""
    c.key("turn", f0, h0, "SINE_IN_OUT")
    c.key("turn", f1, h1)
    period = 2 * (f1 - f0) / steps
    wave(c, "hip_l", f0, period, steps, hip, sign=1.0)
    wave(c, "hip_r", f0, period, steps, hip, sign=-1.0)


def hold(c, channel, f0, f1, value=None):
    v = c.current(channel, f0) if value is None else value
    c.key(channel, f0, v)
    c.key(channel, f1, v)


def hop(c, f0, air, height, interp_up="QUAD_OUT", interp_down="QUAD_IN"):
    """Ballistic hop of the hip-axis centre (exact parabola with QUAD easing)."""
    c.key("move_up", f0, 0.0, interp_up)
    c.key("move_up", f0 + air / 2, height, interp_down)
    c.key("move_up", f0 + air, 0.0)


def bend(c, channel_frames):
    """Bend at the hips (pitch with both legs counter-rotated so the feet stay planted): [(frame, angle)]."""
    for f, a in channel_frames:
        c.key("pitch", f, a)
        c.key("hip_l", f, a)
        c.key("hip_r", f, a)


# --------------------------------------------------------------------------- clips
# Arm poses were chosen with scripts/blender/check_minifigs_clearance.py: with the 9.79 deg shoulder tilt a raised
# hand passes the face between about 2.1 and 2.9 rad, so held poses stay at or below ~2.0 rad (hands before the
# face) or near pi (straight up); long items and wide headgear lower those limits further.
def police():
    out = []
    c = Clip("MF01_police", "walk_patrol", "Walk patrol",
             "Walks four steps out, turns round, walks back, turns to face front again. Legs alternate, arms "
             "counter-swing, the hips dip as the straight legs split.", 144)
    f, pos = gait(c, 8, 4, 24, 0.45, 0.4)
    turn_steps(c, 58, 78, 0.0, PI)
    f, pos = gait(c, 80, 4, 24, 0.45, 0.4, heading=PI, start=pos)
    turn_steps(c, 128, 144, PI, TAU)
    c.seq("neck", [(8, 0), (30, 0.35), (48, 0), (92, -0.35), (112, 0)])
    c.loop = [20, 44]
    out.append(c)

    c = Clip("MF01_police", "look_around", "Look around",
             "Head scans left and right, then the whole body turns left to look along the street with the head "
             "sweeping, and turns back.", 144)
    c.seq("neck", [(1, 0), (20, 1.2), (34, 1.2), (56, -1.2), (70, -1.2), (82, 0), (90, -0.5), (104, 0),
                   (114, 0.6), (124, -0.6), (134, 0), (144, 0)])
    turn_steps(c, 82, 104, 0.0, PI / 2, hip=0.15)
    hold(c, "turn", 104, 124, PI / 2)
    turn_steps(c, 124, 144, PI / 2, 0.0, hip=0.15)
    c.seq("shoulder_r", [(1, 0), (16, 0.25), (130, 0.25), (144, 0)])
    out.append(c)

    c = Clip("MF01_police", "halt_signal", "Halt signal",
             "Right arm straight forward to halt traffic, then beckons; the left hand lifts the radio to the chin.",
             144)
    c.seq("shoulder_r", [(1, 0), (16, 1.57), (50, 1.57)])
    c.seq("wrist_r", [(1, 0), (16, 0.6), (50, 0.6), (56, 0)])
    c.seq("move_forward", [(1, 0), (14, 4), (30, 0)])
    wave(c, "shoulder_r", 54, 16, 6, 0.1, center=1.1, start=1.57)
    c.seq("shoulder_r", [(102, 1.1), (118, 0)])
    c.seq("shoulder_l", [(1, 0), (60, 0), (76, 1.6), (120, 1.6), (140, 0)])
    c.seq("wrist_l", [(1, 0), (60, 0), (76, -1.0), (120, -1.0), (140, 0)])
    c.seq("neck", [(1, 0), (54, 0), (62, -0.3), (78, 0.45), (118, 0.45), (134, 0)])
    out.append(c)
    return out


def spaceman():
    out = []
    c = Clip("MF02_spaceman", "moon_hop", "Moon hop",
             "Four slow low-gravity bounds (two forward, two back to the start): arms swing back, then up in front "
             "through the jump, legs split in the air; exact parabolic flight.", 144)
    travel = [22, 22, -22, -22]
    fwd = 0.0
    for k, t0 in enumerate((10, 40, 70, 100)):
        for side in ("shoulder_l", "shoulder_r"):
            c.key(side, t0 - 6, -0.5)
            c.key(side, t0 + 12, 2.0)
            c.key(side, t0 + 24, 0.3)
        hop(c, t0, 24, 36)
        s = 1 if k % 2 == 0 else -1
        c.seq("hip_l", [(t0, 0), (t0 + 12, 0.35 * s), (t0 + 24, 0)])
        c.seq("hip_r", [(t0, 0), (t0 + 12, -0.35 * s), (t0 + 24, 0)])
        c.key("move_forward", t0, fwd, "LINEAR")
        fwd += travel[k]
        c.key("move_forward", t0 + 24, fwd)
        c.seq("pitch", [(t0 + 22, 0), (t0 + 26, 0.08), (t0 + 30, 0)])
    for side in ("shoulder_l", "shoulder_r"):
        c.seq(side, [(124, 0.3), (140, 0)])
    c.loop = [40, 70]
    out.append(c)

    c = Clip("MF02_spaceman", "zero_g_tumble", "Zero-g tumble",
             "Floats up, turns one slow forward somersault with limbs drifting, and drifts back down to land.",
             144)
    c.seq("move_up", [(1, 0), (30, 70), (108, 70), (140, 0)])
    c.seq("pitch", [(1, 0), (24, 0), (108, TAU), (144, TAU)])
    c.seq("roll", [(1, 0), (40, 0.25), (72, -0.25), (104, 0), (144, 0)])
    c.seq("shoulder_l", [(1, 0), (30, 1.0), (60, 1.9), (90, 1.0), (120, 0.4), (140, 0)])
    c.seq("shoulder_r", [(1, 0), (30, 0.6), (60, -0.4), (90, 0.8), (120, 0.4), (140, 0)])
    c.seq("hip_l", [(1, 0), (30, 0.3), (70, -0.2), (110, 0.15), (136, 0)])
    c.seq("hip_r", [(1, 0), (30, -0.2), (70, 0.3), (110, -0.1), (136, 0)])
    c.seq("neck", [(1, 0), (40, 0.4), (80, -0.4), (120, 0)])
    out.append(c)

    c = Clip("MF02_spaceman", "wave", "Wave",
             "Waves with the right arm raised just past vertical (wrist waggles), leaning away and glancing to the right; "
             "then a smaller wave with the left hand in front of the chest.", 144)
    c.seq("shoulder_r", [(1, 0), (18, 3.3)])
    wave(c, "shoulder_r", 18, 24, 6, 0.08, center=3.3)
    c.seq("shoulder_r", [(90, 3.3), (106, 0)])
    wave(c, "wrist_r", 18, 12, 12, 0.7)
    c.seq("roll", [(1, 0), (18, 0.06), (90, 0.06), (106, 0), (112, -0.05), (136, -0.05), (144, 0)])
    c.seq("neck", [(1, 0), (18, -0.35), (90, -0.35), (108, 0.3), (136, 0.3), (144, 0)])
    c.seq("shoulder_l", [(100, 0), (112, 1.8), (132, 1.8), (144, 0)])
    wave(c, "wrist_l", 112, 10, 4, 0.5)
    c.loop = [18, 42]
    out.append(c)
    return out


def knight():
    out = []
    c = Clip("MF03_knight", "sword_slash", "Sword slash",
             "Three diagonal slashes: blade raised in front, then the wrist rolls it outward and down while the "
             "body turns and lunges into the cut; the shield stays on guard.", 144)
    c.seq("shoulder_l", [(1, 0), (8, 0.9), (130, 0.9), (144, 0)])
    for k, t in enumerate((10, 50, 90)):
        c.key("shoulder_r", t, 0.0 if k == 0 else 1.2)
        c.key("shoulder_r", t + 12, 1.4, "QUAD_IN")
        c.key("shoulder_r", t + 18, 1.0)
        c.key("shoulder_r", t + 34, 1.2)
        c.seq("wrist_r", [(t, 0 if k == 0 else 0.4), (t + 12, 0, "QUAD_IN"), (t + 18, 1.6), (t + 34, 0.4)])
        c.seq("turn", [(t, 0), (t + 12, 0.2, "QUAD_IN"), (t + 18, -0.35), (t + 34, 0)])
        c.seq("pitch", [(t + 12, 0, "QUAD_IN"), (t + 18, 0.12), (t + 34, 0)])
        c.seq("hip_r", [(t + 12, 0), (t + 18, 0.35), (t + 34, 0)])
        c.seq("hip_l", [(t + 12, 0), (t + 18, -0.25), (t + 34, 0)])
        c.seq("move_forward", [(t + 12, 0), (t + 18, 8), (t + 34, 0)])
    c.seq("shoulder_r", [(124, 1.2), (140, 0)])
    c.seq("wrist_r", [(124, 0.4), (140, 0)])
    c.loop = [50, 90]
    out.append(c)

    c = Clip("MF03_knight", "shield_block", "Shield block",
             "Raises the shield in front of the chest in a braced stance with the sword held low, takes three "
             "blows (jolts back), peeks round the shield between blows, counter-thrusts and relaxes.", 144)
    brace = -HIP_HEIGHT * (1 - math.cos(0.3))
    c.seq("shoulder_l", [(1, 0), (16, 1.1), (124, 1.1), (140, 0)])
    c.seq("shoulder_r", [(1, 0), (16, 0.3), (112, 0.3), (118, 1.4, "QUAD_IN"), (124, 1.4), (140, 0)])
    c.seq("wrist_r", [(1, 0), (16, 0.8), (112, 0.8), (118, 0.4), (124, 0.4), (140, 0)])
    c.seq("hip_l", [(1, 0), (16, 0.3), (124, 0.3), (140, 0)])
    c.seq("hip_r", [(1, 0), (16, -0.3), (124, -0.3), (140, 0)])
    c.seq("move_up", [(1, 0), (16, brace), (124, brace), (140, 0)])
    for t in (40, 70, 100):
        c.seq("move_forward", [(t, 0, "QUAD_OUT"), (t + 3, -5), (t + 15, 0)])
        c.seq("pitch", [(t, 0, "QUAD_OUT"), (t + 3, -0.08), (t + 15, 0)])
    c.seq("neck", [(1, 0), (50, 0), (58, 0.45), (64, 0), (80, 0), (88, -0.45), (96, 0)])
    out.append(c)

    c = Clip("MF03_knight", "courtly_bow", "Courtly bow",
             "Sword hand to the chest (blade across the body), shield arm back, bows from the hips (legs stay "
             "upright, feet planted), rises and finishes with the blade raised before the face.", 144)
    c.seq("shoulder_r", [(1, 0), (20, 0.7), (100, 0.7), (112, 0.3), (124, 1.4), (136, 1.4), (144, 0)])
    c.seq("wrist_r", [(1, 0), (20, -1.4), (100, -1.4), (112, 0)])
    c.seq("shoulder_l", [(1, 0), (20, -0.3), (100, -0.3), (118, 0)])
    bend(c, [(20, 0), (50, 0.75), (74, 0.75), (100, 0)])
    c.seq("neck", [(1, 0), (14, 0.3), (24, 0), (110, 0), (124, -0.25), (140, 0)])
    out.append(c)
    return out


def builder():
    out = []
    c = Clip("MF04_builder", "hammering", "Hammering",
             "Leans in holding a nail with the left hand and strikes five times with the hammer, the last two "
             "faster; the body nods into each blow.", 144)
    c.seq("shoulder_l", [(1, 0), (14, 0.9), (120, 0.9), (136, 0)])
    bend(c, [(1, 0), (14, 0.12), (118, 0.12), (136, 0)])
    t = 14
    for dur in (24, 24, 24, 16, 16):
        up = dur - 8
        c.key("shoulder_r", t, 0.0 if t == 14 else 0.8)
        c.key("shoulder_r", t + up, 1.8, "QUAD_IN")
        c.key("shoulder_r", t + up + 4, 0.8)
        c.key("shoulder_r", t + dur, 0.8)
        c.seq("wrist_r", [(t, 0), (t + up, 0.4, "QUAD_IN"), (t + up + 4, 0), (t + dur, 0)])
        c.seq("roll", [(t + up, 0), (t + up + 4, -0.04), (t + dur, 0)])
        t += dur
    c.seq("shoulder_r", [(t, 0.8), (t + 18, 0)])
    c.loop = [14, 38]
    out.append(c)

    c = Clip("MF04_builder", "carry_load", "Carry load",
             "Both arms held forward as if carrying a load; short careful steps out, turn round, back, turn to "
             "the front and lower the arms.", 144)
    for side in ("shoulder_l", "shoulder_r"):
        c.seq(side, [(1, 0), (14, 1.45), (134, 1.45), (144, 0)])
    f, pos = gait(c, 14, 3, 28, 0.3, 0.0, arms="carry")
    turn_steps(c, 56, 76, 0.0, PI)
    f, pos = gait(c, 76, 3, 28, 0.3, 0.0, arms="carry", heading=PI, start=pos)
    turn_steps(c, 118, 134, PI, TAU)
    c.loop = [28, 56]
    out.append(c)

    c = Clip("MF04_builder", "head_shake_no", "Shrug and head shake",
             "Shrugs (both arms forward a little, hands roll outward), shakes the head 'no', then a facepalm with "
             "the free left hand.", 144)
    for side, wrist in (("shoulder_l", "wrist_l"), ("shoulder_r", "wrist_r")):
        c.seq(side, [(1, 0), (14, 0.35), (26, 0.35), (40, 0)])
        c.seq(wrist, [(1, 0), (14, 0.9), (26, 0.9), (40, 0)])
    c.seq("pitch", [(1, 0), (14, -0.05), (26, -0.05), (40, 0)])
    wave(c, "neck", 40, 12, 10, [0.3, 0.5, 0.6, 0.6, 0.6, 0.6, 0.6, 0.5, 0.4, 0.3])
    wave(c, "roll", 40, 12, 10, 0.03, sign=-1)
    c.seq("shoulder_l", [(100, 0), (112, 1.9), (130, 1.9), (144, 0)])
    c.seq("wrist_l", [(100, 0), (112, 0.8), (130, 0.8), (144, 0)])
    bend(c, [(100, 0), (112, 0.1), (130, 0.1), (144, 0)])
    out.append(c)
    return out


def chef():
    out = []
    shoulder, wrist = PAN_LEVEL
    c = Clip("MF05_chef", "stirring", "Stirring",
             "Stirs a pot with the ladle (bowl down): shoulder and wrist oscillate a quarter cycle apart so the "
             "bowl circles; the pan hangs at the side; glances aside, then taps the ladle twice.", 144)
    c.seq("shoulder_r", [(1, 0), (16, 1.05)])
    wave(c, "shoulder_r", 16, 24, 8, 0.12, center=1.05)
    wave(c, "wrist_r", 22, 24, 8, 0.5)
    c.seq("shoulder_r", [(112, 1.05), (117, 1.3, "QUAD_IN"), (121, 1.05), (126, 1.3, "QUAD_IN"), (130, 1.05),
                         (144, 0)])
    c.seq("shoulder_l", [(1, 0), (16, 0.2), (130, 0.2), (144, 0)])
    bend(c, [(1, 0), (16, 0.08), (112, 0.08), (126, 0)])
    wave(c, "roll", 16, 24, 8, 0.03)
    c.seq("neck", [(1, 0), (56, 0), (64, 0.4), (80, 0.4), (88, 0)])
    c.loop = [16, 40]
    out.append(c)

    c = Clip("MF05_chef", "pan_flip", "Pan flip",
             "Holds the frying pan level in front and flips three times (dip, flick up with a wrist snap, follow the "
             "pancake); the third flip comes with a hop; then points at the pan with the ladle.", 144)
    c.seq("shoulder_l", [(1, 0), (16, shoulder)])
    c.seq("wrist_l", [(1, 0), (16, wrist)])
    c.seq("shoulder_r", [(1, 0), (16, 0.3)])
    for k, t in enumerate((30, 62, 94)):
        c.seq("shoulder_l", [(t, shoulder), (t + 4, shoulder - 0.12, "QUAD_OUT"), (t + 8, shoulder + 0.45),
                             (t + 20, shoulder)])
        c.seq("wrist_l", [(t + 4, wrist, "QUAD_OUT"), (t + 8, wrist + 0.35), (t + 16, wrist)])
        c.seq("neck", [(t + 6, 0), (t + 12, 0.25), (t + 22, 0)])
        if k == 2:
            hop(c, t + 4, 14, 10)
    c.seq("shoulder_l", [(114, shoulder), (130, shoulder), (144, 0)])
    c.seq("wrist_l", [(114, wrist), (130, wrist), (144, 0)])
    c.seq("shoulder_r", [(114, 0.3), (124, 0.6), (134, 0.6), (144, 0)])
    out.append(c)

    c = Clip("MF05_chef", "celebrate", "Celebrate",
             "Arms up in front (utensils rolled outward), three happy hops with kicking legs and waving hands, a "
             "full spin, fist pumps, arms down.", 144)
    for side, wrist_ch in (("shoulder_l", "wrist_l"), ("shoulder_r", "wrist_r")):
        c.seq(side, [(1, 0, "QUAD_OUT"), (14, 1.8)])
        c.seq(wrist_ch, [(1, 0), (14, 0.8), (130, 0.8), (144, 0)])
    for k, t in enumerate((14, 38, 62)):
        hop(c, t, 20, 14)
        s = 1 if k % 2 == 0 else -1
        c.seq("hip_l", [(t, 0), (t + 10, 0.35 * s), (t + 20, 0)])
        c.seq("hip_r", [(t, 0), (t + 10, -0.2 * s), (t + 20, 0)])
    wave(c, "wrist_r", 14, 12, 12, 0.25, center=0.8)
    c.seq("turn", [(1, 0), (86, 0), (110, TAU), (144, TAU)])
    c.seq("neck", [(86, 0), (94, -0.4), (106, 0.4), (114, 0)])
    wave(c, "shoulder_l", 110, 10, 4, 0.2, center=1.8)
    wave(c, "shoulder_r", 110, 10, 4, 0.2, center=1.8, sign=-1)
    for side in ("shoulder_l", "shoulder_r"):
        c.seq(side, [(130, 1.8), (144, 0)])
    out.append(c)
    return out


def pirate():
    out = []
    c = Clip("MF06_pirate", "hornpipe_jig", "Hornpipe jig",
             "Ten alternating forward kicks with a little hop on the standing leg, arms swinging, body twisting "
             "with each kick.", 144)
    c.seq("shoulder_l", [(1, 0), (12, 1.2)])
    c.seq("shoulder_r", [(1, 0), (12, 0.7)])
    for k in range(10):
        t = 12 + 12 * k
        kick, stand = ("hip_l", "hip_r") if k % 2 == 0 else ("hip_r", "hip_l")
        c.seq(kick, [(t, 0), (t + 6, 0.7), (t + 12, 0)])
        c.seq(stand, [(t, 0), (t + 6, -0.15), (t + 12, 0)])
        hop(c, t, 12, 5)
        s = 1 if k % 2 == 0 else -1
        c.seq("turn", [(t, 0), (t + 6, 0.25 * s), (t + 12, 0)])
        c.seq("neck", [(t, 0), (t + 6, -0.2 * s), (t + 12, 0)])
        c.key("shoulder_l", t + 6, 1.2 - 0.4 * s)
        c.key("shoulder_r", t + 6, 0.7 + 0.4 * s)
    for side, v in (("shoulder_l", 1.2), ("shoulder_r", 0.7)):
        c.seq(side, [(132, v), (144, 0)])
    c.loop = [12, 36]
    out.append(c)

    c = Clip("MF06_pirate", "lookout", "Lookout",
             "Left hand raised to shade the eyes, leans to peer and scans the horizon left and right with body and "
             "head; spots something and points the cutlass at it.", 144)
    c.seq("shoulder_l", [(1, 0), (20, 1.7), (124, 1.7), (144, 0)])
    c.seq("wrist_l", [(1, 0), (20, 1.0), (124, 1.0), (144, 0)])
    c.seq("turn", [(1, 0), (20, 0), (50, 1.0), (60, 1.0), (100, -1.0), (124, 0)])
    c.seq("neck", [(20, 0), (36, 0.5), (56, 0), (72, -0.5), (96, 0)])
    bend(c, [(1, 0), (20, 0.06), (124, 0.06), (140, 0)])
    c.seq("shoulder_r", [(1, 0), (20, 0.3), (104, 0.3), (112, 1.57, "QUAD_OUT"), (128, 1.57), (144, 0)])
    out.append(c)

    c = Clip("MF06_pirate", "cutlass_lunge", "Cutlass lunge",
             "En garde stance, two fencing lunges (thrust, front leg forward, back leg extended), recover, then "
             "a flourish with the blade swung out to the side.", 144)
    stance = -HIP_HEIGHT * (1 - math.cos(0.3))
    c.seq("shoulder_r", [(1, 0), (16, 1.3)])
    c.seq("wrist_r", [(1, 0), (16, LUNGE_WRIST)])
    c.seq("shoulder_l", [(1, 0), (16, -0.8), (128, -0.8), (144, 0)])
    c.seq("hip_r", [(1, 0), (16, 0.3)])
    c.seq("hip_l", [(1, 0), (16, -0.3)])
    c.seq("move_up", [(1, 0), (16, stance)])
    for t in (24, 64):
        c.seq("move_forward", [(t, 0, "QUAD_OUT"), (t + 8, 20), (t + 16, 20), (t + 32, 0)])
        c.seq("hip_r", [(t, 0.3, "QUAD_OUT"), (t + 8, 0.65), (t + 16, 0.65), (t + 32, 0.3)])
        c.seq("hip_l", [(t, -0.3, "QUAD_OUT"), (t + 8, -0.45), (t + 16, -0.45), (t + 32, -0.3)])
        lunge = -HIP_HEIGHT * (1 - math.cos(0.55))
        c.seq("move_up", [(t, stance, "QUAD_OUT"), (t + 8, lunge), (t + 16, lunge), (t + 32, stance)])
        c.seq("pitch", [(t, 0, "QUAD_OUT"), (t + 8, 0.18), (t + 16, 0.18), (t + 32, 0)])
        c.seq("shoulder_r", [(t, 1.3, "QUAD_OUT"), (t + 8, LUNGE_THRUST), (t + 16, LUNGE_THRUST), (t + 32, 1.3)])
    c.seq("shoulder_r", [(104, 1.3), (118, 1.6), (126, 1.6), (138, 0)])
    c.seq("wrist_r", [(104, LUNGE_WRIST), (118, 1.4), (126, 1.4), (138, 0)])
    c.seq("hip_r", [(104, 0.3), (124, 0)])
    c.seq("hip_l", [(104, -0.3), (124, 0)])
    c.seq("move_up", [(104, stance), (124, 0)])
    out.append(c)
    return out


def firefighter():
    out = []
    c = Clip("MF07_firefighter", "ladder_climb", "Ladder climb",
             "Climbs four rungs of an imaginary ladder in front (16 LDU each) with alternating hands gripping at "
             "chest-to-face height and alternating feet, looks around at the top, climbs back down.", 144)
    for side in ("shoulder_l", "shoulder_r"):
        c.seq(side, [(1, 0), (8, 1.5)])
    c.seq("wrist_r", [(1, 0), (8, 0.5), (136, 0.5), (144, 0)])
    c.seq("pitch", [(1, 0), (8, 0.05), (136, 0.05), (144, 0)])
    height = 0.0
    for k, t in enumerate([8, 24, 40, 56, 80, 96, 112, 128]):
        up = k < 4
        reach, other = ("shoulder_l", "shoulder_r") if k % 2 == 0 else ("shoulder_r", "shoulder_l")
        step = "hip_l" if k % 2 == 0 else "hip_r"
        c.seq(reach, [(t, 1.5), (t + 8, 1.7), (t + 16, 1.5)])
        c.seq(other, [(t, 1.5), (t + 8, 1.35), (t + 16, 1.5)])
        c.seq(step, [(t, 0), (t + 8, 0.6), (t + 16, 0)])
        c.key("move_up", t, height)
        height += 16 if up else -16
        c.key("move_up", t + 16, height)
    hold(c, "move_up", 72, 80, 64.0)
    c.seq("neck", [(72, 0), (76, 0.6), (80, 0)])
    for side in ("shoulder_l", "shoulder_r"):
        c.seq(side, [(144 - 8, 1.5), (144, 0)])
    c.loop = [8, 40]
    out.append(c)

    c = Clip("MF07_firefighter", "run", "Run",
             "Runs out (fast leg and arm swing, forward lean, a short flight lift at each stride), turns round "
             "with a skid, runs back and turns to the front. Feet slide: travel is shorter than the stride.", 144)
    f, pos = gait(c, 6, 4, 16, 0.75, 0.9, distance=95, lean=0.12, flight=2.0, arm_bias=0.3)
    turn_steps(c, 38, 58, 0.0, PI, hip=0.25)
    f, pos = gait(c, 60, 4, 16, 0.75, 0.9, heading=PI, start=pos, distance=95, lean=0.12, flight=2.0,
                  arm_bias=0.3)
    turn_steps(c, 94, 114, PI, TAU, hip=0.2)
    for side in ("shoulder_l", "shoulder_r"):
        c.seq(side, [(94, 0.3), (114, 0)])
    c.loop = [14, 30]
    out.append(c)

    c = Clip("MF07_firefighter", "hose_sweep", "Hose sweep",
             "Braced stance, both hands forward on the hose, sweeps the spray left and right with body and head "
             "and leans back against the pressure.", 144)
    brace = -HIP_HEIGHT * (1 - math.cos(0.3))
    for side, v in (("shoulder_r", 1.35), ("shoulder_l", 1.2)):
        c.seq(side, [(1, 0), (16, v), (128, v), (144, 0)])
    c.seq("hip_l", [(1, 0), (16, 0.3), (128, 0.3), (144, 0)])
    c.seq("hip_r", [(1, 0), (16, -0.3), (128, -0.3), (144, 0)])
    c.seq("move_up", [(1, 0), (16, brace), (128, brace), (144, 0)])
    c.seq("pitch", [(1, 0), (16, -0.05), (128, -0.05), (144, 0)])
    wave(c, "turn", 20, 48, 4, 0.6)
    wave(c, "neck", 20, 48, 4, 0.25)
    c.loop = [20, 68]
    out.append(c)
    return out


def athlete():
    out = []
    c = Clip("MF08_athlete", "sprint", "Sprint",
             "Set position, sprints out with big leg and arm swings and a strong forward lean, turns round, jogs "
             "back and turns to the front.", 144)
    c.seq("pitch", [(1, 0), (12, 0.3)])
    c.seq("shoulder_l", [(1, 0), (12, 0.8)])
    c.seq("shoulder_r", [(1, 0), (12, -0.6)])
    f, pos = gait(c, 12, 6, 12, 0.9, 1.2, distance=110, flight=3.0, lead="r")
    c.seq("shoulder_l", [(12, 0.8)])
    c.seq("pitch", [(12, 0.3), (48, 0.22), (54, 0.12), (62, 0)])
    turn_steps(c, 52, 72, 0.0, PI, hip=0.3)
    f, pos = gait(c, 74, 4, 24, 0.5, 0.5, heading=PI, start=pos, distance=110, lean=0.06)
    turn_steps(c, 124, 144, PI, TAU)
    c.loop = [18, 30]
    out.append(c)

    c = Clip("MF08_athlete", "high_jump", "Spin jump",
             "Two arm pre-swings, a big jump (75 LDU) with a full turn in the air, arms straight up and legs tucked, "
             "landing with a forward lean, fist pumps overhead and a victory hop.", 144)
    for side in ("shoulder_l", "shoulder_r"):
        c.seq(side, [(1, 0), (12, 1.0), (24, -0.9), (34, PI, "QUAD_OUT"), (60, PI), (72, 1.0), (84, PI + 0.13)])
    c.seq("pitch", [(1, 0), (24, 0.15), (30, 0), (58, 0), (62, 0.1), (72, 0)])
    hop(c, 24, 36, 75)
    c.seq("turn", [(24, 0), (58, TAU), (144, TAU)])
    for hip in ("hip_l", "hip_r"):
        c.seq(hip, [(30, 0), (42, 1.2), (56, 0)])
    wave(c, "shoulder_l", 84, 12, 4, 0.13, center=PI + 0.13)
    wave(c, "shoulder_r", 84, 12, 4, 0.13, center=PI + 0.13, sign=-1)
    hop(c, 96, 16, 14)
    c.seq("neck", [(84, 0), (96, 0.5), (110, -0.5), (122, 0)])
    for side in ("shoulder_l", "shoulder_r"):
        c.seq(side, [(108, PI + 0.13), (128, 0)])
    out.append(c)

    c = Clip("MF08_athlete", "warmup_leg_swings", "Warm-up",
             "Arms forward for balance: three right-leg swings, three left-leg swings (the body counter-leans), "
             "then forward arm circles.", 144)
    for side in ("shoulder_l", "shoulder_r"):
        c.seq(side, [(1, 0), (12, 1.4), (108, 1.4), (132, 1.4 + TAU, "LINEAR"), (144, TAU)])
        c.key(side, 108, 1.4, "LINEAR")
    wave(c, "hip_r", 12, 16, 6, 0.9)
    wave(c, "pitch", 12, 16, 6, 0.08, sign=-1)
    wave(c, "hip_l", 60, 16, 6, 0.9)
    wave(c, "pitch", 60, 16, 6, 0.08, sign=-1)
    c.loop = [12, 28]
    out.append(c)
    return out


def wizard():
    out = []
    c = Clip("MF09_wizard", "spell_spin", "Spell spin",
             "Raises both arms forward (staff up), pirouettes a full turn with the head lagging, points the staff "
             "forward and twirls it with the wrist.", 144)
    c.seq("shoulder_l", [(1, 0), (16, 1.4), (64, 1.4), (80, 1.0), (120, 1.0), (140, 0)])
    c.seq("shoulder_r", [(1, 0), (16, 1.5), (64, 1.5), (72, 1.0, "QUAD_IN"), (120, 1.0), (140, 0)])
    c.seq("wrist_r", [(1, 0), (16, 0.5), (64, 0.5), (72, 0)])
    c.seq("turn", [(1, 0), (16, 0), (64, TAU), (144, TAU)])
    c.seq("neck", [(16, 0), (30, -0.5), (52, 0.5), (64, 0)])
    wave(c, "wrist_r", 80, 16, 4, 0.5)
    out.append(c)

    c = Clip("MF09_wizard", "levitate", "Levitate",
             "Arms forward with the palms rolled out, rises 40 LDU, hovers with a slow bob and yaw while the legs "
             "dangle, and settles back down.", 144)
    for side, wrist_ch, w in (("shoulder_l", "wrist_l", 0.8), ("shoulder_r", "wrist_r", 0.5)):
        c.seq(side, [(1, 0), (24, 1.3), (116, 1.3), (140, 0)])
        c.seq(wrist_ch, [(1, 0), (24, w), (116, w), (140, 0)])
    c.seq("move_up", [(1, 0), (10, 0), (40, 40)])
    wave(c, "move_up", 40, 24, 6, 5, center=40)
    c.seq("move_up", [(112, 40), (140, 0)])
    wave(c, "turn", 40, 72, 2, 0.6)
    wave(c, "hip_l", 40, 36, 4, 0.12)
    wave(c, "hip_r", 40, 36, 4, 0.12, sign=-1)
    c.loop = [40, 64]
    out.append(c)

    c = Clip("MF09_wizard", "cast_spell", "Cast spell",
             "Raises the staff, casts it down and forward with a lean and a step (recoil back), twice; then circles "
             "the staff with the wrist.", 144)
    c.seq("shoulder_l", [(1, 0), (20, 1.2)])
    # Staff rolled outward (clear of the hat brim) only once the arm is up: rolled low, its lower end swings
    # into the leg.
    c.seq("wrist_r", [(1, 0), (12, 0), (20, 0.5), (88, 0.5)])
    c.seq("shoulder_r", [(1, 0), (20, 1.6)])
    for t in (20, 60):
        if t > 20:
            c.seq("shoulder_r", [(t - 12, 1.0), (t, 1.6, "QUAD_IN")])
        c.seq("shoulder_r", [(t, 1.6, "QUAD_IN"), (t + 8, 1.0)])
        c.seq("pitch", [(t - 12, 0), (t, -0.08, "QUAD_IN"), (t + 8, 0.2), (t + 28, -0.05), (t + 36, 0)])
        c.seq("hip_r", [(t, 0, "QUAD_IN"), (t + 8, 0.35), (t + 28, 0)])
        c.seq("hip_l", [(t, 0, "QUAD_IN"), (t + 8, -0.2), (t + 28, 0)])
        c.seq("move_forward", [(t, 0, "QUAD_IN"), (t + 8, 10), (t + 28, -6), (t + 36, 0)])
        c.seq("shoulder_l", [(t, 1.2, "QUAD_IN"), (t + 8, 1.5), (t + 28, 1.2)])
    c.seq("shoulder_r", [(68, 1.0), (88, 1.0)])
    c.seq("wrist_r", [(88, 0.5), (96, 0)])
    wave(c, "wrist_r", 96, 16, 2, 0.5)
    c.seq("shoulder_r", [(112, 1.0), (124, 1.0), (140, 0)])
    c.seq("shoulder_l", [(96, 1.2), (124, 1.2), (140, 0)])
    out.append(c)
    return out


def diver():
    out = []
    c = Clip("MF10_diver", "swim_crawl", "Swim crawl",
             "Rises into imaginary water and lies prone (pitch pi/2), front-crawl arms windmill half a stroke "
             "apart with a flutter kick and side breaths, then rights itself, drifts home and sinks.", 144)
    c.seq("move_up", [(1, 0), (24, 40), (120, 40), (144, 0)])
    c.seq("pitch", [(1, 0), (4, 0), (24, PI / 2), (100, PI / 2), (120, 0)])
    c.seq("shoulder_l", [(1, 0), (20, 0, "LINEAR"), (100, 2 * TAU), (144, 2 * TAU)])
    c.seq("shoulder_r", [(1, 0), (40, 0, "LINEAR"), (120, 2 * TAU), (144, 2 * TAU)])
    wave(c, "hip_l", 20, 8, 20, 0.25)
    wave(c, "hip_r", 20, 8, 20, 0.25, sign=-1)
    wave(c, "hip_l", 100, 16, 4, 0.3)
    wave(c, "hip_r", 100, 16, 4, 0.3, sign=-1)
    wave(c, "roll", 20, 40, 4, 0.15)
    c.seq("neck", [(1, 0), (44, 0), (50, 0.6), (56, 0), (84, 0), (90, 0.6), (96, 0)])
    c.seq("move_forward", [(1, 0), (20, 0, "LINEAR"), (100, 80), (110, 80), (140, 0)])
    c.loop = [40, 80]
    out.append(c)

    c = Clip("MF10_diver", "sit_down_stand_up", "Sit down and stand up",
             "Sits down on the floor leaning back a little (legs flat, hip axis lowered to the seated height, "
             "flippers point up), hands at the sides, waves and looks around while seated, stands back up.", 144)
    seat = SIT_HEIGHT - HIP_HEIGHT
    for hip in ("hip_l", "hip_r"):
        c.seq(hip, [(1, 0), (30, SIT_HIP), (90, SIT_HIP), (120, 0)])
    c.seq("move_up", [(1, 0), (30, seat), (90, seat), (120, 0)])
    c.seq("pitch", [(1, 0), (30, -SIT_LEAN), (90, -SIT_LEAN), (100, 0.15), (120, 0)])
    c.seq("shoulder_r", [(1, 0), (40, 0), (50, 2.0), (74, 2.0), (84, 0)])
    wave(c, "wrist_r", 50, 12, 4, 0.6)
    c.seq("neck", [(30, 0), (40, 0.8), (54, 0.8), (66, -0.8), (80, -0.8), (90, 0)])
    out.append(c)

    c = Clip("MF10_diver", "fall_and_get_up", "Fall and get up",
             "Stumbles backward, falls onto its air tanks (the hip axis swings round the heels), kicks and "
             "flails, sits up, stands up and walks back to the start.", 144)
    tank = 24.0 - HIP_HEIGHT  # lying on the air tanks: hip axis about 24 LDU above the floor
    seat = SIT_HEIGHT - HIP_HEIGHT
    c.seq("pitch", [(1, 0), (10, -0.15), (28, -PI / 2, "QUAD_IN"), (60, -PI / 2), (84, -SIT_LEAN), (92, -SIT_LEAN),
                    (112, 0)])
    c.key("pitch", 10, -0.15, "QUAD_IN")
    half = HIP_HEIGHT * math.sin(PI / 4)
    c.seq("move_forward", [(1, 0), (10, -4, "QUAD_IN"), (19, -half - 2, "QUAD_IN"), (28, -HIP_HEIGHT),
                           (84, -HIP_HEIGHT), (112, -14), (136, 0)])
    c.seq("move_up", [(1, 0), (10, 0, "QUAD_IN"), (19, half - HIP_HEIGHT), (28, tank, "QUAD_OUT"),
                      (31, tank + 3, "QUAD_IN"), (34, tank), (60, tank), (84, seat), (112, 0)])
    for side, top in (("shoulder_l", 2.0), ("shoulder_r", 1.9)):
        c.seq(side, [(1, 0), (10, top), (28, top), (40, 0.0), (112, 0)])
    wave(c, "wrist_l", 34, 12, 4, 0.6)
    wave(c, "wrist_r", 34, 12, 4, 0.6, sign=-1)
    for hip, s in (("hip_l", 1), ("hip_r", -1)):
        c.seq(hip, [(1, 0), (10, 0), (28, 0.5)])
        wave(c, hip, 34, 12, 4, 0.25, center=0.5, sign=s)
        c.seq(hip, [(60, 0.5), (84, SIT_HIP), (92, SIT_HIP), (112, 0)])
    wave(c, "neck", 60, 12, 2, 0.5)
    f, pos = gait(c, 112, 2, 24, 0.3, 0.25, distance=14, start=(-14.0, 0.0))
    out.append(c)
    return out


FIGURE_CLIPS = (police, spaceman, knight, builder, chef, pirate, firefighter, athlete, wizard, diver)


def library():
    """All clips in figure order, three per figure (windows A, B, C)."""
    clips = []
    for make in FIGURE_CLIPS:
        made = make()
        if len(made) != 3:
            raise ValueError(f"{make.__name__}: expected 3 clips")
        clips += made
    return clips


def window_of(clip, clips=None):
    clips = clips or library()
    mine = [c for c in clips if c.figure == clip.figure]
    return "ABC"[[c.name for c in mine].index(clip.name)]


# --------------------------------------------------------------------------- checks and export
def check(clip, tolerance=1e-9):
    """Clip rules: neutral start and end (whole turns allowed on periodic channels), ranges, continuity."""
    problems = []
    for ch in CHANNELS:
        keys = clip.keys(ch)
        if abs(keys[0][1]) > tolerance:
            problems.append(f"{ch} starts at {keys[0][1]}")
        end = keys[-1][1]
        if ch in PERIODIC:
            turns = end / TAU
            if abs(turns - round(turns)) > tolerance / TAU:
                problems.append(f"{ch} ends at {end}, not a whole turn")
        elif abs(end) > tolerance:
            problems.append(f"{ch} ends at {end}")
        lo, hi = (JOINTS.get(ch) or FIGURE[ch])["min"], (JOINTS.get(ch) or FIGURE[ch])["max"]
        samples = [clip.value(ch, f / 4) for f in range(4, 4 * clip.frames + 1)]
        if min(samples) < lo - tolerance or max(samples) > hi + tolerance:
            problems.append(f"{ch} leaves [{lo}, {hi}]")
        # Continuity: no jump larger than a fast swing between quarter frames.
        jump = max((abs(b - a) for a, b in zip(samples, samples[1:])), default=0.0)
        limit = 20.0 if ch.startswith("move_") else 0.35
        if jump > limit:
            problems.append(f"{ch} jumps {jump:.3f} within a quarter frame")
    if clip.loop:
        a, b = clip.loop
        if not 1 <= a < b <= clip.frames:
            problems.append(f"loop range {clip.loop} outside the clip")
    return problems


def baked(clip):
    return {ch: [round(clip.value(ch, f), 6) for f in range(1, clip.frames + 1)] for ch in CHANNELS}


def clip_document(clip, clips=None):
    clips = clips or library()
    w = window_of(clip, clips)
    start = WINDOWS[w][0]
    return dict(
        id=clip.id,
        figure=clip.figure,
        clip=clip.name,
        title=clip.title,
        description=clip.description,
        window=w,
        timeline_start=start,
        frames=clip.frames,
        fps=FPS,
        duration_seconds=round(clip.frames / FPS, 3),
        loop_range=clip.loop,
        blender=dict(action=clip.id, nla_track=f"{w} {clip.name}", controller_slot="OBminifig_controller",
                     strip_start=start),
        units=dict(joints="radian", move_forward="ldu", move_left="ldu", move_up="ldu", turn="radian",
                   pitch="radian", roll="radian"),
        channels={ch: [dict(frame=f, value=round(v, 9), interpolation=INTERPOLATIONS[i][0],
                            easing=INTERPOLATIONS[i][1]) for f, v, i in clip.keys(ch)] for ch in CHANNELS},
        baked=baked(clip),
        notes="Clip-local frames start at 1. Each key's interpolation/easing applies to the segment that starts "
              "at it. 'baked' holds the evaluated value at every integer frame. Joint channels are minifig plan "
              "controls; move_*/turn/pitch/roll move the whole figure about its hip-axis centre (see "
              "catalog.json 'conventions').",
    )


def conventions():
    return dict(
        figure_frame="LDraw LDU in the minifig's own frame: torso origin at the neck, -Y up, the face looks "
                     "along -Z, the figure's left is +X. Ground at y = +72 (feet).",
        pivot=list(PIVOT),
        hip_height=HIP_HEIGHT,
        seated_height=SEATED_HEIGHT,
        joints=JOINTS,
        figure_channels=FIGURE,
        channel_order=CHANNELS,
        periodic_channels=sorted(PERIODIC),
        whole_figure_transform="world = T(pivot) * T(move_left*left + move_up*up + move_forward*forward) * "
                               "R(up, turn) * R(left, pitch) * R(back, roll) * T(-pivot); home-frame axes "
                               "forward=(0,0,-1), left=(1,0,0), up=(0,-1,0), back=(0,0,1). In Blender (figure "
                               "facing -Y): MOVE location = (move_left, -move_forward, move_up) * 0.0004 m, "
                               "rotation_mode 'YXZ', rotation_euler = (pitch, roll, turn).",
        rules="Every clip starts at the neutral pose (all channels 0) and ends at it (periodic channels may end on "
              "whole turns, an identical pose); the figure returns to its home spot.",
        windows=WINDOWS,
        fps=FPS,
        frames=FRAMES,
    )


def figure_transform(values):
    """Whole-figure 4x4 transform in the figure's LDraw frame (rest = identity)."""
    def rot(axis, a):
        x, y, z = axis
        c, s, t = math.cos(a), math.sin(a), 1 - math.cos(a)
        return [[t * x * x + c, t * x * y - s * z, t * x * z + s * y],
                [t * x * y + s * z, t * y * y + c, t * y * z - s * x],
                [t * x * z - s * y, t * y * z + s * x, t * z * z + c]]

    def mm(a, b):
        return [[sum(a[i][k] * b[k][j] for k in range(3)) for j in range(3)] for i in range(3)]

    r = mm(mm(rot((0, -1, 0), values.get("turn", 0.0)), rot((1, 0, 0), values.get("pitch", 0.0))),
           rot((0, 0, 1), values.get("roll", 0.0)))
    move = [values.get("move_left", 0.0), -values.get("move_up", 0.0), -values.get("move_forward", 0.0)]
    p = PIVOT
    rp = [sum(r[i][k] * p[k] for k in range(3)) for i in range(3)]
    t = [p[i] + move[i] - rp[i] for i in range(3)]
    return [r[0] + [t[0]], r[1] + [t[1]], r[2] + [t[2]], [0.0, 0.0, 0.0, 1.0]]


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
