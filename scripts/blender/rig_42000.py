"""Rig and animate the LEGO 42000 Grand Prix Racer (data/models-annotated/42000-1.mpd).

Mechanisms, in LDraw space (LDU, -Y up, the car faces -Z, +X is the car's left):

* Steering: the driver's yoke (3L double pin + two 2L beams on an axle 6) drives a 20T
  double bevel, which turns the vertical steering column (12T bevel, with a 12T knob on
  top). The column turns a second 20T on the steering shaft, whose 12T pinion moves the
  rack. Tie rods (160 LDU between ball centres) turn both knuckles about vertical kingpins.
* Drive: each rear wheel turns a differential side gear; the carrier's 28T crown turns
  the propeller shaft (20T), which turns the V8 crank (12T) with 8 conrods and pistons.

Every moving body is an empty, PIV_<body>, under a static FRM_<body> whose Z is the joint
axis. Drivers (simple expressions only) and a few constraints pose them from CTRL_42000:
`steering` (yoke angle) and `spin_fl/fr/rl/rr` (wheel angles). `integrate()` turns the
`steering` and `speed` curves into the car's path and the rolling angle of each wheel.

In Blender:
    import sys; sys.path.insert(0, "<repo>/scripts/blender")
    import rig_42000; rig_42000.main(save="<repo>/42000-1-animated.blend")
Headless:
    blender -b --python scripts/blender/rig_42000.py -- --glb 42000-1.glb --save 42000-1-animated.blend
    blender -b 42000-1-animated.blend --python scripts/blender/rig_42000.py -- --bake-export out.blend
"""

import argparse
import math
import os
import sys

import bpy
from mathutils import Matrix, Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ldraw_mecha as lm  # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MPD = os.path.join(REPO, "data", "models-annotated", "42000-1.mpd")
SUBMODEL = "42000 - 42000.L3B.ldr"
GLTF_ROOT = "Node_0"
CTRL = "CTRL_42000"
RIG_COLLECTION = "42000 rig"
RIG_PREFIXES = ("FRM_", "PIV_", "BALL_", "PIN_", "CAR_")

X, Z, UP = Vector((1, 0, 0)), Vector((0, 0, 1)), Vector((0, -1, 0))

BODIES = {
    "yoke": [("3706.dat", (0, -100, 50)), ("32269.dat", (0, -100, 0)), ("3713.dat", (0, -100, 80)),
             ("32138.dat", (0, -100, 101)), ("43857.dat", (20, -100, 101)), ("43857.dat", (-20, -100, 101))],
    "column": [("87083.dat", (0, -68, -20)), ("3713.dat", (0, -40, -20)), ("6589.dat", (0, -73, -20)),
               ("32123a.dat", (0, -85, -20)), ("59443.dat", (0, -110, -20)), ("4519.dat", (0, -140, -20)),
               ("32270.dat", (0, -160, -20))],
    "steer_shaft": [("32269.dat", (0, -100, -40)), ("3705.dat", (0, -100, -70)), ("59443.dat", (0, -100, -110)),
                    ("32062.dat", (0, -100, -130)), ("59443.dat", (0, -100, -150)), ("3708.dat", (0, -100, -270)),
                    ("32270.dat", (0, -100, -320))],
    "rack": [("87761.dat", (0, -80, -320)), ("6628.dat", (60, -70, -320)), ("6628.dat", (-60, -70, -320))],
    "tierod_l": [("32293.dat", (220, -60, -320))],
    "tierod_r": [("32293.dat", (-60, -60, -320))],
    "knuckle_l": [("11949.dat", (220, -60, -280))],
    "knuckle_r": [("11949.dat", (-220, -60, -280))],
    "wheel_fl": [("92909.dat", (250, -60, -280)), ("44772.dat", (272, -60, -280)), ("44771.dat", (270, -60, -280))],
    "wheel_fr": [("92909.dat", (-250, -60, -280)), ("44772.dat", (-272, -60, -280)), ("44771.dat", (-270, -60, -280))],
    "wheel_rl": [("6589.dat", (17, -60, 640)), ("92906.dat", (60, -60, 640)), ("32494.dat", (60, -60, 640)),
                 ("3706.dat", (140, -60, 640)), ("32494.dat", (225, -60, 640)), ("92909.dat", (250, -60, 640)),
                 ("44772.dat", (272, -60, 640)), ("44771.dat", (270, -60, 640))],
    "wheel_rr": [("6589.dat", (-17, -60, 640)), ("92906.dat", (-60, -60, 640)), ("32494.dat", (-60, -60, 640)),
                 ("3706.dat", (-140, -60, 640)), ("32494.dat", (-225, -60, 640)), ("92909.dat", (-250, -60, 640)),
                 ("44772.dat", (-272, -60, 640)), ("44771.dat", (-270, -60, 640))],
    "diff": [("62821.dat", (0, -60, 640))],
    "planet": [("6589.dat", (0, -60, 657))],
    "propshaft": [("6587.dat", (0, -60, 578)), ("32269.dat", (0, -60, 560)), ("32269.dat", (0, -60, 600))],
    "crank": [("2853.dat", (0, -100, 470)), ("2854.dat", (0, -100, 450)), ("32062.dat", (10, -100, 430)),
              ("2854.dat", (0, -100, 410)), ("32062.dat", (-10, -100, 390)), ("2854.dat", (0, -100, 370)),
              ("2853.dat", (0, -100, 350)), ("32073.dat", (0, -100, 530)), ("32062.dat", (0, -100, 320)),
              ("32270.dat", (0, -100, 560))],
}

