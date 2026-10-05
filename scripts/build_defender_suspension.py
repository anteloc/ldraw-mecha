#!/usr/bin/env python3
"""Author the 42110 independent-suspension motion plan (suspension only).

    scripts/build_defender_suspension.py \
        --study output/42110-suspension/study/plan.json \
        --evidence output/42110-suspension/evidence/contacts-suspension.json \
        --output output/42110-suspension/plan.json \
        --bodywork output/42110-suspension/bodywork.json --ready

The study must be prepared from the derived MPD written by
`scripts/split_shortcuts.py`, in which each complete shock absorber is an
assembly of its official piston rod, cylinder and spring. The evidence file is
a bounded pyldraw3 contact run over the four corners; it is created on first
use with the selection rule recorded inside it.

Every corner is measured, not typed in. The upper and lower wishbones, the
toe links (rear) or tie rod (front), the UJ-centre-to-CV half-shaft and the
inner coupler liftarms are parallel links with equal pivot spacing, i.e.
parallelograms: the knuckle, hub and wheel translate along an arc without
rotating. The builder asserts that before writing any motion. Each shock
cylinder pivots on its frame pin and aims at its eye on the upper arm; the
piston rod slides in the cylinder and the coil spring is scaled between its
cylinder seat and the rod (`stretch`). Steering and drive are not rigged.

Frame: selected root (42110 - main.ldr), LDU, -Y up, front -Z, the car's left
+X. Controls are wheel-centre rise from the source pose, which is full droop:
every shock sits at its 110 LDU free length.
"""

import argparse
from collections import defaultdict
import hashlib
import json
import math
from pathlib import Path
import re
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
from build_defender_rig import (  # noqa: E402
    BODY_PANEL,
    BODYWORK,
    EXTRA_HIDDEN,
    FLEXIBLE,
    OPENINGS,
    ROOF_LEVEL,
    Geometry,
    bodywork,
    sections,
)
from ldraw_mechanisms import analysis, plan as contract  # noqa: E402
from ldraw_mechanisms.math3d import add, cross, dot, length, mul, sub, unit  # noqa: E402

# Source identities per corner; every position, axis and length is measured.
CORNERS = {
    "fl": dict(label="Front left", upper="0/0/53", lower="0/0/20", bearing="0/0/57",
               wheel=["0/0/65", "0/380", "0/381"], yoke="0/0/27/19", links=["0/0/111/12"],
               shocks=["0/0/79", "0/0/80"]),
    "fr": dict(label="Front right", upper="0/0/54", lower="0/0/19", bearing="0/0/62",
               wheel=["0/0/66", "0/387", "0/386"], yoke="0/0/27/16", links=["0/0/111/11"],
               shocks=["0/0/76", "0/0/77"]),
    "rl": dict(label="Rear left", upper="0/1/88", lower="0/1/47", bearing="0/1/89",
               wheel=["0/1/92", "0/382", "0/383"], yoke="0/1/16", links=["0/1/70", "0/1/71"],
               shocks=["0/1/227", "0/1/229"]),
    "rr": dict(label="Rear right", upper="0/1/104", lower="0/1/39", bearing="0/1/96",
               wheel=["0/1/99", "0/385", "0/384"], yoke="0/1/20", links=["0/1/72", "0/1/73"],
               shocks=["0/1/236", "0/1/237"]),
}
UP = [0.0, -1.0, 0.0]
PARALLEL_TOL = 0.3  # LDU: largest accepted difference between parallelogram link vectors
LINK_LENGTH = 100.0  # every wishbone, toe link, tie rod and half-shaft (asserted, not assumed)
EVIDENCE_RULE = ("non-embedded library parts with |x|>=45, -300<=y<=10 and z in [-400,-200] or [180,380] "
                 "(full-model frame): the four suspension corners and their frame mounts")


def key(s):
    return [int(x) for x in s.split("/")]


def r6(v):
    return [round(x, 6) for x in v]


