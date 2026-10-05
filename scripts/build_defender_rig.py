#!/usr/bin/env python3
"""Author the motion plan for 42110-1 (Land Rover Defender) from a prepared study.

    scripts/build_defender_rig.py --study output/42110/study/plan.json \
        --evidence output/42110/evidence/contacts-mechanical.json \
        --output output/42110/plan.json --bodywork output/42110/bodywork.json --ready

Inputs are the unmodified source manifest embedded in the study, bounded pyldraw3
contact evidence (axle-in-axle-hole contacts define rotationally locked groups)
and library connector frames. Embedded DAT parts (pre-release copies such as
`42110 - 18575.dat`) get the frames of their library alias for this analysis
only; their geometry is not replaced. Every gear ratio, sign, pivot and link
length below is computed from those frames and asserted, never typed in.

Frame: selected root (42110 - main.ldr), LDU, -Y up, front is -Z, the car's
left is +X (the steering wheel sits at +X). The chassis is placed with a
0.003 rad tilt about X, so "Z" shafts use the measured chassis axis ZC.
Angles are radians, right-hand rule about each body's axis.
"""

import argparse
import copy
from collections import defaultdict
import json
import math
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ldraw_mechanisms import linkages, plan as contract  # noqa: E402
from ldraw_mechanisms.analysis import jsonable  # noqa: E402
from ldraw_mechanisms.math3d import (  # noqa: E402
    add,
    cross,
    direction,
    dot,
    length,
    mul,
    point,
    rack_ratio,
    signed_gear_ratio,
    sub,
    unit,
)
from ldraw_mechanisms.placements import analysis_placement  # noqa: E402
from ldraw_mechanisms.source import parts_library  # noqa: E402

X = [1.0, 0.0, 0.0]
GEAR_RING = 10.0  # driving-ring travel (LDU): the source 1st-gear ring sits 10 LDU off centre
PI = math.pi


def r6(v):
    return [round(x, 6) for x in v]


class Geometry:
    """World frames, library connector frames and axle-locked groups."""

    def __init__(self, manifest, evidence):
        self.nodes = {n["id"]: n for n in manifest["nodes"]}
        self.lib = parts_library()
        self._conn = {}
        adj = defaultdict(set)
        for c in evidence["contacts"]:
            if {c["first"]["kind"], c["second"]["kind"]} == {"axle", "axle_hole"}:
                adj[c["a"]].add(c["b"])
                adj[c["b"]].add(c["a"])
        self.group_of = {}
        for start in sorted(adj):
            if start in self.group_of:
                continue
            stack, comp = [start], {start}
            while stack:
                for y in adj[stack.pop()]:
                    if y not in comp:
                        comp.add(y)
                        stack.append(y)
            frozen = frozenset(comp)
            for i in comp:
                self.group_of[i] = frozen

    def world(self, i):
        return analysis_placement(self.nodes[i])[0]

    def at(self, i, p=(0, 0, 0)):
        return point(self.world(i), list(p))

    def conn(self, i, kind=None):
        if i not in self._conn:
            n = self.nodes[i]
            ref = n.get("library_alias") or n["ref"]
            meta = self.lib.connection_metadata(ref.removesuffix(".dat"))
            w = self.world(i)
            out = []
            for f in meta.features:
                item = jsonable(f)
                out.append(
                    dict(
                        kind=item["kind"],
                        pos=point(w, item["position"]),
                        axis=unit(direction(w, [row[1] for row in item["frame"]])),
                    )
                )
            self._conn[i] = out
        return [c for c in self._conn[i] if kind is None or c["kind"] == kind]

    def one(self, i, kind):
        hits = self.conn(i, kind)
        if not hits:
            raise ValueError(f"{i} has no {kind} connector")
        return hits[0]

    def group(self, seed, extra=(), drop=()):
        """Axle-locked group containing `seed`, plus reviewed extra members."""
        if seed not in self.group_of:
            raise ValueError(f"{seed} has no axle-locked contact group")
        members = (set(self.group_of[seed]) | set(extra)) - set(drop)
        return sorted(members, key=lambda s: [int(x) for x in s.split("/")])

    def on_line(self, i, p, axis, tol=0.6):
        d = sub(self.at(i), p)
        return length(cross(d, unit(axis))) < tol

    def desc(self, i):
        return self.nodes[i]["description"]


