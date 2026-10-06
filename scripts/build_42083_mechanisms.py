#!/usr/bin/env python3
"""Five standalone 42083 (Bugatti Chiron) mechanisms: selection, extraction and motion plans.

    NAME in drivetrain | gearbox | dnr | doors | wing; OUT = output/42083-mechanisms/NAME
    scripts/build_42083_mechanisms.py select NAME            # OUT/keep.json (+ local contact evidence)
    scripts/build_42083_mechanisms.py extract NAME           # OUT/source/42083-NAME.mpd + idmap.json
    ./ldraw-mecha prepare OUT/source/42083-NAME.mpd --output OUT/study
    scripts/build_42083_mechanisms.py plan NAME --ready      # OUT/plan.json + OUT/kinematics.json

Source: data/models-annotated/42083-1.mpd (Philippe Hurbain [Philo], CCAL 2.0), selected section
`42083 - chiron.ldr`, unmodified. Every extract keeps that section's frame (LDU, -Y up, front -Z,
the car's left +X), so motion is authored on the source occurrence IDs and remapped through the
extract's ID map. Gear ratios, signs, pivots and link lengths are computed from library connector
frames and asserted here, never typed in. Embedded DATs (`42083 - 35185.dat` ...) use their
library part's connector frames for analysis only; their geometry is not replaced.

Gearbox reconstruction: the source lacks two 12T double-bevel gears (32270) that the set includes
(8 in the official inventory, 6 in this file). Without them the 20T clutch gear 0/90/84 and shaft
0/90/30 have no partner and the 8-speed collapses to 3 ratios. The gearbox extract alone adds them
in the empty 20-LDU slots on the shafts that need them (see RECONSTRUCTED); the source is untouched.
"""

from __future__ import annotations

import argparse
import copy
from collections import defaultdict
import json
import math
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
from build_defender_rig import Geometry  # noqa: E402
from build_defender_suspension import seated  # noqa: E402
import extract_subsystem  # noqa: E402
from ldraw_mechanisms import analysis, linkages, plan as contract  # noqa: E402
from ldraw_mechanisms.math3d import add, cross, dot, length, mul, signed_gear_ratio, sub, unit  # noqa: E402
from ldraw_mechanisms.source import Document, sha256  # noqa: E402
from timeline_42083 import (  # noqa: E402,F401  (pure timelines and the shared opening limits)
    CARRIES, DOOR_MAX, FPS, FRAMES, GEARBOX_SHIFTS, SHIFT_FRAMES, SPEEDS, STATE, WING_RANGE, continuity,
    controls_at, ramp, smooth, speed_profile, timeline,
)

SOURCE = ROOT / "data/models-annotated/42083-1.mpd"
SECTION = "42083 - chiron.ldr"
OUT = ROOT / "output/42083-mechanisms"
EVIDENCE = OUT / "evidence/contacts-mechanical.json"
NAMES = ("drivetrain", "gearbox", "dnr", "doors", "wing")
PLAN_NAMES = {n: f"chiron_42083_{n}" for n in NAMES}
X, Y, Z = [1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]
PI = math.pi
RING = 10.0  # driving-ring travel (LDU): source ring 0/90/57 sits 10 LDU off its joiner, where the catch lobe holds it
GB = "0/90/"

# Reconstructed 12T double-bevel gears (gearbox extract only): pseudo-ID -> (shaft, centre, partner).
RECONSTRUCTED = {
    "R/S6_12T": dict(centre=[80.0, 0.0, 40.0], like=GB + "14", partner=GB + "84",
                     shaft="stage-1 output shaft 0/90/53 (empty slot between beams 0/90/86 and 0/90/68)"),
    "R/S5_12T": dict(centre=[-80.0, -40.0, 160.0], like=GB + "14", partner=GB + "13",
                     shaft="low-range shaft 0/90/30 (empty slot beside 20T 0/90/13)"),
}


def key(s):
    return [(0, int(x), "") if x.isdigit() else (1, 0, x) for x in s.split("/")]


def r6(v):
    return [round(x, 6) for x in v]


def num(v):
    return repr(float(v))


def out_dir(name):
    return OUT / name


# --------------------------------------------------------------------------- source geometry
def full_manifest():
    return Document(SOURCE).manifest(SECTION)


def aliased(manifest):
    """Copy with library aliases for embedded `42083 - NNNN.dat` parts (connector frames only)."""
    m = copy.deepcopy(manifest)
    for n in m["nodes"]:
        hit = re.fullmatch(r"42083 - (\w+)\.dat", n["ref"]) if n.get("embedded") else None
        if hit:
            n["library_alias"] = hit.group(1) + ".dat"
    return m


class Source:
    def __init__(self):
        self.manifest = full_manifest()
        self.aliased = aliased(self.manifest)
        self.evidence = json.loads(EVIDENCE.read_text())
        self.g = Geometry(self.aliased, self.evidence)
        self.nodes = self.g.nodes

    def parts(self):
        return [i for i, n in self.nodes.items() if n["kind"] == "part"]


ROTATING_OK = re.compile(r"Axle|Gear|Joiner|Bush|Universal Joint|Crankshaft|Knob|Spindle|Connector #2|"
                         r"Steering Wheel Large|2 x  0.5 Liftarm|Towball|Differential|Beam  1$", re.I)


class Author:
    """Measured motion authoring on source IDs (pseudo IDs R/... for reconstructed gears)."""

    def __init__(self, src, name):
        self.src, self.g, self.name = src, src.g, name
        self.controls, self.signals, self.bodies, self.anchors, self.checks = {}, {}, {}, {}, []
        self.connections, self.review, self.meshes, self.locks = {}, defaultdict(list), [], []

    # ---- positions/axes (reconstructed gears are exact copies of their model part's frame)
    def at(self, i, p=(0, 0, 0)):
        if i in RECONSTRUCTED:
            return add(RECONSTRUCTED[i]["centre"], list(p))
        return self.g.at(i, p)

    def axis(self, i):
        if i in RECONSTRUCTED:
            return self.axis(RECONSTRUCTED[i]["like"])
        c = self.g.conn(i)
        for kind in ("axle_hole", "pin_hole", "axle"):
            for f in c:
                if f["kind"] == kind:
                    a = f["axis"]
                    for ref in (X, Y, Z):
                        if abs(abs(dot(a, ref)) - 1) < 1e-6:
                            return ref
                    return unit(a)
        raise ValueError(f"{i}: no shaft connector")

    def desc(self, i):
        return "12T double bevel (reconstructed)" if i in RECONSTRUCTED else self.g.desc(i)

    # ---- plan primitives
    def control(self, name, lo, hi, description, unit_name="radian", default=0.0):
        self.controls[name] = dict(default=default, min=lo, max=hi, unit=unit_name, description=description)
        return "control:" + name

    def clamped(self, name):
        c = self.controls[name]
        return self.signal(name + "_v", f"clamp(v,{c['min']!r},{c['max']!r})", v="control:" + name)

    def signal(self, name, expr, **variables):
        if len(expr) > 255 or len(name) > 40:
            raise ValueError(f"{name}: expression or name too long")
        self.signals[name] = dict(expression=expr,
                                  variables={k: v if ":" in v else "signal:" + v for k, v in variables.items()})
        return name

    def body(self, name, instances, origin, axis, sig=None, kind="revolute", parent=None, **extra):
        owned = {i for b in self.bodies.values() for i in b["instances"]}
        clash = owned & set(instances)
        if clash:
            raise ValueError(f"{name}: parts already owned {sorted(clash)}")
        b = dict(instances=list(instances), kind=kind, origin=r6(origin), axis=r6(unit(axis)), **extra)
        if sig:
            b["signal"] = sig
        if parent:
            b["parent"] = parent
        self.bodies[name] = b
        return name

    def edge(self, kind, a, b, evidence_text, note, measurements=None):
        k = f"r_{kind}_{a}_{b}".replace("/", "_")
        entry = dict(a=a, b=b, kind=kind, status="reviewed", evidence=evidence_text, review=note)
        if measurements:
            entry["measurements"] = measurements
        self.connections[k] = entry

    def group(self, seed, extra=(), drop=(), rotating=True):
        """Axle-locked group; rotating groups must hold only shaft-like parts (end-face contacts are dropped)."""
        members = sorted((set(self.g.group_of.get(seed, {seed})) | set(extra)) - set(drop), key=key)
        if rotating:
            odd = [i for i in members if i not in RECONSTRUCTED and not ROTATING_OK.search(self.desc(i))
                   and not self.src.nodes[i].get("embedded")]
            if odd:
                raise ValueError(f"Group of {seed} holds frame-like parts {odd}: review end-face contacts")
        return members

    def on_line(self, i, p, axis, tol=0.6):
        return length(cross(sub(self.at(i), p), unit(axis))) < tol

    # ---- gears
    def spur(self, a, ta, b, tb, view, tol=0.6, a_centre=None, b_centre=None):
        """Signed ratio w_b / w_a about the shared axis for a parallel external mesh (diagonal allowed)."""
        pa, pb = a_centre or self.at(a), b_centre or self.at(b)
        axis = self.axis(a)
        if abs(abs(dot(axis, self.axis(b))) - 1) > 1e-6:
            raise ValueError(f"{a}-{b}: axes not parallel")
        d = sub(pb, pa)
        axial = dot(d, axis)
        radial = length(sub(d, mul(axis, axial)))
        nominal = 1.25 * (ta + tb)
        if abs(axial) > 10.5 or abs(radial - nominal) > tol:
            raise ValueError(f"{a}-{b}: not a {ta}/{tb} mesh ({radial:.2f} vs {nominal}, axial {axial:.2f})")
        ratio = signed_gear_ratio(axis, pa, ta, axis, pb, tb)
        self.meshes.append((a, axis, b, axis, ratio))
        self.edge("gear_mesh", a, b,
                  "Parallel axes from connector frames; centre distance against 1.25 LDU/tooth pitch radii; "
                  "20 LDU thick gears overlap axially",
                  f"Reviewed {ta}T/{tb}T external mesh, ratio {ratio:+.4f} about the shared axis",
                  dict(centre_distance_ldu=round(radial, 3), nominal_ldu=nominal, axial_offset_ldu=round(axial, 3)))
        self.review[view].append(f"{a} {ta}T / {b} {tb}T: {radial:.2f} LDU (nominal {nominal}), axial {axial:+.1f}")
        return ratio

    def bevel(self, a, ta, b, tb, view, a_centre=None, b_centre=None, axis_a=None, axis_b=None):
        """Signed ratio w_b (about axis_b) per w_a (about axis_a) for perpendicular bevel/knob meshes."""
        pa, pb = a_centre or self.at(a), b_centre or self.at(b)
        axis_a, axis_b = axis_a or self.axis(a), axis_b or self.axis(b)
        if abs(dot(axis_a, axis_b)) > 1e-3:
            raise ValueError(f"{a}-{b}: bevel axes not perpendicular")
        w = sub(pa, pb)
        bd, dd, ee = dot(axis_a, axis_b), dot(axis_a, w), dot(axis_b, w)
        s = (bd * ee - dd) / (1 - bd * bd)
        t = (ee - bd * dd) / (1 - bd * bd)
        qa, qb = add(pa, mul(axis_a, s)), add(pb, mul(axis_b, t))
        if length(sub(qa, qb)) > 0.6:
            raise ValueError(f"{a}-{b}: axes do not intersect ({length(sub(qa, qb)):.2f})")
        apex = mul(add(qa, qb), 0.5)
        out_a, out_b = unit(sub(pa, apex)), unit(sub(pb, apex))
        ratio = -ta / tb
        self.meshes.append((a, out_a, b, out_b, ratio))
        self.edge("gear_mesh", a, b, "Perpendicular axes meeting at a common apex (closest approach measured)",
                  f"Reviewed {ta}/{tb} perpendicular mesh, w_b = {ratio:+.4f} w_a about the outward axes",
                  dict(apex=r6(apex), a_from_apex_ldu=round(length(sub(pa, apex)), 3),
                       b_from_apex_ldu=round(length(sub(pb, apex)), 3)))
        self.review[view].append(f"{a} {ta} / {b} {tb} perpendicular: apex {r6(apex)}")
        return dot(axis_b, out_b) * ratio * dot(axis_a, out_a), (out_a, out_b, ratio)

    def zbody(self, name, seed, sig, extra=(), drop=(), view=None):
        grp = self.group(seed, extra, drop)
        ax = self.axis(seed)
        for e in extra:
            if not self.on_line(e, self.at(seed), ax):
                raise ValueError(f"{name}: {e} is not on the shaft line of {seed}")
        self.body(name, grp, self.at(seed), ax, sig)
        if view:
            self.review[view].append(f"{name}: {len(grp)} parts on {seed}'s shaft")
        return grp


