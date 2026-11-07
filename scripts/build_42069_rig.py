#!/usr/bin/env python3
"""Author the in-place motion plan for 42069-1 (Extreme Adventure, four track pods).

    scripts/build_42069_rig.py --study output/42069/study/plan.json \
        --evidence output/42069/evidence/contacts-mechanical.json \
        --output output/42069/plan.json --report output/42069/kinematics.json --ready

Source: output/42069/source/42069-1-springs.mpd, a copy of
data/models-annotated/42069-1.mpd (Philippe Hurbain) in which the four
LDCad-generated spring meshes are renamed from `.ldr` to embedded `.dat`
parts, so each spring is one physical leaf that can stretch. No other line,
placement or occurrence ID changes.

Evidence: bounded pyldraw3 contacts (axle-in-axle-hole contacts give keyed
groups), library connector frames and the source matrices. Every ratio, sign,
pivot, link length and tread slot is computed here and asserted.

Frame: LDU, -Y up, front -Z, the vehicle's left +X. The vehicle never moves:
tracks circulate and wheels turn in place. Angles are radians, right-hand
rule about each body axis; values are offsets from the source pose.
"""

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
from ldraw_mechanisms import linkages, plan as contract  # noqa: E402
from ldraw_mechanisms.math3d import (  # noqa: E402
    add,
    cross,
    dot,
    inverse,
    length,
    matmul,
    mul,
    point,
    direction,
    rack_ratio,
    signed_gear_ratio,
    sub,
    unit,
)

X, Y, Z = [1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]
UP = [0.0, -1.0, 0.0]
PI = math.pi
SPROCKET_TEETH = 10  # 57519: ten tooth subparts (s01) at 36 degree steps
LINK_PITCH = 30.0  # measured joint-to-joint distance of the 88323 tread links
SUBROWS = 8  # path table rows per tread slot
ROLL_LIMIT = 0.064  # rear axle roll (rad): keeps the extending shock at or below its 110 LDU free length
SHOCK_FREE = 110.0  # 73129/41838 (complete 6.5L shock): rod eye 110 LDU from the cylinder eye
SHOCK_MIN = 90.0  # assumed shortest eye distance used by the animation (20 LDU stroke)
POD_LIMIT = 0.28  # rear pods: frames meet the axle frame at 0.35 rad (clearance sweep)
POD_LIMIT_FRONT = 0.22  # front pods: frame meets the knuckle liftarms at 0.28 rad
STEER_RACK_LIMIT = 16.0  # LDU of rack each way; at 20-24 the pinion-side UJ yoke clips the column axle (clearance sweep)


def r6(v):
    return [round(x, 6) for x in v]


def idsort(ids):
    return sorted(ids, key=lambda s: [int(x) for x in s.split("/")])