# body: (parent body, origin, joint axis, x hint); revolute about Z, except the rack slides along Z.
FRAMES = {
    "yoke": (None, (0, -100, 50), Z, X),
    "column": (None, (0, -100, -20), UP, X),
    "steer_shaft": (None, (0, -100, -180), Z, X),
    "rack": (None, (0, -80, -320), X, Z),
    "knuckle_l": (None, (220, -60, -280), UP, X),
    "knuckle_r": (None, (-220, -60, -280), UP, X),
    "wheel_fl": ("knuckle_l", (270, -60, -280), X, Z),
    "wheel_fr": ("knuckle_r", (-270, -60, -280), X, Z),
    "wheel_rl": (None, (270, -60, 640), X, Z),
    "wheel_rr": (None, (-270, -60, 640), X, Z),
    "diff": (None, (0, -60, 640), X, Z),
    "planet": ("diff", (0, -60, 657), Z, X),
    "propshaft": (None, (0, -60, 580), Z, X),
    "crank": (None, (0, -100, 410), Z, X),
}

# Gear meshes: (body A, centre A, teeth A, body B, centre B, teeth B). The diff's 28T crown
# sits on its -X end (measured from the 62821 mesh).
MESHES = [
    ("yoke", (0, -100, 0), 20, "column", (0, -73, -20), 12),
    ("column", (0, -73, -20), 12, "steer_shaft", (0, -100, -40), 20),
    ("diff", (-24, -60, 640), 28, "propshaft", (0, -60, 600), 20),
    ("propshaft", (0, -60, 560), 20, "crank", (0, -100, 560), 12),
    ("wheel_rl", (17, -60, 640), 12, "planet", (0, -60, 657), 12),
]
PINION = ("steer_shaft", (0, -100, -320), 12)
RACK_POINT = (0, -80, -320)
REAR_AXLE_Z = 640
TIEROD_LENGTH = 160.0  # ball centre to ball centre of the 32293 steering link
CONROD_BALL = Vector((0, -40, 0))  # conrod ball in 2852 part space
TOWBALL_BALL = Vector((-10, 0, 0))  # 6628 ball in part space
KNUCKLE_BALLS = (Vector((40, 0, 0)), Vector((-40, 0, 0)))  # 11949 ball arms in part space


def axis(body):
    return Vector(FRAMES[body][2])


def fmt(v):
    return f"({v:.8g})" if v < 0 else f"{v:.8g}"


class Steering:
    """Yoke angle -> column, shaft, rack travel and knuckle angles (all closed form)."""

    def __init__(self, parts):
        a, b, c = MESHES[0], MESHES[1], PINION
        self.k_column = lm.signed_ratio(axis(a[0]), Vector(a[1]), a[2], axis(a[3]), Vector(a[4]), a[5])
        self.k_shaft = self.k_column * lm.signed_ratio(axis(b[0]), Vector(b[1]), b[2], axis(b[3]), Vector(b[4]), b[5])
        self.k_rack = self.k_shaft * lm.rack_ratio(axis(c[0]), Vector(c[1]), c[2], Vector(RACK_POINT), axis("rack"))
        self.sides = {}
        for side, sx in (("l", 1), ("r", -1)):
            kingpin = Vector(FRAMES[f"knuckle_{side}"][1])
            towball = lm.find_part(parts, "6628.dat", (60 * sx, -70, -320))
            knuckle = lm.find_part(parts, "11949.dat", (220 * sx, -60, -280))
            tierod = lm.find_part(parts, "32293.dat", (220, -60, -320) if sx > 0 else (-60, -60, -320))
            q0 = towball.matrix @ TOWBALL_BALL
            ends = (tierod.matrix @ Vector((0, 0, 0)), tierod.matrix @ Vector((0, 0, TIEROD_LENGTH)))
            b0 = min((knuckle.matrix @ v for v in KNUCKLE_BALLS), key=lambda p: min((p - e).length for e in ends))
            for p in (q0, b0):  # the tie rod really joins the rack ball to the knuckle ball
                assert min((p - e).length for e in ends) < 1.0, (side, p, ends)
            d0 = Vector((q0.x - kingpin.x, q0.z - kingpin.z))
            arm0 = Vector((b0.x - kingpin.x, b0.z - kingpin.z))
            arm, link = arm0.length, (b0 - q0).length
            c0 = (arm * arm + d0.length_squared - link * link) / (2 * arm * d0.length)
            rel = math.atan2(d0.x * arm0.y - d0.y * arm0.x, d0.dot(arm0))
            self.sides[side] = dict(kingpin=kingpin, q0=q0, b0=b0, d0=d0, arm=arm, link=link,
                                    acos_c0=math.acos(c0), branch=math.copysign(1.0, rel))

    def rack(self, y):
        return self.k_rack * y

    def knuckle(self, side, y):
        """Knuckle angle about LDraw -Y (= world up): + turns the wheel towards the car's left."""
        s = self.sides[side]
        d = self.rack(y)
        dx, dz = s["d0"].x + d, s["d0"].y
        rho = math.hypot(dx, dz)
        c = (s["arm"] ** 2 + rho * rho - s["link"] ** 2) / (2 * s["arm"] * rho)
        dbeta = math.atan2(-s["d0"].y * d, s["d0"].length_squared + s["d0"].x * d)
        return dbeta + s["branch"] * (math.acos(max(-1.0, min(1.0, c))) - s["acos_c0"])

    def knuckle_expr(self, side):
        """Same as knuckle(), as a driver simple expression of y, lo and hi (Blender caps it at 255 chars)."""
        s = self.sides[side]
        d0x, d0z, arm, link = s["d0"].x, s["d0"].y, s["arm"], s["link"]
        d = f"{fmt(self.k_rack)}*clamp(y,lo,hi)"
        dx2 = f"pow({fmt(d0x)}+{d},2)"
        return (f"atan2({fmt(-d0z)}*{d},{fmt(s['d0'].length_squared)}+{fmt(d0x)}*{d})"
                f"+{fmt(s['branch'])}*acos(clamp(({fmt(arm * arm - link * link + d0z * d0z)}+{dx2})"
                f"/({fmt(2 * arm)}*sqrt({dx2}+{fmt(d0z * d0z)})),-1,1))-{fmt(s['branch'] * s['acos_c0'])}")