# --------------------------------------------------------------------------- drivetrain
def build_drivetrain(a):
    g = a.g
    a.control("drive", -600.0, 600.0, "Road-wheel roll (mean axle side-gear angle) about +X; positive rolls forward (-Z)")
    a.control("diff_front", -60.0, 60.0, "Front differential split: left (+X) side gear +, right side gear - (half difference)")
    a.control("diff_rear", -60.0, 60.0, "Rear differential split: left (+X) side gear +, right side gear - (half difference)")
    d, sf, sr = a.clamped("drive"), a.clamped("diff_front"), a.clamped("diff_rear")
    for axle, s in (("f", sf), ("r", sr)):
        a.signal(f"side_{axle}l", "m+s", m=d, s=s)
        a.signal(f"side_{axle}r", "m-s", m=d, s=s)
    axles = dict(
        rear=dict(diff="0/85/35", spider="0/85/38", pinion="0/85/125", view="rear_axle",
                  l=("0/85/36", "0/85/33/36", "0/85/33/37", "0/85/33/35", "0/85/33/31", ("0/85/33/30", "565", "566", "567")),
                  r=("0/85/37", "0/85/34/36", "0/85/34/37", "0/85/34/35", "0/85/34/31", ("0/85/34/30", "562", "563", "564"))),
        front=dict(diff="1/89/46/10", spider="1/89/46/13", pinion="1/89/46/15", view="front_axle",
                   l=("1/89/46/11", "1/89/51", "1/89/53", "1/89/52", "1/89/56/4", ("1/89/56/3", "556", "557", "558")),
                   r=("1/89/46/12", "1/89/47", "1/89/49", "1/89/48", "1/89/55/4", ("1/89/55/3", "559", "560", "561"))),
    )
    pinion_per_carrier = {}
    for axle, spec in axles.items():
        view, diff = spec["view"], spec["diff"]
        centre = a.at(diff)
        if abs(abs(dot(g.one(diff, "pin_hole")["axis"], X)) - 1) > 1e-6:
            raise ValueError(f"{diff}: differential axis is not X")
        a.body(f"{axle}_diff", [diff], centre, X, d)
        bar = unit(g.one(diff, "bar")["axis"])
        _, (o_l, o_sp, ratio) = a.bevel(spec["l"][0], 12, spec["spider"], 12, view, axis_a=X, axis_b=bar)
        _, (o_r, o_sp2, _) = a.bevel(spec["r"][0], 12, spec["spider"], 12, view, axis_a=X, axis_b=bar)
        if dot(o_sp, o_sp2) < 0.999 or dot(o_l, o_r) > -0.999:
            raise ValueError(f"{axle} differential side gears are not opposed")
        split = sf if axle == "front" else sr
        a.signal(f"{axle}_spider", f"{num(ratio * dot(o_l, X))}*s", s=split)
        a.body(f"{axle}_spider", [spec["spider"]], a.at(spec["spider"]), o_sp, f"{axle}_spider", parent=f"{axle}_diff")
        ring = a.at(diff, (0, 0, 26))  # 28T ring of 62821 (part-local z=+26)
        k, _ = a.bevel(diff, 28, spec["pinion"], 20, view, a_centre=ring, axis_a=X, axis_b=Z)
        pinion_per_carrier[axle] = k
        a.review[view].append(f"28T ring / 20T pinion: pinion = {k:+.4f} x carrier (about +Z / +X)")
        for side in ("l", "r"):
            gear, end_in, cross_id, end_out, driver, wheel = spec[side]
            grp = a.group(gear)
            if end_in not in grp:
                raise ValueError(f"{end_in} not locked to side gear {gear}")
            sig = f"side_{axle[0]}{side}"
            a.body(f"{axle}_side_{side}", grp, a.at(gear), X, sig)
            jc = a.at(cross_id)
            d_in = mul(X, 1 if dot(sub(jc, centre), X) > 0 else -1)
            d_out = unit(sub(g.one(driver, "generic")["pos"], jc))
            f_in, f_out = g.one(end_in, "clip")["axis"], g.one(end_out, "clip")["axis"]
            theta = a.signal(f"{axle}_{side}_ujin", f"{num(dot(d_in, X))}*s", s=sig)
            out, crs = linkages.universal_joint(a.signals, f"uj_{axle[0]}{side}", theta, d_in, d_out, f_in, f_out)
            a.body(f"{axle}_cross_{side}", [cross_id], jc, f_in, crs, parent=f"{axle}_side_{side}")
            shaft = a.group(end_out)
            if driver not in shaft:
                raise ValueError(f"{driver} not on the {axle} {side} half shaft")
            a.body(f"{axle}_halfshaft_{side}", shaft, jc, d_out, out)
            hub = wheel[0]
            hub_pin = g.one(hub, "pin")
            if abs(abs(dot(hub_pin["axis"], X)) - 1) > 1e-6:
                raise ValueError(f"{hub}: hub axis is not X")
            for part in wheel[1:]:
                if not a.on_line(part, hub_pin["pos"], X):
                    raise ValueError(f"{part} is not on the {axle} {side} hub axis")
            # CV spindle: the hub turns 1:1 with the half shaft (sign only; never scale by the bend cosine).
            ws = a.signal(f"wheel_{axle[0]}{side}", f"{num(math.copysign(1.0, dot(d_out, X)))}*h", h=out)
            a.body(f"wheel_{axle[0]}{side}", list(wheel), hub_pin["pos"], X, ws)
            bend = math.degrees(math.acos(max(-1.0, min(1.0, dot(d_in, d_out)))))
            a.review[view].append(f"{side} half shaft bend {bend:.1f} deg: exact cardan at the diff, "
                                  "spindle driver turns the hub at the half-shaft rate (CV assumption)")
    # Main shaft: rear pinion on it; front pinion shaft through a 16T/16T mesh.
    main = a.group("0/85/124")
    if "0/85/125" not in main or "1/40" not in main or "1/47" not in main:
        raise ValueError("Main shaft group lost a gear")
    r_fp = a.spur("1/40", 16, "1/89/46/28", 16, "main_shaft")
    k_rear, k_front = pinion_per_carrier["rear"], pinion_per_carrier["front"]
    if abs(k_front - r_fp * k_rear) > 1e-9:
        raise ValueError(f"Front and rear axles disagree for straight running ({k_front} vs {r_fp * k_rear})")
    a.review["main_shaft"].append(
        f"No centre differential: both carriers = drive, front pinion {k_front:+.4f} = 16:16 ({r_fp:+.0f}) x rear "
        f"pinion {k_rear:+.4f} (checked equal, so front and rear wheels roll together)")
    a.signal("main", f"{num(k_rear)}*m", m=d)
    a.body("main_shaft", main, a.at("0/85/124"), Z, "main")
    a.signal("front_pinion", f"{num(r_fp)}*m", m="main")
    a.body("front_pinion_shaft", a.group("1/89/46/15"), a.at("1/89/46/15"), Z, "front_pinion")
    # Interfaces: gearbox input shaft (24T) and the D/N/R reverse clutch gear (16T), both driven.
    r_gb = a.spur("0/85/124", 8, GB + "51", 24, "interfaces")
    a.signal("gearbox_input", f"{num(r_gb)}*m", m="main")
    a.body("gearbox_input_shaft", a.group(GB + "51"), a.at(GB + "51"), Z, "gearbox_input")
    r_57 = a.spur("1/47", 16, "1/57", 16, "interfaces")
    a.signal("dnr_reverse_gear", f"{num(r_57)}*m", m="main")
    a.body("dnr_reverse_gear", ["1/57"], a.at("1/57"), Z, "dnr_reverse_gear")
    a.review["interfaces"].append("Driven context only: the gearbox and D/N/R selector are separate extracts")
    return dict(views=[
        ("rear_axle", "Rear differential, Cardan half shafts and wheels", ("rear_", "wheel_r"),
         ["control:drive", "control:diff_rear"], ["body:wheel_rl", "body:wheel_rr"]),
        ("front_axle", "Front differential, half shafts and wheels", ("front_diff", "front_spider", "front_side",
                                                                     "front_cross", "front_halfshaft", "wheel_f"),
         ["control:drive", "control:diff_front"], ["body:wheel_fl", "body:wheel_fr"]),
        ("main_shaft", "Locked main shaft and front pinion (all-wheel drive, no centre differential)",
         ("main_shaft", "front_pinion_shaft"), ["control:drive"], ["body:main_shaft"]),
        ("interfaces", "Driven interface gears of the neighbouring extracts", ("gearbox_input_shaft", "dnr_reverse_gear"),
         ["control:drive"], ["body:gearbox_input_shaft"]),
    ])


# --------------------------------------------------------------------------- gearbox
def sat(u):
    """Ring travel profile of the rotary catch (fraction of RING): dwell near neutral and at full travel."""
    return f"clamp((abs({u})-0.75)*5,0,1)*{u}/max(abs({u}),1e-6)"