def build(study, evidence):
    plan = copy.deepcopy(study)
    g = Geometry(plan["source"], evidence)
    nodes = g.nodes
    at, conn = g.at, g.conn
    controls, signals, bodies, anchors, checks = {}, {}, {}, {}, []
    connections = plan["connections"]
    review = defaultdict(list)
    report = {}

    def raw(i):
        return nodes[i]["world"]

    def pos(i):
        return [raw(i)[k][3] for k in range(3)]

    def control(name, lo, hi, description, unit_name="radian", default=0.0):
        controls[name] = dict(default=default, min=lo, max=hi, unit=unit_name, description=description)
        return "control:" + name

    def signal(name, expr, **variables):
        if len(expr) > 255:
            raise ValueError(f"{name}: expression too long ({len(expr)})")
        if name in signals:
            raise ValueError(f"duplicate signal {name}")
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
        if not instances:
            raise ValueError(f"{name}: no parts")
        b = dict(instances=idsort(instances), kind=kind, origin=r6(origin), axis=r6(unit(axis)), **extra)
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

    def clamped(name):
        c = controls[name]
        return signal(name + "_v", f"clamp(v,{c['min']!r},{c['max']!r})", v="control:" + name)

    def local(i, p):
        return point(inverse(raw(i)), p)

    def local_dir(i, d):
        return unit(direction(inverse(raw(i)), d))

    def coax(name, a, b, p, axis, tol=0.05, deg=0.2, axial=None):
        """Coaxial check on the world rest line (p, axis), expressed part-locally."""
        c = dict(
            kind="coaxial",
            name=name,
            a=dict(instance=a, point=r6(local(a, p)), axis=r6(local_dir(a, axis))),
            b=dict(instance=b, point=r6(local(b, p)), axis=r6(local_dir(b, axis))),
            tolerance_ldu=tol,
            tolerance_degrees=deg,
        )
        if axial is not None:
            c["axial_tolerance_ldu"] = axial
        checks.append(c)

    def rotation(name, terms, carrier=None, tol=2e-3):  # float32 drivers at +-560 rad resolve ~6e-5 rad per term
        c = dict(
            kind="rotation",
            name=name,
            terms=[dict(instance=i, axis=r6(unit(a)), coefficient=k) for i, a, k in terms],
            tolerance_radians=tol,
            axis_tolerance_degrees=0.01,
        )
        if carrier:
            c["carrier"] = carrier
        checks.append(c)

    def gear_axis(i, prefer=(X, Y, Z)):
        holes = conn(i, "axle_hole") or conn(i, "pin_hole") or conn(i, "axle")
        a = holes[0]["axis"]
        for ref in prefer:
            if abs(dot(a, ref)) > 0.999:
                return ref
        raise ValueError(f"{i}: gear axis {a} not along X/Y/Z")

    def spur(a, ta, b, tb, view, tol=0.6):
        pa, pb = at(a), at(b)
        axis = gear_axis(a)
        if abs(dot(axis, gear_axis(b))) < 0.999:
            raise ValueError(f"{a}-{b}: axes not parallel")
        d = sub(pb, pa)
        axial = dot(d, axis)
        radial = length(sub(d, mul(axis, axial)))
        nominal = 1.25 * (ta + tb)
        if abs(axial) > 2.0 or abs(radial - nominal) > tol:
            raise ValueError(f"{a}-{b}: not a coplanar {ta}/{tb} mesh ({radial:.2f} vs {nominal}, axial {axial:.2f})")
        ratio = signed_gear_ratio(axis, pa, ta, axis, pb, tb)
        edge("gear_mesh", a, b, "Parallel axes from connector frames; centre distance against 1.25 LDU/tooth",
             f"Reviewed {ta}T/{tb}T external mesh, ratio {ratio:+.4f} about the shared axis",
             dict(centre_distance_ldu=round(radial, 3), nominal_ldu=nominal, axial_offset_ldu=round(axial, 3)))
        review[view].append(f"{a} {ta}T / {b} {tb}T: {radial:.2f} LDU (nominal {nominal}), ratio {ratio:+.4f}")
        return ratio, axis

    def bevel_mesh(a, ta, pa, axis_a, b, tb, pb, axis_b, view):
        if abs(dot(axis_a, axis_b)) > 1e-3:
            raise ValueError(f"{a}-{b}: bevel axes not perpendicular")
        w = sub(pa, pb)
        bd, dd, ee = dot(axis_a, axis_b), dot(axis_a, w), dot(axis_b, w)
        s = (bd * ee - dd) / (1 - bd * bd)
        t = (ee - bd * dd) / (1 - bd * bd)
        qa, qb = add(pa, mul(axis_a, s)), add(pb, mul(axis_b, t))
        if length(sub(qa, qb)) > 0.6:
            raise ValueError(f"{a}-{b}: bevel axes do not intersect ({length(sub(qa, qb)):.2f})")
        apex = mul(add(qa, qb), 0.5)
        out_a, out_b = unit(sub(pa, apex)), unit(sub(pb, apex))
        if abs(abs(dot(out_a, axis_a)) - 1) > 1e-3 or abs(abs(dot(out_b, axis_b)) - 1) > 1e-3:
            raise ValueError(f"{a}-{b}: bevel centre not on its axis")
        ratio = -ta / tb
        edge("gear_mesh", a, b, "Perpendicular axes meeting at a common apex (closest approach measured)",
             f"Reviewed {ta}T/{tb}T bevel mesh, w_b = {ratio:+.4f} w_a about the outward axes",
             dict(apex=r6(apex), a_from_apex_ldu=round(length(sub(pa, apex)), 3),
                  b_from_apex_ldu=round(length(sub(pb, apex)), 3)))
        review[view].append(f"{a} {ta}T / {b} {tb}T bevel, apex {r6(apex)}")
        return out_a, out_b, ratio

    def bevel_ratio(a, ta, axis_a, b, tb, axis_b, view, a_centre=None, b_centre=None):
        oa, ob, ratio = bevel_mesh(a, ta, a_centre or at(a), axis_a, b, tb, b_centre or at(b), axis_b, view)
        return dot(axis_b, ob) * ratio * dot(axis_a, oa), oa, ob

    def group(seed, extra=(), drop=()):
        return g.group(seed, extra, drop)

    def clip(i):
        return g.one(i, "clip")["axis"]

    # ================================================================ controls
    control("drive", -400.0, 400.0,
            "Track drive: rear sprocket angle about +X (mean of both rear side gears); positive drives forward, "
            "the bottom run moves rearward. The vehicle stays in place")
    control("diff_front", -60.0, 60.0, "Front differential split: left (+X) sprocket +, right sprocket - (half difference)")
    control("diff_rear", -60.0, 60.0, "Rear differential split: left (+X) sprocket +, right sprocket - (half difference)")
    control("steering", -1.0, 1.0, "placeholder")  # range and meaning set after the rack is measured
    for pod in ("fl", "fr", "rl", "rr"):
        lim = POD_LIMIT_FRONT if pod.startswith("f") else POD_LIMIT
        control(f"pod_{pod}", -lim, lim,
                f"Track pod {pod.upper()} pitch about +X on its turntable; positive tips the pod's front end down")
    control("rear_roll", -ROLL_LIMIT, ROLL_LIMIT,
            "Rear axle articulation about its measured roll axis; positive lifts the left (+X) side")
    drive = clamped("drive")
    dfr, drr = clamped("diff_front"), clamped("diff_rear")
    roll = clamped("rear_roll")
    pods = {p: clamped(f"pod_{p}") for p in ("fl", "fr", "rl", "rr")}

    # ========================================================== rear axle roll
    # Trailing arms: chassis pins (axis X) and towballs on the axle. The roll mode
    # that keeps both balls on their arm circles (and the propshaft length) to first
    # order turns about the arm direction through the midpoint of the two balls.
    arm = dict(l=("612/108", "612/107", "612/226"), r=("612/112", "612/111", "612/225"))
    balls, pivots = {}, {}
    for s, (arm_id, ball_id, pin_id) in arm.items():
        balls[s] = g.one(ball_id, "generic")["pos"]
        pivots[s] = g.one(pin_id, "pin")["pos"]
        if abs(abs(dot(g.one(pin_id, "pin")["axis"], X)) - 1) > 1e-6:
            raise ValueError(f"{pin_id}: arm pin not along X")
    radial = sub(balls["l"], pivots["l"])
    radial_r = sub(balls["r"], pivots["r"])
    if length(sub(sub(radial, radial_r), [2 * radial[0], 0, 0])) > 0.05 or abs(radial[0]) > 0.05:
        raise ValueError("Rear arms are not mirror images")
    roll_axis = mul(unit(radial), -1)  # points forward and up
    roll_origin = mul(add(balls["l"], balls["r"]), 0.5)
    if dot(cross(roll_axis, X), UP) <= 0:
        raise ValueError("Positive roll must lift the left side")
    review["rear_suspension"].append(
        f"Roll axis through ball midpoint {r6(roll_origin)} along {r6(roll_axis)} (trailing-arm direction); "
        "first-order exact for both arm circles and the propshaft length")
    signal("roll_c", "cos(a)", a=roll)
    signal("roll_s", "sin(a)", a=roll)

    def rolled(prefix, p0):
        """Signals for a rear-axle point rotated by the roll (Rodrigues, exact)."""
        r = sub(p0, roll_origin)
        dxr = cross(roll_axis, r)
        dr = dot(roll_axis, r)
        names = []
        for k, axn in enumerate("xyz"):
            names.append(signal(
                f"{prefix}_{axn}",
                f"{num(roll_origin[k] + dr * roll_axis[k])}+{num(r[k] - dr * roll_axis[k])}*c+{num(dxr[k])}*s",
                c="roll_c", s="roll_s"))
        return names

    rear_parts = [i for i, n in nodes.items() if n["kind"] == "part" and i.startswith("612/")]

    # ============================================================ track loops
    def tread_loop(section):
        ids = [i for i in rear_parts + [i for i in nodes if i.startswith("617/")]
               if i.startswith(section + "/") and nodes[i]["kind"] == "part"]
        links = [i for i in idsort(ids) if nodes[i]["ref"].endswith("88323.dat")]
        pads = [i for i in idsort(ids) if nodes[i]["ref"].endswith("24375.dat")]
        if len(links) != 25 or len(pads) != 13:
            raise ValueError(f"{section}: expected 25 links and 13 pads")
        return links, pads

    def tread(tag, section, parent, rel_signal):
        links, pads = tread_loop(section)
        J = [pos(i) for i in links]
        n = len(J)
        normal = unit(cross(sub(J[1], J[0]), sub(J[2], J[1])))
        # Each link's local -Z points to the next joint, local X is the loop normal.
        pitch_dev, dir_dev = 0.0, 0.0
        for k, i in enumerate(links):
            R = raw(i)
            nxt = J[(k + 1) % n]
            pitch_dev = max(pitch_dev, abs(length(sub(nxt, J[k])) - LINK_PITCH))
            loc = point(inverse(R), nxt)
            dir_dev = max(dir_dev, math.degrees(math.acos(max(-1, min(1, -loc[2] / length(loc))))))
        if pitch_dev > 0.6 or dir_dev > 1.0:
            raise ValueError(f"{tag}: irregular joints (pitch {pitch_dev:.3f} LDU, direction {dir_dev:.3f} deg)")
            if abs(abs(dot(direction(R, X), normal)) - 1) > 1e-3:
                raise ValueError(f"{i}: link X is not the loop normal")
        normal = unit(direction(raw(links[0]), X))
        # Pads ride the link whose frame holds them at local (+-20, -14, -17).
        owner = {}
        for p in pads:
            hits = [i for i in links if length(sub([abs(v) for v in local(i, pos(p))], [20, 14, 17])) < 0.1]
            if len(hits) != 1:
                raise ValueError(f"{p}: pad owner ambiguous {hits}")
            owner.setdefault(hits[0], []).append(p)
        # Joint polygon in the loop plane; angle of a direction about the normal.
        e1 = unit(sub(J[1], J[0]))
        e2 = cross(normal, e1)

        def ang(v):
            return math.atan2(dot(v, e2), dot(v, e1))

        def on_poly(e, f):
            a, b = J[e % n], J[(e + 1) % n]
            return add(a, mul(sub(b, a), f))

        def walk(e, f, pitch):
            """Next polygon point exactly `pitch` ahead of edge e at fraction f."""
            p = on_poly(e, f)
            for step in range(4):
                a, b = J[(e + step) % n], J[(e + step + 1) % n]
                ab, ap = sub(b, a), sub(a, p)
                qa, qb, qc = dot(ab, ab), 2 * dot(ab, ap), dot(ap, ap) - pitch ** 2
                disc = qb * qb - 4 * qa * qc
                if disc < 0:
                    continue
                for root in sorted(((-qb - math.sqrt(disc)) / (2 * qa), (-qb + math.sqrt(disc)) / (2 * qa))):
                    lo = f + 1e-12 if step == 0 else 0.0
                    if lo <= root <= 1.0:
                        return e + step, root
            raise ValueError(f"{tag}: chain walk failed")

        def chain(t, pitch):
            e = math.floor(t)
            pts = [(e, t - e)]
            for _ in range(n):
                pts.append(walk(*pts[-1], pitch))
            return pts

        def overshoot(t, pitch):
            """Polygon parameter of the 25th walked point beyond t + 25 (slots)."""
            e, f = chain(t, pitch)[-1]
            return e + f - (t + n)

        def config(t):
            """Joints of links 0..24, link 0 at slot parameter t, equal chords c closing the loop."""
            lo, hi = LINK_PITCH - 3.0, LINK_PITCH + 1.0
            flo, fhi = overshoot(t, lo), overshoot(t, hi)
            if flo > 0 or fhi < 0:
                raise ValueError(f"{tag}: closing chord not bracketed at t={t}")
            for _ in range(60):
                mid = (lo + hi) / 2
                if overshoot(t, mid) > 0:
                    hi = mid
                else:
                    lo = mid
            c = (lo + hi) / 2
            pts = chain(t, c)[:n]
            return [on_poly(e_, f_) for e_, f_ in pts], c

        rows_t = [j / SUBROWS for j in range(n * SUBROWS + 1)]
        solved = [config(t) for t in rows_t]
        configs = [pts for pts, _ in solved]
        chords = [c for _, c in solved]
        rest_err = max(length(sub(configs[0][m], J[m])) for m in range(n))
        if rest_err > 0.6:
            raise ValueError(f"{tag}: chain walk does not reproduce the source joints ({rest_err:.3f})")
        worst_gap = 0.0
        closing = max(abs(c - LINK_PITCH) for c in chords)
        names = []
        tables = []
        for k, i in enumerate(links):
            o_k, d_k = J[k], unit(sub(J[(k + 1) % n], J[k]))
            x_k = d_k
            y_k = cross(normal, x_k)
            a_k = ang(d_k)
            rows, prev = [], a_k
            for j, pts in enumerate(configs):
                o, front = pts[k], pts[(k + 1) % n]
                a = ang(sub(front, o))
                while a - prev > PI:
                    a -= 2 * PI
                while a - prev < -PI:
                    a += 2 * PI
                prev = a
                u = sub(o, o_k)
                rows.append([dot(u, x_k), dot(u, y_k), a - a_k])
            turns = (rows[-1][2] - rows[0][2]) / (2 * PI)
            if abs(abs(turns) - 1) > 1e-9 or length(sub(rows[-1][:2], rows[0][:2])) > 1e-9:
                raise ValueError(f"{tag}: link {k} does not close its loop ({turns}, {rows[-1][:2]})")
            rows[0] = [0.0, 0.0, 0.0]
            rows[-1] = [0.0, 0.0, round(turns) * 2 * PI]
            tables.append((k, o_k, x_k, y_k, rows))
            name = f"tread_{tag}_{k:02d}"
            body(name, [i] + owner.get(i, []), o_k, normal, rel_signal, kind="path", parent=parent,
                 x_hint=r6(x_k), path=[r6(r) for r in rows[:-1]] + [rows[-1]])
            names.append(name)

        def world(k, t):
            """Interpolated pose (origin, unit direction) of link k at table position t (rows)."""
            _, o_k, x_k, y_k, rows = tables[k]
            i0 = min(int(math.floor(t)), len(rows) - 2)
            f = t - i0
            r = [rows[i0][c] + (rows[i0 + 1][c] - rows[i0][c]) * f for c in range(3)]
            o = add(o_k, add(mul(x_k, r[0]), mul(y_k, r[1])))
            d = add(mul(x_k, math.cos(r[2])), mul(y_k, math.sin(r[2])))
            return o, d

        spacing = [length(sub(J[(k + 1) % n], J[k])) for k in range(n)]
        pair_gap = [0.0] * n
        for j in range(len(rows_t) - 1):
            for frac in (0.0, 0.5):
                t = j + frac
                for k in range(n):
                    o, d = world(k, t)
                    o2, _ = world((k + 1) % n, t)
                    pair_gap[k] = max(pair_gap[k], length(sub(add(o, mul(d, spacing[k])), o2)))
        worst_gap = max(pair_gap)
        # Chain closure: each link's front joint against the next link's rear joint.
        for k, i in enumerate(links):
            nxt = links[(k + 1) % n]
            tol = pair_gap[k]
            coax(f"tread_{tag}_joint_{k:02d}", i, nxt, J[(k + 1) % n], normal, tol=round(tol + 0.05, 3), deg=0.2)
        # Direction: increasing slot index must run rearward along the bottom (ground) run.
        bottom = max(range(n), key=lambda k: J[k][1])
        nxt = J[(bottom + 1) % n]
        if not (nxt[2] > J[bottom][2] or abs(nxt[1] - J[bottom][1]) > 1):
            raise ValueError(f"{tag}: slot order does not run rearward along the bottom")
        report[f"tread_{tag}"] = dict(links=len(links), pads=len(pads), max_joint_gap_ldu=round(worst_gap, 3),
                                      max_chord_deviation_ldu=round(closing, 3), rest_offset_ldu=round(rest_err, 3), chord_range=[round(min(chords), 3), round(max(chords), 3)],
                                      source_pitch_deviation_ldu=round(pitch_dev, 3), source_direction_deviation_deg=round(dir_dev, 3),
                                      normal=r6(normal), rows=len(rows_t))
        review["tracks"].append(f"{tag}: 25 links / 13 pads, joint gap at most {worst_gap:.2f} LDU between table rows")
        return names, J, normal

    def tread_signals(tag, rel_angle):
        """Table parameter from the sprocket angle relative to its pod (both about +X)."""
        period = 2 * PI * 5  # five sprocket turns = 50 slots = two table periods
        signal(f"tr_{tag}_w", f"r-{num(period)}*floor(r/{num(period)})", r=rel_angle)
        return signal(f"tr_{tag}_x", f"w*{num(SPROCKET_TEETH * SUBROWS / (2 * PI))}", w=f"tr_{tag}_w")

    def idlers(tag, side_sign, section_prefix, pod_body, rel_angle, J):
        """Three keyed idler shafts per pod; spin from the tread speed at their joint radius."""
        found = []
        for grp in {frozenset(v) for v in g.group_of.values()}:
            axles = [i for i in grp if nodes[i]["ref"] == "15462.dat" and i.startswith(section_prefix)
                     and 240 < pos(i)[0] * side_sign < 275]
            if axles:
                found.append(sorted(grp))
        if len(found) != 3:
            raise ValueError(f"{tag}: expected 3 idler shafts, found {len(found)}")
        wheels = [i for i in nodes if i.startswith(section_prefix) and nodes[i]["ref"].endswith("4185b.dat")
                  and pos(i)[0] * side_sign > 0]
        tread_speed = LINK_PITCH * SPROCKET_TEETH / (2 * PI)
        out = []
        idler_axles = []
        for n_, grp in enumerate(sorted(found, key=lambda gr: pos(gr[0])[2])):
            centre = [pos(i) for i in grp if nodes[i]["ref"] == "15462.dat"][0]
            mine = [w for w in wheels if abs(pos(w)[1] - centre[1]) < 0.5 and abs(pos(w)[2] - centre[2]) < 0.5]
            if len(mine) != 2:
                raise ValueError(f"{tag}: idler at {centre} has {len(mine)} wheels")
            # Joint-path radius: nearest polygon edge to the idler centre (in the loop plane).
            best = 1e9
            for k in range(len(J)):
                a, b = J[k], J[(k + 1) % len(J)]
                a2, b2, c2 = [a[1], a[2]], [b[1], b[2]], [centre[1], centre[2]]
                ab = [b2[0] - a2[0], b2[1] - a2[1]]
                t = max(0, min(1, ((c2[0] - a2[0]) * ab[0] + (c2[1] - a2[1]) * ab[1]) / (ab[0] ** 2 + ab[1] ** 2)))
                q = [a2[0] + ab[0] * t, a2[1] + ab[1] * t]
                best = min(best, math.dist(q, c2))
            ratio = tread_speed / best
            name = f"idler_{tag}_{n_}"
            sig = signal(name, f"{num(ratio)}*a", a=rel_angle)
            body(name, list(grp) + mine, centre, X, sig, parent=pod_body)
            out.append(name)
            idler_axles.append((name, [i for i in grp if nodes[i]["ref"] == "15462.dat"][0], centre))
            review["tracks"].append(f"{name}: joint radius {best:.2f} LDU, {ratio:.3f} x sprocket (relative to the pod)")
        pending_bearings.extend(idler_axles)
        return out

    def bearing(name, shaft_part, centre, axis, candidates):
        """Coaxial check of a spinning shaft against a support hole found on its axis."""
        for i in idsort(candidates):
            if nodes[i].get("embedded"):
                continue
            for c in conn(i):
                if c["kind"] in ("pin_hole", "axle_hole") and abs(abs(dot(c["axis"], axis)) - 1) < 1e-4 \
                        and length(cross(sub(c["pos"], centre), axis)) < 0.05:
                    coax(name, shaft_part, i, centre, axis)
                    return i
        raise ValueError(f"{name}: no support hole on the axis")

    pending_bearings = []

    # =================================================================== rear
    # Shafts, differential, pinion, pods, idlers and treads ride the rolling axle.
    rear_sides = dict(l=group("612/8"), r=group("612/7"))
    for s, sprocket in (("l", "612/122"), ("r", "612/124")):
        if sprocket not in rear_sides[s]:
            raise ValueError(f"rear {s}: sprocket {sprocket} not keyed to its side gear")
    rdiff, rspider, rpinion = "612/5", "612/6", "612/2"
    rpin_grp = group(rpinion)
    if set(rpin_grp) != {"612/1", "612/2"}:
        raise ValueError(f"rear pinion group {rpin_grp}")

    # ---------------------------------------------------------------- pods
    def pod_members(section_prefix, side_sign, knuckle=()):
        excluded = set()
        for b in bodies.values():
            excluded |= set(b["instances"])
        members = []
        for i in nodes:
            if nodes[i]["kind"] != "part" or not i.startswith(section_prefix) or i in excluded or i in knuckle:
                continue
            ref = nodes[i]["ref"]
            if "technicChainTread" in i or ref.endswith(("88323.dat", "24375.dat", "4185b.dat")):
                continue
            x, y_ = pos(i)[0] * side_sign, pos(i)[1]
            turntable_section = nodes[nodes[i]["parent"]]["ref"].endswith(("axleturntable.ldr", "axlefrontturntable1.ldr",
                                                                         "axlefrontturntable2.ldr")) if nodes[i]["parent"] != "root" else False
            if turntable_section and ref == "99010.dat":
                continue
            if x >= 205 or (turntable_section and x > 0 and (ref == "99009.dat" or y_ >= -60)):
                members.append(i)
        return members

    # Placeholder bodies are created in an order that lets pods exclude shafts first.
    m_rear = signal("m_rear", "d", d=drive)
    signal("side_rl", "m+s", m=m_rear, s=drr)
    signal("side_rr", "m-s", m=m_rear, s=drr)

    # Bodies on the axle: the axle itself is created last (it owns the remainder).
    body("rear_side_l", rear_sides["l"], at("612/8"), X, "side_rl", parent="rear_axle")
    body("rear_side_r", rear_sides["r"], at("612/7"), X, "side_rr", parent="rear_axle")
    signal("rear_carrier", "(a+b)/2", a="side_rl", b="side_rr")
    body("rear_diff", [rdiff], at(rdiff), X, "rear_carrier", parent="rear_axle")
    bar = g.one(rdiff, "bar")
    o_l, o_sp, ratio = bevel_mesh("612/8", 12, at("612/8"), X, rspider, 12, at(rspider), unit(bar["axis"]), "rear_axle")
    o_r, o_sp2, _ = bevel_mesh("612/7", 12, at("612/7"), X, rspider, 12, at(rspider), unit(bar["axis"]), "rear_axle")
    if dot(o_sp, o_sp2) < 0.999 or dot(o_l, o_r) > -0.999:
        raise ValueError("rear differential side gears are not opposed")
    signal("rear_spider", f"{num(ratio * dot(o_l, X))}*(a-c)", a="side_rl", c="rear_carrier")
    body("rear_spider", [rspider], at(rspider), o_sp, "rear_spider", parent="rear_diff")
    rotation("rear_spider_mesh", [("612/8", o_l, 12), (rspider, o_sp, 12)], carrier=rdiff)
    ring_r = g.at(rdiff, (0, 0, 26))
    k_r, oa, ob = bevel_ratio(rdiff, 28, X, rpinion, 20, Z, "rear_axle", a_centre=ring_r)
    signal("rear_pinion", f"{num(k_r)}*c", c="rear_carrier")
    body("rear_pinion", rpin_grp, at(rpinion), Z, "rear_pinion", parent="rear_axle")
    rotation("rear_ring_pinion", [(rdiff, oa, 28), (rpinion, ob, 20)], carrier="612/0")
    rotation("rear_differential", [("612/8", X, 1), ("612/7", X, 1), (rdiff, X, -2)], carrier="612/0")
    review["rear_axle"].append(f"28T ring / 20T pinion: pinion = {k_r:+.4f} x carrier (about +Z)")

    rear_pods = {}
    for s, sign, section, side_sig in (("l", 1, "612/196", "side_rl"), ("r", -1, "612/195", "side_rr")):
        tag = "r" + s
        hub = [210.0 * sign, pos("612/122")[1], pos("612/122")[2]]
        rel = signal(f"rel_{tag}", "a-p", a=side_sig, p=pods[tag])
        x_sig = tread_signals(tag, rel)
        names, J, normal = tread(tag, section, f"pod_{tag}", x_sig)
        idl = idlers(tag, sign, "612/", f"pod_{tag}", rel, J)
        members = pod_members("612/", sign)
        body(f"pod_{tag}", members, hub, X, pods[tag], parent="rear_axle")
        for nm, shaft_part, centre in pending_bearings:
            bearing(f"{nm}_bearing", shaft_part, centre, X, members)
        pending_bearings.clear()
        tt_top = [i for i in nodes if i.startswith("612/") and nodes[i]["ref"] == "99010.dat" and pos(i)[0] * sign > 0][0]
        tt_bot = [i for i in nodes if i.startswith("612/") and nodes[i]["ref"] == "99009.dat" and pos(i)[0] * sign > 0][0]
        coax(f"pod_{tag}_turntable", tt_bot, tt_top, hub, X)
        rear_pods[tag] = dict(members=len(members), hub=hub, idlers=idl, treads=len(names))

    # ---------------------------------------------------------------- shocks
    roll_eye = {}
    for s, sign, shock, mount_seed, xpin, axle_pin in (("l", 1, "612/97", "612/210", "612/223", "612/94"),
                                                         ("r", -1, "612/96", "612/197", "612/224", "612/95")):
        tag = "r" + s
        cyl, rod, spring = shock + "/0", shock + "/1", shock + "/2"
        T0 = g.one(xpin, "pin")["pos"]
        P0 = g.one(cyl, "pin_hole")["pos"]
        E0 = [c for c in conn(rod, "pin_hole")][0]["pos"]
        if abs(dot(g.one(xpin, "pin")["axis"], X)) < 0.999 or abs(dot(g.one(cyl, "pin_hole")["axis"], Z)) < 0.999:
            raise ValueError(f"{tag}: shock mount axes are not X / Z")
        if abs(P0[0] - T0[0]) > 0.05 or abs(P0[2] - T0[2]) > 0.05:
            raise ValueError(f"{tag}: eye pin is not below the X pin")
        L0 = length(sub(E0, P0))
        if abs(L0 - 102.0) > 0.1:
            raise ValueError(f"{tag}: rest eye distance {L0}")
        ex, ey, ez = rolled(f"eye_{tag}", E0)
        signal(f"sm_{tag}_dy", f"y-{num(T0[1])}", y=ey)
        signal(f"sm_{tag}_dz", f"z-{num(T0[2])}", z=ez)
        signal(f"sm_{tag}_a", "atan2(z,y)", y=f"sm_{tag}_dy", z=f"sm_{tag}_dz")
        h = P0[1] - T0[1]  # eye pin offset along the mount (20 LDU)
        # Eye position in the un-tilted mount frame, relative to the eye pin.
        signal(f"sm_{tag}_wy", f"y*cos(a)+z*sin(a)-{num(h)}", y=f"sm_{tag}_dy", z=f"sm_{tag}_dz", a=f"sm_{tag}_a")
        signal(f"sm_{tag}_wx", f"x-{num(P0[0])}", x=ex)
        w0 = sub(E0, P0)
        signal(f"sm_{tag}_b", f"atan2({num(w0[0])}*y-{num(w0[1])}*x,{num(w0[0])}*x+{num(w0[1])}*y)",
               x=f"sm_{tag}_wx", y=f"sm_{tag}_wy")
        signal(f"sm_{tag}_ext", f"sqrt(x*x+y*y)-{num(L0)}", x=f"sm_{tag}_wx", y=f"sm_{tag}_wy")
        mount = [i for i in group(mount_seed)] + [i for i in nodes if i.startswith("612/") and nodes[i]["kind"] == "part"
                                                   and (nodes[i]["ref"] in ("55981.dat", "2780.dat") or nodes[i]["ref"].endswith("13971.dat"))
                                                   and pos(i)[0] * sign > 125 and pos(i)[1] < -200]
        body(f"shock_{tag}_mount", mount, T0, X, f"sm_{tag}_a")
        body(f"shock_{tag}_cyl", [cyl], P0, Z, f"sm_{tag}_b", parent=f"shock_{tag}_mount")
        a0 = unit(w0)
        body(f"shock_{tag}_rod", [rod], E0, a0, f"sm_{tag}_ext", kind="prismatic", parent=f"shock_{tag}_cyl")
        seat = pos(spring)
        mesh_len = 100.0 - 64.02
        signal(f"sm_{tag}_k", f"({num(mesh_len)}+e)/{num(mesh_len)}", e=f"sm_{tag}_ext")
        body(f"shock_{tag}_spring", [spring], seat, a0, f"sm_{tag}_k", kind="stretch", parent=f"shock_{tag}_cyl")
        coax(f"shock_{tag}_xpin", [i for i in mount if nodes[i]["ref"] == "92907.dat"][0], xpin, T0, X)
        coax(f"shock_{tag}_eye", cyl, [i for i in mount if nodes[i]["ref"] == "32062.dat"][0], P0, Z)
        coax(f"shock_{tag}_slide", rod, cyl, E0, a0, tol=0.05, deg=0.2)
        coax(f"shock_{tag}_lower", rod, axle_pin, E0, Z, tol=0.05, deg=6.0)
        roll_eye[tag] = dict(rest_eye_distance=round(L0, 3), free=SHOCK_FREE, min=SHOCK_MIN)
        review["rear_suspension"].append(
            f"shock {tag}: gimbal mount on X pin {r6(T0)}, eye pin {r6(P0)}, rod eye {r6(E0)}; rest eye distance {L0:.2f} "
            f"(free length {SHOCK_FREE}: pre-compressed {SHOCK_FREE - L0:.2f})")

    # ---------------------------------------------------------------- arms
    for s, (arm_id, ball_id, pin_id) in arm.items():
        tag = "r" + s
        bx, by, bz = rolled(f"ball_{tag}", balls[s])
        Q = pivots[s]
        a = sub(balls[s], Q)
        signal(f"arm_{tag}", f"atan2({num(a[1])}*(z-{num(Q[2])})-{num(a[2])}*(y-{num(Q[1])}),"
                             f"{num(a[1])}*(y-{num(Q[1])})+{num(a[2])}*(z-{num(Q[2])}))", y=by, z=bz)
        body(f"arm_{tag}", [arm_id], Q, X, f"arm_{tag}")
        coax(f"arm_{tag}_pivot", arm_id, pin_id, Q, X)

    # ---------------------------------------------------------------- rear axle body
    owned = {i for b in bodies.values() for i in b["instances"]}
    static_rear = {"612/223", "612/224", "612/225", "612/226", "612/227"}
    axle_parts = [i for i in rear_parts if i not in owned and i not in static_rear]
    body("rear_axle", axle_parts, roll_origin, roll_axis, roll)

    # ========================================================== centre drive
    # Rear propshaft: CV at the axle (rest direction kept), cardan at the main shaft.
    prop_r = group("31")
    main = group("27")
    if "612/227" not in prop_r or "35" not in main or "30" not in main:
        raise ValueError("propshaft groups")
    jc_r = at("32")
    d_prop_r = unit(sub(at("612/227"), jc_r))
    # main shaft angle from the rear pinion: the CV makes prop == pinion; invert the cardan
    # by driving the main shaft and deriving the rear axle from it.
    review["centre"].append(f"rear propshaft {r6(d_prop_r)}, {math.degrees(math.acos(dot(d_prop_r, Z))):.2f} deg from +Z")
    # Main shaft angle about +Z: base of the drivetrain.
    signal("main", f"{num(k_r)}*d", d=drive)  # pinion (= main via cardan + CV) per carrier
    o1, x1 = linkages.universal_joint(signals, "uj_rear", "main", Z, d_prop_r, clip("30"), clip("31"))
    body("main_shaft", main, at("27"), Z, "main")
    body("rear_uj_cross", ["32"], jc_r, clip("30"), x1, parent="main_shaft")
    body("rear_prop", prop_r, jc_r, d_prop_r, o1)
    # The rear axle is driven from the cardan output (CV joint 1:1 to the pinion).
    if dot(d_prop_r, Z) < 0.99:
        raise ValueError("rear propshaft does not run rearward")
    signals["m_rear"] = dict(expression=f"{num(1 / k_r)}*p", variables={"p": "signal:" + o1})
    coax("rear_uj_in", "32", "30", jc_r, clip("30"), deg=0.05)
    coax("rear_uj_out", "32", "31", jc_r, clip("31"), deg=0.05)
    # Front: cardan from the main shaft, CV to the front pinion.
    jc_f = at("36")
    prop_f = group("34")
    d_prop_f = unit(sub(at("617/9"), jc_f))
    o2, x2 = linkages.universal_joint(signals, "uj_front", "main_neg", mul(Z, -1), d_prop_f, clip("35"), clip("34"))
    signal("main_neg", "-m", m="main")
    body("front_uj_cross", ["36"], jc_f, clip("35"), x2, parent="main_shaft")
    body("front_prop", prop_f, jc_f, d_prop_f, o2)
    fdiff, fspider, fpinion = "617/3", "617/5", "617/10"
    fpin_grp = group(fpinion)
    if set(fpin_grp) != {"617/9", "617/10"}:
        raise ValueError(f"front pinion group {fpin_grp}")
    if dot(d_prop_f, Z) > -0.99:
        raise ValueError("front propshaft does not run forward")
    signal("front_pinion", "-p", p=o2)  # CV: prop angle about -Z = pinion angle about -Z
    coax("front_uj_in", "36", "35", jc_f, clip("35"), deg=0.05)
    coax("front_uj_out", "36", "34", jc_f, clip("34"), deg=0.05)
    body("front_pinion", fpin_grp, at(fpinion), Z, "front_pinion")
    ring_f = g.at(fdiff, (0, 0, 26))
    k_f, foa, fob = bevel_ratio(fdiff, 28, X, fpinion, 20, Z, "front_axle", a_centre=ring_f)
    signal("m_front", f"{num(1 / k_f)}*p", p="front_pinion")
    # Straight running: both carriers must turn the same way at the same mean rate.
    if abs(k_f - k_r) > 1e-9:
        raise ValueError(f"Front/rear mean drive disagree (pinion per carrier {k_f} vs {k_r})")
    review["centre"].append("Front and rear carriers turn equally for straight running (both 28T/20T, cardans in series)")
    signal("side_fl", "m+s", m="m_front", s=dfr)
    signal("side_fr", "m-s", m="m_front", s=dfr)
    signal("front_carrier", "(a+b)/2", a="side_fl", b="side_fr")
    body("front_diff", [fdiff], at(fdiff), X, "front_carrier")
    fbar = g.one(fdiff, "bar")
    fo_l, fo_sp, fratio = bevel_mesh("617/4", 12, at("617/4"), X, fspider, 12, at(fspider), unit(fbar["axis"]), "front_axle")
    bevel_mesh("617/6", 12, at("617/6"), X, fspider, 12, at(fspider), unit(fbar["axis"]), "front_axle")
    signal("front_spider", f"{num(fratio * dot(fo_l, X))}*(a-c)", a="side_fl", c="front_carrier")
    body("front_spider", [fspider], at(fspider), fo_sp, "front_spider", parent="front_diff")
    rotation("front_spider_mesh", [("617/4", fo_l, 12), (fspider, fo_sp, 12)], carrier=fdiff)
    rotation("front_ring_pinion", [(fdiff, foa, 28), (fpinion, fob, 20)])
    rotation("front_differential", [("617/4", X, 1), ("617/6", X, 1), (fdiff, X, -2)])
    review["front_axle"].append(f"28T ring / 20T pinion: pinion = {k_f:+.4f} x carrier (about +Z)")

    # ================================================================ engine
    r1, ax1 = spur("28", 16, "19", 16, "engine")
    r2, _ = spur("19", 16, "15", 16, "engine")
    signal("idler16", f"{num(r1)}*m", m="main")
    body("idler16", ["19"], at("19"), Z, "idler16")
    shaft14 = group("15")
    signal("shaft14", f"{num(r2)}*i", i="idler16")
    body("engine_drive", shaft14, at("15"), Z, "shaft14")
    r3, _ = spur("140", 20, "116/76", 12, "engine")
    crank_grp = group("116/76")
    signal("crank", f"{num(r3)}*a", a="shaft14")
    crank_c = at("116/18")
    crank_c = [0.0, crank_c[1], crank_c[2]]
    crank_axis_pt = [0.0, -270.0, -310.0]
    body("crankshaft", crank_grp, crank_axis_pt, Z, "crank")
    rotation("engine_16_16a", [("28", Z, 16), ("19", Z, 16)])
    rotation("engine_16_16b", [("19", Z, 16), ("15", Z, 16)])
    rotation("engine_20_12", [("140", Z, 20), ("116/76", Z, 12)])
    signal("crank_c", "cos(a)", a="crank")
    signal("crank_s", "sin(a)", a="crank")
    pairs = [("116/19", "116/34"), ("116/20", "116/35"), ("116/23", "116/36"), ("116/24", "116/37"),
             ("116/26", "116/38"), ("116/27", "116/39"), ("116/30", "116/40"), ("116/31", "116/41")]
    for n_, (rod, piston) in enumerate(pairs, 1):
        cp = pos(rod)  # big end = crank pin centre
        pp = g.one(piston, "generic")["pos"]
        u = unit(g.one(piston, "generic")["axis"])
        c0 = [0.0, -270.0, cp[2]]
        r = sub(cp, c0)
        if abs(length([r[0], r[1]]) - 10) > 0.05:
            raise ValueError(f"{rod}: crank throw {length(r)}")
        L = length(sub(pp, cp))
        if abs(L - 40) > 0.05:
            raise ValueError(f"{rod}: rod length {L}")
        if length(cross(sub(pp, c0), u)) > 0.05:
            raise ValueError(f"{piston}: piston not on its cylinder line")
        v = [-u[1], u[0], 0.0]  # perpendicular in the crank plane
        # crank pin after rotation by +theta about +Z: (rx c - ry s, rx s + ry c)
        pu = f"({num(r[0] * u[0] + r[1] * u[1])}*c+{num(-r[1] * u[0] + r[0] * u[1])}*s)"
        pv = f"({num(r[0] * v[0] + r[1] * v[1])}*c+{num(-r[1] * v[0] + r[0] * v[1])}*s)"
        t0 = dot(sub(pp, c0), u)
        signal(f"piston{n_}", f"{pu}+sqrt({num(L * L)}-{pv}*{pv})-{num(t0)}", c="crank_c", s="crank_s")
        body(f"piston{n_}", [piston], pp, u, f"piston{n_}", kind="prismatic")
        anchors[f"crankpin{n_}"] = dict(body="crankshaft", point=r6(cp))
        anchors[f"wristpin{n_}"] = dict(body=f"piston{n_}", point=r6(pp))
        yv = unit(sub(pp, cp))
        body(f"conrod{n_}", [rod], cp, Z, kind="rod", start=f"crankpin{n_}", end=f"wristpin{n_}",
             x_hint=r6(unit(cross(yv, Z))))
        checks.append(dict(kind="distance", name=f"conrod{n_}", a=f"crankpin{n_}", b=f"wristpin{n_}",
                           length=round(L, 6), tolerance=0.02))
        cyl = [i for i in nodes if nodes[i].get("parent") == "116" and nodes[i]["ref"].endswith("2850b.dat")
               and abs(pos(i)[2] - pp[2]) < 0.5 and pos(i)[0] * pp[0] > 0][0]
        coax(f"piston{n_}_bore", piston, cyl, pp, u, tol=0.05, deg=0.2)
        review["engine"].append(f"piston{n_} {piston}: throw {r6(r)}, rod {L:.2f}, cylinder axis {r6(u)}")

    # ================================================================ steering
    hog = group("311")
    if "274/13" not in hog:
        raise ValueError("HOG shaft group")
    c1, c2, c3, c4 = at("274/15"), at("7"), at("64"), at("617/142")
    d_mid1 = unit(sub(c2, c1))
    d_mid2 = unit(sub(c4, c3))
    # Steering knob angle about +Y (shaft pointing down to its joint); sign fixed below.
    signal("hog", "s", s="control:steering")  # replaced once the sign is known
    u1, xh1 = linkages.universal_joint(signals, "uj_h1", "hog", Y, d_mid1, clip("274/13"), clip("274/14"))
    u2, xh2 = linkages.universal_joint(signals, "uj_h2", u1, d_mid1, Y, clip("5"), clip("6"))
    body("hog_knob", hog, c1, Y, "hog")
    body("hog_cross1", ["274/15"], c1, clip("274/13"), xh1, parent="hog_knob")
    body("hog_column", group("274/16"), c1, d_mid1, u1)
    body("hog_cross2", ["7"], c2, clip("5"), xh2, parent="hog_column")
    vert = group("4")
    body("steer_vertical", vert, c2, Y, u2)
    kb, boa, bob = bevel_ratio("4", 12, Y, "10", 12, Z, "steering")
    signal("steer_axle8", f"{num(kb)}*a", a=u2)  # about +Z
    rotation("steer_bevel", [("4", boa, 12), ("10", bob, 12)])
    ax8 = group("10")
    body("steer_shaft", ax8, at("10"), Z, "steer_axle8")
    signal("steer_axle8_n", "-a", a="steer_axle8")
    u3, xs3 = linkages.universal_joint(signals, "uj_s3", "steer_axle8_n", mul(Z, -1), d_mid2, clip("62"), clip("63"))
    u4, xs4 = linkages.universal_joint(signals, "uj_s4", u3, d_mid2, mul(Z, -1), clip("617/140"), clip("617/141"))
    body("steer_cross3", ["64"], c3, clip("62"), xs3, parent="steer_shaft")
    body("steer_column", group("65"), c3, d_mid2, u3)
    body("steer_cross4", ["617/142"], c4, clip("617/140"), xs4, parent="steer_column")
    signal("steer_pinion", "-a", a=u4)  # about +Z
    pin_grp = group("617/128")
    body("steer_pinion", pin_grp, at("617/128"), Z, "steer_pinion")
    k_rack = rack_ratio(Z, at("617/128"), 12, at("617/127/0"), X)
    signal("rack", f"{num(k_rack)}*a", a="steer_pinion")
    rack_parts = [f"617/127/{k}" for k in range(7)]
    body("rack", rack_parts, at("617/127/0"), X, "rack", kind="prismatic")
    review["steering"].append(f"rack {k_rack:+.3f} LDU per pinion radian (12T, rack_ratio)")
    knuckles = {}
    for s, sign, tt, tie, beam2, rack_pin, knuckle_pin in (("l", 1, "617/91", "617/127/7", "617/135", "617/127/5", "617/127/9"),
                                                             ("r", -1, "617/94", "617/127/8", "617/136", "617/127/6", "617/127/10")):
        tag = "f" + s
        kp_pin = g.one(f"{tt}/6", "pin")
        if abs(abs(dot(kp_pin["axis"], Y)) - 1) > 1e-6:
            raise ValueError(f"{tag}: kingpin not vertical")
        P = [kp_pin["pos"][0], -130.0, pos(f"{tt}/1")[2]]
        uj_c = at("617/89" if s == "l" else "617/84")
        if length(sub([uj_c[0], uj_c[2]], [P[0], P[2]])) > 0.05:
            raise ValueError(f"{tag}: UJ centre is off the kingpin axis")
        K0 = g.one(knuckle_pin, "pin")["pos"]
        R0 = g.one(rack_pin, "pin")["pos"]
        Ltie = length(sub(K0, R0))
        if abs(Ltie - 80) > 0.05:
            raise ValueError(f"{tag}: tie rod length {Ltie}")
        angle_sig, fn = linkages.ball_link(signals, f"knuckle_{tag}", "rack", P, UP, K0, R0, X, Ltie)
        kn = list(group(f"{tt}/4")) + [f"{tt}/1", f"{tt}/2", f"{tt}/3", f"{tt}/6", f"{tt}/14"]
        body(f"knuckle_{tag}", kn, P, UP, angle_sig)
        knuckles[tag] = dict(fn=fn, P=P)
        anchors[f"tie_{tag}_rack"] = dict(body="rack", point=r6(R0))
        anchors[f"tie_{tag}_arm"] = dict(body=f"knuckle_{tag}", point=r6(K0))
        yv = unit(sub(K0, R0))
        body(f"tierod_{tag}", [tie, beam2, knuckle_pin], R0, UP, kind="rod", start=f"tie_{tag}_rack",
             end=f"tie_{tag}_arm", x_hint=r6(unit(cross(yv, UP))))
        checks.append(dict(kind="distance", name=f"tierod_{tag}", a=f"tie_{tag}_rack", b=f"tie_{tag}_arm",
                           length=round(Ltie, 6), tolerance=0.02))
        housing = [i for i in nodes if i.startswith("617/") and nodes[i]["ref"] == "42003.dat"
                   and abs(pos(i)[0] - 160 * sign) < 0.5 and abs(pos(i)[1] + 90) < 0.5][0]
        coax(f"knuckle_{tag}_kingpin", f"{tt}/6", housing, kp_pin["pos"], Y, tol=0.05, deg=0.2)
        review["steering"].append(f"knuckle {tag}: kingpin {r6(P)}, arm pin {r6(K0)}, rack pin {r6(R0)}, tie rod {Ltie:.2f}")

    # Steering sign: positive control turns the pod fronts to +X (left) = positive about UP.
    tmp = dict(controls=copy.deepcopy(controls), signals=copy.deepcopy(signals), bodies={}, anchors={}, checks=[])
    tmp["controls"]["steering"].update(min=-5, max=5)
    probe = contract.evaluate(tmp, dict(steering=0.3))["signals"]
    hog_sign = 1.0 if probe["knuckle_fl_angle"] > 0 else -1.0
    signals.pop("hog")
    # Steering range from the rack travel limit.
    per_rad = abs(probe["rack"] / 0.3)
    limit = round(STEER_RACK_LIMIT / per_rad, 4)
    controls["steering"] = dict(default=0.0, min=-limit, max=limit, unit="radian",
                                description="Hand-of-god roof knob angle; positive steers left (pod fronts toward +X)")
    signal("hog", f"{num(hog_sign)}*s", s=clamped("steering"))
    for nm, cr, a_in, a_out, cc in (("hog_uj1", "274/15", "274/13", "274/14", c1), ("hog_uj2", "7", "5", "6", c2),
                                     ("steer_uj3", "64", "62", "63", c3), ("steer_uj4", "617/142", "617/140", "617/141", c4)):
        coax(nm + "_in", cr, a_in, cc, clip(a_in), deg=0.05)
        coax(nm + "_out", cr, a_out, cc, clip(a_out), deg=0.05)
    review["steering"].append(f"HOG knob {limit:.3f} rad each way = {STEER_RACK_LIMIT} LDU of rack")

    # ---------------------------------------------------------------- front shafts, UJs, pods
    front_parts = [i for i, n in nodes.items() if n["kind"] == "part" and i.startswith("617/")]
    for s, sign, inner_gear, inner_end, cross_id, outer_end, sprocket, side_sig, loop in (
            ("l", 1, "617/4", "617/87", "617/89", "617/88", "617/119", "side_fl", "617/213"),
            ("r", -1, "617/6", "617/82", "617/84", "617/83", "617/120", "side_fr", "617/214")):
        tag = "f" + s
        inner = group(inner_gear)
        outer = group(outer_end)
        if inner_end not in inner or sprocket not in outer:
            raise ValueError(f"{tag}: half shaft groups")
        a = mul(X, sign)  # input shaft towards the joint
        k = UP
        e3 = cross(a, k)
        fi = unit(clip(inner_end))
        psi = math.atan2(dot(fi, e3), dot(fi, k))
        theta = signal(f"{tag}_theta", f"{num(sign)}*s", s=side_sig)
        dlt = f"knuckle_{tag}_angle"
        signal(f"{tag}_cd", "cos(d)", d=dlt)
        signal(f"{tag}_w", f"atan2(c*sin(t+{num(psi)}),cos(t+{num(psi)}))-{num(psi)}", c=f"{tag}_cd", t=theta)
        signal(f"{tag}_phi", "t+atan2(sin(w-t),cos(w-t))", t=theta, w=f"{tag}_w")
        signal(f"{tag}_gn", f"sin(d)*cos(p+{num(psi)})", d=dlt, p=f"{tag}_phi")
        signal(f"{tag}_gd", f"sin(t+{num(psi)})*sin(p+{num(psi)})+c*cos(t+{num(psi)})*cos(p+{num(psi)})",
               t=theta, p=f"{tag}_phi", c=f"{tag}_cd")
        signal(f"{tag}_gamma", "atan2(n,d)", n=f"{tag}_gn", d=f"{tag}_gd")
        jc = at(cross_id)
        body(f"front_side_{s}", inner, at(inner_gear), X, side_sig)
        body(f"front_uj_{s}", [cross_id], jc, fi, f"{tag}_gamma", parent=f"front_side_{s}")
        signal(f"{tag}_outer", f"{num(sign)}*p", p=f"{tag}_phi")  # about +X in the knuckle frame
        body(f"front_hub_{s}", outer, jc, X, f"{tag}_outer", parent=f"knuckle_{tag}")
        fo = unit(clip(outer_end))
        coax(f"front_uj_{s}_out", cross_id, outer_end, jc, fo, tol=0.05, deg=0.05)
        coax(f"front_uj_{s}_in", cross_id, inner_end, jc, fi, tol=0.05, deg=0.05)
        rel = signal(f"rel_{tag}", "a-p", a=f"{tag}_outer", p=pods[tag])
        x_sig = tread_signals(tag, rel)
        hub = [210.0 * sign, -130.0, pos(sprocket)[2]]
        names, J, normal = tread(tag, loop, f"pod_{tag}", x_sig)
        idl = idlers(tag, sign, "617/", f"pod_{tag}", rel, J)
        members = pod_members("617/", sign, knuckle=set(bodies[f"knuckle_{tag}"]["instances"]))
        body(f"pod_{tag}", members, hub, X, pods[tag], parent=f"knuckle_{tag}")
        for nm, shaft_part, centre in pending_bearings:
            bearing(f"{nm}_bearing", shaft_part, centre, X, members)
        pending_bearings.clear()
        tt_top = [i for i in nodes if i.startswith("617/") and nodes[i]["ref"] == "99010.dat" and pos(i)[0] * sign > 0][0]
        tt_bot = [i for i in nodes if i.startswith("617/") and nodes[i]["ref"] == "99009.dat" and pos(i)[0] * sign > 0][0]
        coax(f"pod_{tag}_turntable", tt_bot, tt_top, hub, X)
        review["tracks"].append(f"pod {tag}: {len(members)} parts on the knuckle turntable")

    # Bevels and the propshaft UJs participate in rotation checks where linear.
    report["roll_eye"] = roll_eye
    report["rear_pods"] = rear_pods
    return dict(plan=plan, controls=controls, signals=signals, bodies=bodies, anchors=anchors, checks=checks,
                review=review, report=report, geometry=g, knuckles=knuckles)