class Drive:
    """Rear wheel angles -> differential, propeller shaft, crank, conrods and pistons."""

    def __init__(self, parts):
        ratio = {}
        for a, ca, na, b, cb, nb in MESHES[2:]:
            ratio[(a, b)] = lm.signed_ratio(axis(a), Vector(ca), na, axis(b), Vector(cb), nb)
        self.k_prop = ratio[("diff", "propshaft")]
        self.k_crank = self.k_prop * ratio[("propshaft", "crank")]
        self.k_planet = ratio[("wheel_rl", "planet")]
        centre = Vector(FRAMES["crank"][1])
        pistons = [p for p in parts if p.file == "2851.dat"]
        self.cylinders = []
        for rod in (p for p in parts if p.file == "2852.dat"):
            ball = rod.matrix @ CONROD_BALL
            piston = min(pistons, key=lambda p: (p.pos - ball).length)
            assert (piston.pos - ball).length < 1.0, (rod.idx, ball)
            pin, pp = rod.pos - centre, piston.pos - centre
            self.cylinders.append(dict(
                rod=rod, piston=piston, pin=rod.pos.copy(), r=pin.xy.length, phi0=math.atan2(pin.y, pin.x),
                bank=Vector((pp.x, pp.y, 0)).normalized(), gamma=math.atan2(pp.y, pp.x), s0=pp.xy.length,
                length=(piston.pos - rod.pos).xy.length))

    def piston_expr(self, cyl):
        a = f"({fmt(cyl['phi0'] - cyl['gamma'])}+{fmt(self.k_crank)}*(rl+rr)*0.5)"
        return (f"{fmt(cyl['r'])}*cos({a})+sqrt({fmt(cyl['length'] ** 2)}-pow({fmt(cyl['r'])}*sin({a}), 2))"
                f"-{fmt(cyl['s0'])}")


# --- Building ----------------------------------------------------------------------------

def tyre_radius(sub, obj):
    """Largest distance of the tyre mesh from its axle (part-local Z), in LDU."""
    inv = lm.part_ldraw_matrix(obj, sub).inverted()
    sub_inv = sub.matrix_world.inverted()
    radius = 0.0
    for m in (c for c in obj.children_recursive if c.type == "MESH"):
        to_part = inv @ lm.C_INV @ sub_inv @ m.matrix_world
        radius = max(radius, max((to_part @ v.co).xy.length for v in m.data.vertices))
    return radius


def ensure_prop(obj, name, value, description, subtype="NONE", **limits):
    if name not in obj:
        obj[name] = value
    obj.id_properties_ui(name).update(subtype=subtype, description=description, **limits)