def gearbox_ratios(a, view="stage1"):
    """Measured shaft ratios of the 8-speed; returns dict of named ratios (w_b per w_a about +Z)."""
    r = {}
    r["in"] = a.spur("0/85/124", 8, GB + "51", 24, "interfaces")  # S1 per main shaft
    r["s7"] = a.spur(GB + "88", 16, GB + "102", 16, view) * a.spur(GB + "102", 16, GB + "85", 16, view)  # S7 per S1
    r["idler102"] = a.spur(GB + "88", 16, GB + "102", 16, view)
    r["s8_per_s9"] = a.spur(GB + "33/7", 8, GB + "33/2", 8, view)
    r["s6_per_s8"] = a.spur(GB + "33/26", 16, GB + "33/22", 16, view)
    r["s6_per_s9"] = r["s8_per_s9"] * r["s6_per_s8"]
    # Stage-1 clutch gears and their constant meshes (gear angle per output shaft).
    r["g84_s6"] = a.spur(GB + "84", 20, "R/S6_12T", 12, view)  # S6 per gear 84
    r["g49_s6"] = a.spur(GB + "49", 16, GB + "33/24", 16, view)
    r["g3313_s9"] = a.spur(GB + "33/13", 20, GB + "33/4", 16, view, tol=0.6)
    r["g75_s9"] = a.spur(GB + "75", 16, GB + "71", 20, view, tol=0.6)
    # S6/S1 for the four catch-1 states (index 0..3 = catch-1 at 0, pi/2, pi, 3pi/2).
    r["k1"] = [r["g84_s6"], r["s7"] * r["g3313_s9"] * r["s6_per_s9"], r["g49_s6"], r["s7"] * r["g75_s9"] * r["s6_per_s9"]]
    # Idler chain at z=-60 (S6 -> 0/94 -> 0/92 -> 0/90/148 -> S4).
    chain = [(GB + "146", "0/94"), ("0/94", "0/92"), ("0/92", GB + "148"), (GB + "148", GB + "147")]
    acc, r["chain"] = 1.0, {}
    for x, y in chain:
        acc *= a.spur(x, 16, y, 16, "stage2")
        r["chain"][y] = acc
    r["s4_per_s6"] = acc
    # Stage 2: high = ring 0/90/57 locks 0/90/28 or 0/90/89 to the output S2 (both -1 from S4);
    # low = ring 0/90/56 locks 0/90/31 or 0/90/90 to S5, which reaches S2 through S3 (12T/20T twice).
    r["g28_s4"] = a.spur(GB + "7", 16, GB + "28", 16, "stage2")
    r["g89_s4"] = a.spur(GB + "82", 16, GB + "89", 16, "stage2")
    r["g31_s4"] = a.spur(GB + "7", 16, GB + "31", 16, "stage2")
    r["g90_s4"] = a.spur(GB + "82", 16, GB + "90", 16, "stage2")
    for k_ in ("g89_s4", "g31_s4", "g90_s4"):
        if abs(r[k_] - r["g28_s4"]) > 1e-12:
            raise ValueError(f"Stage-2 clutch gear {k_} does not match 0/90/28")
    r["s3_per_s2"] = a.spur(GB + "27", 20, GB + "14", 12, "stage2")
    r["s5_per_s3"] = a.spur(GB + "13", 20, "R/S5_12T", 12, "stage2")
    r["s5_per_s2"] = r["s3_per_s2"] * r["s5_per_s3"]
    r["k2_high"] = r["g28_s4"]  # S2 per S4 with ring 0/90/57 engaged
    r["k2_low"] = r["g31_s4"] / r["s5_per_s2"]  # S2 per S4 with ring 0/90/56 engaged
    r["gears"] = [r["in"] * k1 * r["s4_per_s6"] * k2 for k2 in (r["k2_high"], r["k2_low"]) for k1 in r["k1"]]
    return r


