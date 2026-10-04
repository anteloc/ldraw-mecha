#!/usr/bin/env python3
"""Author the motion plan for 10265-1_B-Model from a prepared study.

Run after `./ldraw-mecha prepare ... --output output/10265-v3`:

    scripts/build_mustang_rig.py --study output/10265-v3/study-draft.json \
        --output output/10265-v3/plan.json

Every number is derived from the plan's own source manifest (world matrices) or
from the measured connector frames quoted next to it. Nothing is read from earlier
10265 attempts. Frames are the root section frame (LDU, -Y up, front is -Z, the
car's left is +X). Angles are radians; positive is the right-hand rule about the
stated axis.
"""

import argparse
import copy
import math
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ldraw_mechanisms import mechanisms, plan as contract
from ldraw_mechanisms.math3d import (
    add,
    cross,
    dot,
    length,
    mul,
    signed_gear_ratio,
    sub,
    unit,
)

X = [1.0, 0.0, 0.0]


def _rodrigues(axis, angle):
    x, y, z = unit(axis)
    c, s_ = math.cos(angle), math.sin(angle)
    t = 1 - c
    return [
        [c + x * x * t, x * y * t - z * s_, x * z * t + y * s_],
        [y * x * t + z * s_, c + y * y * t, y * z * t - x * s_],
        [z * x * t - y * s_, z * y * t + x * s_, c + z * z * t],
    ]


def _apply(m, v):
    return [dot(row, v) for row in m]


def cardan_cross(signals, d_in, d_out, fork_in):
    """Add the signal driving the centre cross of a single universal joint.

    Input yoke pivot `fork_in` is normal to the bend plane at rest; the output yoke
    pivot `p` lies in it. With forward-pointing shaft axes d_in/d_out the output
    follows tan(out)=cos(beta) tan(in). The centre cross is a child of the input
    yoke rotating about `fork_in` by gamma, the angle that carries its second arm
    onto the output pivot; the closed form is verified with explicit rotations.
    """
    p = unit(cross(d_out, fork_in))
    cos_beta = dot(d_in, d_out)
    k1 = dot(d_in, p)
    t3 = dot(d_in, cross(d_out, p))
    r = cross(d_in, fork_in)
    rp, rd = dot(r, p), dot(r, d_out)
    if abs(dot(d_out, p)) > 1e-9 or abs(dot(fork_in, p)) > 1e-9:
        raise ValueError("Universal joint pivots are not orthogonal")

    def gamma(theta):
        out = math.atan2(cos_beta * math.sin(theta), math.cos(theta))
        c, s_, co, so = math.cos(theta), math.sin(theta), math.cos(out), math.sin(out)
        n = (
            rd * c * s_ * so
            + k1 * rp * s_ * s_ * co
            + t3 * rp * s_ * s_ * so
            - k1 * rp * c * (1 - c) * co
            + k1 * k1 * rd * (1 - c) * s_ * so
            - k1 * cos_beta * rp * (1 - c) * s_ * so
        )
        d = c * co + cos_beta * s_ * so + k1 * k1 * (1 - c) * co + k1 * t3 * (1 - c) * so
        return out, math.atan2(n, d)

    for i in range(-13, 14):
        theta = 0.1 * i
        out, g = gamma(theta)
        r_in, r_out = _rodrigues(d_in, theta), _rodrigues(d_out, out)
        a1 = _apply(r_in, fork_in)
        # Cardan constraint: the two cross arms stay perpendicular.
        if abs(dot(a1, _apply(r_out, p))) > 1e-9:
            raise ValueError("Output angle violates the universal joint constraint")
        carried = _apply(_rodrigues(a1, g), _apply(r_in, p))
        if length(sub(carried, _apply(r_out, p))) > 1e-9:
            raise ValueError("Cross angle does not carry arm 2 onto the output pivot")
    c = lambda v: repr(float(v))
    signals["uj_c"] = dict(expression="cos(a)", variables=dict(a="signal:column_in"))
    signals["uj_s"] = dict(expression="sin(a)", variables=dict(a="signal:column_in"))
    signals["uj_co"] = dict(expression="cos(a)", variables=dict(a="signal:pinion_fwd"))
    signals["uj_so"] = dict(expression="sin(a)", variables=dict(a="signal:pinion_fwd"))
    v4 = dict(
        c="signal:uj_c", s="signal:uj_s", co="signal:uj_co", so="signal:uj_so"
    )
    signals["uj_n1"] = dict(
        expression=f"{c(rd)}*c*s*so+{c(k1 * rp)}*s*s*co+{c(t3 * rp)}*s*s*so",
        variables=v4,
    )
    signals["uj_n2"] = dict(
        expression=f"-{c(k1 * rp)}*c*(1-c)*co+{c(k1 * k1 * rd)}*(1-c)*s*so-{c(k1 * cos_beta * rp)}*(1-c)*s*so",
        variables=v4,
    )
    signals["uj_d"] = dict(
        expression=f"c*co+{c(cos_beta)}*s*so+{c(k1 * k1)}*(1-c)*co+{c(k1 * t3)}*(1-c)*so",
        variables=v4,
    )
    signals["cross_angle"] = dict(
        expression="atan2(a+b,d)",
        variables=dict(a="signal:uj_n1", b="signal:uj_n2", d="signal:uj_d"),
    )