def build(study, evidence, steer_rack_limit=18.0):
    plan = copy.deepcopy(study)
    g = Geometry(plan["source"], evidence)
    at, conn = g.at, g.conn
    controls, signals, bodies, anchors, checks = {}, {}, {}, {}, []
    connections = plan["connections"]
    review = defaultdict(list)  # view -> evidence notes
    meshes = []  # (part_a, axis_a, part_b, axis_b, ratio): w_b = ratio * w_a about the axes

    # The chassis Z axis (all longitudinal shafts) from the camshaft axle connector.
    ZC = unit(g.one("0/0/127/0", "axle")["axis"])
    if dot(ZC, [0, 0, 1]) < 0:
        ZC = mul(ZC, -1)
    if abs(dot(ZC, X)) > 1e-9 or abs(ZC[1] - 0.003) > 1e-4:
        raise ValueError(f"Unexpected chassis axis {ZC}")
    UP = unit(cross(X, ZC))  # -Y with the chassis tilt
    if dot(UP, [0, -1, 0]) < 0.999:
        raise ValueError("Up axis is not -Y")

    def control(name, lo, hi, description, unit_name="radian", default=0.0):
        controls[name] = dict(default=default, min=lo, max=hi, unit=unit_name, description=description)
        return "control:" + name

    def signal(name, expr, **variables):
        if len(expr) > 255:
            raise ValueError(f"{name}: expression too long")
        signals[name] = dict(
            expression=expr,
            variables={k: v if ":" in v else "signal:" + v for k, v in variables.items()},
        )
        return name

    def body(name, instances, origin, axis, sig=None, kind="revolute", parent=None, **extra):
        owned = {i for b in bodies.values() for i in b["instances"]}
        clash = owned & set(instances)
        if clash:
            raise ValueError(f"{name}: parts already owned {sorted(clash)}")
        b = dict(instances=list(instances), kind=kind, origin=r6(origin), axis=r6(unit(axis)), **extra)
        if sig:
            b["signal"] = sig
        if parent:
            b["parent"] = parent
        bodies[name] = b
        return name

    def edge(kind, a, b, evidence_text, note, measurements=None):
        key = f"r_{kind}_{a}_{b}".replace("/", "_")
        existing = [k for k, c in connections.items() if {c["a"], c["b"]} == {a, b} and c["kind"] == kind]
        key = existing[0] if existing else key
        entry = dict(a=a, b=b, kind=kind, status="reviewed", evidence=evidence_text, review=note)
        if measurements:
            entry["measurements"] = measurements
        connections[key] = entry

    def num(v):
        return repr(float(v))

    # ------------------------------------------------------------------ gears
    def gear_axis(i):
        """Shaft axis of a gear from its axle/pin hole connector, oriented like ZC/X/UP."""
        holes = conn(i, "axle_hole") or conn(i, "pin_hole") or conn(i, "axle")
        a = holes[0]["axis"]
        for ref in (ZC, X, UP):
            if abs(dot(a, ref)) > 0.99:
                return ref
        return unit(a)

    def spur(a, ta, b, tb, a_centre=None, b_centre=None, view="drivetrain", tol=0.6):
        """Signed ratio (b per a) for a parallel external mesh, both about the shared axis."""
        pa, pb = a_centre or at(a), b_centre or at(b)
        axis = gear_axis(a) if a_centre is None else gear_axis(b)
        d = sub(pb, pa)
        axial = dot(d, axis)
        radial = length(sub(d, mul(axis, axial)))
        nominal = 1.25 * (ta + tb)
        if abs(axial) > 2.0 or abs(radial - nominal) > tol:
            raise ValueError(f"{a}-{b}: not a coplanar {ta}/{tb} mesh ({radial:.2f} vs {nominal}, axial {axial:.2f})")
        ratio = signed_gear_ratio(axis, pa, ta, axis, pb, tb)
        meshes.append((a, axis, b, axis, ratio))
        edge(
            "gear_mesh",
            a,
            b,
            "Coplanar parallel axes measured from connector frames; centre distance against 1.25 LDU/tooth pitch radii",
            f"Reviewed {ta}T/{tb}T external mesh, ratio {ratio:+.4f} about the shared axis",
            dict(centre_distance_ldu=round(radial, 3), nominal_ldu=nominal, axial_offset_ldu=round(axial, 3)),
        )
        review[view].append(f"{a} {ta}T / {b} {tb}T: {radial:.2f} LDU (nominal {nominal})")
        return ratio

    def bevel_mesh(a, ta, pa, axis_a, b, tb, pb, axis_b, view):
        # Apex: closest point between the perpendicular axis lines through each centre.
        if abs(dot(axis_a, axis_b)) > 1e-3:
            raise ValueError(f"{a}-{b}: bevel axes not perpendicular")
        w = sub(pa, pb)
        bdot, dd, ee = dot(axis_a, axis_b), dot(axis_a, w), dot(axis_b, w)
        s = (bdot * ee - dd) / (1 - bdot * bdot)
        t = (ee - bdot * dd) / (1 - bdot * bdot)
        qa, qb = add(pa, mul(axis_a, s)), add(pb, mul(axis_b, t))
        if length(sub(qa, qb)) > 0.6:
            raise ValueError(f"{a}-{b}: bevel axes do not intersect ({length(sub(qa, qb)):.2f})")
        apex = mul(add(qa, qb), 0.5)
        out_a, out_b = unit(sub(pa, apex)), unit(sub(pb, apex))
        if abs(abs(dot(out_a, axis_a)) - 1) > 1e-3 or abs(abs(dot(out_b, axis_b)) - 1) > 1e-3:
            raise ValueError(f"{a}-{b}: bevel centre not on its axis")
        ratio = -ta / tb  # w_b about out_b per w_a about out_a (pitch-point velocities)
        meshes.append((a, out_a, b, out_b, ratio))
        ha, hb = length(sub(pa, apex)), length(sub(pb, apex))
        edge(
            "gear_mesh",
            a,
            b,
            "Perpendicular axes intersecting at a common apex (closest approach measured); outward axes from the apex",
            f"Reviewed {ta}T/{tb}T bevel mesh, w_b = {ratio:+.4f} w_a about the outward axes",
            dict(apex=r6(apex), a_from_apex_ldu=round(ha, 3), b_from_apex_ldu=round(hb, 3)),
        )
        review[view].append(f"{a} {ta}T / {b} {tb}T bevel: apex offsets {ha:.1f}/{hb:.1f} LDU")
        return out_a, out_b, ratio

    def bevel_ratio(a, ta, axis_a, b, tb, axis_b, view, a_centre=None, b_centre=None):
        """Signed ratio of b (about axis_b) per a (about axis_a) for a perpendicular bevel mesh."""
        oa, ob, ratio = bevel_mesh(a, ta, a_centre or at(a), axis_a, b, tb, b_centre or at(b), axis_b, view)
        return dot(axis_b, ob) * ratio * dot(axis_a, oa)

    # ---------------------------------------------------------------- controls
    control("drive", -2000.0, 2000.0, "Road-wheel roll angle (axle side-gear angle) about +X; positive drives forward")
    control("diff_front", -200.0, 200.0, "Front differential split: left side gear +, right side gear - (half difference)")
    control("diff_rear", -200.0, 200.0, "Rear differential split: left side gear +, right side gear - (half difference)")
    control("diff_center", -200.0, 200.0, "Centre differential split: front axle +, rear axle - (half difference)")
    control(
        "gear_select",
        -0.5,
        2 * PI,
        "Rotary catch angle of the sequential 4-speed; 0, pi/2, pi, 3pi/2 select gears 1-4 (cyclic). The cab dial turns the other way",
    )
    control("range_select", -1.0, 1.0, "Range lever: -1 low, +1 high (driving ring 0/0/128/62 travel)", "scalar")
    control(
        "direction_select",
        -1.0,
        1.0,
        "Direction lever: +1 forward through the 4-speed, -1 reverse (driving ring 0/0/128/61 travel)",
        "scalar",
    )
    for name, what in (
        ("phase_engine", "engine-side gear train (engine, camshaft, 4-speed input)"),
        ("phase_mid", "4-speed output, rear propshaft and range gears"),
        ("phase_c26", "range output shaft 0/0/128/58"),
    ):
        control(
            name,
            -4000.0,
            4000.0,
            f"Carry offset of the {what}; keyed at ratio changes so angles stay continuous",
        )
    control("winch", -400.0, 400.0, "Winch knob angle (12T knob 0/69 about its vertical axle)")

    def clamped(name):
        c = controls[name]
        return signal(name + "_v", f"clamp(v,{c['min']!r},{c['max']!r})", v="control:" + name)

    drive, dfr, drr, dce = (clamped(n) for n in ("drive", "diff_front", "diff_rear", "diff_center"))
    signal("m_front", "d+c", d=drive, c=dce)
    signal("m_rear", "d-c", d=drive, c=dce)
    signal("side_fl", "m+s", m="m_front", s=dfr)
    signal("side_fr", "m-s", m="m_front", s=dfr)
    signal("side_rl", "m+s", m="m_rear", s=drr)
    signal("side_rr", "m-s", m="m_rear", s=drr)

    # ------------------------------------------------------------ axle drives
    axle_bodies = {}
    for axle, diff_id, spider_id, pinion_id, sides in (
        (
            "front",
            "0/0/27/11",
            "0/0/27/14",
            "0/0/27/8",
            dict(l=("0/0/27/13", "0/0/27/18", "0/0/27/20", "0/0/27/19", "0/0/59"), r=("0/0/27/12", "0/0/27/15", "0/0/27/17", "0/0/27/16", "0/0/64")),
        ),
        (
            "rear",
            "0/1/12",
            "0/1/15",
            "0/1/6",
            dict(l=("0/1/14", "0/1/17", "0/1/18", "0/1/16", "0/1/93"), r=("0/1/13", "0/1/19", "0/1/21", "0/1/20", "0/1/100")),
        ),
    ):
        view = f"{axle}_axle"
        centre = at(diff_id)
        carrier_axis = g.one(diff_id, "pin_hole")["axis"]
        if abs(abs(dot(carrier_axis, X)) - 1) > 1e-6:
            raise ValueError(f"{diff_id}: differential axis is not X")
        mean = "m_" + axle
        body(f"{axle}_diff", [diff_id], centre, X, mean)
        # Spider: relative to the carrier, from the left side gear mesh (12T:12T).
        side_l = sides["l"][0]
        bar = g.one(diff_id, "bar")
        o_l, o_sp, ratio = bevel_mesh(side_l, 12, at(side_l), X, spider_id, 12, at(spider_id), unit(bar["axis"]), view)
        o_r, o_sp2, _ = bevel_mesh(sides["r"][0], 12, at(sides["r"][0]), X, spider_id, 12, at(spider_id), unit(bar["axis"]), view)
        if dot(o_sp, o_sp2) < 0.999 or dot(o_l, o_r) > -0.999:
            raise ValueError(f"{axle} differential side gears are not opposed")
        split = {"front": dfr, "rear": drr}[axle]
        # side_l - mean = +split about X; spider about o_sp = ratio * (o_l . X) * split
        signal(f"{axle}_spider", f"{num(ratio * dot(o_l, X))}*s", s=split)
        body(f"{axle}_spider", [spider_id], at(spider_id), o_sp, f"{axle}_spider", parent=f"{axle}_diff")
        # Ring 28T (part-local z=+26) and the 20T double-bevel pinion.
        ring_c = g.at(diff_id, (0, 0, 26))
        pinion_axis = gear_axis(pinion_id)
        k = bevel_ratio(diff_id, 28, X, pinion_id, 20, pinion_axis, view, a_centre=ring_c)
        axle_bodies[axle] = dict(pinion_per_mean=k * dot(pinion_axis, ZC))
        for side, (gear_id, end_in, cross_id, end_out, driver) in sides.items():
            # Side gear group (gear, UJ input end, stub axle).
            grp = g.group(gear_id)
            if end_in not in grp:
                raise ValueError(f"{end_in} not locked to side gear {gear_id}")
            sig = f"side_{axle[0]}{side}"
            body(f"{axle}_side_{side}", grp, at(gear_id), X, sig)
            # Universal joint: input along the side shaft towards the joint, output to the CV.
            jc = at(cross_id)
            d_in = unit(sub(jc, centre))
            d_in = mul(X, 1 if dot(d_in, X) > 0 else -1)
            d_out = unit(sub(g.one(driver, "generic")["pos"], jc))
            f_in, f_out = g.one(end_in, "clip")["axis"], g.one(end_out, "clip")["axis"]
            theta = signal(f"{axle}_{side}_ujin", f"{num(dot(d_in, X))}*s", s=sig)
            out, crs = linkages.universal_joint(signals, f"uj_{axle[0]}{side}", theta, d_in, d_out, f_in, f_out)
            body(f"{axle}_cross_{side}", [cross_id], jc, f_in, crs, parent=f"{axle}_side_{side}")
            shaft = g.group(end_out)
            if driver not in shaft:
                raise ValueError(f"{driver} not on the {axle} {side} half shaft")
            body(f"{axle}_halfshaft_{side}", shaft, jc, d_out, out)
            review[view].append(
                f"{side} half shaft bend {math.degrees(math.acos(dot(d_in, d_out))):.1f} deg; exact cardan at the diff, CV at the hub"
            )
            axle_bodies[axle][side] = dict(halfshaft=out, d_out=d_out)
        review[view].append(f"28T ring / 20T pinion: pinion = {k:+.4f} x carrier")

    # ---------------------------------------------------- propshafts to centre
    prop_f = g.group("0/9", extra=["0/0/27/8"])
    prop_r = g.group("0/1/7", extra=["0/1/6"])
    for need, grp in (("0/0/27/7", prop_f), ("0/1/5", prop_r)):
        if need not in grp:
            raise ValueError(f"{need} missing from its propshaft group")
    for emb, host in (("0/0/27/8", "0/0/27/7"), ("0/1/6", "0/1/5")):
        if not g.on_line(emb, g.one(host, "axle")["pos"], ZC):
            raise ValueError(f"Embedded pinion {emb} is not on axle {host}")
    signal("prop_front", f"{num(axle_bodies['front']['pinion_per_mean'])}*m", m="m_front")
    signal("prop_rear", f"{num(axle_bodies['rear']['pinion_per_mean'])}*m", m="m_rear")
    body("prop_front", prop_f, at("0/9"), ZC, "prop_front")
    body("prop_rear", prop_r, at("0/1/7"), ZC, "prop_rear")
    r_f = spur("0/9", 8, "0/1/193", 24, view="centre_diff")
    r_r = spur("0/1/7", 8, "0/1/133/56", 24, view="centre_diff")
    cd_f = g.group("0/1/193")
    cd_r = g.group("0/1/133/56")
    if "0/1/157" not in cd_f or "0/1/158" not in cd_r:
        raise ValueError("Centre differential side gears not on their output shafts")
    signal("cdiff_front", f"{num(r_f)}*p", p="prop_front")
    signal("cdiff_rear", f"{num(r_r)}*p", p="prop_rear")
    body("cdiff_front_shaft", cd_f, at("0/1/157"), ZC, "cdiff_front")
    body("cdiff_rear_shaft", cd_r, at("0/1/158"), ZC, "cdiff_rear")
    # Straight running must leave the centre spider still: equal side-gear angles.
    if abs(r_f * axle_bodies["front"]["pinion_per_mean"] - r_r * axle_bodies["rear"]["pinion_per_mean"]) > 1e-9:
        raise ValueError("Front and rear drives disagree for straight running")
    cdiff = "0/1/155"
    if abs(abs(dot(g.one(cdiff, "pin_hole")["axis"], ZC)) - 1) > 1e-6:
        raise ValueError("Centre differential axis is not the chassis Z axis")
    signal("cdiff_carrier", "(a+b)/2", a="cdiff_front", b="cdiff_rear")
    body("cdiff_carrier", [cdiff], at(cdiff), ZC, "cdiff_carrier")
    o_f, o_sp, ratio = bevel_mesh("0/1/157", 12, at("0/1/157"), ZC, "0/1/159", 12, at("0/1/159"), unit(g.one(cdiff, "bar")["axis"]), "centre_diff")
    bevel_mesh("0/1/158", 12, at("0/1/158"), ZC, "0/1/159", 12, at("0/1/159"), unit(g.one(cdiff, "bar")["axis"]), "centre_diff")
    signal("cdiff_spider", f"{num(ratio * dot(o_f, ZC))}*(f-c)", f="cdiff_front", c="cdiff_carrier")
    body("cdiff_spider", ["0/1/159"], at("0/1/159"), o_sp, "cdiff_spider", parent="cdiff_carrier")
    # Carrier 16T ring (part-local z=-30) -> transfer shaft -> 20T on the gearbox output.
    spur16 = g.at(cdiff, (0, 0, -30))
    r_t = spur(cdiff, 16, "0/1/172", 16, a_centre=spur16, view="centre_diff")
    transfer = g.group("0/1/172")
    if "0/1/190" not in transfer:
        raise ValueError("Transfer shaft does not carry both 16T gears")
    signal("transfer", f"{num(r_t)}*c", c="cdiff_carrier")
    body("transfer", transfer, at("0/1/172"), ZC, "transfer")
    r_o = spur("0/1/190", 16, "0/0/128/69", 20, view="centre_diff")
    signal("out", f"{num(r_o)}*t", t="transfer")

    # --------------------------------------------------------- 4-speed and range
    gb = "0/0/128/"
    rb = "0/1/133/"
    gsel = clamped("gear_select")
    rng = clamped("range_select")
    dirn = clamped("direction_select")
    signal("g_p", f"s/{num(PI / 2)}", s=gsel)
    signal("g_n", "floor(p+0.5)", p="g_p")
    signal("g_i", "n-4*floor(n/4)", n="g_n")
    signal("g_on", "clamp(floor(1+(0.2-abs(p-n))/0.2),0,1)", p="g_p", n="g_n")
    signal("fwd", "clamp(floor(2*d),0,1)", d=dirn)
    signal("rev", "clamp(floor(-2*d),0,1)", d=dirn)
    signal("hi", "clamp(floor(2*r),0,1)", r=rng)
    signal("lo", "clamp(floor(-2*r),0,1)", r=rng)
    signal("rg_on", "h+l", h="hi", l="lo")

    # Middle box (engine side): input c24 drives camshaft idler, reverse path and propshaft A idler.
    r_26 = spur(gb + "27", 16, gb + "26", 16, view="gearbox")  # c23 per e
    r_50 = spur(gb + "31", 20, gb + "50", 16, view="gearbox")  # clutch 50 per c23
    r_37 = spur(gb + "27", 16, gb + "37", 16, view="gearbox")  # idler 37 per e
    r_42 = spur(gb + "37", 16, "0/0/135", 16, view="gearbox")  # c42 per idler 37
    r_35 = spur(gb + "27", 16, gb + "35", 16, view="engine")  # cam idler per e
    r_cam = spur(gb + "35", 16, "0/0/127/16", 16, view="engine")  # camshaft per idler
    # Output side of the middle box.
    r_66 = spur(gb + "64", 16, gb + "66", 16, view="gearbox")  # clutch 66 per c26
    r_48 = spur(gb + "45", 16, gb + "48", 20, view="gearbox", tol=2.0)  # low: clutch 48 per c27
    r_63 = spur(gb + "55", 20, gb + "63", 16, view="gearbox", tol=2.0)  # high: clutch 63 per c27
    # Rear 4-speed: input c77, c78 (16:16) and c74 (12T:20T); output c76 with c73 (8T:24T).
    r_78 = spur(rb + "32", 16, rb + "36", 16, view="sequential")
    r_74 = spur(rb + "52", 12, rb + "51", 20, view="sequential")
    r_76_73 = spur(rb + "14", 8, rb + "29", 24, view="sequential")  # c76 per c73
    z360 = [(rb + "13", rb + "18"), (rb + "18", rb + "22"), (rb + "22", rb + "37")]
    z280 = [(rb + "42", rb + "48"), (rb + "48", rb + "47"), (rb + "47", rb + "46"), (rb + "46", rb + "49")]
    train = {}
    acc = 1.0
    for a, b in z360:
        acc *= spur(a, 16, b, 16, view="sequential")
        train[b] = ("c73", acc)  # angle per c73
    acc = 1.0
    for a, b in z280:
        acc *= spur(a, 16, b, 16, view="sequential")
        train[b] = ("c76", acc)  # angle per c76
    c76_per_c73 = r_76_73
    # K_j = c76 / c77 with the engaged clutch gear locked to its shaft.
    K = [
        r_74 * c76_per_c73 / train[rb + "18"][1],  # 1st: ring on c74 -> 18
        r_78 * c76_per_c73 / train[rb + "37"][1],  # 2nd: ring on c78 -> 37
        r_74 / train[rb + "47"][1],  # 3rd: ring on c74 -> 47
        r_78 / train[rb + "49"][1],  # 4th: ring on c78 -> 49
    ]
    expected = [0.2, 1 / 3, 0.6, 1.0]
    if any(abs(abs(k) - e) > 1e-9 for k, e in zip(K, expected)) or len({math.copysign(1, k) for k in K}) != 1:
        raise ValueError(f"Unexpected 4-speed ratios {K}")
    review["sequential"].append("Ratios c76/c77 for gears 1-4: " + ", ".join(f"{k:+.4f}" for k in K))
    signal(
        "g_k",
        "+".join(f"{num(k)}*max(0,1-abs(i-{j}))" for j, k in enumerate(K)),
        i="g_i",
    )
    E42 = r_37 * r_42  # c42 per e (two idling meshes)
    A_F = 1 / r_66  # c26 per out when ring 61 locks clutch 66 to the output shaft
    B_R = 1 / (r_50 * r_26)  # e per out when ring 61 locks clutch 50 (reverse)
    # Range: c26 per c27 through the engaged clutch gear.
    signal("rr", f"{num(r_48)}*l+{num(r_63)}*h", l="lo", h="hi")
    signal("rr_s", "r+1-o", r="rr", o="rg_on")
    signal(
        "ratio_e",
        f"v*{num(B_R)}+f*o*g*{num(A_F / E42)}/(r*k)",
        v="rev",
        f="fwd",
        o="rg_on",
        g="g_on",
        r="rr_s",
        k="g_k",
    )
    signal(
        "ratio_m",
        f"f*o*{num(A_F)}/r+v*g*k*{num(E42 * B_R)}",
        f="fwd",
        o="rg_on",
        r="rr_s",
        v="rev",
        g="g_on",
        k="g_k",
    )
    signal(
        "ratio_c26",
        f"f*{num(A_F)}+v*g*o*r*k*{num(E42 * B_R)}",
        f="fwd",
        v="rev",
        g="g_on",
        o="rg_on",
        r="rr",
        k="g_k",
    )
    signal("engine", "r*o+p", r="ratio_e", o="out", p="control:phase_engine")
    signal("mid", "r*o+p", r="ratio_m", o="out", p="control:phase_mid")
    signal("c26", "r*o+p", r="ratio_c26", o="out", p="control:phase_c26")

    # Middle-box bodies.
    def zbody(name, seed, sig, extra=(), drop=(), centre=None, view="gearbox"):
        grp = g.group(seed, extra, drop)
        for e in extra:
            hosts = [h for h in grp if h != e and g.conn(h, "axle") and any(
                length(cross(sub(at(e), c["pos"]), ZC)) < 0.6 for c in g.conn(h, "axle"))]
            if not hosts:
                raise ValueError(f"{name}: {e} is not on the group's axle line")
        body(name, grp, centre or at(seed), ZC, sig)
        return grp

    zbody("gb_output", gb + "51", "out", extra=[gb + "69"], drop=[gb + "61"])
    zbody("gb_range_shaft", gb + "58", "c26", drop=[gb + "62"])
    zbody("gb_return", gb + "45", "mid", extra=[gb + "55"])
    zbody("gb_input", gb + "27", "engine")
    signal("gb_c23", f"{num(r_26)}*e", e="engine")
    zbody("gb_reverse_lay", gb + "26", "gb_c23", extra=[gb + "31"])
    signal("gb_c42", f"{num(E42)}*e", e="engine")
    zbody("gb_prop_a", "0/0/135", "gb_c42")
    for gid, expr, var in (
        (gb + "50", f"{num(r_50)}*c", "gb_c23"),
        (gb + "37", f"{num(r_37)}*e", "engine"),
        (gb + "35", f"{num(r_35)}*e", "engine"),
        (gb + "66", f"{num(r_66)}*c", "c26"),
        (gb + "48", f"{num(r_48)}*m", "mid"),
        (gb + "63", f"{num(r_63)}*m", "mid"),
    ):
        sname = "gear_" + gid.replace("/", "_")
        signal(sname, expr, **{expr.split("*")[-1]: var})
        body(sname, [gid], at(gid), ZC, sname)
    # Driving rings slide on their ridged joiners and turn with their shafts.
    signal("ring61", f"{GEAR_RING}*d", d=dirn)
    signal("ring62", f"{GEAR_RING}*r", r=rng)
    # Each driving-ring extension sits on one side of its ring and is only pushed
    # (towards its clutch gear) when the ring moves that way.
    for name, ring, ext, shaft, sig, side in (
        ("ring_direction", gb + "61", gb + "65", "gb_output", "ring61", "max"),
        ("ring_range", gb + "62", gb + "57", "gb_range_shaft", "ring62", "min"),
    ):
        if not g.on_line(ext, at(ring), ZC):
            raise ValueError(f"{ext} is not on the axis of ring {ring}")
        offset = dot(sub(at(ext), at(ring)), ZC)
        if (offset > 0) != (side == "max"):
            raise ValueError(f"{ext} is not on the expected side of {ring}")
        body(name, [ring], at(ring), ZC, sig, kind="prismatic", parent=shaft)
        signal(f"push_{name}", f"{side}(0,d)", d=sig)
        body(f"ext_{name.split('_')[1]}", [ext], at(ext), ZC, f"push_{name}", kind="prismatic", parent=shaft)
    # Changeover catches: forks 40 LDU below their X pivots; levers rise into the cab.
    for name, catch, sig in (
        ("lever_direction", gb + "76/19", "ring61"),
        ("lever_range", gb + "76/10", "ring62"),
    ):
        pivot = [c for c in g.conn(catch, "axle_hole") if abs(abs(dot(c["axis"], X)) - 1) < 1e-6][0]["pos"]
        ring_at = at(gb + ("61" if catch.endswith("19") else "62"))
        arm = sub(ring_at, pivot)
        arm_len = length(arm)
        if abs(arm_len - 40) > 0.6 or abs(dot(unit(arm), UP) + 1) > 1e-3:
            raise ValueError(f"{catch}: fork is not 40 LDU below the pivot ({arm_len:.2f})")
        # A small +X rotation moves the fork tip along X x arm.
        tip = cross(X, arm)
        sgn = 1.0 if dot(tip, ZC) > 0 else -1.0
        signal(name, f"{num(sgn)}*asin(clamp(d/{num(arm_len)},-1,1))", d=sig)
        body(name, g.group(catch), pivot, X, name)
        review["shifting"].append(f"{catch}: fork arm {arm_len:.2f} LDU below the X pivot")

    # Propshaft A (c42 -> c77) and B (c27 -> c76): two in-phase joints each.
    def propshaft(tag, src_sig, j1, e1_in, e1_out, j2, e2_in, e2_out, view):
        c1, c2 = at(j1), at(j2)
        d_mid = unit(sub(c2, c1))
        f1 = g.one(e1_in, "clip")["axis"]
        f1 = unit(sub(f1, mul(ZC, dot(ZC, f1))))
        mid_fork = unit(cross(d_mid, f1))
        measured = g.one(e1_out, "clip")["axis"]
        mid_fork = mid_fork if dot(mid_fork, measured) > 0 else mul(mid_fork, -1)
        far = g.one(e2_in, "clip")["axis"]
        phase = math.degrees(math.acos(min(1.0, abs(dot(unit(sub(far, mul(d_mid, dot(d_mid, far)))), mid_fork)))))
        if phase > 0.5:
            raise ValueError(f"Propshaft {tag}: intermediate forks are {phase:.3f} deg out of phase")
        # Same intermediate shaft, same fork line: snap the rounded second fork onto the first.
        o1, x1 = linkages.universal_joint(signals, f"uj_{tag}1", src_sig, ZC, d_mid, f1, mid_fork)
        o2, x2 = linkages.universal_joint(
            signals, f"uj_{tag}2", o1, d_mid, ZC, mid_fork, g.one(e2_out, "clip")["axis"]
        )
        review["propshafts"].append(f"Propshaft {tag}: measured intermediate fork phase {phase:.4f} deg, snapped in phase")
        return c1, c2, d_mid, (o1, x1), (o2, x2)

    pa = propshaft("pa", "gb_c42", "0/1/200", "0/1/199", "0/1/198", "0/1/196", "0/1/195", "0/1/194", "sequential")
    pb = propshaft("pb", "mid", "0/1/207", "0/1/205", "0/1/206", "0/1/203", "0/1/202", "0/1/201", "sequential")
    for tag, (c1, c2, d_mid, first, second) in (("A", pa), ("B", pb)):
        body(f"prop{tag.lower()}_cross1", ["0/1/200" if tag == "A" else "0/1/207"], c1, g.one("0/1/199" if tag == "A" else "0/1/205", "clip")["axis"], first[1], parent="gb_prop_a" if tag == "A" else "gb_return")
        mid_shaft = g.group("0/1/198" if tag == "A" else "0/1/206")
        body(f"prop{tag.lower()}_shaft", mid_shaft, c1, d_mid, first[0])
        body(f"prop{tag.lower()}_cross2", ["0/1/196" if tag == "A" else "0/1/203"], c2, g.one("0/1/195" if tag == "A" else "0/1/202", "clip")["axis"], second[1], parent=f"prop{tag.lower()}_shaft")
        review["propshafts"].append(f"Propshaft {tag}: two cardan joints at {math.degrees(math.acos(dot(ZC, d_mid))):.1f} deg, forks in phase")
    zbody("seq_input", rb + "32", "uj_pa2_out", view="sequential")
    zbody("seq_output", rb + "29", "uj_pb2_out", view="sequential")
    signal("seq_c78", f"{num(r_78)}*a", a="uj_pa2_out")
    signal("seq_c74", f"{num(r_74)}*a", a="uj_pa2_out")
    signal("seq_c73", f"{num(1 / c76_per_c73)}*a", a="uj_pb2_out")
    zbody("seq_shaft_78", rb + "36", "seq_c78", view="sequential")
    zbody("seq_shaft_74", rb + "17", "seq_c74", extra=[rb + "51"], view="sequential")
    zbody("seq_shaft_73", rb + "13", "seq_c73", view="sequential")
    for gid, (base, ratio) in sorted(train.items()):
        sname = "gear_" + gid.replace("/", "_")
        signal(sname, f"{num(ratio)}*a", a="seq_c73" if base == "c73" else "uj_pb2_out")
        body(sname, [gid], at(gid), ZC, sname)
    # Rotary catch on its shaft; the dial shaft is coupled by two 4-knob wheels.
    zbody("seq_selector", "0/1/212", gsel, extra=[rb + "25"], view="sequential")
    r_knob = -1.0  # parallel knob wheels turn oppositely (axes and 40 LDU spacing checked below)
    kd = sub(at("0/1/220"), at("0/1/212"))
    if abs(length(kd) - 40) > 0.6 or abs(dot(gear_axis("0/1/212"), gear_axis("0/1/220"))) < 0.999:
        raise ValueError("Knob wheels are not parallel neighbours")
    edge("gear_mesh", "0/1/212", "0/1/220", "Parallel knob wheels 40 LDU apart (connector frames)", "Reviewed 4-knob coupling, opposite rotation 1:1")
    signal("dial", f"{num(r_knob)}*s", s=gsel)
    zbody("seq_dial", "0/1/220", "dial", view="sequential")
    # Rotary catch drives the two rings alternately (cam profile assumed: see notes).
    signal("cam_u", "cos(s)", s=gsel)
    signal("cam_v", "sin(s)", s=gsel)
    signal("ring20", f"{GEAR_RING}*clamp((abs(u)-0.75)*5,0,1)*u/max(abs(u),1e-6)", u="cam_u")
    signal("ring40", f"{GEAR_RING}*clamp((abs(u)-0.75)*5,0,1)*u/max(abs(u),1e-6)", u="cam_v")
    # Source pose: ring 20 sits +10 LDU towards clutch 18 (1st gear); ring 40 is centred.
    if abs(dot(sub(at(rb + "20"), at(rb + "19")), ZC) - GEAR_RING) > 0.2 or abs(dot(sub(at(rb + "40"), at(rb + "38")), ZC)) > 0.2:
        raise ValueError("Source driving rings are not in the expected 1st-gear pose")
    body("ring_seq_a", [rb + "20"], at(rb + "20"), ZC, "ring20_rel", kind="prismatic", parent="seq_shaft_74")
    body("ring_seq_b", [rb + "40"], at(rb + "40"), ZC, "ring40", kind="prismatic", parent="seq_shaft_78")
    signal("ring20_rel", f"r-{GEAR_RING}", r="ring20")

    # ------------------------------------------------------------------ engine
    cam_axle = g.one("0/0/127/0", "axle")
    signal("camshaft", f"{num(r_cam * r_35)}*e", e="engine")
    zbody("camshaft", "0/0/127/16", "camshaft", view="engine")
    pistons = [("0/0/126/7", "0/0/127/2"), ("0/0/126/10", "0/0/127/3"), ("0/0/126/13", "0/0/127/5"),
               ("0/0/126/16", "0/0/127/4"), ("0/0/126/19", "0/0/127/6"), ("0/0/126/22", "0/0/127/7")]
    for n, (pist, lobe) in enumerate(pistons, 1):
        far = max(g.conn(lobe, "pin_hole"), key=lambda c: length(cross(sub(c["pos"], cam_axle["pos"]), ZC)))
        v = sub(far["pos"], cam_axle["pos"])
        v = sub(v, mul(ZC, dot(v, ZC)))
        ecc = length(v)
        a0 = math.atan2(dot(v, UP), dot(v, X))  # lobe angle from +X towards up
        if abs(ecc - 20) > 0.1:
            raise ValueError(f"Cam {lobe} eccentricity {ecc}")
        grp = g.group(pist)
        seg = [c for c in g.conn(pist, "axle")][0]
        bottom = min((add(seg["pos"], mul(UP, s)) for s in (-30, 30)), key=lambda p: dot(sub(p, cam_axle["pos"]), UP))
        height = dot(sub(bottom, cam_axle["pos"]), UP)
        rest = max(0.0, 20 * math.sin(a0) - 10)
        if abs(height - (20 + rest)) > 0.3:
            raise ValueError(f"Piston {pist} rest height {height:.2f} does not match its cam ({20 + rest})")
        # Rotating about +ZC turns a lobe from +X towards +Y (down): lobe angle a0 - theta.
        signal(f"piston{n}", f"max(0,20*sin({num(a0)}-c)-10)-{num(rest)}", c="camshaft")
        body(f"piston{n}", grp, bottom, UP, f"piston{n}", kind="prismatic")
        edge("surface_contact", pist, lobe, "Piston axle end over the 1x2 liftarm cam; rest heights 20/30 LDU above the camshaft match the cam pose",
             "Agent hypothesis: flat follower on a stadium cam (eccentricity 20, radius 10), stop at 20 LDU; contact force not modelled")
        review["engine"].append(f"piston{n} {pist}: cam {lobe} at {math.degrees(a0):+.0f} deg, rest lift {rest:.1f}")

    # ------------------------------------------------------------------ steering
    col = g.group("0/32")
    j1, j2 = at("0/25"), at("0/0/125")
    d_col = unit(sub(j1, at("0/32")))
    d_mid = unit(sub(j2, j1))
    d_in9 = unit(sub(g.one("0/0/124", "axle_hole")["pos"], j2))
    control("steering", -3.0, 3.0, "Steering wheel angle about the column; positive is clockwise for the driver")
    sw = clamped("steering")
    o1, x1 = linkages.universal_joint(signals, "uj_s1", sw, d_col, d_mid, g.one("0/24", "clip")["axis"], g.one("0/26", "clip")["axis"])
    o2, x2 = linkages.universal_joint(signals, "uj_s2", o1, d_mid, d_in9, g.one("0/0/123", "clip")["axis"], g.one("0/0/124", "clip")["axis"])
    body("steering_wheel", col, j1, d_col, sw)
    body("steer_cross1", ["0/25"], j1, g.one("0/24", "clip")["axis"], x1, parent="steering_wheel")
    body("steer_column", g.group("0/27"), j1, d_mid, o1)
    body("steer_cross2", ["0/0/125"], j2, g.one("0/0/123", "clip")["axis"], x2, parent="steer_column")
    signal("steer_in", f"{num(dot(d_in9, ZC))}*a", a=o2)  # about +ZC
    zbody("steer_input", "0/0/121", "steer_in", extra=["0/0/120"], view="steering")
    r_a = spur("0/0/121", 16, "0/0/94/22", 20, view="steering", tol=1.0)
    signal("steer_mid", f"{num(r_a)}*a", a="steer_in")
    zbody("steer_idler", "0/0/94/23", "steer_mid", extra=["0/0/94/22"], view="steering")
    r_b = spur("0/0/94/23", 12, "0/0/50", 20, view="steering")
    signal("steer_pinion", f"{num(r_b)}*a", a="steer_mid")
    zbody("steer_pinion", "0/0/116", "steer_pinion", extra=["0/0/50"], view="steering")
    rack_parts = sorted((i for i in g.nodes if i.startswith("0/0/111/") and g.nodes[i]["kind"] == "part"
                         and i not in ("0/0/111/11", "0/0/111/12")), key=lambda s: [int(x) for x in s.split("/")])
    k_rack = rack_ratio(ZC, at("0/0/116"), 12, at("0/0/111/0"), X)
    signal("rack", f"{num(k_rack)}*a", a="steer_pinion")
    body("rack", rack_parts, at("0/0/111/0"), X, "rack", kind="prismatic")
    review["steering"].append(f"Rack {k_rack:+.3f} LDU per pinion radian (12T, rack_ratio)")
    # HOG: 24T on the long x=80 shaft meshes the 20T on the steering input shaft (diagonal).
    r_h = spur("0/0/120", 20, "0/0/103", 24, view="steering", tol=2.0)
    signal("hog_shaft", f"{num(r_h)}*a", a="steer_in")
    hog = g.group("0/0/103")
    body("hog_shaft", hog, at("0/0/103"), ZC, "hog_shaft")
    vert = gear_axis("0/1/282/1")
    r_v = bevel_ratio("0/1/282/4", 12, ZC, "0/1/282/1", 12, vert, "steering")
    signal("hog_column", f"{num(r_v)}*a", a="hog_shaft")
    body("hog_column", g.group("0/1/282/1", extra=["0/358"]), at("0/1/282/1"), vert, "hog_column")
    if not g.on_line("0/358", at("0/1/282/1"), vert):
        raise ValueError("Roof knob is not on the HOG column")
    # Knuckles about the kingpin (towball centres); ball links of 100 LDU to the rack.
    for side, kn, pins, arm, hub, rim, tyre, link, rack_ball in (
        ("l", "0/0/57", ("0/0/55", "0/0/56"), "0/0/58", "0/0/65", "0/380", "0/381", "0/0/111/12", "0/0/111/9"),
        ("r", "0/0/62", ("0/0/60", "0/0/61"), "0/0/63", "0/0/66", "0/387", "0/386", "0/0/111/11", "0/0/111/10"),
    ):
        b_up, b_lo = (g.one(p, "generic")["pos"] for p in pins)
        kaxis = unit(sub(b_up, b_lo)) if dot(sub(b_up, b_lo), UP) > 0 else unit(sub(b_lo, b_up))
        kp = b_lo
        ball = g.one(arm, "generic")["pos"]
        socket = g.one(rack_ball, "generic")["pos"]
        link_len = length(sub(ball, socket))
        ends = [c["pos"] for c in g.conn(link, "generic")]
        if min(length(sub(e, ball)) for e in ends) > 0.3 or min(length(sub(e, socket)) for e in ends) > 0.3:
            raise ValueError(f"{link} ends are not at the ball centres")
        if abs(link_len - 100) > 0.3:
            raise ValueError(f"{link}: length {link_len}")
        ang, fn = linkages.ball_link(signals, f"knuckle_{side}", "rack", kp, kaxis, ball, socket, X, link_len)
        body(f"knuckle_{side}", [kn, *pins, arm], kp, kaxis, ang)
        anchors[f"rack_ball_{side}"] = dict(body="rack", point=r6(socket))
        anchors[f"arm_ball_{side}"] = dict(body=f"knuckle_{side}", point=r6(ball))
        body(f"tierod_{side}", [link], socket, kaxis, kind="rod", x_hint=r6(cross(sub(ball, socket), kaxis)),
             start=f"rack_ball_{side}", end=f"arm_ball_{side}")
        checks.append(dict(kind="distance", name=f"tierod_{side}", a=f"rack_ball_{side}", b=f"arm_ball_{side}",
                           length=round(link_len, 6), tolerance=0.02))
        edge("ball", rack_ball, link, "pyldraw3 generic ball contact at the towball centre", "Reviewed ball joint (rack end)")
        edge("ball", arm, link, "pyldraw3 generic ball contact at the towball centre", "Reviewed ball joint (knuckle end)")
        # Wheel: hub, rim and tyre on the hub axis; spins with the half shaft through the CV.
        hub_axle = g.one(hub, "axle")
        hs = axle_bodies["front"][side]
        signal(f"wheel_f{side}", f"{num(dot(hs['d_out'], X))}*h", h=hs["halfshaft"])
        body(f"wheel_f{side}", [hub, rim, tyre], at(hub), X, f"wheel_f{side}", parent=f"knuckle_{side}")
        if not g.on_line(rim, hub_axle["pos"], X) or not g.on_line(tyre, hub_axle["pos"], X):
            raise ValueError(f"Wheel {side} is not on the hub axis")
        cv = g.one("0/0/59" if side == "l" else "0/0/64", "generic")["pos"]
        if length(cross(sub(cv, kp), kaxis)) > 2.5:
            raise ValueError(f"CV centre is far from the {side} kingpin axis")
        review["steering"].append(
            f"{side}: kingpin through {r6(kp)} axis {r6(kaxis)}; arm ball {length(cross(sub(ball, kp), kaxis)):.2f} LDU from it"
        )
    for side, hub, rim, tyre in (("l", "0/1/92", "0/382", "0/383"), ("r", "0/1/99", "0/385", "0/384")):
        hs = axle_bodies["rear"][side]
        signal(f"wheel_r{side}", f"{num(dot(hs['d_out'], X))}*h", h=hs["halfshaft"])
        body(f"wheel_r{side}", [hub, rim, tyre], at(hub), X, f"wheel_r{side}")
        if not all(g.on_line(i, g.one(hub, "axle")["pos"], X) for i in (rim, tyre)):
            raise ValueError("Rear wheel not on its hub axis")
    # Steering limit: the wheel angle that gives `steer_rack_limit` LDU of rack travel
    # (about 27 degrees at the knuckles; sampled clearance is reported separately).
    lim = steer_rack_limit
    plan_tmp = dict(plan, controls=controls, signals=signals, bodies={}, anchors={}, checks=[])
    ev = contract.evaluate(dict(plan_tmp, status="draft"), {"steering": 1.0})
    rack_per = ev["signals"]["rack"]
    sw_max = min(3.0, abs(lim / rack_per))
    controls["steering"].update(min=-round(sw_max, 4), max=round(sw_max, 4))
    signals["steering_v"]["expression"] = f"clamp(v,{-round(sw_max, 4)!r},{round(sw_max, 4)!r})"
    # Sign: positive steering must turn the front wheels towards -X (the car's right).
    ev = contract.evaluate(dict(plan_tmp, status="draft"), {"steering": 0.3})
    turn = ev["signals"]["knuckle_l_angle"]
    fwd = linkages.rotate(mul(ZC, -1), bodies["knuckle_l"]["axis"], turn)
    if dot(fwd, X) > 0:
        raise ValueError("Positive steering turns left; flip the column convention")
    review["steering"].append(f"Steering wheel range +/-{sw_max:.3f} rad for +/-{lim} LDU rack travel")

    # ------------------------------------------------------------------ winch
    wk = clamped("winch")
    vk = gear_axis("0/69")
    body("winch_knob", g.group("0/69"), at("0/69"), vk, wk)
    r_w1 = bevel_ratio("0/58/1", 12, vk, "0/58/5", 12, ZC, "winch")
    signal("winch_mid", f"{num(r_w1)}*w", w=wk)
    body("winch_mid", g.group("0/58/5"), at("0/58/5"), ZC, "winch_mid")
    r_w2 = bevel_ratio("0/58/10", 12, ZC, "0/94", 12, X, "winch")
    signal("winch_drum", f"{num(r_w2)}*w", w="winch_mid")
    body("winch_drum", g.group("0/94"), at("0/94"), X, "winch_drum")

    locks = {
        "fwd": (gb + "66", gb + "51"), "rev": (gb + "50", gb + "51"),
        "lo": (gb + "48", gb + "58"), "hi": (gb + "63", gb + "58"),
        0: (rb + "18", rb + "19"), 1: (rb + "37", rb + "38"), 2: (rb + "47", rb + "19"), 3: (rb + "49", rb + "38"),
    }
    return dict(plan=plan, controls=controls, signals=signals, bodies=bodies, anchors=anchors, checks=checks,
                review=review, geometry=g, meshes=meshes, locks=locks, axes=dict(ZC=ZC, UP=UP))