def evidence(study, path):
    path = Path(path)
    if path.exists():
        return json.loads(path.read_text())

    def inside(n):
        x, y, z = (n["world"][i][3] for i in range(3))
        return abs(x) >= 45 and -300 <= y <= 10 and (-400 <= z <= -200 or 180 <= z <= 380)

    ids = [n["id"] for n in study["source"]["nodes"]
           if n["kind"] == "part" and not n["embedded"] and not n["ref"].lower().startswith("p/") and inside(n)]
    result = analysis.contacts(study["source"], ids, max_instances=2000)
    result["selection"] = EVIDENCE_RULE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result) + "\n")
    return result


class Corner:
    """Measured parallelogram corner in a right-handed in-plane frame (e1, e2=up, n)."""

    def __init__(self, g, name, spec):
        self.g, self.name, self.spec = g, name, spec
        self.A_l, self.B_l, n_l = self.arm(spec["lower"])
        self.A_u, self.B_u, n_u = self.arm(spec["upper"])
        if length(cross(n_l, n_u)) > 1e-3:
            raise ValueError(f"{name}: wishbone axes are not parallel")
        self.v = sub(self.B_l, self.A_l)
        self.v_u = sub(self.B_u, self.A_u)
        if length(sub(self.v, self.v_u)) > PARALLEL_TOL:
            raise ValueError(f"{name}: wishbones are not a parallelogram {self.v} {self.v_u}")
        if abs(length(self.v) - LINK_LENGTH) > 0.1:
            raise ValueError(f"{name}: wishbone length {length(self.v)}")
        # Bump (+theta) lifts the outer ball: choose the axis sign accordingly.
        s = -1.0 if cross(n_l, self.v)[1] > 0 else 1.0
        self.n = mul(n_l, s)
        e2 = unit(sub(UP, mul(self.n, dot(UP, self.n))))
        self.e1, self.e2 = cross(e2, self.n), e2
        self.vx, self.vy = self.flat(self.v)
        if self.vx <= 0:
            raise ValueError(f"{name}: bump sign check failed")

    def arm(self, arm):
        g = self.g
        cup = g.one(arm, "generic")["pos"]
        holes = g.conn(arm, "pin_hole")
        inner = max(holes, key=lambda f: length(sub(f["pos"], cup)))
        axis = unit(inner["axis"])
        pivot = add(inner["pos"], mul(axis, dot(sub(cup, inner["pos"]), axis)))
        return pivot, cup, axis

    def outer_hole(self, arm):
        cup = self.g.one(arm, "generic")["pos"]
        return min(self.g.conn(arm, "pin_hole"), key=lambda f: length(sub(f["pos"], cup)))

    def flat(self, d):
        return dot(d, self.e1), dot(d, self.e2)

    def rise(self, theta):
        return (self.vx * math.sin(theta) + self.vy * math.cos(theta)) - self.vy

    def theta(self, t):
        r = math.hypot(self.vx, self.vy)
        a = math.atan2(self.vy, self.vx)
        return math.asin(math.sin(a) + t / r) - a


def seated(g, part, kinds, candidates, female=("pin_hole", "axle_hole"), tol=0.6, reach=25.0):
    """Parts whose male axle/pin connector lies on one of `part`'s hole lines."""
    out = set()
    for f in g.conn(part):
        if f["kind"] not in female or f["kind"] not in kinds:
            continue
        for q in candidates:
            if q == part:
                continue
            for h in g.conn(q):
                if h["kind"] not in ("pin", "axle"):
                    continue
                d = sub(h["pos"], f["pos"])
                if (abs(abs(dot(unit(f["axis"]), unit(h["axis"]))) - 1) < 1e-3
                        and length(cross(d, unit(f["axis"]))) < tol and abs(dot(d, unit(f["axis"]))) < reach):
                    out.add(q)
    return out


