"""Studied motion plans. Recipes demonstrate the contract; agents can author others.

Selectors deliberately fail if source parts change. Coordinates come from the
source/shadow library and the supplied F1 reference rig, not part-name guessing.
"""

import math

from . import plan as contract
from .math3d import (
    cross,
    direction,
    identity,
    length,
    point,
    rack_ratio,
    signed_gear_ratio,
    sub,
    unit,
)
from .source import Document, normalized


def one(nodes, ref, position=None, key="local"):
    hits = [
        n
        for n in nodes
        if normalized(n["ref"]) == normalized(ref)
        and (position is None or length(sub(point(n[key], [0, 0, 0]), position)) < 0.5)
    ]
    if len(hits) != 1:
        raise ValueError(f"Expected one {ref} at {position}, found {len(hits)}")
    return hits[0]


class Builder:
    def __init__(self, manifest, name, base=None):
        self.plan = contract.draft(manifest, name)
        self.base = base or identity()

    def control(self, name, lo, hi, description, unit_name="radian"):
        self.plan["controls"][name] = dict(
            default=0.0, min=lo, max=hi, unit=unit_name, description=description
        )
        self.signal(name, f"clamp(v,{lo!r},{hi!r})", v="control:" + name)
        return name

    def signal(self, name, expr, **variables):
        self.plan["signals"][name] = dict(
            expression=expr,
            variables={
                k: v if ":" in v else "signal:" + v for k, v in variables.items()
            },
        )
        return name

    def body(
        self,
        name,
        instances,
        origin,
        axis,
        signal=None,
        kind="revolute",
        parent=None,
        x_hint=None,
        **extra,
    ):
        b = dict(
            instances=[n["id"] if isinstance(n, dict) else n for n in instances],
            kind=kind,
            origin=point(self.base, origin),
            axis=direction(self.base, axis),
            **extra,
        )
        if signal:
            b["signal"] = signal
        if parent:
            b["parent"] = parent
        if x_hint is not None:
            b["x_hint"] = direction(self.base, x_hint)
        self.plan["bodies"][name] = b

    def anchor(self, name, body, p):
        self.plan["anchors"][name] = dict(body=body, point=point(self.base, p))

    def distance(self, name, a, b, distance, tolerance=0.02):
        self.plan["checks"].append(
            dict(
                kind="distance",
                name=name,
                a=a,
                b=b,
                length=distance,
                tolerance=tolerance,
            )
        )

    def finish(self, notes):
        self.plan.update(status="ready", notes=notes)
        contract.validate(self.plan)
        return self.plan


def slider_cranks(b, crank, centre, rods, pistons, key="local", first=0):
    """Pistons and conrods on a crank about +Z; `crank` names its body and signal."""
    for i, rod in enumerate(rods, first):
        pin = point(rod[key], [0, 0, 0])
        ball = point(rod[key], [0, -40, 0])
        piston = min(pistons, key=lambda p: length(sub(point(p[key], [0, 0, 0]), ball)))
        pp = point(piston[key], [0, 0, 0])
        if length(sub(pp, ball)) > 1:
            raise ValueError("Conrod does not meet piston ball")
        cr, pr = sub(pin, centre), sub(pp, centre)
        r, s0 = math.hypot(*cr[:2]), math.hypot(*pr[:2])
        bank = unit([pr[0], pr[1], 0])
        # Lateral offset (LDU) of the piston's own axis from the crank centre.
        if length(cross(direction(piston[key], [0, 1, 0]), [pr[0], pr[1], 0])) > 0.5:
            raise ValueError("Cylinder axis does not pass through the crank centre")
        phase = math.atan2(cr[1], cr[0]) - math.atan2(pr[1], pr[0])
        rod_length = math.hypot(pp[0] - pin[0], pp[1] - pin[1])
        b.signal(
            f"piston{i}",
            f"{r!r}*cos({phase!r}+a)+sqrt({rod_length**2!r}-pow({r!r}*sin({phase!r}+a),2))-{s0!r}",
            a=crank,
        )
        b.body(
            f"piston{i}",
            [piston],
            pp,
            bank,
            f"piston{i}",
            kind="prismatic",
            x_hint=[0, 0, 1],
        )
        b.anchor(f"crank_pin{i}", crank, pin)
        b.anchor(f"piston_pin{i}", f"piston{i}", pp)
        b.body(
            f"conrod{i}",
            [rod],
            pin,
            [0, 0, 1],
            kind="rod",
            x_hint=cross(sub(pp, pin), [0, 0, 1]),
            start=f"crank_pin{i}",
            end=f"piston_pin{i}",
        )
        b.distance(
            f"conrod{i}", f"crank_pin{i}", f"piston_pin{i}", length(sub(pp, pin))
        )