def sections(plan, i):
    nodes = {n["id"]: n for n in plan["source"]["nodes"]}
    out = []
    while nodes[i]["parent"] != "root":
        i = nodes[i]["parent"]
        out.append(nodes[i]["ref"].removeprefix("42069 - ").removesuffix(".ldr"))
    return out


DEFERRED = {
    "winch": (("winch", "winchratchet", "ropeLQ-1", "chassis6", "chassis7", "chassis5"),
              "Winch drum, its side-knob drive (chassis6/7 bevel chain), the ratchet and the rope: outside the "
              "requested scope; static in the source pose."),
    "body_openings": (("doorleft", "doorright", "rearsidedoor", "reardoor", "roofrack", "shovel"),
                      "Doors, rear side doors, rear door with spare sprocket, roof rack and shovel: not requested; static."),
    "front_suspension": (("axlefront", "axlefront2"),
                         "Front axle: two leading arms plus two 9L ball links leave one pitch mode (instant axis "
                         "X through (0,-106,-308)). Moving it would bend the chassis-side steering column and propshaft "
                         "by ~4 LDU per 0.05 rad, so the front axle and its shocks stay at the source ride height."),
}


def views(plan, out):
    bodies, review = out["bodies"], out["review"]
    owned = {i for b in bodies.values() for i in b["instances"]}
    v = {}

    def view(key, label, names, inputs, outputs, text, notes=(), parts=(), disposition="planned"):
        v[key] = dict(label=label, parts=idsort(parts), bodies=list(names), inputs=list(inputs),
                      outputs=list(outputs), notes=list(dict.fromkeys(notes)), disposition=disposition, review=text)

    def named(*prefixes):
        return [n for n in bodies if n.startswith(prefixes)]

    view("drivetrain", "Main shaft, cardan propshafts, ring/pinion differentials and sprocket half shafts",
         named("main_shaft", "rear_uj", "front_uj", "rear_prop", "front_prop", "rear_pinion", "front_pinion",
               "rear_diff", "front_diff", "rear_spider", "front_spider", "rear_side", "front_side", "front_hub"),
         ["control:drive", "control:diff_front", "control:diff_rear"],
         ["body:rear_side_l", "body:rear_side_r", "body:front_hub_l", "body:front_hub_r"],
         "Exact cardans at the main shaft, CV joints at both pinions, 28T/20T rings, 12T spiders; front sprockets "
         "through steered single cardans at the kingpins (exact closed form).",
         review["centre"] + review["rear_axle"] + review["front_axle"])
    view("engine", "V8: 16T idler train, 20T/12T to the crank, eight slider-crank pistons",
         named("idler16", "engine_drive", "crankshaft", "piston", "conrod"), ["body:idler16"],
         [f"body:piston{n}" for n in range(1, 9)],
         "Crank throw 10 LDU, rods 40 LDU, cylinders at +-53 degrees; geared 16/16/16 then 20/12 from the main shaft.",
         review["engine"])
    view("steering", "Hand-of-god knob to the front knuckles",
         named("hog_", "steer_", "rack", "knuckle_", "tierod_"), ["control:steering"],
         ["body:knuckle_fl", "body:knuckle_fr"],
         "Four exact cardans at fixed bend, 12T/12T bevel, 12T pinion and rack, two 80 LDU tie rods (closed).",
         review["steering"])
    view("rear_suspension", "Rear axle roll with trailing arms and gimbal-mounted shocks",
         named("rear_axle", "arm_", "shock_"), ["control:rear_roll"], ["body:rear_axle"],
         "Roll about the measured trailing-arm axis; shock mounts, cylinders, rods and springs solved from the rod "
         "eyes (exact).", review["rear_suspension"])
    view("tracks", "Four track pods: pitch, idlers and circulating tread links",
         named("pod_", "idler_", "tread_"),
         ["control:pod_fl", "control:pod_fr", "control:pod_rl", "control:pod_rr", "control:drive"],
         ["body:pod_fl", "body:pod_fr", "body:pod_rl", "body:pod_rr"],
         "10-tooth sprockets advance one 30 LDU link per tooth relative to their pod; links follow the source joint "
         "polygon (path bodies), pads ride their links.", review["tracks"])
    remaining = set(plan["discovery"]["mechanical_parts"]) - owned
    for key, (secs, text) in DEFERRED.items():
        parts = [i for i in remaining if any(s in secs for s in sections(plan, i)[:1])]
        if key == "winch":
            parts += [i for i in remaining if i in ("162", "240", "241", "243", "244", "246", "260", "262", "258",
                                                     "267", "270", "504", "505", "542", "543", "271")]
        parts = sorted(set(parts))
        remaining -= set(parts)
        if parts:
            view(key, key.replace("_", " ").title(), [], [], [], text, [f"Parts: {len(parts)}."], parts, "deferred")
    if remaining:
        view("supports", "Frame, bodywork and accessory axles, pins and connectors", [], [], [],
             "Chassis/bodywork supports not on any rigged motion path; reviewed as static by section and contacts, "
             "not individually.", [f"Parts: {len(remaining)}."], remaining, "static")
    return v