def build():
    """(Re)build the rig in the open scene; returns the context the other steps need."""
    sub = bpy.data.objects[SUBMODEL]
    lm.remove_rig(sub, RIG_PREFIXES)
    parts = lm.parse_mpd(MPD, SUBMODEL)
    mapping, missing = lm.match_parts(sub, parts)
    if missing:
        raise RuntimeError(f"{len(missing)} MPD parts not found in the scene, e.g. {missing[:3]}")
    steering, drive = Steering(parts), Drive(parts)

    bodies = {name: [mapping[lm.find_part(parts, f, p).idx] for f, p in keys] for name, keys in BODIES.items()}
    for i, cyl in enumerate(drive.cylinders):
        bodies[f"conrod{i}"] = [mapping[cyl["rod"].idx]]
        bodies[f"piston{i}"] = [mapping[cyl["piston"].idx]]
    root_node = bpy.data.objects[GLTF_ROOT]
    lm.save_rest(sub, [o for objs in bodies.values() for o in objs],
                 {"roots": {GLTF_ROOT: [list(r) for r in root_node.matrix_world]}})

    coll = bpy.data.collections.get(RIG_COLLECTION)
    if coll is None:
        coll = bpy.data.collections.new(RIG_COLLECTION)
        bpy.context.scene.collection.children.link(coll)

    # Car root on the ground under the rear axle centre; the glTF root hangs below it.
    radius = tyre_radius(sub, bodies["wheel_rl"][-1])
    car = bpy.data.objects.new("CAR_root", None)
    car.empty_display_type = "ARROWS"
    car.empty_display_size = 0.1
    coll.objects.link(car)
    car.matrix_world = Matrix.Translation(sub.matrix_world @ lm.vec_b((0, -60 + radius, REAR_AXLE_Z)))
    lm.reparent_keep_world([root_node], car)

    ctrl = bpy.data.objects.get(CTRL)
    if ctrl is None:
        ctrl = bpy.data.objects.new(CTRL, None)
        ctrl.empty_display_type = "SPHERE"
        ctrl.empty_display_size = 0.02
        coll.objects.link(ctrl)
    ctrl.parent = car
    ctrl.matrix_world = Matrix.Translation(sub.matrix_world @ lm.vec_b((0, -320, 100)))
    ensure_prop(ctrl, "steering", 0.0, "Driver's steering wheel angle; + is counter-clockwise from the seat",
                subtype="ANGLE")
    ensure_prop(ctrl, "steering_min", -math.pi, "Steering lock (physical stop)", subtype="ANGLE")
    ensure_prop(ctrl, "steering_max", math.pi, "Steering lock (physical stop)", subtype="ANGLE")
    ensure_prop(ctrl, "speed", 0.0, "Forward speed in m/s (used by the path integrator)", min=-2.0, max=2.0)
    for w in ("fl", "fr", "rl", "rr"):
        ensure_prop(ctrl, f"spin_{w}", 0.0, f"Rolling angle of wheel {w.upper()}; + rolls forward", subtype="ANGLE")

    # Frames and pivots.
    rest, piv = {}, {}
    for name, (parent, origin, z_axis, x_hint) in FRAMES.items():
        m = lm.frame_matrix(origin, z_axis, x_hint)
        frm = lm.make_empty(f"FRM_{name}", piv[parent] if parent else sub, m, coll, size=8, rest=rest)
        piv[name] = lm.make_empty(f"PIV_{name}", frm, m, coll, display="ARROWS", size=15, rest=rest)
    for side in ("l", "r"):
        s = steering.sides[side]
        toward = (s["b0"] - s["q0"]).cross(UP)
        piv[f"tierod_{side}"] = lm.make_empty(f"PIV_tierod_{side}", piv["rack"], lm.frame_matrix(s["q0"], UP, toward),
                                              coll, display="ARROWS", size=15, rest=rest)
        lm.make_empty(f"BALL_knuckle_{side}", piv[f"knuckle_{side}"], lm.frame_matrix(s["b0"], UP, X), coll,
                      display="SPHERE", size=8, rest=rest)
    for i, cyl in enumerate(drive.cylinders):
        rod_dir = cyl["piston"].pos - cyl["pin"]
        m = lm.frame_matrix(cyl["piston"].pos, cyl["bank"], Z)
        frm = lm.make_empty(f"FRM_piston{i}", sub, m, coll, size=6, rest=rest)
        piv[f"piston{i}"] = lm.make_empty(f"PIV_piston{i}", frm, m, coll, display="ARROWS", size=10, rest=rest)
        lm.make_empty(f"PIN_piston{i}", piv[f"piston{i}"], m, coll, size=5, rest=rest)
        lm.make_empty(f"PIN_crank{i}", piv["crank"], lm.frame_matrix(cyl["pin"], Z, X), coll, size=5, rest=rest)
        piv[f"conrod{i}"] = lm.make_empty(f"PIV_conrod{i}", sub, lm.frame_matrix(cyl["pin"], Z, rod_dir.cross(Z)),
                                          coll, display="ARROWS", size=10, rest=rest)
    for name, objs in bodies.items():
        lm.reparent_keep_world(objs, piv[name])

    # Drivers: steering chain.
    steer_vars = {"y": (ctrl, '["steering"]'), "lo": (ctrl, '["steering_min"]'), "hi": (ctrl, '["steering_max"]')}
    lm.add_driver(piv["yoke"], "rotation_euler", 2, "clamp(y, lo, hi)", steer_vars)
    lm.add_driver(piv["column"], "rotation_euler", 2, f"{fmt(steering.k_column)}*clamp(y, lo, hi)", steer_vars)
    lm.add_driver(piv["steer_shaft"], "rotation_euler", 2, f"{fmt(steering.k_shaft)}*clamp(y, lo, hi)", steer_vars)
    lm.add_driver(piv["rack"], "location", 2, f"{fmt(steering.k_rack)}*clamp(y, lo, hi)", steer_vars)
    for side in ("l", "r"):
        lm.add_driver(piv[f"knuckle_{side}"], "rotation_euler", 2, steering.knuckle_expr(side), steer_vars)
        con = piv[f"tierod_{side}"].constraints.new("DAMPED_TRACK")
        con.target = bpy.data.objects[f"BALL_knuckle_{side}"]
        con.track_axis = "TRACK_Y"

    # Drivers: wheels and drivetrain.
    spin = {w: (ctrl, f'["spin_{w}"]') for w in ("fl", "fr", "rl", "rr")}
    for w in ("fl", "fr", "rl", "rr"):
        lm.add_driver(piv[f"wheel_{w}"], "rotation_euler", 2, "s", {"s": spin[w]})
    rear = {"rl": spin["rl"], "rr": spin["rr"]}
    lm.add_driver(piv["diff"], "rotation_euler", 2, "(rl+rr)*0.5", rear)
    lm.add_driver(piv["planet"], "rotation_euler", 2, f"{fmt(drive.k_planet)}*(rl-rr)*0.5", rear)
    lm.add_driver(piv["propshaft"], "rotation_euler", 2, f"{fmt(drive.k_prop)}*(rl+rr)*0.5", rear)
    lm.add_driver(piv["crank"], "rotation_euler", 2, f"{fmt(drive.k_crank)}*(rl+rr)*0.5", rear)
    for i, cyl in enumerate(drive.cylinders):
        lm.add_driver(piv[f"piston{i}"], "location", 2, drive.piston_expr(cyl), rear)
        rod = piv[f"conrod{i}"]
        con = rod.constraints.new("COPY_LOCATION")
        con.target = bpy.data.objects[f"PIN_crank{i}"]
        con = rod.constraints.new("LOCKED_TRACK")
        con.target = bpy.data.objects[f"PIN_piston{i}"]
        con.track_axis, con.lock_axis = "TRACK_Y", "LOCK_Z"

    slow = [(o.name, fc.data_path, fc.driver.expression) for o in bpy.data.objects if o.name.startswith("PIV_")
            and o.animation_data for fc in o.animation_data.drivers if not fc.driver.is_simple_expression]
    if slow:
        raise RuntimeError(f"drivers outside Blender's simple-expression subset: {slow}")
    bpy.context.view_layer.update()
    return dict(sub=sub, parts=parts, mapping=mapping, bodies=bodies, steering=steering, drive=drive,
                ctrl=ctrl, car=car, radius=radius, piv=piv)