def build_gearbox(a):
    g = a.g
    rt = gearbox_ratios(a)
    s2_per_s1 = [k / rt["in"] for k in rt["gears"]]
    if len({round(abs(k), 9) for k in s2_per_s1}) != 8 or any(x <= y for x, y in zip(map(abs, s2_per_s1), map(abs, s2_per_s1[1:]))):
        raise ValueError(f"Gear ratios are not eight decreasing values: {s2_per_s1}")
    if len({math.copysign(1, k) for k in s2_per_s1}) != 1:
        raise ValueError("Gear ratios change sign between gears")
    a.review["stage1"].append("Output / input shaft ratio, gears 1-8: " + ", ".join(f"{k:.4f}" for k in s2_per_s1))
    a.control("input", -3000.0, 3000.0, "Main-shaft angle about +Z driving the gearbox (8T 0/85/124 on the 24T input gear)")
    a.control("shift", -2 * PI, 8 * PI, "Catch-1 (0/90/66) angle about +Z: k*pi/2 selects gear k+1; the shaft turns pi/2 per paddle stroke")
    a.control("paddle", -0.6, 0.6, "Paddle rocker angle about +Y at (140,-260); negative = paddle at x=180 pulled")
    a.control("phase_stage1", -6000.0, 6000.0, "Carry offset of the stage-1 output shafts, keyed at ratio changes")
    a.control("phase_stage2", -6000.0, 6000.0, "Carry offset of the output shaft group, keyed at ratio changes")
    inp, psi1 = a.clamped("input"), a.clamped("shift")
    # Catch 1: engagement window and ratio index.
    a.signal("p1", f"s/{num(PI / 2)}", s=psi1)
    a.signal("n1", "floor(p+0.5)", p="p1")
    a.signal("i1", "n-4*floor(n/4)", n="n1")
    a.signal("e1", "clamp(floor(1+(0.2-abs(p-n))/0.2),0,1)", p="p1", n="n1")
    a.signal("k1", "+".join(f"{num(k)}*max(0,1-abs(i-{j}))" for j, k in enumerate(rt["k1"])), i="i1")
    # Carry: the crank on knob shaft 0/90/92 turns catch 2 by pi/2 while catch 1 passes 3pi/2 -> 2pi (mod 2pi).
    a.signal("v1", f"s/{num(2 * PI)}", s=psi1)
    a.signal("c2", "floor(v)+clamp((v-floor(v)-0.75)*4,0,1)", v="v1")
    a.signal("psi2", f"{num(PI / 2)}*c", c="c2")
    a.signal("n2", "floor(c+0.5)", c="c2")
    a.signal("i2", "n-2*floor(n/2)", n="n2")
    a.signal("e2", "clamp(floor(1+(0.2-abs(c-n))/0.2),0,1)", c="c2", n="n2")
    a.signal("k2", f"(1-i)*{num(rt['k2_high'])}+i*{num(rt['k2_low'])}", i="i2")
    # Shafts.
    a.signal("s1", f"{num(rt['in'])}*m", m=inp)
    a.signal("s6", "e*k*s+p", e="e1", k="k1", s="s1", p="control:phase_stage1")
    a.signal("s4", f"{num(rt['s4_per_s6'])}*s", s="s6")
    a.signal("s2", "e*k*s+p", e="e2", k="k2", s="s4", p="control:phase_stage2")
    a.signal("s7", f"{num(rt['s7'])}*s", s="s1")
    a.signal("s9", f"s/{num(rt['s6_per_s9'])}", s="s6")
    a.signal("s8", f"{num(rt['s8_per_s9'])}*s", s="s9")
    a.signal("s3", f"{num(rt['s3_per_s2'])}*s", s="s2")
    a.signal("s5", f"{num(rt['s5_per_s2'])}*s", s="s2")
    a.body("main_interface", a.group("0/85/124"), a.at("0/85/124"), Z, inp)  # whole main shaft (driven context)
    for nm, seed, sig, extra, drop in (
        ("shaft_input", GB + "51", "s1", (), ()),
        ("shaft_s7", GB + "85", "s7", (), ()),
        ("shaft_stage1_out", GB + "33/22", "s6", ("R/S6_12T",), ()),
        ("shaft_s9", GB + "33/4", "s9", (), ()),
        ("shaft_s8", GB + "33/2", "s8", (), ()),
        ("shaft_stage2_in", GB + "7", "s4", (), ()),
        ("shaft_output", GB + "27", "s2", (), ("0/85/69", "0/85/70")),
        ("shaft_s3", GB + "13", "s3", (), ()),
        ("shaft_low", GB + "30", "s5", ("R/S5_12T",), ()),
    ):
        a.zbody(nm, seed, sig, extra, drop, view="stage1" if nm in ("shaft_input", "shaft_s7", "shaft_s9", "shaft_s8") else "stage2")
    # Free clutch gears and idlers ride their constant meshes (angle per driving shaft).
    free = [
        (GB + "84", f"s/{num(rt['g84_s6'])}", "s6"),
        (GB + "49", f"s/{num(rt['g49_s6'])}", "s6"),
        (GB + "33/13", f"s/{num(rt['g3313_s9'])}", "s9"),
        (GB + "75", f"s/{num(rt['g75_s9'])}", "s9"),
        (GB + "102", f"{num(rt['idler102'])}*s", "s1"),
        ("0/94", f"{num(rt['chain']['0/94'])}*s", "s6"),
        ("0/92", f"{num(rt['chain']['0/92'])}*s", "s6"),
        (GB + "148", f"{num(rt['chain'][GB + '148'])}*s", "s6"),
        (GB + "28", f"{num(rt['g28_s4'])}*s", "s4"),
        (GB + "89", f"{num(rt['g89_s4'])}*s", "s4"),
        (GB + "31", f"{num(rt['g31_s4'])}*s", "s4"),
        (GB + "90", f"{num(rt['g90_s4'])}*s", "s4"),
    ]
    for gid, expr, var in free:
        sname = "gear_" + gid.replace("/", "_")
        a.signal(sname, expr, s=var)
        a.body(sname, [gid], a.at(gid), Z, sname)
    # Clutch locks used by the kinematic check: (gear, shaft body seed) per state.
    a.locks = dict(c1={0: (GB + "84", GB + "51"), 1: (GB + "33/13", GB + "85"), 2: (GB + "49", GB + "51"), 3: (GB + "75", GB + "85")},
                   c2={0: (GB + "89", GB + "27"), 1: (GB + "90", GB + "30"), 2: (GB + "28", GB + "27"), 3: (GB + "31", GB + "30")})
    # Rotary catches and rings. Both catches have local Z = world -Z; the lobe of the rim (local 90 deg)
    # holds the ring it faces 10 LDU along local +Z (verified: source ring 0/90/57 sits 10 LDU towards 0/90/89).
    a.signal("cos1", "-cos(s)", s=psi1)
    a.signal("sin1", "sin(s)", s=psi1)
    a.signal("cos2", "-cos(s)", s="psi2")
    a.signal("sin2", "-sin(s)", s="psi2")
    a.signal("ring_r1_abs", f"{RING}*" + sat("u"), u="cos1")  # ring 0/90/54, faces catch-1 local 90 deg
    a.signal("ring_r2", f"{RING}*" + sat("u"), u="sin1")  # ring 0/90/55, local 180 deg
    a.signal("ring_r4_abs", f"{RING}*" + sat("u"), u="cos2")  # ring 0/90/57, catch-2 local 90 deg
    a.signal("ring_r3", f"{RING}*" + sat("u"), u="sin2")  # ring 0/90/56, local 0 deg
    a.signal("ring_r4", f"r+{RING}", r="ring_r4_abs")  # source ring 0/90/57 already sits at -10
    a.signal("push_r1", "max(0,r)", r="ring_r1_abs")  # extension 0/90/52 is pushed towards clutch 0/90/49 only
    for nm, ring, shaft, sig in (("ring_r1", GB + "54", "shaft_input", "ring_r1_abs"),
                                 ("ring_r2", GB + "55", "shaft_s7", "ring_r2"),
                                 ("ring_r3", GB + "56", "shaft_low", "ring_r3"),
                                 ("ring_r4", GB + "57", "shaft_output", "ring_r4")):
        if not a.on_line(ring, a.at(a.bodies[shaft]["instances"][0]), Z):
            raise ValueError(f"{ring} is not on {shaft}")
        a.body(nm, [ring], a.at(ring), Z, sig, kind="prismatic", parent=shaft)
    ext = GB + "52"
    if not a.on_line(ext, a.at(GB + "54"), Z) or dot(sub(a.at(ext), a.at(GB + "54")), Z) <= 0:
        raise ValueError("Extension 0/90/52 is not beside ring 0/90/54 towards clutch 0/90/49")
    a.body("ring_ext_r1", [ext], a.at(ext), Z, "push_r1", kind="prismatic", parent="shaft_input")
    # Catch shafts, knob wheels and the carry crank.
    a.zbody("catch1_shaft", GB + "118", psi1, extra=(GB + "66",), view="shifting")
    a.zbody("catch2_shaft", GB + "157", "psi2", extra=(GB + "62",), view="shifting")
    kd = sub(a.at(GB + "93"), a.at(GB + "118"))
    if abs(length(kd) - 40) > 0.6 or abs(dot(a.axis(GB + "93"), a.axis(GB + "118"))) < 0.999:
        raise ValueError("Knob wheels 0/90/93 and 0/90/118 are not parallel neighbours")
    a.edge("gear_mesh", GB + "118", GB + "93", "Parallel 4-knob wheels 40 LDU apart (connector frames)",
           "Reviewed 4-knob coupling, opposite rotation 1:1")
    a.meshes.append((GB + "118", Z, GB + "93", Z, -1.0))
    a.signal("crank", "-s", s=psi1)
    a.zbody("carry_crank", GB + "93", "crank", view="shifting")
    crank = sub(a.at(GB + "155"), a.at(GB + "93"))
    crank[2] = 0.0
    tow = math.degrees(math.atan2(crank[1], crank[0]))
    a.review["shifting"].append(
        f"Carry crank towball 0/90/155 at {length(crank):.1f} LDU, {tow:.0f} deg about the knob shaft; it faces catch 2 "
        "(180 deg) when catch 1 reaches 7pi/4: the carry is modelled over catch 1 = 3pi/2..2pi (mod 2pi)")
    # Front shift chain: catch-1 shaft -> knob 1/31 (Z) -> knobs 1/163, 1/162 (X) -> knob 1/193/22 (Y) -> ratchet.
    k_a, _ = a.bevel("1/31", 4, "1/163", 4, "shifting")
    a.signal("knob_x", f"{num(k_a)}*s", s=psi1)
    a.body("knob_shaft_x", a.group("1/162"), a.at("1/162"), X, "knob_x")
    k_b, _ = a.bevel("1/162", 4, "1/193/22", 4, "shifting")
    a.signal("ratchet", f"{num(k_b)}*s", s="knob_x")
    rollers = ["1/193/24", "1/193/25", "1/193/26", "1/193/27", "1/193/28", "1/193/29", "1/193/30", "1/193/31"]
    cr = a.at("1/193/23")
    for p in rollers:
        rad = length(cross(sub(a.at(p), cr), Y))
        if abs(rad - 14.142) > 0.2:
            raise ValueError(f"{p} is not a ratchet roller ({rad:.2f} LDU from the axis)")
    a.body("ratchet", a.group("1/193/23") + rollers, cr, Y, "ratchet")
    a.review["paddles"].append(f"Ratchet 1/193/23 turns {k_a * k_b:+.0f} x catch 1 about +Y (two 4-knob right angles)")
    # Paddle rocker and its two pawls (tip held on the roller circle while it drives; lifts off otherwise).
    pd = a.clamped("paddle")
    piv = g.one("1/193/18", "pin")
    if abs(abs(dot(piv["axis"], Y)) - 1) > 1e-6:
        raise ValueError("Paddle rocker pivot is not vertical")
    rocker = ["1/193/%d" % k for k in range(36, 51)]
    a.body("paddle_rocker", rocker, piv["pos"], Y, pd)
    centre = [cr[0], 0.0, cr[2]]
    sweeps = {}
    for side, pin, pawl, tip_hole, sign in (("l", "1/193/47", [f"1/193/{k}" for k in range(51, 56)], "1/193/54", -1),
                                            ("r", "1/193/48", [f"1/193/{k}" for k in range(56, 61)], "1/193/59", 1)):
        P0 = g.one(pin, "pin")["pos"]
        holes = [c["pos"] for c in g.conn(tip_hole, "axle_hole")]
        T0 = max(holes, key=lambda p: length(sub(p, a.at(pin))))  # far end of the 157.5 deg connector
        sweeps[side] = pawl_signals(a, side, pd, piv["pos"], P0, T0, centre, sign)
        a.body(f"pawl_{side}", pawl, P0, Y, f"pawl_{side}_rel", parent="paddle_rocker")
    a.review["paddles"].append(
        "Pawl tips ride the ratchet rollers (radius {:.2f} LDU about the ratchet axis) on the driving stroke only; "
        "full stroke 0.6 rad sweeps {:.1f} deg, the stepper detent completes the 90 deg step (assumed)".format(
            sweeps["l"]["rho"], sweeps["l"]["sweep_deg"]))
    a.paddle = dict(up=None)
    # Upshift = shift +pi/2. Ratchet turns k_a*k_b per catch-1 radian; the driving pawl's tip sweep sign
    # tells which paddle stroke turns the ratchet that way.
    want = math.copysign(1, k_a * k_b)
    for side, info in sweeps.items():
        if math.copysign(1, info["sweep_sign"]) == want:
            a.paddle = dict(up=side, up_stroke=info["stroke"])
    a.review["paddles"].append(f"Upshift stroke: paddle={a.paddle['up_stroke']:+.1f} (pawl {a.paddle['up']})")
    return dict(ratios=rt, s2_per_s1=s2_per_s1, views=[
        ("stage1", "Stage 1: four ratios on rings 0/90/54 / 0/90/55 (catch 1)",
         ("shaft_input", "shaft_s7", "shaft_stage1_out", "shaft_s9", "shaft_s8", "ring_r1", "ring_r2", "ring_ext",
          "gear_0_90_84", "gear_0_90_49", "gear_0_90_33_13", "gear_0_90_75", "gear_0_90_102"),
         ["control:shift", "body:shaft_input"], ["body:shaft_stage1_out"]),
        ("stage2", "Stage 2: high/low on rings 0/90/57 / 0/90/56 (catch 2) and the idler chain",
         ("shaft_stage2_in", "shaft_output", "shaft_s3", "shaft_low", "ring_r3", "ring_r4", "gear_0_94", "gear_0_92",
          "gear_0_90_148", "gear_0_90_28", "gear_0_90_89", "gear_0_90_31", "gear_0_90_90"),
         ["body:shaft_stage2_in"], ["body:shaft_output"]),
        ("shifting", "Rotary catches, knob wheels and the carry crank", ("catch1_shaft", "catch2_shaft", "carry_crank",
                                                                          "knob_shaft_x"),
         ["control:shift"], ["body:catch1_shaft", "body:catch2_shaft"]),
        ("paddles", "Paddle rocker, pawls and ratchet", ("paddle_rocker", "pawl_", "ratchet"),
         ["control:paddle", "control:shift"], ["body:ratchet"]),
        ("interfaces", "Main shaft (8T 0/85/124) driving the gearbox input (from the drivetrain extract)", ("main_interface",),
         ["control:input"], ["body:main_interface"]),
    ])


def pawl_signals(a, side, alpha, O, P0, T0, C, sign):
    """Pawl angle (relative to the rocker, about +Y) keeping its tip on the ratchet roller circle.

    In the xz plane a rotation t about +Y maps (x, z) -> (x cos t + z sin t, -x sin t + z cos t) and adds t to
    atan2(x, z). The tip circle around C is reachable only on the driving stroke; the other way the pawl lifts
    off and stays rigid with the rocker (stroke clamped at 0).
    """
    L = math.hypot(T0[0] - P0[0], T0[2] - P0[2])
    rho = math.hypot(T0[0] - C[0], T0[2] - C[2])
    dx, dz = P0[0] - O[0], P0[2] - O[2]

    def solve(t, sig):
        px, pz = O[0] + dx * math.cos(t) + dz * math.sin(t), O[2] - dx * math.sin(t) + dz * math.cos(t)
        ux, uz = C[0] - px, C[2] - pz
        d = math.hypot(ux, uz)
        aa = (L * L - rho * rho + d * d) / (2 * d)
        h2 = L * L - aa * aa
        if h2 < -1e-9:
            return None
        h = math.sqrt(max(h2, 0.0))
        ux, uz = ux / d, uz / d
        return px, pz, px + aa * ux + sig * h * uz, pz + aa * uz - sig * h * ux

    # Driving direction: the one where the circle stays reachable.
    stroke = -0.3 if solve(-0.3, 1) or solve(-0.3, -1) else 0.3
    if not (solve(stroke, 1) or solve(stroke, -1)):
        raise ValueError(f"Pawl {side}: tip circle unreachable on both strokes")
    branch = None
    for sig in (1, -1):
        s0 = solve(math.copysign(1e-4, stroke), sig)
        if s0:
            err = math.hypot(s0[2] - T0[0], s0[3] - T0[2])
            if err < 0.05 and (branch is None or err < branch[1]):
                branch = (sig, err)
    if branch is None:
        raise ValueError(f"Pawl {side}: rest tip not on the roller circle")
    sig = branch[0]
    full = 0.6 * math.copysign(1, stroke)
    s_full = solve(full, sig)
    th0 = math.atan2(T0[0] - C[0], T0[2] - C[2])
    sweep = math.degrees(math.atan2(s_full[2] - C[0], s_full[3] - C[2]) - th0)
    phi0 = math.atan2(T0[0] - P0[0], T0[2] - P0[2])
    p = f"pw{side}_"
    lim = "min(0,t)" if stroke < 0 else "max(0,t)"
    a.signal(p + "t", lim, t=alpha)
    a.signal(p + "px", f"{num(O[0])}+{num(dx)}*cos(t)+{num(dz)}*sin(t)", t=p + "t")
    a.signal(p + "pz", f"{num(O[2])}-{num(dx)}*sin(t)+{num(dz)}*cos(t)", t=p + "t")
    a.signal(p + "ux", f"{num(C[0])}-x", x=p + "px")  # Blender simple drivers reject **
    a.signal(p + "uz", f"{num(C[2])}-z", z=p + "pz")
    a.signal(p + "d", "sqrt(u*u+w*w)", u=p + "ux", w=p + "uz")
    a.signal(p + "a", f"({num(L * L - rho * rho)}+d*d)/(2*d)", d=p + "d")
    a.signal(p + "h", f"sqrt(max({num(L * L)}-a*a,0))", a=p + "a")
    a.signal(p + "tx", f"x+(a*({num(C[0])}-x)+{num(sig)}*h*({num(C[2])}-z))/d",
             x=p + "px", z=p + "pz", a=p + "a", h=p + "h", d=p + "d")
    a.signal(p + "tz", f"z+(a*({num(C[2])}-z)-{num(sig)}*h*({num(C[0])}-x))/d",
             x=p + "px", z=p + "pz", a=p + "a", h=p + "h", d=p + "d")
    a.signal(p + "phi", f"atan2(tx-x,tz-z)", tx=p + "tx", tz=p + "tz", x=p + "px", z=p + "pz")
    a.signal(f"pawl_{side}_rel", f"atan2(sin(f-{num(phi0)}-t),cos(f-{num(phi0)}-t))", f=p + "phi", t=p + "t")
    # Closure check anchors: tip stays rho from the ratchet axis (evaluated in tests through signals).
    a.review["paddles"].append(f"Pawl {side}: arm {L:.2f} LDU, tip radius {rho:.2f} LDU, drives on paddle {stroke:+.1f} side")
    return dict(L=L, rho=rho, stroke=full, sweep_deg=abs(sweep), sweep_sign=math.copysign(1, sweep))