def car106(manifest):
    car = one(manifest["nodes"], "106 - car.ldr")
    nodes = [n for n in manifest["nodes"] if n["parent"] == car["id"]]
    b = Builder(manifest, "car106", car["world"])
    for ref, name, axis in [
        ("3821.dat", "door_right", [0, -1, 0]),
        ("3822.dat", "door_left", [0, 1, 0]),
    ]:
        n = one(nodes, ref)
        b.control(
            name,
            0,
            math.radians(75),
            "Open the " + name.replace("_", " ") + " about its stud hinge",
        )
        b.body(name, [n], point(n["local"], [0, 0, 0]), axis, name)
    roof = one(nodes, "4213.dat")
    b.control(
        "roof", 0, math.radians(75), "Open the roof about the roof-holder finger hinge"
    )
    b.body("roof", [roof], point(roof["local"], [0, 4, 36]), [0, 0, 1], "roof")
    wheels = [n for n in nodes if normalized(n["ref"]) == "106 - wheel assembly.ldr"]
    for i, w in enumerate(wheels):
        name = "spare" if i == 0 else f"wheel_{i}"
        parts = [n for n in manifest["nodes"] if n["parent"] == w["id"]]
        b.control(
            name,
            -2 * math.pi,
            2 * math.pi,
            "Rotate rim and tyre together; "
            + ("spare wheel" if i == 0 else "road wheel"),
        )
        b.body(
            name,
            parts,
            point(w["local"], [0, 0, 0]),
            direction(w["local"], [0, 0, 1]),
            name,
        )
    return b.finish(
        [
            "Roof axis: shadow 4213 SNAP_FGR at (0,4,36), local X.",
            "Door hinge: 3822s01 cylindrical receptacle at local X=Z=0.",
            "Wheel package: source 4624 + 4084, local Z axle.",
            "Angles are offsets from source pose. Roof/door limits are 75 degrees; sampled surface-crossing checks found obstructions at 90 degrees.",
            "The one-piece 3829c01 steering shortcut is static; this System car has no steering transmission.",
        ]
    )


def spaceship928(manifest):
    # The selected hatch also works alone, with a virtual support at its hinge.
    standalone = (
        normalized(manifest["section"]) == "928 - space ship - cargo hatchway.ldr"
    )
    hatch = (
        None
        if standalone
        else one(manifest["nodes"], "928 - Space Ship - Cargo Hatchway.ldr")
    )
    base = identity() if standalone else hatch["world"]
    members = [
        n
        for n in manifest["nodes"]
        if n["kind"] == "part" and (standalone or n["id"].startswith(hatch["id"] + "/"))
    ]
    b = Builder(manifest, "hatch928", base)
    b.control(
        "hatch",
        -math.radians(114) if standalone else -1.25,
        0,
        "Cargo ramp: zero is the source open pose; negative raises it to the clearance stop in the parent model",
    )
    b.body("hatch", members, [0, 0, 0], [1, 0, 0], "hatch")
    return b.finish(
        [
            "3149e support and 314e lid share the source origin and local X finger-hinge axis.",
            "The rigid group includes the 3958 plate. Parent source already places the hatch at an angle.",
            "Standalone selection has a virtual fixed support; actual support and pivot pin live in the parent model.",
            "Parent range stops at -1.25 radians before its already-posed side hatches. Full closure requires coordinating those hatches. Standalone range is wider because those obstructions are absent.",
            "Other spaceship mechanisms remain static. This example verifies nested transforms and exact group selection.",
        ]
    )