# --- Controls without animation (for sweeps and checks) -----------------------------------

class Unanimated:
    """Temporarily detach CTRL's action so the script can set its properties directly."""

    def __init__(self, ctrl):
        self.ctrl = ctrl

    def __enter__(self):
        ad = self.ctrl.animation_data
        self.saved = (ad.action, ad.action_slot) if ad and ad.action else None
        self.values = {k: self.ctrl[k] for k in ("steering", "spin_fl", "spin_fr", "spin_rl", "spin_rr")}
        if self.saved:
            ad.action = None
        return self

    def set(self, **values):
        for k, v in values.items():
            self.ctrl[k] = v
        self.ctrl.update_tag()
        bpy.context.view_layer.update()

    def __exit__(self, *exc):
        for k, v in self.values.items():
            self.ctrl[k] = v
        if self.saved:
            ad = self.ctrl.animation_data
            ad.action, ad.action_slot = self.saved
        bpy.context.view_layer.update()


# --- Steering lock ----------------------------------------------------------------------

# Bodies that swing or slide when steering. The steering shafts only spin about their own axes,
# so they cannot run into anything: they are left out (their bearing and gear contacts are by design).
SWEPT_BODIES = ("rack", "tierod_l", "tierod_r", "knuckle_l", "knuckle_r", "wheel_fl", "wheel_fr")
SPINNING_BODIES = ("yoke", "column", "steer_shaft")


def find_steering_lock(rig, step_deg=1.0, max_deg=50.0, log=print):
    """Largest yoke angles (each way) before steering parts hit anything they don't touch at rest."""
    ctrl, sub, steering = rig["ctrl"], rig["sub"], rig["steering"]
    moving = [o for b in SWEPT_BODIES for o in rig["bodies"][b]]
    others = [o for o in sub.children if o.get("fileName")]
    for b in rig["bodies"]:
        if b not in SWEPT_BODIES + SPINNING_BODIES:
            others += rig["bodies"][b]
    deps = bpy.context.evaluated_depsgraph_get()
    static = lm.near_parts(moving, others, margin=0.04)
    # Yoke step for ~1 degree of knuckle travel.
    eps = 1e-3
    y_step = math.radians(step_deg) / abs((steering.knuckle("l", eps) - steering.knuckle("l", -eps)) / (2 * eps))
    limits = {}
    with Unanimated(ctrl) as u:
        u.set(steering_min=-1e3, steering_max=1e3, steering=0.0)
        trees = {}
        rest = lm.overlapping_pairs(moving, static, deps, trees)
        for sign in (1, -1):
            limits[sign] = None
            for i in range(1, int(max_deg / step_deg) + 1):
                y = sign * i * y_step
                if not all(abs(steering.knuckle(s, y)) < math.radians(max_deg) for s in "lr"):
                    break
                u.set(steering=y)
                hits = lm.overlapping_pairs(moving, static, deps, trees) - rest
                if hits:
                    limits[sign] = (i - 1) * y_step
                    names = sorted({f"{n} ({o.get('description', '')})" for pair in hits for n in pair
                                    for o in [bpy.data.objects[n]]})
                    log(f"steering {'+' if sign > 0 else '-'}: first contact at yoke {math.degrees(y):.1f} deg "
                        f"(knuckle {math.degrees(steering.knuckle('l', y)):.1f}/"
                        f"{math.degrees(steering.knuckle('r', y)):.1f} deg): {sorted(hits)[:4]} {names[:6]}")
                    break
            if limits[sign] is None:
                limits[sign] = (i - 1) * y_step
                log(f"steering {'+' if sign > 0 else '-'}: no contact up to yoke {math.degrees(limits[sign]):.1f} deg")
    return limits[-1] * -1, limits[1]


def set_lock(ctrl, lo, hi):
    ctrl["steering_min"], ctrl["steering_max"] = lo, hi
    ctrl.id_properties_ui("steering").update(min=lo, max=hi, soft_min=lo, soft_max=hi)


# --- Path integrator ----------------------------------------------------------------------