def build(study, ev, max_compression=16.0, stops=None):
    """`stops` maps corners to measured contact limits (LDU of travel) that are lower than the shock limit."""
    g = Geometry(study["source"], ev)
    nodes = g.nodes
    parts = [n["id"] for n in study["source"]["nodes"] if n["kind"] == "part"
             and not n["ref"].lower().startswith("p/")]
    contacts = defaultdict(set)
    for c in ev["contacts"]:
        contacts[c["a"]].add(c["b"])
        contacts[c["b"]].add(c["a"])
    controls, signals, bodies, anchors, checks, connections = {}, {}, {}, {}, [], {}
    corners, review = {}, {}

    def num(v):
        return repr(float(v))

    def signal(name, expr, **variables):
        if len(expr) > 255:
            raise ValueError(f"Expression too long: {name}")
        signals[name] = dict(expression=expr, variables=variables)

    def body(name, instances, origin, axis, sig=None, kind="revolute", parent=None, **extra):
        b = dict(instances=sorted(instances, key=key), kind=kind, origin=r6(origin), axis=r6(unit(axis)))
        if sig:
            b["signal"] = sig
        if parent:
            b["parent"] = parent
        b.update(extra)
        bodies[name] = b

    def anchor(name, b, p):
        anchors[name] = dict(body=b, point=r6(p))
        return name

    def check(name, a, b, tol=0.02):
        measured = length(sub(anchors[a]["point"], anchors[b]["point"]))
        checks.append(dict(kind="distance", name=name, a=a, b=b, length=round(measured, 6), tolerance=tol))

    def edge(kind, a, b, text, note, measurements=None):
        cid = f"susp_{kind}_{a}_{b}".replace("/", "_")
        if len(cid) > 40:
            cid = "susp_" + hashlib.sha256(cid.encode()).hexdigest()[:16]
        connections[cid] = dict(a=a, b=b, kind=kind, status="reviewed", evidence=text, review=note,
                                measurements=measurements or {})

    near = lambda c, r: [q for q in parts if length(sub(g.at(q), c)) < r]  # noqa: E731

    for c, spec in CORNERS.items():
        k = Corner(g, c, spec)
        corners[c] = k
        U, L, K = spec["upper"], spec["lower"], spec["bearing"]
        local = near(k.B_l, 260)
        rod_ids = {f"{s}/0" for s in spec["shocks"]}

        # Lower and upper wishbones, with the parts locked in their axle holes.
        lower = {L} | (seated(g, L, ("axle_hole",), local) - rod_ids)
        upper = {U} | (seated(g, U, ("axle_hole",), local) - rod_ids)
        # Inner coupler: liftarms and axles on both arms' outer pin holes.
        h_l, h_u = k.outer_hole(L), k.outer_hole(U)
        on_l = {q for q in local if any(abs(abs(dot(unit(h_l["axis"]), unit(f["axis"]))) - 1) < 1e-3
                and length(cross(sub(f["pos"], h_l["pos"]), unit(h_l["axis"]))) < 0.6
                and abs(dot(sub(f["pos"], h_l["pos"]), unit(h_l["axis"]))) < 25
                for f in g.conn(q) if f["kind"] in ("axle", "axle_hole"))} - {L, U}
        on_u = {q for q in local if any(abs(abs(dot(unit(h_u["axis"]), unit(f["axis"]))) - 1) < 1e-3
                and length(cross(sub(f["pos"], h_u["pos"]), unit(h_u["axis"]))) < 0.6
                and abs(dot(sub(f["pos"], h_u["pos"]), unit(h_u["axis"]))) < 25
                for f in g.conn(q) if f["kind"] in ("axle", "axle_hole"))} - {L, U}
        liftarms = {q for q in on_l & on_u if "Liftarm" in g.desc(q)}
        coupler = liftarms | {q for q in on_l | on_u if re.match(r"Technic Axle", g.desc(q))}
        if len(liftarms) != 2 or len(coupler) != 4:
            raise ValueError(f"{c}: unexpected coupler {sorted(coupler)}")
        C_l = h_l["pos"]
        if length(sub(sub(h_u["pos"], k.A_u), sub(C_l, k.A_l))) > PARALLEL_TOL:
            raise ValueError(f"{c}: coupler is not a parallelogram")
        # Knuckle: bearing, the ball pins and towball axles in its holes, hub, rim and tyre.
        knuckle = {K} | seated(g, K, ("pin_hole", "axle_hole"), local) | set(spec["wheel"])
        hub_axis = g.one(spec["wheel"][0], "axle_hole")
        for w in spec["wheel"][1:]:
            if length(cross(sub(g.at(w), hub_axis["pos"]), unit(hub_axis["axis"]))) > 0.6:
                raise ValueError(f"{c}: {w} is not on the hub axis")
        # Half-shaft: the output yoke's axle-locked group (yoke, axle, bush, CV spindle driver).
        half = set(g.group(spec["yoke"]))
        cv = next(q for q in half if "Spindle" in g.desc(q))
        uj = g.one(spec["yoke"], "clip")
        uj_c, cv_c = uj["pos"], g.one(cv, "generic")["pos"]
        cross_part = next(q for q in local if "Universal Joint 3L Centre" in g.desc(q)
                          and length(sub(g.at(q), uj_c)) < 0.6)
        in_yoke = next(q for q in local if q != spec["yoke"] and "Universal Joint 3L End" in g.desc(q)
                       and length(sub(g.one(q, "clip")["pos"], uj_c)) < 0.6)
        # The bend (about the wishbone axis) happens on whichever cross arm lies on that axis.
        if abs(abs(dot(unit(uj["axis"]), k.n)) - 1) < 1e-3:
            hinge = (spec["yoke"], cross_part, "Output yoke fork on the cross arm parallel to the wishbone axis.",
                     "The bend changes about this arm only; the cross stays with the input yoke (wheels not driven).")
        elif abs(abs(dot(unit(g.one(in_yoke, "clip")["axis"]), k.n)) - 1) < 1e-3:
            half.add(cross_part)
            hinge = (in_yoke, cross_part, "Input yoke fork on the cross arm parallel to the wishbone axis.",
                     "The cross swings with the output yoke about this arm (wheels not driven).")
        else:
            raise ValueError(f"{c}: no cross arm on the wishbone axis")
        if length(sub(sub(cv_c, uj_c), k.v)) > PARALLEL_TOL:
            raise ValueError(f"{c}: half-shaft is not parallel to the wishbones")
        # Decorative clusters hanging only from one body ride with it (e.g. 0/0/82..86).
        owned_here = (lower | upper | coupler | knuckle | half | set(spec["links"])
                      | {f"{x}/{i}" for x in spec["shocks"] for i in range(3)})

        def dangling(group):
            found = set()
            for seed in sorted(group):
                for start in contacts[seed] - group - owned_here - found:
                    comp, stack = {start}, [start]
                    while stack:
                        for y in contacts[stack.pop()] - group - owned_here:
                            if y not in comp:
                                comp.add(y)
                                stack.append(y)
                    outside = set().union(*(contacts[x] for x in comp)) - comp
                    if len(comp) <= 10 and outside <= group:
                        found |= comp
            return found

        extras = {}
        for name_, grp in (("lower", lower), ("upper", upper), ("knuckle", knuckle)):
            extras[name_] = sorted(dangling(grp), key=key)
            grp |= set(extras[name_])

        th = f"th_{c}"
        t = f"travel_{c}"
        r = math.hypot(k.vx, k.vy)
        a = math.atan2(k.vy, k.vx)
        signal(th, f"asin({num(math.sin(a))}+t/{num(r)})-({num(a)})", t=f"control:{t}")
        body(f"lower_{c}", lower, k.A_l, k.n, th)
        body(f"upper_{c}", upper, k.A_u, k.n, th)
        body(f"knuckle_{c}", knuckle, k.B_l, mul(k.n, -1), th, parent=f"lower_{c}")
        body(f"coupler_{c}", coupler, C_l, mul(k.n, -1), th, parent=f"lower_{c}")
        body(f"halfshaft_{c}", half, uj_c, k.n, th)

        anchor(f"ua_pivot_{c}", f"upper_{c}", k.A_u)
        anchor(f"ua_ball_{c}", f"upper_{c}", k.B_u)
        anchor(f"la_pivot_{c}", f"lower_{c}", k.A_l)
        anchor(f"kn_upper_{c}", f"knuckle_{c}", k.B_u)
        anchor(f"kn_lower_{c}", f"knuckle_{c}", k.B_l)
        anchor(f"kn_cv_{c}", f"knuckle_{c}", cv_c)
        anchor(f"cp_upper_{c}", f"coupler_{c}", h_u["pos"])
        anchor(f"hs_uj_{c}", f"halfshaft_{c}", uj_c)
        anchor(f"hs_cv_{c}", f"halfshaft_{c}", cv_c)
        check(f"upper_ball_{c}", f"kn_upper_{c}", f"ua_pivot_{c}")
        check(f"lower_ball_{c}", f"kn_lower_{c}", f"la_pivot_{c}")
        check(f"coupler_{c}", f"cp_upper_{c}", f"ua_pivot_{c}")
        check(f"halfshaft_{c}", f"kn_cv_{c}", f"hs_uj_{c}")
        check(f"halfshaft_end_{c}", f"hs_cv_{c}", f"kn_lower_{c}")

        # Toe links (rear) or tie rod (front): ball links parallel to the wishbones.
        for j, link in enumerate(spec["links"]):
            balls = [f["pos"] for f in g.conn(link, "generic")]
            outer = min(balls, key=lambda p: length(sub(p, k.B_l)))
            inner = max(balls, key=lambda p: length(sub(p, k.B_l)))
            if length(sub(sub(outer, inner), k.v)) > PARALLEL_TOL:
                raise ValueError(f"{c}: link {link} is not parallel to the wishbones")
            ball, gap = min(((q, length(sub(f["pos"], outer))) for q in knuckle for f in g.conn(q, "generic")),
                            key=lambda x: x[1])
            if gap > 3.0:
                raise ValueError(f"{c}: no knuckle towball under link {link}")
            name = f"link_{c}{j}"
            body(name, [link], inner, k.n, th)
            anchor(f"lk_inner_{c}{j}", name, inner)
            anchor(f"lk_outer_{c}{j}", name, outer)
            anchor(f"kn_ball_{c}{j}", f"knuckle_{c}", outer)
            check(f"link_{c}{j}", f"kn_ball_{c}{j}", f"lk_inner_{c}{j}")
            check(f"link_end_{c}{j}", f"lk_outer_{c}{j}", f"kn_lower_{c}")
            edge("ball", link, ball, "Steering-link socket on the knuckle towball (generic connectors).",
                 f"Link {length(sub(outer, inner)):.3f} LDU, parallel to the wishbones: no bump steer. "
                 f"Socket-to-ball offset in the source: {gap:.3f} LDU; closure uses the socket point.")

        # Shocks: cylinder pivots on the frame pin, rod rides the upper-arm axle, spring scales.
        shock_rows = []
        for j, s in enumerate(spec["shocks"]):
            rod, cyl, spring = f"{s}/0", f"{s}/1", f"{s}/2"
            top = g.one(cyl, "pin_hole")
            eye = g.one(rod, "pin_hole")
            T, E = top["pos"], eye["pos"]
            if abs(abs(dot(unit(top["axis"]), k.n)) - 1) > 1e-3:
                raise ValueError(f"{c}: shock {s} top pin is not parallel to the wishbone axis")
            L0 = length(sub(E, T))
            d0 = unit(sub(E, T))
            px, py = k.flat(sub(E, k.A_u))
            qx, qy = k.flat(sub(k.A_u, T))
            h = dot(sub(E, T), k.n)
            spring_len = SPRING_LENGTH[nodes[spring]["ref"].lower()]
            seat = [nodes[spring]["world"][i][3] for i in range(3)]
            tag = f"{c}{j}"
            signal(f"wx_{tag}", f"{num(qx)}+{num(px)}*cos(a)-({num(py)})*sin(a)", a=f"signal:{th}")
            signal(f"wy_{tag}", f"{num(qy)}+{num(px)}*sin(a)+({num(py)})*cos(a)", a=f"signal:{th}")
            w0x, w0y = qx + px, qy + py
            signal(f"ang_{tag}", f"atan2({num(w0x)}*y-({num(w0y)})*x,{num(w0x)}*x+({num(w0y)})*y)",
                   x=f"signal:wx_{tag}", y=f"signal:wy_{tag}")
            signal(f"ext_{tag}", f"sqrt(x*x+y*y+{num(h * h)})-{num(L0)}",
                   x=f"signal:wx_{tag}", y=f"signal:wy_{tag}")
            signal(f"k_{tag}", f"({num(spring_len)}+e)/{num(spring_len)}", e=f"signal:ext_{tag}")
            body(f"cyl_{tag}", [cyl], T, k.n, f"ang_{tag}")
            body(f"rod_{tag}", [rod], E, d0, f"ext_{tag}", kind="prismatic", parent=f"cyl_{tag}")
            body(f"spring_{tag}", [spring], seat, d0, f"k_{tag}", kind="stretch", parent=f"cyl_{tag}")
            anchor(f"rod_eye_{tag}", f"rod_{tag}", E)
            anchor(f"ua_eye_{tag}", f"upper_{c}", E)
            check(f"shock_pivot_{tag}", f"rod_eye_{tag}", f"ua_pivot_{c}")
            check(f"shock_ball_{tag}", f"rod_eye_{tag}", f"ua_ball_{c}")
            # The spring's free end must stay on the rod: seat + scaled length = rest end + extension.
            shock_rows.append(dict(shock=s, top=r6(T), eye=r6(E), free_length=round(L0, 4),
                                   out_of_plane=round(h, 4), spring=spring, spring_length=spring_len,
                                   spring_seat_from_top=round(dot(sub(seat, T), d0), 4)))
            axle = next(iter(seated(g, rod, ("pin_hole",), local) & upper), None)
            pin = next(iter(seated(g, cyl, ("pin_hole",), local)), None)
            if axle is None or pin is None:
                raise ValueError(f"{c}: shock {s} mounts not found")
            edge("revolute", cyl, pin, "Cylinder eye on a frame axle (connector line).",
                 "Cylinder pivots about the frame pin, parallel to the wishbone axis.")
            edge("revolute", rod, axle, "Rod eye on the axle locked in the upper wishbone.",
                 f"Eye {length(sub(E, k.A_u)):.3f} LDU from the upper pivot, on the arm line.")
            edge("prismatic", rod, cyl, "Official shortcut sub-parts: piston rod slides in the cylinder.",
                 f"Free length {L0:.3f} LDU at the source pose (full extension).")

        for arm, pivot in ((U, k.A_u), (L, k.A_l)):
            axle = next(iter(seated(g, arm, ("pin_hole",), near(pivot, 40))), None)
            if axle:
                edge("revolute", arm, axle, "Wishbone inner pin holes on a frame axle (connector line).",
                     "Pivot axis parallel to the other wishbone; arm length "
                     f"{length(k.v):.3f} LDU.")
        for arm in (U, L):
            cup = g.one(arm, "generic")["pos"]
            pin, gap = min(((q, length(sub(f["pos"], cup))) for q in knuckle for f in g.conn(q, "generic")),
                           key=lambda x: x[1])
            if gap > 3.0:
                raise ValueError(f"{c}: no towball under the {arm} cup")
            edge("ball", arm, pin, "Wishbone cup on a towball pin seated in the knuckle bearing.",
                 f"Ball joint, cup-to-ball offset {gap:.3f} LDU in the source; the parallelogram keeps the "
                 "knuckle orientation fixed.")
        edge("revolute", *hinge)
        travel_limit = bisect_travel(k, shock_rows, max_compression)
        corners[c] = k
        review[c] = dict(
            label=spec["label"], pivots=dict(upper=r6(k.A_u), lower=r6(k.A_l)), balls=dict(upper=r6(k.B_u),
            lower=r6(k.B_l)), axis=r6(k.n), arm_vector=r6(k.v), arm_vector_upper=r6(k.v_u),
            arm_length=round(length(k.v), 4), uj_centre=r6(uj_c), cv_centre=r6(cv_c),
            coupler_holes=[r6(C_l), r6(h_u["pos"])], shocks=shock_rows,
            travel_for_max_compression=round(travel_limit, 3), dangling_clusters=extras,
            members=dict(lower=sorted(lower, key=key), upper=sorted(upper, key=key),
                         knuckle=sorted(knuckle, key=key), coupler=sorted(coupler, key=key),
                         halfshaft=sorted(half, key=key)))
    stops = stops or {}
    limits = {}
    for c in corners:
        limits[c] = math.floor(review[c]["travel_for_max_compression"] * 2) / 2
        if c in stops:
            limits[c] = min(limits[c], float(stops[c]))
        review[c]["travel_limit"] = limits[c]
        controls[f"travel_{c}"] = dict(default=0.0, min=0.0, max=float(limits[c]), unit="ldu",
                                       description=f"{CORNERS[c]['label']} wheel rise (bump) from full droop")
    return dict(controls=controls, signals=signals, bodies=bodies, anchors=anchors, checks=checks,
                connections=connections, review=review, corners=corners, limits=limits, stops=stops,
                geometry=g)