# --------------------------------------------------------------------------- D/N/R selector
NOMINAL_GEAR = 3  # 1:1 internal path (rings 0/90/54 -> 0/90/49, 0/90/57 high); uses only source meshes


def build_dnr(a):
    g = a.g
    rt = dict(in_=a.spur("0/85/124", 8, GB + "51", 24, "interfaces"))
    # 3rd gear: S6 = (49->33/24) S1, S4 = chain S6, S2 = high S4 (measured again here, source meshes only).
    k49 = a.spur(GB + "49", 16, GB + "33/24", 16, "interfaces")
    chain = 1.0
    for x, y in [(GB + "146", "0/94"), ("0/94", "0/92"), ("0/92", GB + "148"), (GB + "148", GB + "147")]:
        chain *= a.spur(x, 16, y, 16, "interfaces")
    high = a.spur(GB + "7", 16, GB + "28", 16, "interfaces")
    g3 = rt["in_"] * k49 * chain * high  # gearbox output S2 per main shaft in 3rd
    a.review["interfaces"].append(f"Gearbox output held in gear {NOMINAL_GEAR}: output shaft = {g3:+.4f} x main shaft")
    a.control("input", -3000.0, 3000.0, "Main-shaft angle about +Z (16T 1/47 on the main shaft)")
    a.control("selector", -1.0, 1.0, "Console lever: +1 D (through the gearbox), 0 N, -1 R (direct 16:16 path)", "scalar")
    a.control("phase_ring_shaft", -6000.0, 6000.0, "Carry offset of the ring shaft and engine input, keyed at engagement changes")
    inp, sel = a.clamped("input"), a.clamped("selector")
    r57 = a.spur("1/47", 16, "1/57", 16, "selector")
    r63 = a.spur("1/64/31", 24, "1/63", 20, "selector", tol=2.0)
    a.review["selector"].append("1/63 20T and 1/64/31 24T sit on the 2x2 diagonal: 56.57 LDU against 55 nominal "
                                "(+1.57 LDU, loose); the only partner of 1/63, accepted as the designed mesh")
    r_e = a.spur("1/66", 24, "1/231/12", 8, "selector")
    a.signal("gb_out", f"{num(g3)}*m", m=inp)
    a.signal("g57", f"{num(r57)}*m", m=inp)
    a.signal("g63", f"{num(r63)}*o", o="gb_out")
    a.signal("fwd", "clamp(floor(2*d),0,1)", d=sel)
    a.signal("rev", "clamp(floor(-2*d),0,1)", d=sel)
    a.signal("ring_shaft", "f*a+r*b+p", f="fwd", r="rev", a="g63", b="g57", p="control:phase_ring_shaft")
    a.signal("engine_in", f"{num(r_e)}*s", s="ring_shaft")
    a.body("main_interface", a.group("0/85/124"), a.at("1/47"), Z, inp)  # whole main shaft (driven context)
    a.body("gearbox_output_interface", a.group(GB + "27", drop=("0/85/69", "0/85/70")), a.at("1/64/31"), Z, "gb_out")
    a.body("clutch_reverse", ["1/57"], a.at("1/57"), Z, "g57")
    a.body("clutch_drive", ["1/63"], a.at("1/63"), Z, "g63")
    a.body("ring_shaft", a.group("1/66", drop=("1/62",)), a.at("1/66"), Z, "ring_shaft")
    a.body("engine_input_shaft", a.group("1/231/12"), a.at("1/231/12"), Z, "engine_in")
    # Ring towards 1/63 (+Z) = D, towards 1/57 (-Z) = R.
    for gid, sgn in (("1/63", 1), ("1/57", -1)):
        if math.copysign(1, dot(sub(a.at(gid), a.at("1/62")), Z)) != sgn:
            raise ValueError("Unexpected clutch side of ring 1/62")
    a.signal("ring", f"{RING}*d", d=sel)
    a.body("ring", ["1/62"], a.at("1/62"), Z, "ring", kind="prismatic", parent="ring_shaft")
    catch = "1/150/39"
    pivot = [c for c in g.conn(catch, "axle_hole") if abs(abs(dot(c["axis"], X)) - 1) < 1e-6][0]["pos"]
    arm = sub(a.at("1/62"), pivot)
    if abs(length(arm) - 40) > 0.6:
        raise ValueError(f"Changeover fork is not 40 LDU from its pivot ({length(arm):.2f})")
    sgn = 1.0 if dot(cross(X, arm), Z) > 0 else -1.0
    a.signal("lever", f"{num(sgn)}*asin(clamp(d/{num(length(arm))},-1,1))", d="ring")
    a.body("lever", a.group(catch, rotating=False), pivot, X, "lever")
    a.review["selector"].append(f"Changeover catch {catch}: fork 40 LDU from its X pivot, lever 1/150/40 rises into the console")
    # Engine sign: D and R must turn the engine oppositely for the same road direction (true reverse).
    d_engine = r_e * r63 * g3
    r_engine = r_e * r57
    if d_engine * r_engine >= 0:
        raise ValueError("D and R turn the engine the same way: label states by path instead")
    a.review["selector"].append(f"Engine input per main-shaft radian: D {d_engine:+.4f} (gear {NOMINAL_GEAR}), R {r_engine:+.4f}: "
                                "opposite signs, so pushing the car backwards in R turns the engine forwards")
    a.locks = dict(D=("1/63", "1/66"), R=("1/57", "1/66"))
    a.dnr = dict(d_engine=d_engine, r_engine=r_engine, gb_out=g3)
    return dict(views=[
        ("selector", "D/N/R console lever, changeover catch and driving ring 1/62",
         ("ring_shaft", "ring", "lever", "clutch_"), ["control:selector", "control:input"], ["body:ring_shaft"]),
        ("interfaces", "Main shaft (16T 1/47), gearbox output shaft (24T 1/64/31) and engine-input shaft (driven context)",
         ("main_interface", "gearbox_output_interface", "engine_input_shaft"), ["control:input"], ["body:engine_input_shaft"]),
    ])


# --------------------------------------------------------------------------- doors and wing


def build_doors(a):
    g = a.g
    views = []
    for side, door, pin, x_sign, mirror in (("left", "450", "400", 1, ("536", "537", "538")),
                                           ("right", "443", "438", -1, ("548", "549", "547"))):
        # Side mirror: liftarm on the door's long sill pin, axle pin and fairing housing (moves with the door).
        axle = g.one(mirror[1], "axle")["pos"]
        if not any(length(sub(h["pos"], axle)) < 0.6 for h in g.conn(mirror[0], "axle_hole")) or not any(
                length(sub(h["pos"], axle)) < 12 for h in g.conn(mirror[2], "pin_hole")):
            raise ValueError(f"Mirror parts {mirror} are not stacked on axle pin {mirror[1]}")
        parts = sorted([i for i in a.src.parts() if i.startswith(door + "/")] + [pin, *mirror], key=key)
        hinge = g.one(pin, "pin")
        if abs(abs(dot(hinge["axis"], Y)) - 1) > 1e-6:
            raise ValueError(f"Door hinge {pin} is not vertical")
        # The rear edge must swing outwards (+X for the left door): w x r . X has the sign of x_sign.
        rear = [max((a.at(i) for i in parts), key=lambda p: p[2])][0]
        r = sub(rear, hinge["pos"])
        out = dot(cross(Y, r), X)
        sgn = 1.0 if out * x_sign > 0 else -1.0
        a.control(f"door_{side}", 0.0, DOOR_MAX, f"Open the {side} door (radians about its front-pillar hinge pin {pin})")
        v = a.clamped(f"door_{side}")
        a.signal(f"door_{side}_angle", f"{num(sgn)}*d", d=v)
        a.body(f"door_{side}", parts, hinge["pos"], Y, f"door_{side}_angle")
        a.edge("revolute", pin, {"left": "399", "right": "437"}[side], "Pin of 32054 in frame pin holes (contacts)",
               f"Reviewed vertical hinge of the {side} door; door parts are axle-locked to the pin")
        a.review[f"door_{side}"].append(f"Hinge pin {pin} at {r6(hinge['pos'])}, axis +Y; opening sign {sgn:+.0f}; "
                                        f"side mirror {'/'.join(mirror)} hangs on the door's long pin and swings with it")
        views.append((f"door_{side}", f"{side.capitalize()} door on its pillar hinge", (f"door_{side}",),
                      [f"control:door_{side}"], [f"body:door_{side}"]))
    return dict(views=views)


WING_BASE = ["107/%d" % k for k in range(10)] + ["107/13", "107/16"]  # H-beam base and the two L-U links (static)
WING_PANEL = ["107/21", "107/22", "107/23", "107/24", "107/25", "107/26", "107/43", "108", "109", "110", "148", "149",
              "150", "151", "152", "153", "154", "155", "156", "157", "158", "159", "160", "161"]