def technic42000(manifest):
    from .recipe_42000_data import BODIES, FRAMES, MESHES, PINION, RACK_POINT

    standalone = normalized(manifest["section"]) == "42000 - 42000.l3b.ldr"
    car = None if standalone else one(manifest["nodes"], "42000 - 42000.L3B.ldr")
    nodes = [
        n
        for n in manifest["nodes"]
        if n["parent"] == ("root" if standalone else car["id"])
    ]
    b = Builder(manifest, "technic42000", identity() if standalone else car["world"])
    body_nodes = {
        name: [one(nodes, ref, pos) for ref, pos in selectors]
        for name, selectors in BODIES.items()
    }
    ratios = {}
    for a, ca, na, bb, cb, nb in MESHES:
        ratios[(a, bb)] = signed_gear_ratio(FRAMES[a][2], ca, na, FRAMES[bb][2], cb, nb)
    b.control(
        "steering",
        -1.0160234876686451,
        1.0160234876686451,
        "Driver yoke angle; propagates through gears, rack and tie rods",
    )
    for w in ("fl", "fr", "rl", "rr"):
        b.control(
            "spin_" + w,
            -2 * math.pi,
            2 * math.pi,
            "Wheel "
            + w.upper()
            + " angle; rear wheels drive the differential and engine",
        )
    b.signal("yoke", "s", s="steering")
    b.signal("column", f"{ratios[('yoke', 'column')]!r}*s", s="yoke")
    b.signal("steer_shaft", f"{ratios[('column', 'steer_shaft')]!r}*s", s="column")
    rack_k = rack_ratio(
        FRAMES[PINION[0]][2], PINION[1], PINION[2], RACK_POINT, FRAMES["rack"][2]
    )
    b.signal("rack", f"{rack_k!r}*s", s="steer_shaft")
    for w in ("fl", "fr", "rl", "rr"):
        b.signal("wheel_" + w, "s", s="spin_" + w)
    b.signal("diff", "(l+r)*0.5", l="spin_rl", r="spin_rr")
    b.signal(
        "planet",
        f"{ratios[('wheel_rl', 'planet')]!r}*(l-r)*0.5",
        l="spin_rl",
        r="spin_rr",
    )
    b.signal("propshaft", f"{ratios[('diff', 'propshaft')]!r}*s", s="diff")
    b.signal("crank", f"{ratios[('propshaft', 'crank')]!r}*s", s="propshaft")
    for side, sx in (("l", 1), ("r", -1)):
        king = FRAMES["knuckle_" + side][1]
        tow = one(nodes, "6628.dat", [60 * sx, -70, -320])
        knuckle = one(nodes, "11949.dat", [220 * sx, -60, -280])
        rod = body_nodes["tierod_" + side][0]
        q0 = point(tow["local"], [-10, 0, 0])
        ends = [point(rod["local"], v) for v in ([0, 0, 0], [0, 0, 160])]
        b0 = min(
            [point(knuckle["local"], v) for v in ([40, 0, 0], [-40, 0, 0])],
            key=lambda p: min(length(sub(p, e)) for e in ends),
        )
        if any(min(length(sub(p, e)) for e in ends) > 1 for p in (q0, b0)):
            raise ValueError("Steering link does not meet its ball centres")
        dx, dz = q0[0] - king[0], q0[2] - king[2]
        ax, az = b0[0] - king[0], b0[2] - king[2]
        arm, link = math.hypot(ax, az), length(sub(b0, q0))
        c0 = (arm * arm + dx * dx + dz * dz - link * link) / (
            2 * arm * math.hypot(dx, dz)
        )
        branch = math.copysign(1, math.atan2(dx * az - dz * ax, dx * ax + dz * az))
        b.signal("rho_" + side, f"sqrt(pow({dx!r}+d,2)+{dz * dz!r})", d="rack")
        # Split equations into signals to keep each Blender expression below 255 bytes.
        b.signal(
            "cosine_" + side,
            f"({arm * arm - link * link!r}+rho*rho)/({2 * arm!r}*rho)",
            rho="rho_" + side,
        )
        b.signal(
            "knuckle_" + side,
            f"atan2({-dz!r}*d,{dx * dx + dz * dz!r}+{dx!r}*d)+{branch!r}*(acos(clamp(c,-1,1))-{math.acos(c0)!r})",
            d="rack",
            c="cosine_" + side,
        )
        b.anchor("rack_ball_" + side, "rack", q0)
        b.anchor("knuckle_ball_" + side, "knuckle_" + side, b0)
        b.body(
            "tierod_" + side,
            [rod],
            q0,
            [0, -1, 0],
            kind="rod",
            x_hint=cross(sub(b0, q0), [0, -1, 0]),
            start="rack_ball_" + side,
            end="knuckle_ball_" + side,
        )
        b.distance("tie_rod_" + side, "rack_ball_" + side, "knuckle_ball_" + side, link)
    for name, (parent, origin, axis, hint) in FRAMES.items():
        b.body(
            name,
            body_nodes[name],
            origin,
            axis,
            name,
            kind="prismatic" if name == "rack" else "revolute",
            parent=parent,
            x_hint=hint,
        )
    slider_cranks(
        b,
        "crank",
        FRAMES["crank"][1],
        [n for n in nodes if normalized(n["ref"]) == "2852.dat"],
        [n for n in nodes if normalized(n["ref"]) == "2851.dat"],
    )
    return b.finish(
        [
            "Mechanism geometry and selectors adapted from the supplied rig_42000.py.",
            "Steering locks preserve the supplied collision-swept yoke range (about +/-58.215 degrees).",
            "Gear contact signs use the original tangent-velocity method; rack pitch is 8 LDU.",
            "Two tie-rod closures and eight connecting-rod closures are checked numerically.",
            "Ideal rigid kinematics: no backlash, friction, compliance or force simulation.",
            "Car travel/path integration remains in the supplied specialized rig; these controls operate the stationary mechanisms.",
        ]
    )