PLANETS = {"0/0/27/14": "0/0/27/11", "0/1/15": "0/1/12", "0/1/159": "0/1/155"}  # spider -> carrier


def part_angle(plan, result, part, axis, relative_to=None):
    """Rotation of a part's body about `axis` (0 for static parts), optionally in a carrier frame."""
    def owner(p):
        return next((n for n, b in plan["bodies"].items() if p in b["instances"]), None)

    if owner(part) is None:
        return 0.0
    t = result["transforms"][owner(part)]
    if relative_to:
        c = result["transforms"][owner(relative_to)]
        rc = [[c[j][i] for j in range(3)] for i in range(3)]  # inverse rotation
        t = [[sum(rc[i][k] * t[k][j] for k in range(3)) for j in range(3)] for i in range(3)]
    a = unit(axis)
    v = unit(cross(a, [1, 0, 0] if abs(a[0]) < 0.9 else [0, 1, 0]))
    w = [sum(t[i][j] * v[j] for j in range(3)) for i in range(3)]
    return math.atan2(dot(cross(v, w), a), dot(v, w))


def verify_kinematics(plan, meshes, locks, zc, step=0.01):
    """Every mesh and every engaged clutch obeys its ratio in all 16 gear states."""
    report = []
    for direction in (1.0, -1.0):
        for rng in (-1.0, 1.0):
            for j in range(4):
                base = dict(direction_select=direction, range_select=rng, gear_select=j * PI / 2,
                            drive=0.3, diff_front=0.07, diff_rear=-0.05, diff_center=0.04, steering=0.0)
                e0 = contract.evaluate(plan, base)
                e1 = contract.evaluate(plan, dict(base, drive=0.3 + step, diff_front=0.07 + 0.013 * step / 0.01,
                                                  diff_rear=-0.05 - 0.011 * step / 0.01, diff_center=0.04 + 0.007 * step / 0.01))
                worst = 0.0
                for a, axa, b, axb, ratio in meshes:
                    carrier = PLANETS.get(b) or PLANETS.get(a)
                    da = part_angle(plan, e1, a, axa, carrier) - part_angle(plan, e0, a, axa, carrier)
                    db = part_angle(plan, e1, b, axb, carrier) - part_angle(plan, e0, b, axb, carrier)
                    worst = max(worst, abs(db - ratio * da))
                    if abs(db - ratio * da) > 1e-9:
                        raise ValueError(f"Mesh {a}-{b} violated in state {direction},{rng},{j}: {db} vs {ratio * da}")
                engaged = [locks["fwd" if direction > 0 else "rev"], locks["lo" if rng < 0 else "hi"], locks[j]]
                moving = 0.0
                for gear, shaft in engaged:
                    dg = part_angle(plan, e1, gear, zc) - part_angle(plan, e0, gear, zc)
                    ds = part_angle(plan, e1, shaft, zc) - part_angle(plan, e0, shaft, zc)
                    if abs(dg - ds) > 1e-9:
                        raise ValueError(f"Clutch {gear} slips on {shaft} in state {direction},{rng},{j}")
                    moving = max(moving, abs(dg))
                de = e1["signals"]["engine"] - e0["signals"]["engine"]
                report.append(dict(direction=direction, range=rng, gear=j + 1, engine_per_wheel=de / step,
                                   worst_mesh_error=worst))
    return report