def default_inputs(ctrl, steering, cruise=0.12):
    """Straight, left, straight, right, straight while speeding up and coming to a stop."""
    lo, hi = ctrl["steering_min"], ctrl["steering_max"]
    left = hi if steering.knuckle("l", hi) > 0 else lo  # yoke direction that turns the car left
    right = lo if left == hi else hi
    a, b = 0.9 * left, 0.9 * right
    fc = lm.fcurve(ctrl, '["steering"]')
    lm.set_keys(fc, (1, 30, 70, 100, 135, 175, 205, 235, 250), (0, 0, a, a, 0, b, b, 0, 0), "BEZIER")
    fc = lm.fcurve(ctrl, '["speed"]')
    lm.set_keys(fc, (1, 36, 215, 250), (0, cruise, cruise, 0), "BEZIER")
    for fc in (lm.find_fcurve(ctrl, '["steering"]'), lm.find_fcurve(ctrl, '["speed"]')):
        for kp in fc.keyframe_points:
            kp.handle_left_type = kp.handle_right_type = "AUTO_CLAMPED"
        fc.update()


def integrate(rig, substeps=8, log=print):
    """Drive the car along the path set by the steering and speed curves; key CAR_root and spins.

    Kinematic bicycle model about the rear-axle centre (no slip at the rear wheels). Each
    wheel's rolling angle comes from its own contact-point velocity along its rolling
    direction, so inner and outer wheels turn at different rates and the differential and
    engine follow. The front wheel centres move with steering (50 LDU kingpin offset).
    """
    scene, ctrl, car, steering = bpy.context.scene, rig["ctrl"], rig["car"], rig["steering"]
    sub = rig["sub"]
    if lm.find_fcurve(ctrl, '["steering"]') is None or lm.find_fcurve(ctrl, '["speed"]') is None:
        default_inputs(ctrl, steering)
    f_steer, f_speed = lm.find_fcurve(ctrl, '["steering"]'), lm.find_fcurve(ctrl, '["speed"]')
    lo, hi = ctrl["steering_min"], ctrl["steering_max"]
    ldu = sub.matrix_world.to_scale()[0]  # metres per LDU
    radius = rig["radius"] * ldu
    wheelbase = (REAR_AXLE_Z - FRAMES["knuckle_l"][1][2]) * ldu
    # Car-local ground coordinates (metres): x = LDraw x, y = LDraw z - rear axle z; forward is -y.
    rear = {"rl": Vector((FRAMES["wheel_rl"][1][0] * ldu, 0)), "rr": Vector((FRAMES["wheel_rr"][1][0] * ldu, 0))}
    front = {}
    for w, side in (("fl", "l"), ("fr", "r")):
        k = Vector(FRAMES[f"knuckle_{side}"][1])
        c = Vector(FRAMES[f"wheel_{w}"][1])
        front[w] = (side, Vector((k.x, k.z - REAR_AXLE_Z)) * ldu, Vector((c.x - k.x, c.z - k.z)) * ldu)

    def steer(frame):
        y = max(lo, min(hi, f_steer.evaluate(frame)))
        return {side: steering.knuckle(side, y) for side in "lr"}

    def rot(v, a):
        return Vector((v.x * math.cos(a) - v.y * math.sin(a), v.x * math.sin(a) + v.y * math.cos(a)))

    start, end, fps = scene.frame_start, scene.frame_end, scene.render.fps / scene.render.fps_base
    base = car.matrix_world.translation.copy()
    pos, yaw = Vector((0.0, 0.0)), 0.0
    spins = {w: 0.0 for w in ("fl", "fr", "rl", "rr")}
    rec = {k: [] for k in ("x", "y", "yaw", "fl", "fr", "rl", "rr")}
    frames = list(range(start, end + 1))
    for f in frames:
        for k, v in (("x", base.x + pos.x), ("y", base.y + pos.y), ("yaw", yaw), *spins.items()):
            rec[k].append(v)
        if f == end:
            break
        dt = 1.0 / (fps * substeps)
        for i in range(substeps):
            t0, t1, tm = f + i / substeps, f + (i + 1) / substeps, f + (i + 0.5) / substeps
            v = f_speed.evaluate(tm)
            d0, d1, dm = steer(t0), steer(t1), steer(tm)
            yaw_rate = v * (math.tan(dm["l"]) + math.tan(dm["r"])) / (2 * wheelbase)
            heading = yaw + 0.5 * yaw_rate * dt
            pos += Vector((math.sin(heading), -math.cos(heading))) * v * dt
            yaw += yaw_rate * dt
            for w, r in rear.items():
                vel = Vector((0, -v)) + Vector((-r.y, r.x)) * yaw_rate
                spins[w] += vel.dot(Vector((0, -1))) * dt / radius
            for w, (side, kingpin, offset) in front.items():
                centre_off = rot(offset, dm[side])
                r = kingpin + centre_off
                steer_rate = (d1[side] - d0[side]) / dt
                vel = Vector((0, -v)) + Vector((-r.y, r.x)) * yaw_rate + Vector((-centre_off.y, centre_off.x)) * steer_rate
                spins[w] += vel.dot(rot(Vector((0, -1)), dm[side])) * dt / radius
    lm.set_keys(lm.fcurve(car, "location", 0), frames, rec["x"])
    lm.set_keys(lm.fcurve(car, "location", 1), frames, rec["y"])
    lm.set_keys(lm.fcurve(car, "location", 2), frames, [base.z] * len(frames))
    lm.set_keys(lm.fcurve(car, "rotation_euler", 2), frames, rec["yaw"])
    for w in ("fl", "fr", "rl", "rr"):
        lm.set_keys(lm.fcurve(ctrl, f'["spin_{w}"]'), frames, rec[w])
    log(f"path: {len(frames)} frames, end offset ({rec['x'][-1] - base.x:.3f}, {rec['y'][-1] - base.y:.3f}) m, "
        f"yaw {math.degrees(rec['yaw'][-1]):.1f} deg; wheel turns "
        + ", ".join(f"{w} {rec[w][-1] / (2 * math.pi):.2f}" for w in ("fl", "fr", "rl", "rr")))