def notes():
    return [
        "Source: output/42069/source/42069-1-springs.mpd = data/models-annotated/42069-1.mpd (Philippe Hurbain) with "
        "the four LDCad spring meshes renamed .ldr -> .dat (embedded parts) so they can stretch. IDs unchanged.",
        "Frame: LDU, -Y up, front -Z, left +X. The vehicle stays in place: no root motion.",
        "Contacts: bounded pyldraw3 run over 1471 non-embedded mechanical parts (191/194 axles keyed). "
        "Keyed (axle-in-axle-hole) groups define rigid shafts.",
        "Tracks: path bodies follow the source joint polygon (25 links, 30 LDU) with 4 table rows per slot; between "
        "rows the links interpolate. Pads ride their links. Sprocket teeth: 10 (one link per tooth).",
        "Rear axle roll is a rotation about the first-order roll axis of the trailing arms; arms re-aim to the balls "
        "(second-order ball gap below 0.5 LDU at the limit) and the rear propshaft keeps its rest direction "
        "(CV offset about 1.2 LDU at full roll).",
        "Shock free eye distance 110 LDU (official 73129/41838); the source sits at 102 LDU, so rolls stay within "
        "about +-8 LDU. Spring rate, damping, gravity and contact forces are not modelled.",
        "Steering cardans and propshaft cardans use exact fixed-bend equations; the front kingpin cardans use the exact "
        "single-cardan relation with the steering angle as the bend.",
        "Not modelled: front suspension pitch, winch, ratchet, doors, rope, friction, backlash. Clearance is sampled "
        "in renders, not proven.",
        "xray review (output/42069/xray/<board>/mosaic.png): pod-rl and pod-fl rod through the hub/turntable, whole "
        "pod with idlers and treads coloured, +-20 deg clear; knuckle-fl rod through the vertical kingpin, pod steers "
        "+-12 deg clear of the bumper; rear-axle rod along the tilted trailing-arm roll axis, housing and both pods "
        "coloured; shock-rl-mount rod along the X chassis pin, mount with its hanging rim stacks; tread-rl-00 one link "
        "and its pad (path bodies are not posed by xray).",
    ]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--study", required=True)
    ap.add_argument("--evidence", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--report")
    ap.add_argument("--ready", action="store_true")
    args = ap.parse_args()
    study = contract.load(args.study)
    evidence = json.loads(Path(args.evidence).read_text())
    out = build(study, evidence)
    plan = out["plan"]
    plan.update(name="extreme_adventure_42069", controls=out["controls"], signals=out["signals"],
                bodies=out["bodies"], anchors=out["anchors"], checks=out["checks"], status="draft", notes=notes())
    plan["mechanisms"] = {}
    plan["mechanisms"] = views(plan, out)
    if args.ready:
        plan["status"] = "ready"
    contract.validate(plan)
    contract.save(args.output, plan)
    if args.report:
        Path(args.report).write_text(json.dumps(dict(report=out["report"], review=out["review"]), indent=1) + "\n")
    owned = sum(len(b["instances"]) for b in plan["bodies"].values())
    print(json.dumps(dict(plan=args.output, status=plan["status"], bodies=len(plan["bodies"]), moving_parts=owned,
                          signals=len(plan["signals"]), checks=len(plan["checks"]),
                          views={k: m["disposition"] for k, m in plan["mechanisms"].items()})))


if __name__ == "__main__":
    main()