def bisect_travel(k, shock_rows, max_compression):
    """Wheel rise at which the most compressed shock of this corner reaches `max_compression`."""

    def compression(t):
        th = k.theta(t)
        worst = 0.0
        for s in shock_rows:
            E, T = s["eye"], s["top"]
            px, py = k.flat(sub(E, k.A_u))
            qx, qy = k.flat(sub(k.A_u, T))
            wx = qx + px * math.cos(th) - py * math.sin(th)
            wy = qy + px * math.sin(th) + py * math.cos(th)
            worst = max(worst, s["free_length"] - math.sqrt(wx * wx + wy * wy + s["out_of_plane"] ** 2))
        return worst

    lo, hi = 0.0, 0.9 * math.hypot(k.vx, k.vy)
    if compression(hi) < max_compression:
        return hi
    for _ in range(80):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if compression(mid) < max_compression else (lo, mid)
    return lo


def spring_lengths():
    db = sqlite3.connect(f"file:{ROOT / 'data/ldraw-info.db'}?mode=ro", uri=True)
    rows = db.execute("select alias, min_y, max_y from PART_BBOXES where alias in ('22977.dat','41837.dat')")
    return {a.lower(): hi - lo for a, lo, hi in rows}


SPRING_LENGTH = spring_lengths()