# --- Checks -----------------------------------------------------------------------------

def _world(obj):
    return obj.evaluated_get(bpy.context.evaluated_depsgraph_get()).matrix_world


def _ld(sub, obj, local=Vector((0, 0, 0))):
    """LDraw-space position of a point given in an object's local space."""
    return lm.vec_l(sub.matrix_world.inverted() @ _world(obj) @ local)


def _part_ld(sub, obj):
    return lm.to_ldraw(sub.matrix_world.inverted() @ _world(obj))


def check(rig, log=print):
    """Numerical checks of the live rig; returns the worst errors."""
    sub, ctrl, steering, drive, b = rig["sub"], rig["ctrl"], rig["steering"], rig["drive"], rig["bodies"]
    o = bpy.data.objects
    worst = {}

    def note(key, value):
        worst[key] = max(worst.get(key, 0.0), value)

    def sub_m(name):
        return sub.matrix_world.inverted() @ _world(o[f"PIV_{name}"])

    with Unanimated(ctrl) as u:
        lo, hi = ctrl["steering_min"], ctrl["steering_max"]
        for i in range(21):
            y = lo + (hi - lo) * i / 20
            u.set(steering=y)
            for side in "lr":
                s = steering.sides[side]
                q, ball = _ld(sub, o[f"PIV_tierod_{side}"]), _ld(sub, o[f"BALL_knuckle_{side}"])
                note("tie rod length (LDU)", abs((ball - q).length - s["link"]))
                rod = _part_ld(sub, b[f"tierod_{side}"][0])
                ends = (rod.translation, rod @ Vector((0, 0, TIEROD_LENGTH)))
                note("tie rod ends on balls (LDU)",
                     max(min((ball - e).length for e in ends), min((q - e).length for e in ends)))
                knuckle = o[f"PIV_knuckle_{side}"].evaluated_get(bpy.context.evaluated_depsgraph_get())
                note("knuckle angle vs model (deg)", abs(math.degrees(knuckle.rotation_euler.z - steering.knuckle(side, y))))
        centre = Vector(FRAMES["crank"][1])
        for i in range(24):
            th = 2 * math.pi * i / 24 / drive.k_crank
            u.set(steering=0.0, spin_rl=th, spin_rr=th)
            for k, cyl in enumerate(drive.cylinders):
                pin, pp = _ld(sub, o[f"PIN_crank{k}"]), _ld(sub, o[f"PIN_piston{k}"])
                note("conrod length (LDU)", abs((pp - pin).length - cyl["length"]))
                rod_ball = _part_ld(sub, b[f"conrod{k}"][0]) @ CONROD_BALL
                note("conrod ball on piston (LDU)", (rod_ball - _part_ld(sub, b[f"piston{k}"][0]).translation).length)
                off = (pp - centre).xy
                note("piston off bank axis (LDU)", (off - cyl["bank"].xy * off.dot(cyl["bank"].xy)).length)
        # Every mesh: teeth must move the same way at the contact, at the tooth-count ratio.
        drive_both, drive_split = {"spin_rl": 0.2, "spin_rr": 0.2}, {"spin_rl": 0.2, "spin_rr": -0.2}
        turn = {"steering": 0.5 * hi}
        cases = [(MESHES[0], turn), (MESHES[1], turn), (MESHES[2], drive_both), (MESHES[3], drive_both),
                 (MESHES[4], drive_split), ((*PINION, "rack", RACK_POINT, None), turn)]
        for (a, ca, na, bb, cb, nb), move in cases:
            ca, cb = Vector(ca), Vector(cb)
            towards = ((cb - ca) - axis(a) * (cb - ca).dot(axis(a))).normalized()
            p, tangent = lm.vec_b(ca + towards * lm.pitch_radius(na)), axis(a).cross(towards)
            u.set(steering=0.0, spin_rl=0.0, spin_rr=0.0)
            m0 = {n: sub_m(n) for n in (a, bb)}
            u.set(**move)
            step = {n: sub_m(n) @ m0[n].inverted() for n in (a, bb)}
            va = (lm.vec_l(step[a] @ p) - lm.vec_l(p)).dot(tangent)
            vb = (lm.vec_l(step[bb] @ p) - lm.vec_l(p)).dot(tangent)
            wa = step[a].to_quaternion().angle
            if nb is None:  # rack: travel per pinion radian
                measured, expected = step[bb].translation.length / wa, lm.pitch_radius(na)
            else:
                measured, expected = step[bb].to_quaternion().angle / wa, na / nb
            log(f"mesh {a} -> {bb}: same direction at contact {va * vb > 0}, ratio {measured:.4f} (teeth {expected:.4f})")
            note("mesh direction mismatch", 0.0 if va * vb > 0 else 1.0)
            note("mesh ratio error", abs(measured / expected - 1))
        u.set(spin_rl=0.3, spin_rr=0.1)
        diff = o["PIV_diff"].evaluated_get(bpy.context.evaluated_depsgraph_get()).rotation_euler.z
        note("carrier - mean of rear wheels (rad)", abs(diff - 0.2))
    for k, v in worst.items():
        log(f"check {k}: {v:.4g}")
    return worst