def build(study, steer_limit=0.2):
    plan = copy.deepcopy(study)
    nodes = {n["id"]: n for n in plan["source"]["nodes"]}

    def at(i):
        w = nodes[i]["world"]
        return [w[r][3] for r in range(3)]

    def column(i, c):
        w = nodes[i]["world"]
        return [w[r][c] for r in range(3)]

    def leaves(prefix):
        return sorted(
            (i for i, n in nodes.items() if n["kind"] == "part" and i.startswith(prefix + "/")),
            key=lambda s: [int(x) for x in s.split("/")],
        )

    def edge(a, b, kind=None):
        hits = [
            c
            for c in plan["connections"].values()
            if {c["a"], c["b"]} == {a, b} and (kind is None or c["kind"] == kind)
        ]
        if not hits:
            raise ValueError(f"No discovered connection {a} - {b}")
        return hits

    controls, signals, bodies, anchors, checks = {}, {}, {}, {}, []

    def control(name, lo, hi, description, unit_name="radian"):
        controls[name] = dict(default=0.0, min=lo, max=hi, unit=unit_name, description=description)

    def signal(name, expr, **variables):
        signals[name] = dict(
            expression=expr,
            variables={k: v if ":" in v else "signal:" + v for k, v in variables.items()},
        )
        return name

    def body(name, instances, origin, axis, sig=None, kind="revolute", parent=None, **extra):
        b = dict(instances=list(instances), kind=kind, origin=list(origin), axis=list(axis), **extra)
        if sig:
            b["signal"] = sig
        if parent:
            b["parent"] = parent
        bodies[name] = b

    # ---- Front axle geometry -------------------------------------------------
    # Crank axis: 40T gear 0/91/7 on axle 0/91/8. connector world_axis (0,-0.052,0.999).
    gear40 = at("0/91/7")
    a = unit(mul(column("0/91/7", 2), -1))  # +a is rearward; it is the crank rotation axis
    k = unit(cross(a, X))  # kingpin axis (steering arm 0/90/16 vertical studs), -Y is up
    if abs(dot(a, k)) > 1e-9 or abs(dot(k, X)) > 1e-9:
        raise ValueError("Chassis frame is not orthogonal")
    pin = at("0/91/9")  # crank pin axle (axle 2 notched through both liftarms)
    d = sub(pin, gear40)
    d = sub(d, mul(a, dot(d, a)))
    crank_radius = length(d)
    if abs(crank_radius - 20.0) > 0.05:
        raise ValueError(f"Crank radius {crank_radius} is not the expected 20 LDU")
    pu, ph = dot(d, X), dot(d, k)
    if abs(pu) > 1e-6:
        raise ValueError("Crank pin is not directly below the gear axis at rest")
    # 16T pinion 0/103 drives the 40T gear; parallel external mesh.
    pinion = at("0/103")
    mesh = edge("0/91/7", "0/103", "gear_mesh")[0]["measurements"]
    if abs(mesh["distance_error_ldu"]) > 0.05:
        raise ValueError("Gear centre distance does not match 16T/40T pitch circles")
    ratio_40_per_16 = signed_gear_ratio(a, pinion, 16, a, gear40, 40)
    # Universal joint (3326b centre, 3712 ends): column axis -> pinion axis.
    wheel_pt = at("0/312/22")
    joint = at("0/307")
    d_in = unit(sub(joint, wheel_pt))  # forward-pointing column direction
    if length(cross(d_in, sub(at("0/312/21"), wheel_pt))) > 1.0:
        raise ValueError("Steering wheel and column axle are not collinear")
    d_out = mul(a, -1)  # forward-pointing pinion axis (a is rearward)
    fork_in = X  # input yoke pivot at rest (clip axis, connector 0/312/23 = +X)
    cos_beta = dot(d_in, d_out)
    # Cardan constraint check: tan(out) = cos(beta) * tan(in), measured about the forward axes
    # when the input pivot is perpendicular to the bend plane and the output pivot lies in it.
    bend_normal = unit(cross(d_in, d_out))
    if abs(abs(dot(bend_normal, fork_in)) - 1.0) > 1e-6:
        raise ValueError("Universal joint input pivot is not normal to the bend plane")

    # ---- Controls -------------------------------------------------------------
    # Default 0.2 rad is the sampled-clearance-free range (clearance.json): hub bevels cross the
    # tie rods from about 0.225 rad. The linkage stays solvable to roughly 1.3 rad (--steer-limit).
    control(
        "steering_wheel",
        -steer_limit,
        steer_limit,
        "Steering wheel angle about the column; positive is clockwise seen by the driver (right turn)",
    )
    for w in ("fl", "fr", "rl", "rr"):
        control(
            "spin_" + w,
            -20 * math.pi,
            20 * math.pi,
            "Free spin of this wheel about its hub; positive rolls the car forward",
        )
    control(
        "rear_shaft",
        -20 * math.pi,
        20 * math.pi,
        "Rear worm shaft (4716) angle about its axis; drives the 8T gear and axle 9 through the worm mesh",
    )
    control("gear_lever", -0.35, 0.35, "Gear lever swing about the console hinge")
    # Sampled clearance: no new crossings from -0.45 to 0; the lid plate 0/357/7 is crossed beyond.
    control("spoiler", -0.45, 0.0, "Rear spoiler flap about its lid hinge; negative lays it rearward")

    # ---- Steering chain -------------------------------------------------------
    control_ref = "steering_wheel"
    signal("steer_clamped", "clamp(v,%r,%r)" % (-steer_limit, steer_limit), v="control:" + control_ref)
    signal("column_in", "s", s="steer_clamped")
    # tan(out)=cos(beta)*tan(in) with atan2 to stay continuous through +/-90 degrees.
    signal("pinion_fwd", f"atan2({cos_beta!r}*sin(s),cos(s))", s="column_in")
    signal("pinion_a", "-s", s="pinion_fwd")  # angle about +a
    signal("crank_angle", f"{ratio_40_per_16!r}*s", s="pinion_a")
    signal("crank_counter", "-s", s="crank_angle")  # keeps the coupler beam from turning

    body(
        "steering_column",
        ["0/312/22", "0/312/21", "0/312/23"],
        joint,
        d_in,
        "column_in",
        x_hint=X,
    )
    cardan_cross(signals, d_in, d_out, fork_in)
    body("uj_cross", ["0/307"], joint, X, "cross_angle", parent="steering_column")
    body(
        "steer_pinion",
        ["0/308", "0/102", "0/103"],
        pinion,
        d_out,
        "pinion_fwd",
    )
    body("crank", ["0/91/7", "0/91/8", "0/91/4", "0/91/14", "0/91/9"], gear40, a, "crank_angle")
    body(
        "pitman",
        ["0/91/5", "0/91/2", "0/91/3"],
        pin,
        a,
        "crank_counter",
        parent="crank",
    )

    knuckle_parts = {
        "l": dict(arm="0/90/17", rod="0/93", pitman_ball="0/91/3"),
        "r": dict(arm="0/90/16", rod="0/92", pitman_ball="0/91/2"),
    }
    for side, spec in knuckle_parts.items():
        king = at(spec["arm"])
        # Ball centres from the discovered generic ball contacts.
        q_edge = edge(spec["pitman_ball"], spec["rod"])[0]["measurements"]["position"]
        b_edge = edge(spec["arm"], spec["rod"])[0]["measurements"]["position"]
        if abs(dot(sub(king, at("0/90/18" if side == "l" else "0/90/19")), X)) < 19.9:
            raise ValueError("Unexpected hub offset")
        q0, b0 = list(q_edge), list(b_edge)
        link = length(sub(q0, b0))
        if abs(link - 100.0) > 0.2:
            raise ValueError(f"6L steering link length {link} is not about 100 LDU")

        def uhw(p):
            r = sub(p, king)
            return dot(r, X), dot(r, k), dot(r, a)

        ub, hb, wb = uhw(b0)
        uq, hq, wq = uhw(q0)
        if abs(hb) > 1.5 or abs(hq) > 1.5:
            raise ValueError("Ball joints are not at kingpin height at rest")
        r_arm = math.hypot(ub, wb)
        rho0 = math.hypot(uq, wq)
        leff0_sq = link * link - (hb - hq) ** 2
        c0 = (r_arm**2 + rho0**2 - leff0_sq) / (2 * r_arm * rho0)
        alpha_a = math.atan2(wb, ub)
        alpha_q0 = math.atan2(wq, uq)
        delta0 = math.acos(c0)
        branch = math.copysign(1.0, (alpha_a - alpha_q0 + math.pi) % (2 * math.pi) - math.pi)
        # Pitman ball translation for crank angle phi: crank pin offset (0, ph) rotates about +a.
        signal(
            f"tau_u_{side}",
            f"{-ph!r}*sin(p)",
            p="crank_angle",
        )
        signal(f"tau_h_{side}", f"{ph!r}*(cos(p)-1)", p="crank_angle")
        signal(
            f"leff2_{side}",
            f"{link * link!r}-pow({hb - hq!r}-t,2)",
            t=f"tau_h_{side}",
        )
        signal(
            f"rho_{side}",
            f"sqrt(pow({uq!r}+t,2)+{wq * wq!r})",
            t=f"tau_u_{side}",
        )
        signal(
            f"cosd_{side}",
            f"({r_arm * r_arm!r}+r*r-l)/({2 * r_arm!r}*r)",
            r=f"rho_{side}",
            l=f"leff2_{side}",
        )
        signal(
            f"knuckle_{side}",
            f"{alpha_a!r}-atan2({wq!r},{uq!r}+t)-{branch!r}*acos(clamp(c,-1,1))",
            t=f"tau_u_{side}",
            c=f"cosd_{side}",
        )
        body(
            f"knuckle_{side}",
            [spec["arm"]],
            king,
            k,
            f"knuckle_{side}",
        )
        anchors[f"pitman_ball_{side}"] = dict(body="pitman", point=q0)
        anchors[f"knuckle_ball_{side}"] = dict(body=f"knuckle_{side}", point=b0)
        body(
            f"tierod_{side}",
            [spec["rod"]],
            q0,
            k,
            kind="rod",
            x_hint=cross(sub(b0, q0), k),
            start=f"pitman_ball_{side}",
            end=f"knuckle_ball_{side}",
        )
        checks.append(
            dict(
                kind="distance",
                name=f"tie_rod_{side}",
                a=f"pitman_ball_{side}",
                b=f"knuckle_ball_{side}",
                length=link,
                tolerance=0.02,
            )
        )
        if abs(branch * delta0 - (alpha_a - alpha_q0)) > 1e-6:
            raise ValueError("Rest pose does not sit on the chosen tie-rod branch")

    # ---- Wheels ---------------------------------------------------------------
    wheels = {
        "fl": ["0/453", "0/454", "0/445", "0/90/18", "0/90/21"],
        "fr": ["0/455", "0/456", "0/446", "0/90/19", "0/90/20"],
        "rl": ["0/457", "0/458", "0/447", "0/88/18", "0/88/21"],
        "rr": ["0/459", "0/460", "0/448", "0/88/15", "0/88/22"],
    }
    for w, ids in wheels.items():
        hub = at(ids[0])
        for i in ids[1:]:
            off = sub(at(i), hub)
            if length(cross(off, X)) > 0.2:
                raise ValueError(f"{i} is not on the hub line of {w}")
        signal("wheel_" + w, "s", s="control:spin_" + w)
        body(
            "wheel_" + w,
            ids,
            hub,
            X,
            "wheel_" + w,
            parent={"fl": "knuckle_l", "fr": "knuckle_r"}.get(w),
        )

    # ---- Rear worm drive ------------------------------------------------------
    worm = at("0/104/37")
    a_w = unit(column("0/104/37", 2))  # worm axis (4716 hole axis is part Z)
    if dot(a_w, [0, 0, 1]) < 0:
        a_w = mul(a_w, -1)
    spur = at("0/104/41")
    a_g = X
    wm = edge("0/104/37", "0/104/41", "worm_mesh")[0]["measurements"]
    if abs(wm["distance_error_ldu"]) > 0.05:
        raise ValueError("Worm and 8T gear are not at their pitch centre distance")
    teeth, starts = 8, 1
    n = unit(cross(a_w, a_g))
    r_vec = mul(n, dot(sub(worm, spur), n))  # from gear axis toward worm axis
    contact = mul(unit(r_vec), 10.0)  # 8T pitch radius, LDU
    # Right-handed single-start thread (4716 slices advance +90 degrees per +2 LDU
    # along the part axis): surface speed along a_w equals w*lead/2pi.
    lever = dot(a_w, cross(a_g, contact))
    worm_ratio = math.copysign(starts / teeth, lever)
    signal("worm_angle", "s", s="control:rear_shaft")
    signal("diff_angle", f"{worm_ratio!r}*s", s="worm_angle")
    body(
        "worm_shaft",
        ["0/104/35", "0/104/37", "0/104/40", "0/104/36"],
        worm,
        a_w,
        "worm_angle",
    )
    body(
        "diff_shaft",
        ["0/104/34", "0/104/41", "0/104/38", "0/104/39", "0/104/49", "0/104/50"],
        spur,
        a_g,
        "diff_angle",
    )

    # ---- Hinged parts ---------------------------------------------------------
    lever_pos = edge("0/276", "0/282", "revolute")[0]["measurements"]["position"]
    signal("lever_angle", "s", s="control:gear_lever")
    body("gear_lever", ["0/282", "0/281"], lever_pos, X, "lever_angle")
    pivot = [0.0, -142.4, 696.8]  # hinge finger of 44302a (connector 'lckHng' world_position)
    signal("spoiler_angle", "s", s="control:spoiler")
    flap = [i for i in leaves("0/357/17") if i not in ("0/357/17/19", "0/357/17/20")]
    body("spoiler", flap, pivot, X, "spoiler_angle")

    plan.update(
        name="mustang10265",
        status="draft",
        controls=controls,
        signals=signals,
        bodies=bodies,
        anchors=anchors,
        checks=checks,
        notes=NOTES,
    )
    plan["mechanisms"] = curated_views(plan)
    review_edges(plan)
    return plan