FLEXIBLE = ("42110 - ropelq-1.ldr", "42110 - technicribhose-lq-1.ldr", "42110 - rubberbandround-1.ldr",
            "42110 - rubberbandround-2.ldr")
# Bodywork sections hidden in Blender (panels, doors, roof, seats, lights, ...). The frame,
# axles, wheels and every rigged part stay visible.
BODYWORK = (
    "roof", "roofside1", "roofside2", "roofbottom", "roofrack", "sidecase1", "sidecaselid", "ladder", "ladder2",
    "rooftrunk", "rooftrunklid", "door1", "door1b", "door2", "door2b", "bonnet", "bonnettop", "bonnetside1",
    "bonnetside2", "bonnetside3", "bonnetside4", "frontwheelarch", "frontlight1", "frontlight2", "frontbottom",
    "frontbottom2", "backdoor", "backdoor2", "backdoorlatch", "backpilar", "backwindows1", "backwindows2",
    "backwheelarch1", "backwheelarch2", "backwheelarchtop", "backbottom", "backbottomside1", "backbottomside2",
    "cabinside1", "cabinside2", "seat", "backseat", "dashboard", "dashboard2", "pillar1", "pillar2",
    "runningboard1", "runningboard2", "technicribhose-lq-1", "rubberbandround-2",
)
BODY_PANEL = re.compile(r"Panel|Fairing|Mudguard|Slope|^Tile|^Plate|^Brick|Windscreen|Glass|Wheel Rim|Tyre|Dish|Headlight", re.I)
ROOF_LEVEL = -400.0  # chassis-level parts above this height (LDU, -Y up) carry the hidden roof and cab
EXTRA_HIDDEN = ("0/390",)  # 12T knob of the hidden tailgate latch
OPENINGS = ("door1", "door2", "bonnet", "backdoor", "rooftrunk", "sidecase1", "ladder")