def views(plan, out, hidden):
    g = out["geometry"]
    owned = {i for b in plan["bodies"].values() for i in b["instances"]}
    v = {}

    def view(name, label, body_names, inputs, outputs, text, notes=(), parts=(), disposition="planned"):
        v[name] = dict(label=label, parts=sorted(parts, key=key), bodies=list(body_names), inputs=list(inputs),
                       outputs=list(outputs), notes=list(notes), disposition=disposition, review=text)

    for c, spec in CORNERS.items():
        r = out["review"][c]
        names = [b for b in plan["bodies"] if b.endswith("_" + c) or re.search(rf"_{c}\d$", b)]
        view(f"suspension_{c}", f"{spec['label']} double-wishbone suspension", names,
             [f"control:travel_{c}"], [f"body:knuckle_{c}"],
             "Measured parallelogram: wishbones, links, half-shaft and inner coupler are parallel "
             f"{r['arm_length']:.2f} LDU links, so the knuckle and wheel translate. Shock cylinders pivot on "
             "the frame; rods follow the upper-arm eye; springs scale between their seats.",
             [f"Shock free length {r['shocks'][0]['free_length']} LDU = source pose (full droop).",
              f"Travel for {out['max_compression']} LDU shock compression: {r['travel_for_max_compression']} LDU.",
              f"Travel limit: {r['travel_limit']} LDU"
              + (" (contact stop measured by clearance)." if c in out["stops"] else " (shock compression).")])
    remaining = set(plan["discovery"]["mechanical_parts"]) - owned
    groups = []

    def take(pred):
        hit = sorted((i for i in remaining if pred(i)), key=key)
        remaining.difference_update(hit)
        return hit

    flex_secs = [f.removeprefix("42110 - ").removesuffix(".ldr") for f in FLEXIBLE]
    groups.append(("flexible", "Rope, hose, bands and hook",
                   take(lambda i: any(s in flex_secs for s in sections(plan, i)) or i == "0/98"), "deferred",
                   "Flexible LDCad paths and the winch hook; outside this suspension-only study."))
    groups.append(("body_openings", "Doors, bonnet, tailgate, roof trunk, side case and ladder",
                   take(lambda i: any(s in OPENINGS for s in sections(plan, i))), "deferred",
                   "Bodywork is hidden; hinges are outside this suspension-only study."))
    groups.append(("bodywork", "Hidden bodywork axles and pins", take(lambda i: i in hidden), "deferred",
                   "Structural parts inside hidden body sections; not reviewed in this study."))
    groups.append(("drivetrain_steering", "Drivetrain, gearboxes, engine, steering and winch",
                   take(lambda i: sections(plan, i)[:1] in (["frontaxle"], ["rearaxle"]) or
                        any(s in ("frontgearbox", "reargearbox", "engine", "camshaft", "steerrack", "winchgears",
                                  "shiftplate") for s in sections(plan, i))),
                   "deferred",
                   "Rigged and animated separately in output/42110/plan.json (steering, drive, gearboxes, engine, "
                   "winch); held at zero here, so the suspension study does not claim their motion."))
    groups.append(("supports", "Frame axles, pins and connectors", sorted(remaining, key=key), "deferred",
                   "Chassis supports, including the wishbone pivot axles, shock top axles and frame liftarms; "
                   "static in this study and not individually reviewed beyond the corner mounts."))
    for name, label, parts, disposition, text in groups:
        if parts:
            view(name, label, [], [], [], text, [f"Parts: {len(parts)}."], parts, disposition)
    return v