def yz_rot(v, t):
    """Rotate (y, z) about +X by t (adds t to atan2(z, y))."""
    return [v[0] * math.cos(t) - v[1] * math.sin(t), v[0] * math.sin(t) + v[1] * math.cos(t)]


def build_wing(a):
    g = a.g
    lower = g.one("107/11", "axle")
    if abs(abs(dot(lower["axis"], X)) - 1) > 1e-6:
        raise ValueError("Wing cross-axle is not along X")
    L = lower["pos"]
    U = g.one("107/14", "axle")["pos"]
    P1 = [c["pos"] for c in g.conn("107/12", "pin")][0]  # lower crank pin in strut 107/21
    P2 = [c["pos"] for c in g.conn("107/17", "pin")][0]  # upper crank pin in strut 107/21
    yz = lambda v: [v[1], v[2]]  # noqa: E731
    lp, up_, lu = sub(yz(P1), yz(L)), sub(yz(P2), yz(U)), sub(yz(U), yz(L))
    if any(abs(length(v) - 40) > 0.6 for v in (lp, up_, lu)) or length(sub(lp, up_)) > 0.3:
        raise ValueError("Wing struts are not the measured 40 LDU parallelogram")
    a.review["wing"].append(
        f"Parallelogram: lower axle L {r6(L)}, upper axle U {r6(U)}, crank pins 40 LDU along the 15 deg strut line "
        f"(difference {length(sub(lp, up_)):.2f} LDU); links 107/13/16 hold U 40 LDU from L.")
    a.control("wing", WING_RANGE[0], WING_RANGE[1],
              "Lower-crank angle about +X: positive lifts the struts and wing (parallel lift); manual, no drive in the model")
    th = a.clamped("wing")
    a.signal("wing_neg", "-t", t=th)
    lower_crank = a.group("107/11", extra=("107/12", "107/19"))
    a.body("wing_crank_lower", lower_crank, L, X, th)
    a.body("wing_crank_upper", a.group("107/14", extra=("107/17", "107/18"), rotating=False) if "107/14" in a.g.group_of
           else ["107/14", "107/15", "107/17", "107/18"], U, X, th)
    # Struts + wing: rotate theta with the lower crank, then -theta about the crank pin = pure translation.
    a.body("wing_lift", WING_PANEL, P1, X, "wing_neg", parent="wing_crank_lower")
    a.anchors["strut_upper_pin"] = dict(body="wing_lift", point=r6(P2))
    a.anchors["upper_axle"] = dict(body="wing_crank_upper", point=r6(U))
    a.checks.append(dict(kind="distance", name="upper_crank", a="strut_upper_pin", b="upper_axle",
                         length=round(length(sub(P2, U)), 6), tolerance=0.3))
    # Rear links: beam 3 (107/29, 107/37) pivots on L; beam 7 + beam 3 (107/27+107/33, 107/35+107/34) is a rod to the wing.
    for side, link, pin_s, rod, pin_q in (("l", "107/29", "107/28", ["107/27", "107/31", "107/32", "107/33"], "107/32"),
                                           ("r", "107/37", "107/36", ["107/35", "107/39", "107/40", "107/34"], "107/40")):
        holes = [c["pos"] for c in g.conn(link, "pin_hole")]
        S0 = max(holes, key=lambda p: length(sub(yz(p), yz(L))))
        if abs(length(sub(yz(S0), yz(L))) - 40) > 0.6 or not any(length(cross(sub(h, L), X)) < 0.6 for h in holes):
            raise ValueError(f"{link} is not a 40 LDU link on the lower axle")
        Q0 = g.one(pin_q, "pin")["pos"]
        r1, r2 = length(sub(yz(S0), yz(L))), length(sub(yz(Q0), yz(S0)))
        p = f"wl{side}_"
        dy, dz = P1[1] - L[1], P1[2] - L[2]
        a.signal(p + "qy", f"{num(Q0[1])}+{num(dy)}*(cos(t)-1)-{num(dz)}*sin(t)", t=th)
        a.signal(p + "qz", f"{num(Q0[2])}+{num(dy)}*sin(t)+{num(dz)}*(cos(t)-1)", t=th)
        a.signal(p + "dy", f"y-{num(L[1])}", y=p + "qy")
        a.signal(p + "dz", f"z-{num(L[2])}", z=p + "qz")
        a.signal(p + "d", "sqrt(y*y+z*z)", y=p + "dy", z=p + "dz")
        a.signal(p + "a", f"({num(r1 * r1 - r2 * r2)}+d*d)/(2*d)", d=p + "d")
        a.signal(p + "h", f"sqrt(max({num(r1 * r1)}-a*a,0))", a=p + "a")
        rest = None
        for sig in (1.0, -1.0):
            Dy, Dz = Q0[1] - L[1], Q0[2] - L[2]
            dd = math.hypot(Dy, Dz)
            aa = (r1 * r1 - r2 * r2 + dd * dd) / (2 * dd)
            hh = math.sqrt(max(r1 * r1 - aa * aa, 0))
            sy, sz = (aa * Dy - sig * hh * Dz) / dd, (aa * Dz + sig * hh * Dy) / dd
            err = math.hypot(sy - (S0[1] - L[1]), sz - (S0[2] - L[2]))
            if rest is None or err < rest[1]:
                rest = (sig, err)
        if rest[1] > 0.1:
            raise ValueError(f"Wing rear link {side}: rest pose not on the closure ({rest[1]:.3f})")
        sig = rest[0]
        a.signal(p + "sy", f"(a*y-{num(sig)}*h*z)/d", a=p + "a", h=p + "h", y=p + "dy", z=p + "dz", d=p + "d")
        a.signal(p + "sz", f"(a*z+{num(sig)}*h*y)/d", a=p + "a", h=p + "h", y=p + "dy", z=p + "dz", d=p + "d")
        phi0 = math.atan2(S0[2] - L[2], S0[1] - L[1])
        a.signal(p + "ang", f"atan2(sin(atan2(z,y)-{num(phi0)}),cos(atan2(z,y)-{num(phi0)}))", y=p + "sy", z=p + "sz")
        a.body(f"wing_link_{side}", [link, pin_s], L, X, p + "ang")
        a.anchors[f"wing_s_{side}"] = dict(body=f"wing_link_{side}", point=r6(S0))
        a.anchors[f"wing_q_{side}"] = dict(body="wing_lift", point=r6(Q0))
        xh = unit(sub(Q0, S0))
        a.body(f"wing_rod_{side}", rod, S0, X, kind="rod", start=f"wing_s_{side}", end=f"wing_q_{side}",
               x_hint=r6(unit(cross(xh, X))))
        a.checks.append(dict(kind="distance", name=f"wing_rod_{side}", a=f"wing_s_{side}", b=f"wing_q_{side}",
                             length=round(r2, 6), tolerance=0.05))
        a.review["wing"].append(f"Rear link {side}: {link} ({r1:.2f} LDU on L) and rod {'+'.join(rod)} ({r2:.2f} LDU) "
                                "close on the lifting wing by circle intersection")
    a.edge("revolute", "107/11", "26", "Axle through the perpendicular round pin hole of 15100 (no axle contact)",
           "Reviewed wing pivot: cross-axle turns in round bearings on both sides")
    a.review["wing"].append("Assumption: the upper axle 107/14 stays put (links 107/13/16 static), so the struts and wing "
                            "translate; the real set switches the active wing with the top-speed key (not installed here).")
    return dict(views=[("wing", "Rear wing parallel lift on its strut parallelogram", ("wing_",), ["control:wing"],
                        ["body:wing_lift"])])


BUILDERS = dict(drivetrain=build_drivetrain, gearbox=build_gearbox, dnr=build_dnr, doors=build_doors, wing=build_wing)


# --------------------------------------------------------------------------- selection
NEVER = re.compile(r"Gear|Differential|Rack|Driving Ring|Changeover|Panel|Fairing|Tile|Plate|Slope|Brick|Wheel|Tyre|"
                   r"Hose|Rope|String|Hook|Steering Wheel |Shock|Spring|Windscreen|Wedge|Mudguard", re.I)
CONNECTOR = re.compile(r"Pin|Axle|Bush|Cross Block|Angle Connector|Joiner|Connector", re.I)
MEMBER = re.compile(r"Beam|Liftarm", re.I)
STATIC_EXTRA = dict(
    drivetrain=["0/85/33/29", "0/85/34/29", "1/89/55/0", "1/89/56/0", "1/89/55/1", "1/89/55/2", "1/89/56/1", "1/89/56/2"],
    gearbox=[],
    dnr=[],
    doors=[],
    wing=WING_BASE + ["25", "26", "132", "141"],
)
ELASTIC = re.compile(r"rubberband", re.I)


def plan_parts(name, src):
    """Moving + interface parts of a subsystem (authored with a scratch Author)."""
    a = Author(src, name)
    BUILDERS[name](a)
    return sorted({i for b in a.bodies.values() for i in b["instances"]} - set(RECONSTRUCTED), key=key)


def select(name, src, depth=3, radius=70.0):
    moving = plan_parts(name, src)
    nodes = src.nodes
    static_seed = [i for i in STATIC_EXTRA[name] if i not in moving]
    if name == "gearbox":  # the rubber bands of the stepper and gearbox, as static context
        static_seed += [i for i, n in nodes.items() if n["kind"] == "part"
                        and any(ELASTIC.search(nodes[p]["ref"]) for p in ancestors(nodes, i))
                        and (i.startswith("1/193/") or i.startswith("0/"))]
    seeds = moving + static_seed
    pts = {i: src.g.at(i) for i in seeds}
    near = [i for i in src.parts() if i not in pts and not nodes[i].get("embedded")
            and not nodes[i]["ref"].lower().startswith("p/")
            and any(length(sub(src.g.at(i), p)) < radius for p in pts.values())]
    run = [i for i in seeds + near if not nodes[i].get("embedded")]
    if len(run) > 2000:
        raise ValueError(f"{name}: local contact selection too large ({len(run)})")
    ev = analysis.contacts(src.aliased, run, max_instances=2000)
    adj = defaultdict(set)
    for c in ev["contacts"]:
        adj[c["a"]].add(c["b"])
        adj[c["b"]].add(c["a"])
    g = src.g
    reasons = {i: ("moving", "plan body") for i in moving}
    for i in static_seed:
        reasons[i] = ("mount", "listed static context (bearing, knuckle, latch, base or band)")
    candidates = [i for i in near if i not in reasons]

    def joined(r, pool):
        local = [q for q in pool if length(sub(g.at(q), g.at(r))) < 120]
        out = adj[r] | seated(g, r, ("pin_hole", "axle_hole"), local, reach=60)
        out |= {q for q in local if r in seated(g, q, ("pin_hole", "axle_hole"), [r], reach=60)}
        return out

    for m in moving + static_seed:
        if nodes[m].get("embedded"):
            continue
        for q in joined(m, candidates):
            if q not in reasons and not NEVER.search(g.desc(q)):
                reasons[q] = ("mount", f"joined to {m} ({g.desc(m)})")
    frontier = [q for q, (role, _) in reasons.items() if role == "mount" and not nodes[q].get("embedded")]
    for level in range(1, depth + 1):
        nxt = []
        for r in frontier:
            if reasons[r][0] == "frame" and MEMBER.search(g.desc(r)):
                continue
            for q in sorted(joined(r, candidates) - set(reasons), key=key):
                d = g.desc(q)
                if NEVER.search(d):
                    continue
                if MEMBER.search(d) or CONNECTOR.search(d):
                    reasons[q] = ("frame", f"depth {level} from {r} ({g.desc(r)})")
                    nxt.append(q)
        frontier = nxt
    rows = [dict(id=i, role=role, reason=why, description=g.desc(i)) for i, (role, why) in
            sorted(reasons.items(), key=lambda kv: key(kv[0]))]
    return rows, ev, dict(rule=f"seeds + non-embedded parts within {radius} LDU; depth {depth} connector closure to the first beams",
                          tested=len(run))