def check_rolling(rig, every=10, log=print):
    """Contact patches must not slide along each wheel's rolling direction between frames."""
    scene, ldu = bpy.context.scene, rig["sub"].matrix_world.to_scale()[0]
    radius, worst = rig["radius"] * ldu, 0.0
    current = scene.frame_current
    for f in range(scene.frame_start, scene.frame_end, every):
        for w in ("fl", "fr", "rl", "rr"):
            piv = bpy.data.objects[f"PIV_wheel_{w}"]
            scene.frame_set(f)
            m0 = _world(piv).copy()
            centre = m0.translation.copy()
            spin_axis = (m0.to_3x3() @ Vector((0, 0, 1))).normalized()
            roll_dir = spin_axis.cross(Vector((0, 0, 1))).normalized()
            contact = centre - Vector((0, 0, radius))
            local = m0.inverted() @ contact
            scene.frame_set(f + 1)
            m1 = _world(piv)
            moved = (m1.translation - centre).length
            slip = (m1 @ local - contact).dot(roll_dir)
            if moved > 1e-5:
                worst = max(worst, abs(slip) / moved)
    scene.frame_set(current)
    log(f"check rolling slip / travel (worst): {worst:.4g}")
    return worst


# --- Export bake ----------------------------------------------------------------------------

def bake_export(path):
    """Replace drivers and constraints with plain keys on every rig object, then save `path`.

    Destroys the live rig in the open session; meant for headless runs on a saved file.
    """
    scene = bpy.context.scene
    objs = [o for o in bpy.data.objects if o.name.startswith(("PIV_",))]
    frames = range(scene.frame_start, scene.frame_end + 1)
    poses = {o.name: [] for o in objs}
    for f in frames:
        scene.frame_set(f)
        for o in objs:
            parent = o.parent.matrix_world @ o.matrix_parent_inverse
            poses[o.name].append(parent.inverted() @ o.matrix_world)
    for o in objs:
        if o.animation_data:
            for fc in list(o.animation_data.drivers):
                o.animation_data.drivers.remove(fc)
        o.constraints.clear()
        o.rotation_mode = "QUATERNION"
        prev = None
        loc = [[], [], []]
        quat = [[], [], [], []]
        for m in poses[o.name]:
            t, q, _ = m.decompose()
            if prev is not None:
                q.make_compatible(prev)
            prev = q
            for i in range(3):
                loc[i].append(t[i])
            for i in range(4):
                quat[i].append(q[i])
        for i in range(3):
            lm.set_keys(lm.fcurve(o, "location", i), list(frames), loc[i])
        for i in range(4):
            lm.set_keys(lm.fcurve(o, "rotation_quaternion", i), list(frames), quat[i])
    bpy.ops.wm.save_as_mainfile(filepath=path, copy=True)


# --- Entry points ----------------------------------------------------------------------------

def main(save=None, find_lock=True, reset_inputs=False, log=print):
    rig = build()
    ctrl = rig["ctrl"]
    if find_lock or ctrl["steering_max"] >= math.pi:
        lo, hi = find_steering_lock(rig, log=log)
        step = math.radians(2.0)  # keep a little clearance from first contact
        set_lock(ctrl, min(0.0, lo + step), max(0.0, hi - step))
    log(f"steering lock: yoke {math.degrees(ctrl['steering_min']):.1f} .. {math.degrees(ctrl['steering_max']):.1f} deg; "
        f"knuckles at max: {math.degrees(rig['steering'].knuckle('l', ctrl['steering_max'])):.1f} / "
        f"{math.degrees(rig['steering'].knuckle('r', ctrl['steering_max'])):.1f} deg")
    if reset_inputs:
        for path in ('["steering"]', '["speed"]'):
            lm.remove_fcurve(ctrl, path)
    integrate(rig, log=log)
    check(rig, log=log)
    check_rolling(rig, log=log)
    bpy.context.scene.frame_set(bpy.context.scene.frame_start)
    if save:
        bpy.ops.wm.save_as_mainfile(filepath=save)
        log(f"saved {save}")
    return rig


def _cli():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser(prog="rig_42000")
    ap.add_argument("--glb", help="import this .glb first if the scene does not have the model")
    ap.add_argument("--save", help="save the rigged scene to this .blend")
    ap.add_argument("--bake-export", help="bake the rig in the opened .blend to plain keys and save here")
    ap.add_argument("--reset-inputs", action="store_true", help="rewrite the default steering and speed curves")
    args = ap.parse_args(argv)
    if args.bake_export:
        bake_export(os.path.abspath(args.bake_export))
        return
    if SUBMODEL not in bpy.data.objects:
        if not args.glb:
            raise SystemExit(f"{SUBMODEL!r} is not in the scene; pass --glb")
        bpy.ops.wm.read_factory_settings(use_empty=True)
        bpy.ops.import_scene.gltf(filepath=os.path.abspath(args.glb))
    main(save=os.path.abspath(args.save) if args.save else None, reset_inputs=args.reset_inputs)


if __name__ == "__main__":
    _cli()