NOTES = [
    "Authored from scratch for 10265-1_B-Model.mpd; no earlier 10265 recipe or rig was used.",
    "Motion values are offsets from the source pose. The car's left is +X, its front is -Z and -Y is up.",
    "Ideal rigid kinematics only: no backlash, friction, compliance, gravity or dynamics.",
    "Steering: wheel -> universal joint (exact Cardan relation) -> 16T pinion -> 40T crank gear -> crank pin"
    " carries the coupler beam -> two 6L tie rods -> kingpin knuckles. The coupler beam is held un-rotated"
    " by composing the crank with an equal and opposite pin rotation, so its balls translate exactly.",
    "Tie-rod lengths are closed numerically in 3D (distance checks); the solution is the source-pose branch.",
    "Rear worm drive: right-handed single-start 4716 worm turning the 8T gear on axle 9. The sign comes from"
    " the helix handedness of the LDraw thread slices; the magnitude 1/8 is tooth-count based. Axle 9 and"
    " its bevel gears are not meshed with anything that reaches the wheels in the discovered contacts.",
    "Wheels are free to spin on their hub axles. No contact connects the rear axle 5.5 shafts to a static"
    " bearing (inspection is incomplete), so rear hubs are rigged as spinning about the discovered axle line.",
    "The universal joint is exact: the centre cross is a child of the input yoke rotating about the input pivot"
    " (cardan_cross), and the output yoke follows tan(out)=cos(beta)tan(in). Both are verified numerically at build time.",
    "Steering lock is limited to the sampled-clearance-free range (hub bevels begin crossing the tie rods near"
    " 0.225 rad of wheel angle, about 5 degrees at the knuckles). The kinematics remain solvable to roughly +/-1.3 rad.",
    "The sill hinges of the windshield are confirmed contacts, but the windshield-and-roof group crossed neighbouring"
    " parts at every sampled angle beyond about 0.06 rad forward and immediately backward, so it is deferred, not rigged.",
    "Spoiler hinge pivot is the lckHng finger axis of 44302a (0/357/17/19). The matching single-finger part is an"
    " embedded DAT without connectors, so the pairing is geometric, not metadata-confirmed.",
]