def ancestors(nodes, i):
    out, cur = [], nodes[i]["parent"]
    while cur != "root":
        out.append(cur)
        cur = nodes[cur]["parent"]
    return out


# --------------------------------------------------------------------------- extraction (+ reconstruction)
def extract(name, src):
    d = out_dir(name)
    keep = json.loads((d / "keep.json").read_text())["parts"]
    target = d / "source" / f"42083-{name}.mpd"
    idmap, report = extract_subsystem.extract(SOURCE, [r["id"] for r in keep], target,
                                              name=f"42083-{name}.ldr",
                                              title=f"42083 Bugatti Chiron - {name} standalone extract",
                                              section=SECTION)
    added = {}
    if name == "gearbox":
        lines = target.read_text().splitlines()
        files = [k for k, ln in enumerate(lines) if ln.startswith("0 FILE ")]
        insert_at = files[1] - 1 if len(files) > 1 else len(lines)
        while insert_at > 0 and not lines[insert_at - 1].strip():
            insert_at -= 1
        new_lines = []
        for k, (pid, spec) in enumerate(RECONSTRUCTED.items()):
            like = src.nodes[spec["like"]]
            w = like["world"]
            c = spec["centre"]
            values = [*c, *w[0][:3], *w[1][:3], *w[2][:3]]
            new_lines += [f"0 // reconstructed {pid}: 12T double bevel (32270) absent from the source file; "
                          f"meshes {spec['partner']} on the {spec['shaft']}",
                          f"1 {like['effective_colour']} " + " ".join(extract_subsystem.number(v) for v in values)
                          + f" {like['ref']}"]
            added[pid] = str(len(idmap) + k)
        lines[insert_at:insert_at] = new_lines
        lines[1] = lines[1].replace(f"({len(idmap)} parts)", f"({len(idmap)} source parts + {len(added)} reconstructed gears)")
        target.write_text("\n".join(lines) + "\n")
        check = {n["id"]: n for n in Document(target).manifest()["nodes"]}
        for pid, new in added.items():
            n = check[new]
            if n["ref"] != "32270.dat" or max(abs(n["world"][k][3] - RECONSTRUCTED[pid]["centre"][k]) for k in range(3)) > 1e-9:
                raise ValueError(f"Reconstructed gear {pid} not found at {new}")
        report["reconstructed"] = {pid: dict(id=new, **RECONSTRUCTED[pid]) for pid, new in added.items()}
        report["output_sha256"] = sha256(target)
    (target.with_name("idmap.json")).write_text(json.dumps(dict(idmap=idmap, reconstructed=added, report=report), indent=1) + "\n")
    return dict(output=str(target), kept=len(idmap), reconstructed=added,
                max_world_matrix_error=report["max_world_matrix_error"])


# --------------------------------------------------------------------------- plan assembly
def build(name, src):
    a = Author(src, name)
    extra = BUILDERS[name](a)
    return a, extra


def remap_plan(name, a, extra, study, idmap, reconstructed, keep):
    m = dict(idmap, **reconstructed)
    nm = lambda i: m[i]  # noqa: E731
    out = copy.deepcopy(study)
    bodies = {}
    for bname, b in a.bodies.items():
        b = dict(b)
        b["instances"] = sorted((nm(i) for i in b["instances"]), key=key)
        bodies[bname] = b
    out.update(name=PLAN_NAMES[name], controls=a.controls, signals=a.signals, bodies=bodies, anchors=a.anchors,
               checks=a.checks, status="draft")
    connections = {k: v for k, v in out.get("connections", {}).items()}
    for cid, c in a.connections.items():
        if c["a"] in m and c["b"] in m:
            connections[cid] = dict(c, a=nm(c["a"]), b=nm(c["b"]))
    out["connections"] = connections
    owned = {i for b in bodies.values() for i in b["instances"]}
    views = {}
    for vkey, label, prefixes, inputs, outputs in extra["views"]:
        names = [b for b in bodies if b.startswith(prefixes)]
        views[vkey] = dict(label=label, parts=[], bodies=names, inputs=inputs, outputs=outputs,
                           notes=list(dict.fromkeys(a.review.get(vkey, []))), disposition="planned",
                           review="Measured motion declared in this plan; see notes and scripts/build_42083_mechanisms.py")
    covered = {b for v in views.values() for b in v["bodies"]}
    missing = set(bodies) - covered
    if missing:
        raise ValueError(f"Bodies outside every view: {sorted(missing)}")
    static = [nm(r["id"]) for r in keep if r["role"] != "moving"]
    leftover = sorted((set(study.get("discovery", {}).get("mechanical_parts", [])) | set(static)) - owned, key=key)
    views["mounting_frame"] = dict(
        label="Mounting frame and context (static)", parts=leftover, bodies=[], inputs=[], outputs=[],
        notes=[f"Parts: {len(leftover)}."], disposition="static",
        review="Static by decision: supports, bearings, latches and context parts selected around the moving "
               "mechanism (keep.json). The rest of the car is absent from this extract.")
    out["mechanisms"] = views
    out["notes"] = notes(name, a, extra)
    return out


def notes(name, a, extra):
    common = [
        "Source: data/models-annotated/42083-1.mpd (Philippe Hurbain [Philo], CCAL 2.0), section '42083 - chiron.ldr', "
        "unmodified. Standalone extract written by scripts/extract_subsystem.py --section in the same frame "
        "(LDU, -Y up, front -Z, car's left +X); motion authored on source IDs and remapped (source/idmap.json).",
        "Ratios, signs, pivots and link lengths are measured from library connector frames by "
        "scripts/build_42083_mechanisms.py; embedded DATs use their library part's frames for analysis only.",
        "Kinematic and transform checks do not prove collision-free or physically feasible motion.",
    ]
    specific = dict(
        drivetrain=["Interfaces (gearbox 24T input shaft, D/N/R 16T clutch gear 1/57) are driven context only.",
                    "Hubs turn at the half-shaft rate through the spindle drivers (CV assumption); exact Cardan at each diff.",
                    "Suspension and steering are static (not selected); front wheels stay straight."],
        gearbox=["RECONSTRUCTION: two 12T double-bevel gears (32270) absent from the source are added to this extract only: "
                 "on shaft 0/90/53 at (80,0,40) meshing 20T clutch 0/90/84, and on shaft 0/90/30 at (-80,-40,160) meshing "
                 "20T 0/90/13. Evidence: the official inventory lists 8 such gears, the file has 6; both 20T gears and shaft "
                 "0/90/30 otherwise have no partner; with them the measured trains give eight decreasing ratios.",
                 "Rotary-catch ring travel uses an assumed dwell profile (10 LDU x sat(cos/sin)); the lobe direction is "
                 "measured (source ring 0/90/57 at -10). The source leaves ring 0/90/54 centred although catch 1 holds it "
                 "at -10 in 1st gear; the rig shows the cam position.",
                 "The carry (catch 2 steps pi/2 once per catch-1 revolution) is timed from the crank geometry and "
                 "modelled as a linear transfer over the 4th->5th shift; the detent rocker 0/90/149 stays static.",
                 "Paddle pawls keep their tips on the ratchet roller circle while driving and lift off otherwise; the "
                 "detent completing each 90 deg step is assumed. Rubber bands are static context.",
                 "Gear ratios (output/input shaft): " + ", ".join(f"{k:.4f}" for k in extra.get("s2_per_s1", []))],
        dnr=[f"The gearbox is not in this extract: its output 24T 1/64/31 turns as in gear {NOMINAL_GEAR} (1:1 internal).",
             "1/63 (20T) to 1/64/31 (24T) is a loose 2x2 diagonal mesh (+1.57 LDU), accepted as designed.",
             "Ring travel 10 LDU, engaged for |selector| >= 0.5; the catch fork is measured 40 LDU from its pivot."],
        doors=["Doors swing on their measured front-pillar pins; each side mirror (liftarm, axle pin and fairing on the "
               "door's long pin) swings with its door. Opening limit chosen from a separate clearance-context study that "
               "adds the surrounding bodywork (clearance-context/clearance.json)."],
        wing=["Parallel-lift model: the lower cranks turn on the cross-axle, the upper axle 107/14 is held (assumption), so "
              "the strut parallelogram translates the wing straight up; the rear beam-7 links close by circle intersection.",
              "A rigid tilt about the lower axle was rejected: it crosses the rear fascia and end plates within 0.05-0.1 rad.",
              "The real set switches the active wing with the top-speed key, which is not installed in this file; nothing in "
              "the model drives the wing. Range chosen from the clearance-context study."],
    )
    return common + specific[name]


# --------------------------------------------------------------------------- kinematic verification
def part_angle(plan, result, part, axis, relative_to=None):
    """Rotation of a part's body about `axis` (0 for static parts), optionally in a carrier's frame."""
    def owner(p):
        return next((n for n, b in plan["bodies"].items() if p in b["instances"]), None)

    if owner(part) is None:
        return 0.0
    t = result["transforms"][owner(part)]
    if relative_to and owner(relative_to):
        c = result["transforms"][owner(relative_to)]
        rc = [[c[j][i] for j in range(3)] for i in range(3)]
        t = [[sum(rc[i][k] * t[k][j] for k in range(3)) for j in range(3)] for i in range(3)]
    a_ = unit(axis)
    v = unit(cross(a_, [1, 0, 0] if abs(a_[0]) < 0.9 else [0, 1, 0]))
    w = [sum(t[i][j] * v[j] for j in range(3)) for i in range(3)]
    return math.atan2(dot(cross(v, w), a_), dot(v, w))