def sections(plan, i):
    nodes = {n["id"]: n for n in plan["source"]["nodes"]}
    out, cur = [], nodes[i]["parent"]
    while cur != "root":
        out.append(nodes[cur]["ref"].lower().removeprefix("42110 - ").removesuffix(".ldr"))
        cur = nodes[cur]["parent"]
    return out


def bodywork(plan, bodies):
    owned = {i for b in bodies.values() for i in b["instances"]}
    nodes = {n["id"]: n for n in plan["source"]["nodes"]}
    hidden = []
    for i, n in nodes.items():
        if n["kind"] != "part" or i in owned:
            continue
        secs = sections(plan, i)
        chassis_level = secs == ["chassis"]
        roof = chassis_level and n["world"][1][3] < ROOF_LEVEL
        if (any(s in BODYWORK for s in secs) or roof or i in EXTRA_HIDDEN
                or (chassis_level and BODY_PANEL.search(n["description"] or ""))):
            hidden.append(i)
    return sorted(hidden, key=lambda s: [int(x) for x in s.split("/")])


def views(plan, out, hidden):
    g, bodies, review = out["geometry"], out["bodies"], out["review"]
    owned = {i for b in bodies.values() for i in b["instances"]}
    v = {}

    def view(key, label, body_names, inputs, outputs, text, notes=(), parts=(), disposition="planned"):
        v[key] = dict(label=label, parts=sorted(parts, key=lambda s: [int(x) for x in s.split("/")]),
                      bodies=list(body_names), inputs=list(inputs), outputs=list(outputs),
                      notes=list(notes), disposition=disposition, review=text)

    def named(prefixes):
        return [n for n in bodies if n.startswith(prefixes)]

    view("steering", "Steering wheel and roof knob to the front knuckles",
         named(("steering_wheel", "steer_", "rack", "knuckle_", "tierod_", "hog_")),
         ["control:steering"], ["body:knuckle_l", "body:knuckle_r", "body:hog_column"],
         "Two exact cardan joints, three measured gear meshes, rack-and-pinion and two closed 100 LDU ball links; "
         "the roof knob is geared to the same input shaft through the diagonal 24T/20T mesh.",
         review["steering"])
    view("front_axle", "Front differential, half shafts and wheels",
         named(("front_", "wheel_f")), ["control:drive", "control:diff_front", "control:diff_center"],
         ["body:wheel_fl", "body:wheel_fr"],
         "28T ring / 20T pinion and 12T spider bevels measured; cardan joint at the diff and CV spindle at each hub; "
         "front wheels ride the steering knuckles.", review["front_axle"])
    view("rear_axle", "Rear differential, half shafts and wheels", named(("rear_", "wheel_r")),
         ["control:drive", "control:diff_rear", "control:diff_center"], ["body:wheel_rl", "body:wheel_rr"],
         "Same layout as the front axle; rear knuckles are fixed.", review["rear_axle"])
    view("centre_diff", "Propshafts, centre differential and transfer shaft",
         named(("prop_front", "prop_rear", "cdiff_", "transfer")), ["control:drive", "control:diff_center"],
         ["body:transfer"], "8T/24T steps to both axles; centre carrier drives the transfer shaft by its 16T ring.",
         review["centre_diff"])
    view("gearbox", "Range and direction gearbox (middle box) with its cab levers",
         named(("gb_", "gear_0_0_128", "ring_direction", "ring_range", "ext_", "lever_")),
         ["control:direction_select", "control:range_select", "body:gb_output"],
         ["body:gb_input", "body:gb_prop_a"],
         "Ring 0/0/128/61 picks forward (clutch 66, through the 4-speed) or reverse (clutch 50, direct); ring "
         "0/0/128/62 picks low (20T clutch 48 via extension 57) or high (clutch 63). Catches are measured 40 LDU forks.",
         review["gearbox"] + review["shifting"])
    view("sequential", "Sequential 4-speed (rear box), rotary catch, dial and internal propshafts",
         named(("seq_", "gear_0_1_133", "ring_seq", "propa_", "propb_")),
         ["control:gear_select", "body:seq_input"], ["body:seq_output"],
         "Constant-mesh trains at z=360 and z=280; two driving rings select 1st-4th alternately (ratios checked); "
         "two in-phase double cardan propshafts link it to the middle box.",
         review["sequential"] + review["propshafts"])
    view("engine", "Inline six: camshaft and six cam-driven pistons", named(("camshaft", "piston")),
         ["body:camshaft"], [f"body:piston{n}" for n in range(1, 7)],
         "Camshaft geared 1:1 to the gearbox input through idler 0/0/128/35; piston lift max(0,20 sin(a-theta)-10).",
         review["engine"])
    view("winch", "Winch knob, bevels and drum", named(("winch",)), ["control:winch"], ["body:winch_drum"],
         "Three 12T bevel meshes measured (knob 0/69 under the bonnet). The rope is static.", review["winch"])

    def leftover(pred):
        return [i for i in remaining if pred(i)]

    remaining = set(plan["discovery"]["mechanical_parts"]) - owned
    groups = []
    flex = leftover(lambda i: any(s in [f.removeprefix("42110 - ").removesuffix(".ldr") for f in FLEXIBLE]
                                  for s in sections(plan, i)) or i == "0/98")
    groups.append(("flexible", "Rope, hose, bands and hook", flex, "deferred",
                   "Flexible LDCad paths (rope merged into one mesh) and the winch hook stay static; unwinding is not modelled."))
    remaining -= set(flex)
    susp_seed = [i for i in remaining if re.search(r"Shock|Suspension Arm|Axles at Both Ends|Towball|Steering Wheel Bearing",
                                                   g.desc(i)) and sections(plan, i)[:1] in (["frontaxle"], ["rearaxle"])]
    susp = set(susp_seed)
    for i in susp_seed:
        if i in g.group_of:
            susp |= set(g.group_of[i]) - owned
    susp = sorted(susp & remaining)
    groups.append(("suspension", "Independent double-wishbone suspension (all corners)", susp, "deferred",
                   "Static ride height by decision: each shock absorber is one rigid part, and travel needs a per-wheel "
                   "loop solve with the steering links and half shafts."))
    remaining -= set(susp)
    openings = leftover(lambda i: any(s in OPENINGS for s in sections(plan, i)))
    groups.append(("body_openings", "Doors, bonnet, tailgate, roof trunk, side case and ladder", openings, "deferred",
                   "Bodywork is hidden by request, so its hinges are not rigged."))
    remaining -= set(openings)
    body_parts = leftover(lambda i: i in hidden)
    groups.append(("bodywork", "Other hidden bodywork axles and pins", body_parts, "deferred",
                   "Structural axles and pins inside hidden body sections; hidden by request, not reviewed."))
    remaining -= set(body_parts)
    pawl = leftover(lambda i: i in ("0/112", "0/113", "0/114", "0/115"))
    groups.append(("winch_ratchet", "Winch ratchet pawl", pawl, "deferred",
                   "Pawl bearing on the 16T ratchet gear 0/111; clicking is a surface contact and is not animated."))
    remaining -= set(pawl)
    brackets = leftover(lambda i: i.startswith(("0/0/127/9", "0/0/127/1", "0/1/147/", "0/1/223/"))
                        or i in g.group("0/0/128/76/1") or i == "0/1/133/28")
    groups.append(("brackets", "Camshaft, selector-dial and gearbox brackets", brackets, "static",
                   "Reviewed in renders and contacts: pinned to the engine block or frame (0/0/127/14 to 0/0/126/2), "
                   "carry round bearing holes only."))
    remaining -= set(brackets)
    groups.append(("supports", "Frame axles, pins and connectors", sorted(remaining), "deferred",
                   "Axle/pin/connector supports of the chassis and gearbox frames, not traced to any motion path; "
                   "not individually reviewed."))
    for key, label, parts, disposition, text in groups:
        if parts:
            view(key, label, [], [], [], text, [f"Parts: {len(parts)}."], parts, disposition)
    return v