def notes(out):
    return [
        "Source: output/42110-suspension/source/42110-1-shocks-split.mpd, derived from data/models-annotated/"
        "42110-1.mpd (Philippe Hurbain) by scripts/split_shortcuts.py: the 8 complete shock absorbers became "
        "assemblies of their official piston rod, cylinder and spring; every other occurrence is unchanged.",
        "Frame: LDU, -Y up, front -Z, car's left +X. Controls are wheel-centre rise from the source pose, which is "
        "full droop (each shock at its 110 LDU free length), so travel is bump only.",
        "Each corner is a measured parallelogram (wishbones, links, half-shaft and inner coupler are parallel "
        "100 LDU links, pivots 80 LDU apart): knuckles translate without camber or toe change; half-shafts do not "
        "plunge.",
        f"Travel limits (LDU) {out['limits']}: rear = the travel that compresses a shock by "
        f"{out['max_compression']} LDU (the measured piston-to-bore-floor stroke is 20 LDU); front = "
        f"{out['stops'] or 'none'}, where the round tile and plate on each front lower arm reach the static "
        "inner pivot liftarm (sampled clearance, then a 0.25 LDU BVH sweep: stop-sweep.json). Whether that "
        "cluster is an intended bump stop is not established.",
        "Springs use the `stretch` kind: scaled along the shock axis between the cylinder seat and the rod.",
        "Steering, drive, wheel spin and the drivetrain are not rigged in this plan (see output/42110).",
        "Kinematic only: no spring rates, damping, weight transfer or contact forces. Clearance is sampled, not "
        "proven.",
    ]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--study", required=True)
    parser.add_argument("--evidence", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--bodywork", required=True)
    parser.add_argument("--review", help="Measured geometry and membership report (JSON)")
    parser.add_argument("--max-compression", type=float, default=16.0,
                        help="Shock compression (LDU) that sets the travel limit; stroke is 20 LDU")
    parser.add_argument("--stop", action="append", default=[], metavar="CORNER=LDU",
                        help="Measured contact limit for a corner (from clearance), e.g. fl=30.5")
    parser.add_argument("--ready", action="store_true")
    args = parser.parse_args()
    study = contract.load(args.study)
    ev = evidence(study, args.evidence)
    stops = {k: float(v) for k, v in (s.split("=", 1) for s in args.stop)}
    if set(stops) - set(CORNERS):
        raise SystemExit(f"Unknown corner in --stop: {sorted(set(stops) - set(CORNERS))}")
    out = build(study, ev, args.max_compression, stops)
    out["max_compression"] = args.max_compression
    plan = dict(study)
    plan.update(name="defender_42110_suspension", controls=out["controls"], signals=out["signals"],
                bodies=out["bodies"], anchors=out["anchors"], checks=out["checks"], status="draft",
                notes=notes(out))
    plan["connections"] = {**study.get("connections", {}), **out["connections"]}
    hidden = bodywork(plan, out["bodies"])
    plan["mechanisms"] = {}
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
    if args.review:
        Path(args.review).write_text(json.dumps(dict(corners=out["review"], limits=out["limits"], stops=stops,
                                                     max_compression=args.max_compression), indent=1) + "\n")
    owned = sum(len(b["instances"]) for b in plan["bodies"].values())
    print(json.dumps(dict(plan=args.output, status=plan["status"], bodies=len(plan["bodies"]), moving_parts=owned,
                          signals=len(plan["signals"]), checks=len(plan["checks"]), travel_limits=out["limits"],
                          hidden=len(hidden), views={k: m["disposition"] for k, m in plan["mechanisms"].items()})))


if __name__ == "__main__":
    main()