def review_edges(plan):
    """Mark the connection records that were measured while authoring."""

    def mark(a, b, kind, text):
        for c in plan["connections"].values():
            if {c["a"], c["b"]} == {a, b} and c["kind"] == kind:
                c["status"] = "reviewed"
                c["review"] = text

    mark(
        "0/91/7",
        "0/103",
        "gear_mesh",
        "Measured: 40T and 16T, centre distance 70.0 LDU equals the pitch-circle sum, parallel axes; counter-rotating.",
    )
    mark(
        "0/104/37",
        "0/104/41",
        "worm_mesh",
        "Measured: single-start 4716 worm and 8T gear at 20.007 LDU centre distance; direction taken from thread handedness.",
    )
    for a, b in (("0/1/72", "0/407/0"), ("0/82/59", "0/407/1")):
        mark(a, b, "revolute", "Hinge fingers coincide along X at the sill; windshield swings about this line.")
    mark("0/276", "0/282", "revolute", "Gear-lever hinge arm on the console hinge plate; axis along X.")


def curated_views(plan):
    nodes = {n["id"]: n for n in plan["source"]["nodes"]}
    owned = {i for b in plan["bodies"].values() for i in b["instances"]}
    views = {}

    def view(key, label, bodies, inputs, outputs, review, notes=(), parts=(), disposition="planned"):
        views[key] = dict(
            label=label,
            parts=sorted(parts),
            bodies=bodies,
            inputs=inputs,
            outputs=outputs,
            notes=list(notes),
            disposition=disposition,
            review=review,
        )

    view(
        "steering",
        "Steering wheel to front knuckles",
        [
            "steering_column",
            "uj_cross",
            "steer_pinion",
            "crank",
            "pitman",
            "knuckle_l",
            "knuckle_r",
            "tierod_l",
            "tierod_r",
        ],
        ["control:steering_wheel"],
        ["body:knuckle_l", "body:knuckle_r"],
        "Gear mesh, ball joints and kingpin axes measured from connector frames; linkage closed numerically.",
        [
            "Universal joint ratio follows tan(out)=cos(beta)tan(in); the bend angle is about 29 degrees.",
            "Range limited to sampled-clearance-free wheel angles; fenders and tyres were not part of the sampled pairs that failed.",
        ],
    )
    view(
        "wheels",
        "Four free-spinning wheels",
        ["wheel_fl", "wheel_fr", "wheel_rl", "wheel_rr"],
        [f"control:spin_{w}" for w in ("fl", "fr", "rl", "rr")],
        [f"body:wheel_{w}" for w in ("fl", "fr", "rl", "rr")],
        "Rim, tyre, bush, hub axle and bevel on each hub share the discovered axle line; front wheels follow the knuckles.",
    )
    view(
        "rear_drive",
        "Rear worm shaft to 8T gear and axle 9",
        ["worm_shaft", "diff_shaft"],
        ["control:rear_shaft"],
        ["body:diff_shaft"],
        "Worm mesh measured; output stops at axle 9 and its bevels, with no discovered path to the wheels.",
    )
    view(
        "gear_lever",
        "Gear lever hinge",
        ["gear_lever"],
        ["control:gear_lever"],
        ["body:gear_lever"],
        "Hinge contact between 0/276 and 0/282 confirmed; the pneumatic T knob 0/281 is assumed to be seated in the arm.",
    )
    view(
        "spoiler",
        "Rear spoiler flap",
        ["spoiler"],
        ["control:spoiler"],
        ["body:spoiler"],
        "Pivot from the 44302a finger connector; the single-finger partner is an embedded DAT with no connectors.",
    )

    leftovers = [i for i in plan["discovery"]["mechanical_parts"] if i not in owned]
    groups = [
        (
            "windshield_hinges",
            "Windshield sill hinges",
            lambda i: i.startswith("0/407/") or i in ("0/1/72", "0/82/59"),
            "Revolute contacts at x=+/-100 confirmed (axis X, y=-66.8, z=130.6), but sampled clearance of the windshield with its"
            " roof and trusses found crossings at 0.07 rad forward and at -0.01 rad backward, so no usable travel was rigged.",
        ),
        (
            "bottom_group_axles",
            "Transverse axles in the Bottom Group",
            lambda i: i.startswith("0/0/") or i in ("0/94", "0/95", "0/100", "0/101", "0/309"),
            "Axle/bush chains on the chassis plate were not traced to an input or output.",
        ),
        (
            "door_sill_hinges",
            "Door sill hinge plate pairs",
            lambda i: i.startswith(("0/1/", "0/82/")),
            "Hinge plate pairs and hinge bases form angled sill brackets; no door panel or actuation was found.",
        ),
        (
            "door_rails",
            "Plates with door rail",
            lambda i: nodes[i]["ref"].startswith(("4510", "32028", "32531")) or "Door Rail" in nodes[i]["description"],
            "Sliding-rail candidates in bonnet, engine, dashboard, lid; no slide path studied.",
        ),
        (
            "engine_hinges",
            "Engine bank hinges",
            lambda i: i.startswith("0/284/"),
            "Hinge pairs set the engine bank angle; revolute contacts are geometric only and nothing drives them.",
        ),
        (
            "belt_drive",
            "Supercharger belts and pulleys",
            lambda i: i.startswith(("0/285/", "0/449/")) or i == "0/449",
            "Belt/pulley arrangement seen in the source; pulley coupling not rigged.",
        ),
        (
            "rear_axle_adjust",
            "Rear axle adjustment linkage",
            lambda i: i.startswith("0/88/"),
            "Cross blocks, axle pins and axles for rear alignment; support of the rear hub axles not resolved.",
        ),
        (
            "front_axle_structure",
            "Front axle structure and bevels",
            lambda i: i.startswith("0/90/"),
            "Cross blocks, axle pins, connectors and bevel gears inboard of the knuckles; no independent motion found.",
        ),
        (
            "rear_axle_structure",
            "Rear axle structure",
            lambda i: i.startswith("0/104/") or i in ("0/105", "0/106"),
            "Cross blocks, axle pins, axlehole bricks and bevel gears of the rear assembly not driven by the worm.",
        ),
        (
            "console_and_roof_hinges",
            "Radio console, roof and trunk hinges",
            lambda i: i in ("0/276", "0/277", "0/310/4") or i.startswith("0/357/"),
            "Radio console hinge and the trunk lid hinge pair are visible but unmeasured; the lid is also posed 15 degrees in the source.",
        ),
        (
            "trim_axles",
            "Stabilizer, battery, radiator, exhaust, nitrous and steering-column plate",
            lambda i: i.startswith(("0/412/", "0/413/", "0/417/", "0/418/", "0/450/", "0/451/", "0/180/", "0/312/")),
            "Axle/pin/elbow trim parts found by library category; no motion input was identified.",
        ),
        (
            "universal_joint_leftovers",
            "Universal joint ends",
            lambda i: i in ("0/307", "0/308"),
            "Moving universal-joint parts are in the steering view; this entry only exists if they were left over.",
        ),
    ]
    remaining = set(leftovers)
    for key, label, pred, text in groups:
        parts = sorted((i for i in remaining if pred(i)), key=lambda s: [int(x) for x in s.split("/")])
        if not parts:
            continue
        remaining -= set(parts)
        view(key, label, [], [], [], "Deferred, not reviewed as static: " + text, ["Parts: %d." % len(parts)], parts, "deferred")
    if remaining:
        view(
            "unclassified",
            "Other discovered mechanical parts",
            [],
            [],
            [],
            "Deferred: no review was done for these parts.",
            [],
            sorted(remaining),
            "deferred",
        )
    return views


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--study", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--ready", action="store_true", help="mark the plan ready for rigging")
    parser.add_argument(
        "--steer-limit",
        type=float,
        default=0.2,
        help="steering wheel range in radians; values above 0.2 exceed the sampled-clearance-free range",
    )
    args = parser.parse_args()
    study = contract.load(args.study)
    plan = build(study, args.steer_limit)
    if args.ready:
        plan["status"] = "ready"
    contract.save(args.output, plan)
    print(contract.validate(plan))


if __name__ == "__main__":
    main()