def w16_42083(manifest):
    # Section frame throughout: the lower banks are nested submodel occurrences.
    if normalized(manifest["section"]) != "42083 - engine.ldr":
        raise ValueError("Recipe 42083 studies the section '42083 - engine.ldr'")
    parts = [n for n in manifest["nodes"] if n["kind"] == "part"]
    b = Builder(manifest, "w16_42083")
    z = [0, 0, 1]
    # (gear ref, gear centre, teeth, expected crank-group size) per shaft.
    shafts = {
        "input_shaft": ("18575.dat", [0, 90, -40], 20, None),
        "crank_c": ("24505.dat", [0, 50, 200], 24, 11),
        "crank_l": ("24505.dat", [-36, 98, 200], 24, 10),
        "crank_r": ("24505.dat", [36, 98, 200], 24, 10),
    }
    for ref, centre, _, _ in shafts.values():
        gear = one(parts, ref, centre, "world")
        if length(cross(direction(gear["world"], [0, 0, 1]), z)) > 1e-6:
            raise ValueError(f"Gear {gear['id']} axis is not parallel to Z")
    crank_refs = {"2853.dat", "2854.dat", "32062.dat", "32073.dat", "4519.dat"}
    crank_refs |= {"24505.dat", "32270.dat"}

    def near(n, centre, radius):
        p = point(n["world"], [0, 0, 0])
        return math.hypot(p[0] - centre[0], p[1] - centre[1]) <= radius

    groups = {
        "input_shaft": [
            one(parts, ref, p, "world")
            for ref, p in (
                ("55013.dat", [0, 90, -68]),
                ("18575.dat", [0, 90, -40]),
                ("59443.dat", [0, 90, -150]),
            )
        ]
    }
    for name, (_, centre, _, size) in shafts.items():
        if size is None:
            continue
        groups[name] = [
            n
            for n in parts
            if normalized(n["ref"]) in crank_refs and near(n, centre, 10.5)
        ]
        if len(groups[name]) != size:
            raise ValueError(
                f"{name}: expected {size} parts, found {len(groups[name])}"
            )
    bevel = signed_gear_ratio(z, [0, 90, -40], 20, z, [0, 50, -40], 12)
    one(parts, "32270.dat", [0, 50, -40], "world")  # 12T meshing the input 20T
    b.control(
        "drive",
        -4 * math.pi,
        4 * math.pi,
        "Input shaft angle at the gearbox joiner; turns all three crankshafts",
    )
    b.signal("crank_c", f"{bevel!r}*s", s="drive")
    for side in ("l", "r"):
        k = signed_gear_ratio(
            z, shafts["crank_c"][1], 24, z, shafts["crank_" + side][1], 24
        )
        b.signal("crank_" + side, f"{k!r}*s", s="crank_c")
    for name, (_, centre, _, _) in shafts.items():
        b.body(
            name, groups[name], centre, z, "drive" if name == "input_shaft" else name
        )
    rods = [n for n in parts if normalized(n["ref"]) == "2852.dat"]
    pistons = [n for n in parts if normalized(n["ref"]) == "2851.dat"]
    first = 0
    for name in ("crank_c", "crank_l", "crank_r"):
        centre = shafts[name][1]
        own = [r for r in rods if near(r, centre, 10.5)]
        slider_cranks(b, name, centre, own, pistons, "world", first)
        first += len(own)
    if first != 16 or len(pistons) != 16:
        raise ValueError(
            f"Expected 16 conrods and pistons, found {first}/{len(pistons)}"
        )
    return b.finish(
        [
            "Source: 42083 Bugatti Chiron W16 engine section by Philippe Hurbain [Philo], CCAL 2.0.",
            "Input axle 9 carries 20T double bevel 83 and joiner 111 (pyldraw3 axle contacts); 111 is the missing gearbox interface in chassisrear.",
            "20T (0,90) meshes the 12T double bevel on the centre crank (0,50): coplanar at z=-40, centre distance 40 LDU.",
            "Centre 24T (0,50) meshes both lower 24T gears (-36,98) and (36,98): coplanar at z=200, centre distance 60 LDU; the lower gears are 72 LDU apart and do not mesh.",
            "Gear/axle/crank chains for the lower banks are pyldraw3 contacts; the 15-degree centre crank reports none, but its axles are coaxial with the 12T and 24T axle holes.",
            "Crank groups are selected within 10.5 LDU of each axis and counted; Beam 1 (110) has a round hole and stays static.",
            "Sixteen slider cranks: 10 LDU throw, 40 LDU conrods; each cylinder axis passes within 0.5 LDU of its crank centre.",
            "Ideal rigid kinematics: no gear tooth phasing, backlash, friction or force simulation; no collision proof or bore containment check.",
        ]
    )


RECIPES = {
    "106": car106,
    "928": spaceship928,
    "42000": technic42000,
    "42083": w16_42083,
}


def create(path, recipe=None, section=None):
    manifest = Document(path).manifest(section)
    return RECIPES[recipe](manifest) if recipe else contract.draft(manifest)