def mesh_residual(plan, meshes, e0, e1, idmap, carriers=None):
    worst = 0.0
    carriers = carriers or {}
    for pa, axa, pb, axb, ratio in meshes:
        a_, b_ = idmap.get(pa), idmap.get(pb)
        if a_ is None or b_ is None:
            continue
        c = carriers.get(pb) or carriers.get(pa)
        rel = idmap[c] if c else None
        da = part_angle(plan, e1, a_, axa, rel) - part_angle(plan, e0, a_, axa, rel)
        db = part_angle(plan, e1, b_, axb, rel) - part_angle(plan, e0, b_, axb, rel)
        da = math.atan2(math.sin(da), math.cos(da))
        db = math.atan2(math.sin(db), math.cos(db))
        worst = max(worst, abs(db - ratio * da))
    return worst


def verify(name, plan, a, m):
    """Every reviewed mesh obeys its ratio and every engaged clutch is locked, in every state."""
    step = 0.01
    rows = []
    if name == "drivetrain":
        carriers = {"0/85/38": "0/85/35", "1/89/46/13": "1/89/46/10"}
        for base in (dict(drive=0.37), dict(drive=-2.9, diff_front=0.4, diff_rear=-0.25), dict(drive=7.3, diff_front=-1.1, diff_rear=0.9)):
            e0 = contract.evaluate(plan, base)
            e1 = contract.evaluate(plan, dict(base, drive=base["drive"] + step, diff_front=base.get("diff_front", 0) + 0.3 * step,
                                              diff_rear=base.get("diff_rear", 0) - 0.2 * step))
            res = mesh_residual(plan, a.meshes, e0, e1, m, carriers)
            sides = {k: e0["signals"][f"side_{k}"] for k in ("fl", "fr", "rl", "rr")}
            law = max(abs((sides[f"{x}l"] + sides[f"{x}r"]) / 2 - e0["signals"]["drive_v"]) for x in "fr")
            rows.append(dict(state=base, worst_mesh_error=res, diff_law_error=law))
            if res > 1e-9 or law > 1e-12:
                raise ValueError(f"Drivetrain check failed in {base}: mesh {res}, diff {law}")
    elif name == "gearbox":
        for c2 in range(4):
            for c1 in range(4):
                psi = (4 * c2 + c1) * PI / 2
                base = dict(shift=psi, input=0.7)
                e0 = contract.evaluate(plan, base)
                e1 = contract.evaluate(plan, dict(base, input=0.7 + step))
                if e0["signals"]["e1"] != 1 or e0["signals"]["e2"] != 1:
                    raise ValueError(f"Gearbox state {c2},{c1} not engaged")
                res = mesh_residual(plan, a.meshes, e0, e1, m)
                for gear, shaft in (a.locks["c1"][c1], a.locks["c2"][c2]):
                    dg = part_angle(plan, e1, m[gear], Z) - part_angle(plan, e0, m[gear], Z)
                    ds = part_angle(plan, e1, m[shaft], Z) - part_angle(plan, e0, m[shaft], Z)
                    if abs(dg - ds) > 1e-9 or abs(ds) < 1e-6:
                        raise ValueError(f"Clutch {gear} slips on {shaft} in state {c2},{c1}")
                d_in = e1["signals"]["s1"] - e0["signals"]["s1"]
                d_out = e1["signals"]["s2"] - e0["signals"]["s2"]
                ring = {k: round(e0["signals"][k], 6) for k in ("ring_r1_abs", "ring_r2", "ring_r3", "ring_r4_abs")}
                rows.append(dict(catch1=c1, catch2=c2, gear=(c2 % 2) * 4 + c1 + 1, output_per_input=d_out / d_in,
                                 rings=ring, worst_mesh_error=res))
                if res > 1e-9:
                    raise ValueError(f"Mesh violated in gearbox state {c2},{c1}: {res}")
                if sum(1 for v in ring.values() if abs(v) > 9.99) != 2:
                    raise ValueError(f"State {c2},{c1}: not exactly one ring per catch engaged: {ring}")
    elif name == "dnr":
        for sel in (-1.0, 0.0, 1.0):
            base = dict(selector=sel, input=0.4)
            e0 = contract.evaluate(plan, base)
            e1 = contract.evaluate(plan, dict(base, input=0.4 + step))
            res = mesh_residual(plan, a.meshes, e0, e1, m)
            de = (e1["signals"]["engine_in"] - e0["signals"]["engine_in"]) / step
            if sel:
                gear, shaft = a.locks["D" if sel > 0 else "R"]
                dg = part_angle(plan, e1, m[gear], Z) - part_angle(plan, e0, m[gear], Z)
                ds = part_angle(plan, e1, m[shaft], Z) - part_angle(plan, e0, m[shaft], Z)
                if abs(dg - ds) > 1e-9:
                    raise ValueError(f"Clutch {gear} slips in state {sel}")
            elif abs(de) > 1e-12:
                raise ValueError("Neutral still drives the engine")
            rows.append(dict(selector=sel, engine_per_main=de, worst_mesh_error=res))
            if res > 1e-9:
                raise ValueError(f"Mesh violated in D/N/R state {sel}: {res}")
    return rows


# --------------------------------------------------------------------------- clearance context (doors, wing)
CONTEXT = dict(
    # Bodywork around the swept volume, as static obstacles for choosing the opening limits.
    doors=dict(box=lambda p: abs(p[0]) >= 150 and -620 <= p[2] <= 40 and -330 <= p[1] <= 60,
               wide={"door_left": (0.0, 1.7), "door_right": (0.0, 1.7)}),
    wing=dict(box=lambda p: abs(p[0]) <= 300 and 250 <= p[2] <= 640 and -340 <= p[1] <= 0,
              wide={"wing": (-0.4, 1.8)}),
)


def context_keep(name, src):
    moving = set(plan_parts(name, src))
    keep = json.loads((out_dir(name) / "keep.json").read_text())["parts"]
    ids = {r["id"] for r in keep}
    box = CONTEXT[name]["box"]
    extra = [i for i in src.parts() if i not in ids and not src.nodes[i]["ref"].lower().startswith("p/")
             and box(src.g.at(i))]
    rows = keep + [dict(id=i, role="context", reason="bodywork near the swept volume (clearance study only)",
                        description=src.g.desc(i)) for i in sorted(extra, key=key)]
    return rows, len(moving)


def context_plan(name, a, extra, study, idmap, keep):
    plan = remap_plan(name, a, extra, study, idmap, {}, keep)
    for ctrl, (lo, hi) in CONTEXT[name]["wide"].items():
        plan["controls"][ctrl].update(min=lo, max=hi)
        plan["signals"][ctrl + "_v"]["expression"] = f"clamp(v,{lo!r},{hi!r})"
    plan["name"] = PLAN_NAMES[name] + "_ctx"
    plan["status"] = "ready"  # declared study motion; widened range is the point of the study
    plan["notes"].append("Clearance-context study only: widened range and surrounding bodywork as obstacles.")
    return plan


# --------------------------------------------------------------------------- CLI
def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub_ = ap.add_subparsers(dest="command", required=True)
    for cmd in ("select", "extract", "plan", "context", "context-plan"):
        p = sub_.add_parser(cmd)
        p.add_argument("name", choices=NAMES)
        if cmd == "plan":
            p.add_argument("--ready", action="store_true")
    args = ap.parse_args()
    src = Source()
    d = out_dir(args.name)
    if args.command == "select":
        rows, ev, rule = select(args.name, src)
        d.mkdir(parents=True, exist_ok=True)
        contract.save(d / "evidence-contacts.json", dict(ev, selection_rule=rule["rule"]))
        counts = {r: sum(1 for x in rows if x["role"] == r) for r in ("moving", "mount", "frame")}
        contract.save(d / "keep.json", dict(parts=rows, counts=counts, source=str(SOURCE.relative_to(ROOT)),
                                            section=SECTION, rule=rule))
        print(json.dumps(dict(keep=str(d / "keep.json"), **counts, contact_parts=rule["tested"])))
        return
    if args.command == "extract":
        print(json.dumps(extract(args.name, src)))
        return
    if args.command in ("context", "context-plan"):
        if args.name not in CONTEXT:
            raise ValueError("Clearance context exists for doors and wing only")
        cd = d / "clearance-context"
        if args.command == "context":
            rows, moving = context_keep(args.name, src)
            contract.save(cd / "keep.json", dict(parts=rows, moving=moving))
            target = cd / "source" / f"42083-{args.name}-context.mpd"
            idmap, report = extract_subsystem.extract(SOURCE, [r["id"] for r in rows], target,
                                                      name=f"42083-{args.name}-context.ldr", section=SECTION,
                                                      title=f"42083 Bugatti Chiron - {args.name} clearance context")
            target.with_name("idmap.json").write_text(json.dumps(dict(idmap=idmap, report=report), indent=1) + "\n")
            print(json.dumps(dict(output=str(target), kept=len(idmap))))
            return
        a, extra = build(args.name, src)
        study = contract.load(cd / "study/plan.json")
        idmap = json.loads((cd / "source/idmap.json").read_text())["idmap"]
        keep = json.loads((cd / "keep.json").read_text())["parts"]
        plan = context_plan(args.name, a, extra, study, idmap, keep)
        contract.validate(plan)
        contract.save(cd / "plan.json", plan)
        print(json.dumps(dict(plan=str(cd / "plan.json"), parts=sum(1 for n in plan["source"]["nodes"] if n["kind"] == "part"))))
        return
    a, extra = build(args.name, src)
    study = contract.load(d / "study/plan.json")
    idmap_doc = json.loads((d / "source/idmap.json").read_text())
    keep = json.loads((d / "keep.json").read_text())["parts"]
    plan = remap_plan(args.name, a, extra, study, idmap_doc["idmap"], idmap_doc.get("reconstructed", {}), keep)
    m = dict(idmap_doc["idmap"], **idmap_doc.get("reconstructed", {}))
    contract.validate(plan)
    rows = verify(args.name, plan, a, m)
    up = getattr(a, "paddle", {}).get("up_stroke", -0.6)
    tl = timeline(args.name, plan, paddle_up_stroke=up)
    cont = continuity(plan, tl)
    if not cont["passed"]:
        raise ValueError(f"Timeline continuity failed: {cont['violations']}")
    if args.ready:
        plan["status"] = "ready"
    contract.validate(plan)
    contract.save(d / "plan.json", plan)
    report = dict(states=rows, meshes=len(a.meshes), review={k: v for k, v in a.review.items()},
                  continuity=cont, paddle=getattr(a, "paddle", None), dnr=getattr(a, "dnr", None),
                  gear_ratios=extra.get("s2_per_s1"))
    contract.save(d / "kinematics.json", report)
    print(json.dumps(dict(plan=str(d / "plan.json"), status=plan["status"], bodies=len(plan["bodies"]),
                          moving=sum(len(b["instances"]) for b in plan["bodies"].values()),
                          signals=len(plan["signals"]), meshes=len(a.meshes), states=len(rows),
                          views={k: v["disposition"] for k, v in plan["mechanisms"].items()})))


if __name__ == "__main__":
    main()