def notes():
    return [
        "Source 42110-1.mpd (Philippe Hurbain) is unmodified; occurrence IDs are its type-1 index paths.",
        "Frame: LDU, -Y up, front -Z, car's left +X; longitudinal shafts use the measured 0.003 rad chassis tilt.",
        "Contacts: bounded pyldraw3 run over 1538 non-embedded, non-cosmetic parts (226/230 axles with axle-hole contacts); "
        "axle-locked groups define rigid shafts. Embedded pre-release DATs use their library alias frames for analysis only.",
        "Every gear mesh, clutch lock and differential relation is checked in all 16 gear/range/direction states by "
        "scripts/build_defender_rig.py (mesh residual < 1e-12 rad).",
        "Driving-ring travel (10 LDU) is taken from the source 1st-gear ring offset. The rotary catch cam profile is "
        "assumed: each ring follows 10*sat(cos/sin of the catch angle) with an 18 degree dwell, so rings never overlap.",
        "Shifts change ratios: the animation keys phase_engine / phase_mid / phase_c26 at each ratio change so every "
        "shaft stays continuous.",
        "Propshafts A and B: intermediate forks measured in phase within 0.01 degree and snapped exactly in phase "
        "(constant velocity).",
        "Not modelled: suspension travel, body hinges, rope/hose, winch ratchet, friction, backlash, gravity. "
        "Clearance is sampled, not proven.",
    ]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--study", required=True)
    parser.add_argument("--evidence", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--bodywork", required=True)
    parser.add_argument("--report", help="Kinematic state report (JSON)")
    parser.add_argument("--ready", action="store_true")
    args = parser.parse_args()
    study = contract.load(args.study)
    evidence = json.loads(Path(args.evidence).read_text())
    out = build(study, evidence)
    plan = out["plan"]
    plan.update(name="defender_42110", controls=out["controls"], signals=out["signals"], bodies=out["bodies"],
                anchors=out["anchors"], checks=out["checks"], status="draft", notes=notes())
    plan["mechanisms"] = {}
    report = verify_kinematics(plan, out["meshes"], out["locks"], out["axes"]["ZC"])
    hidden = bodywork(plan, out["bodies"])
    plan["mechanisms"] = views(plan, out, set(hidden))
    if args.ready:
        plan["status"] = "ready"
    contract.validate(plan)
    contract.save(args.output, plan)
    Path(args.bodywork).write_text(json.dumps(dict(
        hidden=hidden,
        rules=dict(sections=list(BODYWORK), chassis_level_descriptions=BODY_PANEL.pattern,
                   chassis_level_above_y=ROOF_LEVEL, explicit=list(EXTRA_HIDDEN),
                   kept="Every part owned by a rig body stays visible"),
        plan_digest=contract.digest(plan), count=len(hidden)), indent=1) + "\n")
    if args.report:
        Path(args.report).write_text(json.dumps(dict(states=report, meshes=len(out["meshes"])), indent=1) + "\n")
    owned = sum(len(b["instances"]) for b in plan["bodies"].values())
    print(json.dumps(dict(plan=args.output, status=plan["status"], bodies=len(plan["bodies"]), moving_parts=owned,
                          signals=len(plan["signals"]), meshes=len(out["meshes"]), hidden=len(hidden),
                          views={k: m["disposition"] for k, m in plan["mechanisms"].items()})))


if __name__ == "__main__":
    main()
