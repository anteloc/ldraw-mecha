"""Build twenty plant cases moved by wind, author their plans and export the wind-clip catalog.

    .venv/bin/python scripts/build_plants.py mpd               # output/plants/Pxx_*/source/scenario.mpd
    ./ldraw-mecha prepare output/plants/Pxx_*/source/scenario.mpd --output output/plants/Pxx_*/study
    .venv/bin/python scripts/build_plants.py plan [--ready]    # output/plants/Pxx_*/plan.json, kinematics.json
    .venv/bin/python scripts/build_plants.py catalog           # clips/*.json, catalog.json, CATALOG.md

Every case is a small mock: the plant, the mount it moves on (clip, socket, bar, stud, hole) and a base. Parts are
picked by constant name from the vendored category tables (data/categories/parts/*.py, parsed as text); a few parts
missing from the tables (the vine segment subfiles) are named by their LDraw reference and flagged. Moving parts are
placed by mating LDCad shadow connector frames read through pyldraw3 (data/offLibShadow), or copied from an official
construction (the 2518c01 palm shortcut, the 10315 bamboo stalks, the 10297 vase) where one exists; placements that
an official model also holds are compared with it (`source/parts.json` -> `reference_checks`).

Joints are of two kinds (recorded per joint): `real` - the LEGO connection allows that rotation (ball in socket,
clip on bar, bar or pin in a hole, part on a stud); `flex_approx` - a small tilt of a rigid part at its attachment
standing in for bending plastic (a stem, a grass blade, a flexible vine), limited to wind_clips.FLEX_LIMIT.
"""

from __future__ import annotations

import argparse
import copy
import json
import math
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
from ldraw_mechanisms import analysis, plan as contract  # noqa: E402
from ldraw_mechanisms.source import library_path  # noqa: E402
import build_movables as bm  # noqa: E402
from build_movables import (Build, find_connector, part_ref, ry, rx, unit, r6, author_plan,  # noqa: E402
                            asymmetric, model_sections, TABLE)
from build_minifigs import library_title, number, pose, rotation, world_dir, world_point  # noqa: E402
import wind_clips as wc  # noqa: E402

OUT = wc.OUT
MODELS = ROOT / "data/models-annotated"
I3 = np.eye(3)

# Vine segment subfiles: official LDraw part files (parts/16981k0x.dat, parts/73828k0x.dat) whose titles start with
# "~" because they are normally only used inside 16981 / 73828. P09 rebuilds the flexible vine from them.
SEGMENTS = {
    "16981k01": "Vine 16981 leaf (right)", "16981k02": "Vine 16981 leaf (left)",
    "16981k03": "Vine 16981 liana end segment (bar with stop)", "16981k04": "Vine 16981 liana segment (unit "
                                                                           "cylinder, scaled along x)",
}
bm.LIBRARY_ONLY.update({k: v + " (subfile of the table part, used to rebuild the flexible vine)"
                        for k, v in SEGMENTS.items()})

# Colours (LDraw codes)
BLACK, GREEN, BROWN, LGREY, YELLOW, RED, WHITE, TAN, DTAN = 0, 2, 6, 7, 14, 4, 15, 19, 28
LIME, BGREEN, DGREEN, OLIVE, SGREEN, RBROWN, DBROWN = 27, 10, 288, 330, 378, 70, 308
BPINK, DPINK, MLAV, ORANGE, MAGENTA, LBG, DBG, PGOLD, CORAL = 29, 5, 30, 25, 26, 71, 72, 297, 353


# --------------------------------------------------------------------------- helpers
def orient(a_loc, a_w, b_loc, b_w):
    """Rotation taking local direction a onto world a, and b (made perpendicular) onto world b."""
    al, aw = unit(a_loc), unit(a_w)
    bl = unit(np.asarray(b_loc, float) - np.dot(b_loc, al) * al)
    bw = unit(np.asarray(b_w, float) - np.dot(b_w, aw) * aw)
    loc = np.column_stack([al, bl, np.cross(al, bl)])
    wor = np.column_stack([aw, bw, np.cross(aw, bw)])
    return np.round(wor @ loc.T, 12)


def conn(ref, kind, near=None, feature=None, axis=None):
    return find_connector(ref, kind, near, axis, feature)


def const(ref, prefer=("plants.", "plates.", "bricks.", "bars.", "cylinders.", "cones.", "tiles.", "spheres.",
                       "hinges.")):
    """Table constant for a reference (used when copying an official construction)."""
    names = sorted((k for k, v in TABLE.items() if v == ref and not k.split(".")[1].startswith("_")),
                   key=lambda k: (next((i for i, p in enumerate(prefer) if k.startswith(p)), 99), k))
    if names:
        return names[0]
    if ref in bm.LIBRARY_ONLY:
        return f"ref:{ref}"
    raise ValueError(f"{ref} is not in the tables")


def section_parts(model, section):
    """[(colour, ref, 4x4)] of one FILE section of an official model, in file order (colours kept)."""
    out, cur = [], None
    for line in (MODELS / model).read_text(encoding="utf-8", errors="replace").splitlines():
        t = line.split()
        if len(t) >= 3 and t[0] == "0" and t[1].upper() == "FILE":
            cur = " ".join(t[2:]).lower()
        elif cur == section.lower() and len(t) >= 15 and t[0] == "1":
            v = [float(x) for x in t[2:14]]
            m = np.eye(4)
            m[:3, 3] = v[:3]
            m[:3, :3] = np.array(v[3:]).reshape(3, 3)
            out.append((int(t[1]), " ".join(t[14:]).lower().removesuffix(".dat"), m))
    return out


def part_file(ref):
    """[(colour, ref, 4x4)] of the type-1 lines of a library part file (a shortcut or a flexible part)."""
    out = []
    for line in (library_path() / "parts" / f"{ref}.dat").read_text(encoding="utf-8-sig").splitlines():
        t = line.split()
        if len(t) >= 15 and t[0] == "1":
            v = [float(x) for x in t[2:14]]
            m = np.eye(4)
            m[:3, 3] = v[:3]
            m[:3, :3] = np.array(v[3:]).reshape(3, 3)
            out.append((int(t[1]), " ".join(t[14:]).lower().removesuffix(".dat"), m))
    return out


class PlantBuild(Build):
    """Build with flex_approx joints, wind tips and placements copied from official constructions."""

    def __init__(self, sc):
        super().__init__(sc)
        self.flex = {}
        self.tips = {}
        self.checks = []

    def add(self, role, name, colour, t=(0, 0, 0), r=I3):
        if name.startswith("ref:") and name[4:] in SEGMENTS:
            if any(p["role"] == role for p in self.parts):
                raise ValueError(f"{self.sc['key']}: duplicate role {role}")
            ref = name[4:]
            if not (library_path() / "parts" / f"{ref}.dat").exists():
                raise ValueError(f"{ref}.dat is not in the LDraw library")
            m = pose(np.asarray(r, float), np.asarray(t, float))
            self.parts.append(dict(role=role, table=None, ref=ref, colour=colour, matrix=m))
            return m
        return super().add(role, name, colour, t, r)

    def add_m(self, role, name, colour, m):
        return self.add(role, name, colour, m[:3, 3], m[:3, :3])

    def put(self, role, name, colour, r, local, world):
        """Place a part so that its local point lands on a world point."""
        r = np.asarray(r, float)
        return self.add(role, name, colour, np.asarray(world, float) - r @ np.asarray(local, float), r)

    def wp(self, role, p):
        return world_point(self.m(role), p)

    def wd(self, role, d):
        return unit(world_dir(self.m(role), d))

    def hinge(self, name, parent_role, child_role, origin, axis, how, flex=None):
        """Declare a revolute joint; `flex` (a reason) marks it flex_approx."""
        self.joint(name, parent_role, child_role, origin, axis, "revolute",
                   ("flex_approx: " + flex + ". " if flex else "real: ") + how)
        if flex:
            self.flex[name] = flex

    def moving(self, name, roles, joint, control, parent=None, test=None, tip=None):
        """A body driven by its own control; `tip` (role, local point) defines its wind swing."""
        self.body(name, roles, joint, control=control, parent=parent, test=test)
        if tip or test:
            self.tips[name] = tip or test[:2]

    def check(self, name, value, limit, note):
        self.checks.append(dict(name=name, value=round(float(value), 4), limit=limit, passed=bool(value <= limit),
                                note=note))
        if value > limit:
            raise ValueError(f"{self.sc['key']}: {name} = {value} > {limit} ({note})")


def tip_up(role, p):
    return (role, p, 1, -1)


def downwind(role, p):
    return (role, p, 0, 1)


def stack(b, prefix, name, colour, x, z, n, y0=0.0, h=24.0, start=0):
    for k in range(n):
        b.add(f"{prefix}{k + start}", name, colour, (x, y0 - h * (k + 1), z))
    return y0 - h * n


def handle_hub(b, colour, y1, filler="plates.Plate1X1"):
    """Two layers of 1x2 plates with a handle on the end on a 2x2 round top: four horizontal handle bars, radial
    plates pointing +X / -X (lower layer, bars along Z) and +Z / -Z (upper layer, bars along X)."""
    b.add("hub_x_pos", "plates.Plate1X2WithHandleOnEnd", colour, (20, y1, -10))
    b.add("hub_x_neg", "plates.Plate1X2WithHandleOnEnd", colour, (-20, y1, -10), ry(180))
    b.add("hub_fill_a", filler, colour, (10, y1, 10))
    b.add("hub_fill_b", filler, colour, (-10, y1, 10))
    b.add("hub_z_pos", "plates.Plate1X2WithHandleOnEnd", colour, (10, y1 - 8, 20), ry(-90))
    b.add("hub_z_neg", "plates.Plate1X2WithHandleOnEnd", colour, (10, y1 - 8, -20), ry(90))
    bar = conn("60478", "bar")
    return {k: (b.wp(f"hub_{k}", bar["position"]), b.wd(f"hub_{k}", bar["axis"]))
            for k in ("x_pos", "x_neg", "z_pos", "z_neg")}


def outward(point, axis, centre=(0, 0, 0)):
    """Horizontal direction perpendicular to a bar axis, pointing away from a centre."""
    o = unit(np.cross(axis, (0, 1, 0)))
    d = np.asarray(point, float) - np.asarray(centre, float)
    return o if np.dot(o, d) >= 0 else -o


def clip_leaf(b, role, name, colour, grip_local, bar_point, bar_axis, out, droop_deg, centre=None):
    """Swordleaf with its clip on a bar: leaf plane perpendicular to the bar, leaf pointing `out`, drooping."""
    d = math.radians(droop_deg)
    direction = math.cos(d) * np.asarray(out, float) + math.sin(d) * np.array([0, 1.0, 0])
    r = orient((0, 1, 0), bar_axis, (0, 0, -1), direction)
    return b.put(role, name, colour, r, grip_local, bar_point)


# --------------------------------------------------------------------------- cases
def p01_palm_tree(b):
    """2518c01 palm shortcut taken apart: the official sub-part placements (an S-curved trunk of six ball-jointed
    segments, top, four large leaves)."""
    b.add("base", "plates.Plate6X6", DTAN, (10, 0, 10))
    segs, leaves = 0, []
    for colour, ref, m in part_file("2518c01"):
        if ref == "2563a":
            b.add_m("palm_base", const(ref), RBROWN, m)
        elif ref == "2536a":
            segs += 1
            b.add_m(f"seg{segs}", const(ref), RBROWN, m)
        elif ref == "2566b":
            b.add_m("crown", const(ref), RBROWN, m)
        elif ref == "2518":
            d = m[:3, 0]
            name = ("downwind" if d[0] > 0.7 else "upwind" if d[0] < -0.7 else "back" if d[2] > 0 else "front")
            leaves.append(name)
            b.add_m(f"leaf_{name}", const(ref), GREEN, m)
        elif ref == "4032a":
            b.add_m("crown_plate", const(ref), GREEN, m)
        elif ref == "3062b":
            b.add_m("crown_cap", const(ref), GREEN, m)
    prev = "palm_base"
    for k in range(1, 7):
        ball = b.wp(f"seg{k}", (0, 3, 0))
        socket = b.wp(prev, (0, -32, 0))
        b.check(f"ball_socket_gap_{k}", np.linalg.norm(ball - socket), 0.5,
                "segment ball (local y=+3) vs the socket below (local y=-32) in the official shortcut")
        b.hinge(f"bend_{k}", prev, f"seg{k}", ball, (0, 0, 1),
                f"2536a ball (y=+3) in the socket (y=-32) of {b.ref(prev)}; one of the ball's two tilt freedoms "
                "used, about Z so that the trunk bends with the wind")
        b.moving(f"seg{k}", [f"seg{k}"], f"bend_{k}", f"bend_{k}", parent=f"seg{k - 1}" if k > 1 else None,
                 test=downwind(f"seg{k}", (0, -32, 0)))
        prev = f"seg{k}"
    spike = b.wp("crown", (0, 20, 0))
    up = b.wd("crown", (0, -1, 0))
    b.check("crown_axis_vs_segment", 1 - abs(np.dot(up, b.wd("seg6", (0, -1, 0)))), 1e-3,
            "2566b spike axis parallel to the top segment axis")
    b.hinge("crown_twist", "seg6", "crown", spike, up, "2566b spike (pin, local y 20..44) turning in the top "
            "2536a; twist about the trunk axis")
    b.moving("crown", ["crown", "crown_plate", "crown_cap"], "crown_twist", "crown_twist", parent="seg6",
             tip=("crown", (60, 0, 0)))
    for name in leaves:
        role = f"leaf_{name}"
        b.hinge(role, "crown", role, b.wp(role, (0, 8, 0)), b.wd(role, (0, 0, 1)),
                "2518 leaf root between its two prong holes; tilt about the leaf's own cross axis", flex=(
                    "the leaf is held rigidly on two 2566b prongs; the tilt stands in for the long leaf bending"))
        b.moving(role, [role], role, role, parent="crown", test=tip_up(role, (150, 24, 0)))
    b.references.append(dict(model="2518c01.dat (LDraw shortcut)", section="(part file)", parent="palm_base",
                             part="all", official_refs=["2563a", "2536a", "2566b", "2518", "4032a", "3062b"],
                             position_offset_ldu=0.0, rotation_offset=0.0,
                             note="Placements copied from the official shortcut (identity transform)."))


def p02_swordleaf_palm(b):
    b.add("base", "plates.Plate6X6", GREEN, (0, 0, 0))
    top = stack(b, "trunk", "bricks.Brick2X2RoundWithoutReinforcement", RBROWN, 0, 0, 6)
    bars = handle_hub(b, RBROWN, top - 8)
    grip = (0.0, 4.0, 30.0)  # clip5 primitive origin in 10884 (connector frame reports y=4, z=27.01; see notes)
    for k, (hub, droop) in enumerate((("x_pos", 32), ("x_neg", 32), ("z_pos", 18), ("z_neg", 18))):
        p, a = bars[hub]
        o = outward(p, a)
        name = {"x_pos": "downwind", "x_neg": "upwind", "z_pos": "back", "z_neg": "front"}[hub]
        role = f"frond_{name}"
        clip_leaf(b, role, "plants.PlantLeaves6X5SwordleafWithC_Clip", LIME, grip, p, a, o, droop)
        b.hinge(role, f"hub_{hub}", role, p, a, "10884 C-clip (clip5 primitive at local (0,4,30), grip axis "
                "local Y) on the 60478 handle bar; turns about the bar")
        b.moving(role, [role], role, role, test=tip_up(role, (0, 4, -80)))
    # Official check: in 10297's palm tree the 10884 clips hold 23443 handle bars; with the clip5 origin the grip
    # centre lies on the bar line (the shadow-derived connector point is 3 LDU off it).
    clip = np.array(grip)
    items = model_sections("10297-1.mpd")["10297 - palmtree.ldr"]
    handle = conn("23443", "bar", (0, 0, 0))
    worst = 0.0
    for ref, m in items:
        if ref != "10884.dat":
            continue
        p = m[:3, :3] @ clip + m[:3, 3]
        a = m[:3, :3] @ np.array([0, 1.0, 0])
        best = min((np.linalg.norm((p - bp) - np.dot(p - bp, ba) * ba), abs(abs(np.dot(a, ba)) - 1))
                   for r2, tm in items if r2 == "23443.dat"
                   for bp, ba in [(tm[:3, :3] @ handle["position"] + tm[:3, 3], tm[:3, :3] @ handle["axis"])])
        worst = max(worst, best[0])
    b.check("clip5_grip_vs_10297_handles", worst, 0.6, "10884 grip centre to the 23443 handle bar line in 10297")
    b.references.append(dict(model="10297-1.mpd", section="10297 - palmtree.ldr", parent="23443 handle",
                             part="10884 clip", official_refs=["23443", "10884"],
                             position_offset_ldu=round(worst, 3), rotation_offset=0.0,
                             note="Worst distance of the 10884 grip centre (clip5 origin) from the handle bar line "
                                  "over the five fronds of the official palm; grip axis parallel to the bar."))


def p03_bamboo(b):
    """Four canes copied from the 10315 bamboo stalks, each on a ball joint in a friction socket, splayed."""
    b.add("base", "plates.Plate6X6", GREEN, (0, 0, 0))
    sockets = []
    socket_c = conn("14418", "generic", (30, 4, 0))
    for k, (t, r) in enumerate((((-40, -16, -10), I3), ((40, -16, 10), ry(180)), ((10, -16, -40), ry(-90)),
                                ((-10, -16, 40), ry(90)))):
        b.add(f"riser{k + 1}", "plates.Plate1X2", DGREEN, (t[0], -8, t[2]), r)
        b.add(f"socket{k + 1}", "hinges.Plate1X2WithSocketJoint_8WithFriction", DBG, t, r)
        sockets.append(b.wp(f"socket{k + 1}", socket_c["position"]))
    stalks = ["10315 - bamboo-stalk-2.ldr", "10315 - bamboo-stalk-1.ldr", "10315 - bamboo-stalk-4.ldr",
              "10315 - bamboo-stalk-3.ldr"]
    splay, yaw = (24, 20, 28, 30), (0, 70, 140, 210)
    colours = {"85861": LIME, "59900": BGREEN, "37762": BGREEN, "22484": DBG, "63965a": RBROWN, "30374": RBROWN,
               "30176": GREEN, "32607": LIME}
    for k, (sock, section) in enumerate(zip(sockets, stalks), start=1):
        radial = unit([sock[0], 0, sock[2]])
        tilt = rotation(np.cross((0, -1, 0), radial), math.radians(splay[k - 1]))
        m_cane = pose(tilt @ ry(yaw[k - 1]), sock)
        parts = section_parts("10315-1.mpd", section)
        leaf_ids = [i for i, (_, ref, m) in enumerate(parts) if ref == "30176"]
        leaf_ids = sorted(leaf_ids, key=lambda i: parts[i][2][1, 3])[:2]  # the two highest leaf bricks
        roles, spinners = [], []
        for i, (_, ref, m) in enumerate(parts):
            role = f"cane{k}_leaf{len(spinners) + 1}" if i in leaf_ids else f"cane{k}_{ref}_{i}"
            b.add_m(role, const(ref), colours[ref], m_cane @ m)
            (spinners if i in leaf_ids else roles).append(role)
        ball = next(r for r in roles if "_22484_" in r)
        bar = next(r for r in roles if "_63965a_" in r or "_30374_" in r)
        b.hinge(f"cane_{k}", f"socket{k}", ball, sock, (0, 0, 1),
                "22484 ball (centre at the stalk origin, as in 10315) in the 14418 friction socket; one of the "
                "ball's two tilt freedoms used, about Z")
        top = max(roles, key=lambda r: -b.wp(r, (0, 0, 0))[1])
        b.moving(f"cane_{k}", roles, f"cane_{k}", f"cane_{k}", test=downwind(top, (0, 0, 0)))
        for j, role in enumerate(spinners, start=1):
            b.hinge(f"rustle_{k}{'ab'[j - 1]}", bar, role, b.wp(role, (0, 0, 0)), b.wd(role, (0, -1, 0)),
                    "30176 threaded on the cane's bar (bar hole and hollow stud); turns about the bar")
            b.moving(f"rustle_{k}{'ab'[j - 1]}", [role], f"rustle_{k}{'ab'[j - 1]}", f"rustle_{k}{'ab'[j - 1]}",
                     parent=f"cane_{k}", tip=(role, (40, 0, 0)))
    b.references.append(dict(model="10315-1.mpd", section="10315 - bamboo-stalk-1..4.ldr", parent="22484",
                             part="stalk", official_refs=["22484", "63965a", "30374", "30176", "32607"],
                             position_offset_ldu=0.0, rotation_offset=0.0,
                             note="Stalk contents copied from the official sections (ball centre at the stalk "
                                  "origin); each stalk is placed on its own socket with a catalog splay and yaw."))


def p04_flower_bed(b):
    b.add("base", "plates.Plate6X8", GREEN, (0, 0, 0))
    pins = [c for c in find_all("3741a", "pin") if c["position"][1] < 0]
    hole = conn("3742", "pin_hole")
    colours = ((YELLOW, RED, YELLOW), (WHITE, MAGENTA, WHITE), (RED, YELLOW, BPINK))
    for k, (x, z) in enumerate(((-60, 0), (0, -20), (60, 20)), start=1):
        b.add(f"pot{k}", "bricks.Brick2X2RoundWithoutReinforcement", RBROWN, (x, -24, z))
        b.add(f"stem{k}", "plants.PlantFlowerStem", GREEN, (x, -32, z), ry(40 * k))
        b.hinge(f"stem_{k}", f"pot{k}", f"stem{k}", b.wp(f"stem{k}", (0, 8, 0)), (0, 0, 1),
                "3741a stem on the 2x2 round brick (official 10037 mount)",
                flex="the stem is a single rigid part on its stud; the tilt stands in for its thin stems bending")
        b.moving(f"stem_{k}", [f"stem{k}"], f"stem_{k}", f"stem_{k}", test=downwind(f"stem{k}", (0, -30, 0)))
        for j, pin in enumerate(pins, start=1):
            p = b.wp(f"stem{k}", pin["position"])
            a = b.wd(f"stem{k}", pin["axis"])
            r = orient((0, 1, 0), -a, (1, 0, 0), np.cross(a, (0, 0, 1)) + np.array([1e-3, 0, 0]))
            role = f"head{k}{'abc'[j - 1]}"
            b.put(role, "plants.PlantFlower", colours[k - 1][j - 1], r, hole["position"], p + pin["length"] * a)
            b.hinge(f"head_{k}{'abc'[j - 1]}", f"stem{k}", role, p, a, "3742 on the 3741a flower pin (R2 pin in "
                    "the flower's hole); spins about the pin")
            b.moving(f"head_{k}{'abc'[j - 1]}", [role], f"head_{k}{'abc'[j - 1]}", f"head_{k}{'abc'[j - 1]}",
                     parent=f"stem_{k}", tip=(role, (10, 0, 0)))
    b.reference("3185-1.mpd", "stem1", "head1a", note="3742 on a 3741a pin; official flower beds of 3185")


def find_all(ref, kind):
    from build_minifigs import connectors
    return [c for c in connectors(ref) if c["kind"] == kind]


def p05_sunflower(b):
    b.add("base", "plates.Plate6X6", GREEN, (10, 0, 10))
    top = stack(b, "stem", "bricks.Brick1X1RoundWithHollowStud", GREEN, 0, 0, 5)
    b.add("pivot", "plates.Plate1X1WithClipHorizontal_ThickC_Clip_", GREEN, (0, top - 8, 0), ry(90))
    clip = conn("61252", "clip", (0, 2, -20), feature="snap_clp")
    c = b.wp("pivot", clip["position"])
    a = b.wd("pivot", clip["axis"])
    bar = conn("2540", "bar", (0, 2, -20))
    r = orient((1, 0, 0), (0, 0, -1), (0, 0, 1), (0, -1, 0))  # handle along Z, plate standing up from it
    b.put("head_plate", "plates.Plate1X2WithHandle", GREEN, r, bar["position"], c)
    b.add("head", "plants.PlantFlower4X4With4RoundedPetals", YELLOW, b.wp("head_plate", (-10, -16, 0)), r)
    b.hinge("nod", "pivot", "head_plate", c, a, "2540 handle bar in the 61252 clip (stem top); the head turns "
            "about the bar")
    b.hinge("stem_lean", "base", "stem0", (0, 0, 0), (0, 0, 1), "1x1 round brick stem on the base stud",
            flex="a brick stack cannot tilt; the tilt stands in for a long flower stalk bending")
    b.moving("stem", [f"stem{k}" for k in range(5)] + ["pivot"], "stem_lean", "stem_lean",
             test=downwind("pivot", (0, 0, 0)))
    b.moving("head", ["head_plate", "head"], "nod", "nod", parent="stem", test=downwind("head", (0, -10, 0)))


def p06_pinwheel_daisies(b):
    b.add("base", "plates.Plate4X4", GREEN, (10, 0, 10))
    clip = conn("63868", "clip", (30, 2, 0), feature="snap_clp")
    y = 0.0
    flowers = (("plants.PlantFlowerWith7AlternatePetalsWithBarAndPinHole", "32606", YELLOW, ry(90), -10),
               ("plants.PlantFlowerWith6RoundedPetalsWithBarAndPinHole", "95831", WHITE, ry(-90), 10),
               ("plants.PlantFlowerWith7AlternatePetalsWithCentreRingWithBarAndPinHole", "4367", MAGENTA, ry(90),
                -10))
    n = 0
    for k, (name, ref, colour, r, dz) in enumerate(flowers, start=1):
        for _ in range(2):
            y -= 24
            b.add(f"post{n}", "bricks.Brick1X1", GREEN, (0, y, 0))
            n += 1
        y -= 8
        b.add(f"arm{k}", "plates.Plate1X2WithClipHorizontalOnEnd_ThickC_Clip_", GREEN, (0, y, dz), r)
        c = b.wp(f"arm{k}", clip["position"])
        a = b.wd(f"arm{k}", clip["axis"])
        stem = next(x for x in find_all(ref, "pin") + find_all(ref, "bar"))
        centre = stem["position"] + stem["axis"] * stem["length"] / 2
        rf = orient((0, 1, 0), (1, 0, 0), (0, 0, 1), (0, 0, 1))  # bar along X, flower facing the wind (-X)
        b.put(f"daisy{k}", name, colour, rf, centre, c)
        b.hinge(f"spin_{k}", f"arm{k}", f"daisy{k}", c, a if a[0] > 0 else -a,
                f"{ref} bar in the 63868 clip; turns about the bar (right-hand about +X)")
        b.moving(f"spin_{k}", [f"daisy{k}"], f"spin_{k}", f"spin_{k}", tip=(f"daisy{k}", (10, -12, 0)))
    b.add("cap", "plates.Plate1X1Round", YELLOW, (0, y - 8, 0))


def p07_grass_meadow(b):
    b.add("base", "plates.Plate6X8", GREEN, (0, 0, 0))
    spots = ((-70, -30), (-50, 10), (-30, -10), (-30, 30), (-10, -30), (10, 10), (30, -10), (30, 30), (50, -30),
             (70, 10))
    colours = (LIME, GREEN, BGREEN, OLIVE)
    for k, (x, z) in enumerate(spots, start=1):
        b.add(f"blade{k}", "plants.PlantGrassStem", colours[k % 4], (x, 0, z), ry(37 * k))
        b.hinge(f"blade_{k}", "base", f"blade{k}", (x, 0, z), (0, 0, 1), "15279 on a base stud",
                flex="the grass stem is one rigid part; the tilt stands in for the blade bending")
        b.moving(f"blade_{k}", [f"blade{k}"], f"blade_{k}", f"blade_{k}", test=downwind(f"blade{k}", (0, -60, 0)))


def p08_reeds(b):
    """Two sea-grass reeds face-on to the viewer; each carries a swordleaf clipped on its tall top bar."""
    b.add("base", "plates.Plate6X6", GREEN, (0, 0, 0))
    grip = conn("30239", "clip")["position"]
    top_bar = find_connector("30093", "bar", (10, -104, 0), axis=(0, 1, 0))
    for k, (x, z, r, out) in enumerate(((-40, -20, I3, (0, 0, -1)), (40, 20, ry(180), (0, 0, 1))), start=1):
        b.add(f"mound{k}", "bricks.Brick2X2RoundWithoutReinforcement", DBG, (x, -24, z))
        b.add(f"clump{k}", "cones.Cone2X2X2WithHollowStudOpen", DGREEN, (x, -72, z))
        b.add(f"stalk{k}", "plants.PlantSeaGrass", OLIVE, (x, -76, z), r)
        b.hinge(f"stalk_{k}", f"clump{k}", f"stalk{k}", b.wp(f"stalk{k}", (0, 0, 0)), (0, 0, 1),
                "30093 bar in the cone's hollow stud (official 7161 mount)",
                flex="the bar in the hollow stud only allows a twist; the tilt stands in for the reed bending")
        b.moving(f"stalk_{k}", [f"stalk{k}"], f"stalk_{k}", f"stalk_{k}", test=downwind(f"stalk{k}", (10, -104, 0)))
        p = b.wp(f"stalk{k}", top_bar["position"] + top_bar["axis"] * top_bar["length"] / 2)
        a = b.wd(f"stalk{k}", top_bar["axis"])
        clip_leaf(b, f"leaf{k}", "plants.PlantLeaves6X5SwordleafWithU_Clip", GREEN, grip, p, a, out, 0)
        b.hinge(f"leaf_{k}", f"stalk{k}", f"leaf{k}", p, (0, -1, 0), "30239 U-clip on the vertical top bar of the "
                "30093 reed; the leaf swings about the bar like a flag (right-hand about up)")
        b.moving(f"leaf_{k}", [f"leaf{k}"], f"leaf_{k}", f"leaf_{k}", parent=f"stalk_{k}",
                 tip=(f"leaf{k}", (0, 10, -70)))
    b.reference("7161-1.mpd", "clump1", "stalk1", a_ref="3942b",
                note="30093 on a 2x2x2 cone's hollow stud (7161 uses the 3942b cone; same height and stud)")


VINE_LINKS = (39.0, 90.0, 141.0, 192.0, 243.0, 281.0)  # 16981 stem split points (local -x), end segments at 0/320


def vine_parts(b, prefix, m_vine, stem_colour, leaf_colour):
    """Rebuild 16981 from its official subfiles: two end segments, five stem pieces and ten leaves.

    Returns {link index: [roles]} for links 0..4 (stem split at local x = -90, -141, -192, -243)."""
    links = {k: [] for k in range(5)}
    for colour, ref, m in part_file("16981"):
        x = m[0, 3]
        if ref == "16981k04":
            for k, (a, c) in enumerate(zip(VINE_LINKS, VINE_LINKS[1:])):
                piece = m.copy()
                piece[0, 3] = -a
                piece[:3, 0] = m[:3, 0] * (c - a) / 242.0
                role = f"{prefix}_stem{k}"
                b.add_m(role, f"ref:{ref}", stem_colour, m_vine @ piece)
                links[k].append(role)
            continue
        k = 0 if x > -VINE_LINKS[1] else 4 if x <= -VINE_LINKS[4] else next(
            i for i in range(1, 5) if -VINE_LINKS[i + 1] < x <= -VINE_LINKS[i])
        role = f"{prefix}_{ref[-3:]}_{int(-x)}"
        b.add_m(role, f"ref:{ref}", stem_colour if ref == "16981k03" else leaf_colour, m_vine @ m)
        links[k].append(role)
    return links


def p09_hanging_vine(b):
    b.add("base", "plates.Plate6X12", GREEN, (-40, 0, 0))
    top = stack(b, "trunk", "bricks.Brick2X2RoundWithoutReinforcement", RBROWN, -100, 0, 14)
    b.add("arm", "plates.Plate2X8", RBROWN, (-50, top - 8, 0))
    b.add("crown", "plants.PlantLeaves6X5", GREEN, (-100, top - 16, -10))
    b.add("hanger", "plates.Plate1X1WithClipVertical_ThickC_Clip_", RBROWN, (20, top, -10))
    clip = conn("60897", "clip", (0, 4, -20), feature="snap_clp")
    g = b.wp("hanger", clip["position"])
    r = np.column_stack([(0, -1.0, 0), (0, 0, -1.0), (1.0, 0, 0)])  # vine local -x hangs down, leaves face -Z
    m_vine = pose(r, g - r @ np.array([-10.0, 0, 0]))  # grip 10 LDU from the end of the top end bar
    links = vine_parts(b, "vine", m_vine, DGREEN, GREEN)
    b.hinge("twist", "hanger", links[0][0], g, (0, -1, 0), "16981 top end bar (16981k03) in the 60897 vertical "
            "clip; turns about the bar")
    b.moving("link0", links[0], "twist", "twist", tip=("vine_k01_50", (0, 0, 25)))
    for k in range(1, 5):
        p = world_point(m_vine, (-VINE_LINKS[k], 0, 0))
        b.hinge(f"bend_{k}", links[k - 1][0], links[k][0], p, (0, 0, 1), f"vine stem split at local x = "
                f"-{VINE_LINKS[k]:g}", flex="16981 is a flexible part (LDraw 'Flexible_Section' segments); the "
                "rebuilt rigid links bend at their joints")
        b.moving(f"link{k}", links[k], f"bend_{k}", f"bend_{k}", parent=f"link{k - 1}",
                 test=downwind(links[k][0], (1, 0, 0)), tip=(links[k][0], (1, 0, 0)))


def p10_rushes(b):
    b.add("base", "plates.Plate8X16", GREEN, (-30, 0, 10))
    socket_c = conn("14418", "generic", (30, 4, 0))
    parts = section_parts("10315-1.mpd", "10315 - bamboo-stalk-3.ldr")
    colours = {"85861": TAN, "59900": DTAN, "37762": OLIVE, "22484": DBG, "30374": OLIVE, "30176": DTAN,
               "32607": OLIVE}
    for k, x in enumerate((-150, -70, 10, 90), start=1):
        b.add(f"riser{k}", "plates.Plate1X2", DGREEN, (x, -8, 0))
        b.add(f"socket{k}", "hinges.Plate1X2WithSocketJoint_8WithFriction", DBG, (x, -16, 0))
        s = b.wp(f"socket{k}", socket_c["position"])
        m_rush = pose(ry((90, -90, 75, -75)[k - 1]), s)  # leaf lobes toward +-Z, away from the neighbours
        roles = []
        for i, (_, ref, m) in enumerate(parts):
            ref = "32607" if ref == "30176" else ref  # small leaf plates: the 30176 lobes would reach the neighbours
            role = f"rush{k}_{ref}_{i}"
            b.add_m(role, const(ref), colours[ref], m_rush @ m)
            roles.append(role)
        ball = next(r for r in roles if "_22484_" in r)
        b.hinge(f"rush_{k}", f"socket{k}", ball, s, (0, 0, 1), "22484 ball in the 14418 friction socket "
                "(stalk as 10315 bamboo-stalk-3, its 30176 leaf bricks swapped for 32607 leaf plates); one tilt "
                "freedom used, about Z")
        top = max(roles, key=lambda r: -b.wp(r, (0, 0, 0))[1])
        b.moving(f"rush_{k}", roles, f"rush_{k}", f"rush_{k}", test=downwind(top, (0, 0, 0)))


def p11_hinged_oak(b):
    b.add("base", "plates.Plate6X6", GREEN, (0, 0, 0))
    top = stack(b, "trunk", "bricks.Brick2X2RoundWithoutReinforcement", RBROWN, 0, 0, 4)
    clip = conn("61252", "clip", (0, 2, -20), feature="snap_clp")
    bar = conn("2540", "bar", (0, 2, -20))
    y = top - 8
    for name, (sx, sz), r, o in (("front", (-10, -10), I3, (0, 0, -1)), ("downwind", (10, -10), ry(-90), (1, 0, 0)),
                                 ("back", (10, 10), ry(180), (0, 0, 1)), ("upwind", (-10, 10), ry(90), (-1, 0, 0))):
        b.add(f"hub_{name}", "plates.Plate1X1WithClipHorizontal_ThickC_Clip_", RBROWN, (sx, y, sz), r)
        c = b.wp(f"hub_{name}", clip["position"])
        a = b.wd(f"hub_{name}", clip["axis"])
        rb = orient((0, 1, 0), (0, 1, 0), (0, 0, 1), o)
        b.put(f"branch_{name}", "plates.Plate1X2WithHandle", RBROWN, rb, bar["position"], c)
        rl = orient((0, 1, 0), (0, 1, 0), (0, 0, -1), o)
        b.add(f"leaves_{name}", "plants.PlantLeaves4X3", GREEN if name in ("front", "back") else BGREEN,
              b.wp(f"branch_{name}", (10, 0, 0)) + np.array([0, -8.0, 0]), rl)
        b.hinge(f"branch_{name}", f"hub_{name}", f"branch_{name}", c, a, "2540 handle bar in the 61252 clip on "
                "the trunk top; the branch turns about the bar")
        b.moving(f"branch_{name}", [f"branch_{name}", f"leaves_{name}"], f"branch_{name}", f"branch_{name}",
                 test=tip_up(f"leaves_{name}", (0, 0, -60)))
    stack(b, "upper", "bricks.Brick2X2RoundWithoutReinforcement", RBROWN, 0, 0, 2, y0=y)
    b.add("crown", "plants.PlantLeaves6X5", GREEN, (10, y - 48 - 8, -10))


def p12_aspen(b):
    b.add("base", "plates.Plate4X4", GREEN, (10, 0, 10))
    y = stack(b, "trunk_a", "bricks.Brick1X1RoundWithHollowStud", RBROWN, 0, 0, 3)
    b.add("knot_a", "bricks.Brick1X1WithStudsOnFourSides", RBROWN, (0, y - 24, 0))
    y = stack(b, "trunk_b", "bricks.Brick1X1RoundWithHollowStud", RBROWN, 0, 0, 3, y0=y - 24)
    b.add("knot_b", "bricks.Brick1X1WithStudsOnFourSides", RBROWN, (0, y - 24, 0))
    y = stack(b, "trunk_c", "bricks.Brick1X1RoundWithHollowStud", RBROWN, 0, 0, 1, y0=y - 24)
    b.add("leaf_top", "plants.PlantLeaves4X3", YELLOW, (0, y - 8, 0), ry(20))
    b.hinge("leaf_top", "trunk_c0", "leaf_top", (0, y, 0), (0, -1, 0), "2423 on the top hollow stud; turns on the "
            "stud (right-hand about up)")
    b.moving("leaf_top", ["leaf_top"], "leaf_top", "leaf_top", tip=("leaf_top", (0, 0, -60)))
    colours = {"front": LIME, "back": YELLOW, "upwind": LIME, "downwind": YELLOW}
    for knot, sides in (("knot_a", (("front", (0, 10, -10), (0, 0, -1)), ("back", (0, 10, 10), (0, 0, 1)))),
                        ("knot_b", (("upwind", (-10, 10, 0), (-1, 0, 0)), ("downwind", (10, 10, 0), (1, 0, 0))))):
        for name, local, axis in sides:
            s = b.wp(knot, local)
            n = np.asarray(axis, float)
            r = orient((0, 1, 0), -n, (0, 0, -1), (0, 1, 0))  # leaf face outward, hanging down from the stud
            b.put(f"leaf_{name}", "plants.PlantLeaves4X3", colours[name], r, (0, 8, 0), s)
            b.hinge(f"leaf_{name}", knot, f"leaf_{name}", s, n, "2423 on a side stud of 4733; swings about the "
                    "stud like a pendulum")
            b.moving(f"leaf_{name}", [f"leaf_{name}"], f"leaf_{name}", f"leaf_{name}",
                     test=downwind(f"leaf_{name}", (0, 0, -60)) if name in ("front", "back") else None,
                     tip=(f"leaf_{name}", (0, 0, -60)))


def p13_fern(b):
    b.add("base", "plates.Plate6X6", GREEN, (0, 0, 0))
    b.add("rock", "bricks.Brick2X2RoundWithoutReinforcement", DBG, (0, -24, 0))
    bars = handle_hub(b, DGREEN, -32)
    grip = conn("30239", "clip")["position"]
    for hub, rise in (("x_pos", -12), ("x_neg", -12), ("z_pos", -28), ("z_neg", -28)):
        p, a = bars[hub]
        name = {"x_pos": "downwind", "x_neg": "upwind", "z_pos": "back", "z_neg": "front"}[hub]
        role = f"frond_{name}"
        clip_leaf(b, role, "plants.PlantLeaves6X5SwordleafWithU_Clip", GREEN if hub[0] == "x" else BGREEN, grip, p,
                  a, outward(p, a), rise)
        b.hinge(role, f"hub_{hub}", role, p, a, "30239 U-clip on the 60478 handle bar; turns about the bar")
        b.moving(role, [role], role, role, test=tip_up(role, (0, 10, -70)))


def p14_bouquet(b):
    b.add("base", "plates.Plate6X6", WHITE, (0, 0, 0))
    vase = section_parts("10297-1.mpd", "10297 - vase.ldr")
    shift_a = pose(I3, (-40, -8, -20))
    flower_colour = (WHITE, BPINK, YELLOW)
    heads = 0
    for colour, ref, m in vase:
        if ref == "32606":
            heads += 1
            b.add_m(f"head_a{heads}", const(ref), flower_colour[heads - 1], shift_a @ m)
        elif ref == "24855":
            b.add_m("stem_a", const(ref), GREEN, shift_a @ m)
        else:
            b.add_m(f"vase_a_{ref}", const(ref), {0: BLACK, 297: PGOLD}.get(colour, colour), shift_a @ m)
    b.hinge("stem_a", "vase_a_85861", "stem_a", b.wp("stem_a", (0, 20, 0)), (0, 0, 1),
            "24855 bar in the vase's open stud (official 10297 vase)",
            flex="the bar in the stud only allows a twist; the tilt stands in for the stem bending")
    b.moving("stem_a", ["stem_a"], "stem_a", "stem_a", test=downwind("stem_a", (0, -20, 0)))
    pins = find_all("24855", "pin")
    for k in range(1, 4):
        role = f"head_a{k}"
        hole = b.wp(role, conn("32606", "pin_hole")["position"])
        pin = min(pins, key=lambda c: np.linalg.norm(b.wp("stem_a", c["position"] + c["axis"] * c["length"]) - hole))
        p, a = b.wp("stem_a", pin["position"]), b.wd("stem_a", pin["axis"])
        b.hinge(f"head_a{k}", "stem_a", role, p, a, "32606 on a long 24855 pin (R2); spins about the pin")
        b.moving(f"head_a{k}", [role], f"head_a{k}", f"head_a{k}", parent="stem_a", tip=(role, (10, -10, 0)))
    shift_b = pose(I3, (40, -8, 20))
    for colour, ref, m in vase:
        if ref in ("32606", "24855"):
            continue
        b.add_m(f"vase_b_{ref}", const(ref), {0: DBG, 297: LGREY}.get(colour, colour), shift_b @ m)
    stem_a_bar = conn("24855", "bar")
    bar_bottom = (vase_m(vase, "24855") @ np.append(stem_a_bar["position"], 1))[:3]
    bar19 = conn("19119", "bar")
    r19 = ry(30)
    m19 = pose(r19, bar_bottom - r19 @ (bar19["position"] + bar19["axis"] * bar19["length"]))
    b.add_m("stem_b", "plants.PlantFlowerStemWithBarAnd6Stems", GREEN, shift_b @ m19)
    b.hinge("stem_b", "vase_b_85861", "stem_b", b.wp("stem_b", (0, 0, 0)), b.wd("stem_b", (0, -1, 0)),
            "19119 bar in the vase's open stud (same seat as the 24855 bar); turns about the bar")
    b.moving("stem_b", ["stem_b"], "stem_b", "stem_b", tip=("stem_b", (20, -20, 0)))
    hole = conn("3742", "pin_hole")
    colours = (RED, YELLOW, MAGENTA, WHITE, ORANGE, BPINK)
    for k, pin in enumerate(find_all("19119", "pin"), start=1):
        p, a = b.wp("stem_b", pin["position"]), b.wd("stem_b", pin["axis"])
        r = orient((0, 1, 0), -a, (1, 0, 0), np.cross(a, (0, 0, 1)) + np.array([1e-3, 0, 0]))
        role = f"head_b{k}"
        b.put(role, "plants.PlantFlower", colours[k - 1], r, hole["position"], p + 6 * a)
        b.hinge(f"head_b{k}", "stem_b", role, p, a, "3742 on a 19119 flower pin (R2); spins about the pin")
        b.moving(f"head_b{k}", [role], f"head_b{k}", f"head_b{k}", parent="stem_b", tip=(role, (10, 0, 0)))
    b.reference("41075-1.mpd", "stem_b", "head_b1", note="3742 on a 19119 pin (official 41075 bouquets)")


def vase_m(vase, ref):
    return next(m for _, r, m in vase if r == ref)


def p15_tiered_shrub(b):
    b.add("base", "plates.Plate4X4", GREEN, (10, 0, 10))
    b.add("seat", "plates.Plate1X1RoundWithOpenStud", DGREEN, (0, -8, 0))
    b.add("bar", "bars.Bar6LWithThickStop", RBROWN, (0, -20, 0))
    for k in range(4):
        y = -12 - 32 * k
        b.add(f"tier{k + 1}", "plants.PlantWithBarAndOff_ShootWithHollowStud", (GREEN, BGREEN, LIME, GREEN)[k],
              (0, y, 0), ry(30 + 100 * k))
        b.hinge(f"tier_{k + 1}", "bar", f"tier{k + 1}", (0, y, 0), (0, -1, 0), "1566 threaded on the 6L bar "
                "(sliding bar hole); turns about the bar (right-hand about up)")
        b.moving(f"tier_{k + 1}", [f"tier{k + 1}"], f"tier_{k + 1}", f"tier_{k + 1}",
                 tip=(f"tier{k + 1}", (24, -24, 0)))


def p16_liana(b):
    b.add("base", "plates.Plate8X16", DTAN, (0, 0, 0), ry(90))
    clip = conn("61252", "clip", (0, 2, -20), feature="snap_clp")
    for name, x, zc, n, inner in (("thorny", 0, 100, 4, -10), ("leafy", 60, 140, 6, 10)):
        for s, side in ((1, "back"), (-1, "front")):
            top = stack(b, f"post_{name}_{side}", "bricks.Brick2X2RoundWithoutReinforcement", RBROWN, x, s * zc, n)
            b.add(f"clip_{name}_{side}", "plates.Plate1X1WithClipHorizontal_ThickC_Clip_", RBROWN,
                  (x - 10, top - 8, s * (zc + inner)), ry(90))
    g_back = b.wp("clip_thorny_back", clip["position"])
    g_front = b.wp("clip_thorny_front", clip["position"])
    r = np.column_stack([(0, 0, 1.0), (-1.0, 0, 0), (0, -1.0, 0)])  # thorns (local -z) hang down
    b.put("vine_thorny", "plants.PlantVineWith8Thorns10L", OLIVE, r, (-10, 0, 0), g_back)
    b.check("thorny_grip_span", abs(np.linalg.norm(g_back - g_front) - 180), 0.5,
            "73828 end bars (local x 0..-20 and -180..-200) gripped 10 LDU from each end")
    b.hinge("rock_thorny", "clip_thorny_back", "vine_thorny", g_back, g_front - g_back,
            "73828 end bars (bar with stop, measured from 73828k03: x 0..-20) in two 61252 clips; turns about "
            "the line through both clips")
    b.moving("rock_thorny", ["vine_thorny"], "rock_thorny", "rock_thorny",
             test=downwind("vine_thorny", (-100, 0, -10)))
    g_back = b.wp("clip_leafy_back", clip["position"])
    g_front = b.wp("clip_leafy_front", clip["position"])
    r = np.column_stack([(0, 0, 1.0), (1.0, 0, 0), (0, 1.0, 0)])
    b.put("vine_leafy", "plants.PlantVineWith10Leaves16L", GREEN, r, (-10, 0, 0), g_back)
    b.check("leafy_grip_span", abs(np.linalg.norm(g_back - g_front) - 300), 0.5,
            "16981 end bars (connector length 25) gripped 10 LDU from each end")
    b.hinge("rock_leafy", "clip_leafy_back", "vine_leafy", g_back, g_front - g_back,
            "16981 end bars (16981k03 bar connectors) in two 61252 clips; turns about the line through both clips")
    b.moving("rock_leafy", ["vine_leafy"], "rock_leafy", "rock_leafy", test=downwind("vine_leafy", (-100, 0, 25)))


def p17_tendrils(b):
    b.add("base", "plates.Plate4X12", DTAN, (0, 0, 0))
    for side, x in (("left", -100), ("right", 100)):
        stack(b, f"post_{side}", "bricks.Brick2X2RoundWithoutReinforcement", DBG, x, 0, 5)
    b.add("beam", "plates.Plate2X10", DBG, (0, -128, 0))
    clip = conn("61252", "clip", (0, 2, -20), feature="snap_clp")
    r = np.column_stack([(1.0, 0, 0), (0, 0, 1.0), (0, -1.0, 0)])  # 28870 bar along Z, stem hanging down
    for k, x in enumerate((-30, 10, 50), start=1):
        b.add(f"spacer{k}", "plates.Plate1X1", DBG, (x, -120, -10))
        b.add(f"hook{k}", "plates.Plate1X1WithClipHorizontal_ThickC_Clip_", DBG, (x, -112, -10), ry(90))
        c = b.wp(f"hook{k}", clip["position"])
        a = b.wd(f"hook{k}", clip["axis"])
        b.put(f"tendril{k}", "plants.PlantStemCurvedWith2ThornsAnd2Swirls", (GREEN, OLIVE, BGREEN)[k - 1], r,
              (0, 5, 0), c)
        b.hinge(f"swing_{k}", f"hook{k}", f"tendril{k}", c, a, "28870 bar (local y 0..10) in the 61252 clip; the "
                "curved stem hangs below the bar and swings about it")
        b.moving(f"swing_{k}", [f"tendril{k}"], f"swing_{k}", f"swing_{k}",
                 test=downwind(f"tendril{k}", (0, -20, -75)))
    b.add("hook4", "plates.Plate1X1WithClipVertical_ThickC_Clip_", DBG, (-10, -120, 10), ry(180))  # behind
    c = b.wp("hook4", conn("60897", "clip", (0, 4, -20), feature="snap_clp")["position"])
    b.put("curl", "plants.PlantVineCurledWithBar", GREEN, rx(180), (0, -4, 0), c)
    b.hinge("twist_curl", "hook4", "curl", c, (0, -1, 0), "1997 bar (local y -8..0) in the 60897 vertical clip; "
            "the curl hangs along its bar, so the clip only lets it turn about the bar")
    b.moving("twist_curl", ["curl"], "twist_curl", "twist_curl", tip=("curl", (0, -60, 25)))


def p18_ground_cover(b):
    b.add("base", "plates.Plate8X8", DTAN, (0, 0, 0))
    plants = (("plants.Plant1X1X0_667RoundWith3LargeLeaves", "6255", GREEN, (-50, -30), 16),
              ("plants.Plant3X3With3LongLeaves", "7264", BGREEN, (50, -50), 8),
              ("plants.Plate1X1RoundWith3Leaves", "32607", LIME, (-10, 10), 8),
              ("plants.PlantFlower2X2WithHollowStud", "4728", YELLOW, (-50, 50), 24),
              ("plants.PlantFlower2X2WithSolidStud", "98262", BPINK, (50, 30), 24),
              ("plants.PlantSerratedLeaf", "2682a", GREEN, (10, -50), 8))
    for k, (name, ref, colour, (x, z), lift) in enumerate(plants, start=1):
        b.add(f"plant{k}", name, colour, (x, -lift, z), ry(50 * k))
        b.hinge(f"turn_{k}", "base", f"plant{k}", (x, 0, z), (0, -1, 0), f"{ref} on a base stud; turns on the "
                "stud (right-hand about up)")
        b.moving(f"turn_{k}", [f"plant{k}"], f"turn_{k}", f"turn_{k}", tip=(f"plant{k}", (25, 0, 0)))


def p19_leaf_vanes(b):
    """Three poles in a row along the wind, tallest upwind: a leaf turning downwind passes over the lower poles."""
    b.add("base", "plates.Plate8X8", GREEN, (0, 0, 0))
    vanes = (("bars.Bar8LWithStopRingsAndPin_RoundedEnd", "2714a", -50, "plants.PlantTreePalmLeafLarge", BGREEN, -135,
              -163.5),
             ("bars.Bar6LWithThickStop", "63965a", 10, "plants.PlantPalmLeafSmall", GREEN, 90, -124),
             ("bars.Bar3L", "87994", 70, "plants.PlantPalmLeafSmall", LIME, -90, -64))
    z = -10
    for k, (bar_name, ref, x, leaf, colour, yaw, top) in enumerate(vanes, start=1):
        b.add(f"seat{k}", "plates.Plate1X1RoundWithOpenStud", DBG, (x, -8, z))
        b.add(f"pole{k}", bar_name, RBROWN, (x, {"63965a": -20, "2714a": -22}.get(ref, top), z))
        b.put(f"vane{k}", leaf, colour, ry(yaw), (-10, 0, 0), (x, top, z))
        b.hinge(f"vane_{k}", f"pole{k}", f"vane{k}", (x, top, z), (0, -1, 0), f"{leaf.split('.')[1]} on the top of "
                f"a {ref} bar through one of its two holes; turns about the bar (right-hand about up)")
        b.moving(f"vane_{k}", [f"vane{k}"], f"vane_{k}", f"vane_{k}", tip=(f"vane{k}", (100, 0, 0)))


def p20_friends_palm(b):
    b.add("base", "plates.Plate6X6", TAN, (0, 0, 0))
    b.add("trunk", "plants.PlantTreePalmBase4X4", RBROWN, (0, -8, 0))
    axle = conn("30338", "axle")
    p = b.wp("trunk", axle["position"])
    a = b.wd("trunk", axle["axis"])
    if a[1] > 0:
        a = -a
    hole = conn("30339", "pin_hole")
    for k, (yaw, colour) in enumerate(((0, GREEN), (45, BGREEN)), start=1):
        side = unit(np.cross(a, (0, 0, 1)))
        side = rotation(a, math.radians(yaw)) @ side
        r = orient((0, -1, 0), a, (1, 0, 0), side)
        b.put(f"crown{k}", "plants.PlantTreePalmLeafQuadruple", colour, r, hole["position"], p + (1 + 3 * k) * a)
        b.hinge(f"crown_{k}", "trunk" if k == 1 else "crown1", f"crown{k}", p, a, "30339 round centre hole on the "
                "30338 trunk-top axle; turns about the axle (right-hand about the axle's up direction)")
        b.moving(f"crown_{k}", [f"crown{k}"], f"crown_{k}", f"crown_{k}", tip=(f"crown{k}", (120, 30, 0)))


BUILDERS = {
    "P01_palm_tree": p01_palm_tree, "P02_swordleaf_palm": p02_swordleaf_palm, "P03_bamboo": p03_bamboo,
    "P04_flower_bed": p04_flower_bed, "P05_sunflower": p05_sunflower, "P06_pinwheel_daisies": p06_pinwheel_daisies,
    "P07_grass_meadow": p07_grass_meadow, "P08_reeds": p08_reeds, "P09_hanging_vine": p09_hanging_vine,
    "P10_rushes": p10_rushes, "P11_hinged_oak": p11_hinged_oak, "P12_aspen": p12_aspen, "P13_fern": p13_fern,
    "P14_bouquet": p14_bouquet, "P15_tiered_shrub": p15_tiered_shrub, "P16_liana": p16_liana,
    "P17_tendrils": p17_tendrils, "P18_ground_cover": p18_ground_cover, "P19_leaf_vanes": p19_leaf_vanes,
    "P20_friends_palm": p20_friends_palm,
}


def assemble(sc):
    b = PlantBuild(sc)
    BUILDERS[sc["key"]](b)
    return b


# --------------------------------------------------------------------------- MPD
def write_mpd(sc, b, path):
    name = f"{sc['key'].lower()}.ldr"
    lines = [
        f"0 FILE {name}",
        f"0 Plant wind case {sc['key']} {sc['title']}",
        f"0 Name: {name}",
        "0 Author: ldraw-mecha scripts/build_plants.py",
        "0 // Generated mock case: parts picked by constant name from data/categories/parts (vine subfiles by LDraw "
        "reference); moving parts placed from LDCad shadow connector frames (data/offLibShadow) via pyldraw3 or "
        "copied from official constructions (2518c01, 10315, 10297). Frame: LDU, -Y up, the case front faces -Z, "
        "ground (base top) at y = 0. Wind blows toward +X.",
        "",
    ]
    for p in b.parts:
        m = p["matrix"]
        values = [m[0, 3], m[1, 3], m[2, 3], *m[0, :3], *m[1, :3], *m[2, :3]]
        lines.append(f"0 // {p['role']}: {p['table'] or 'library ' + p['ref']}")
        lines.append(f"1 {p['colour']} " + " ".join(number(v) for v in values) + f" {p['ref']}.dat")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n")


def case_dir(sc):
    return OUT / sc["key"]


def part_title(ref):
    if ref in SEGMENTS:
        return (library_path() / "parts" / f"{ref}.dat").read_text(encoding="utf-8-sig").splitlines()[0][2:].strip()
    return library_title(ref)


def cmd_mpd(only=None):
    summary = []
    for sc in wc.CASES:
        if only and sc["key"] not in only:
            continue
        b = assemble(sc)
        d = case_dir(sc)
        write_mpd(sc, b, d / "source/scenario.mpd")
        roles = [dict(role=p["role"], id=str(k), table=p["table"], ref=p["ref"], colour=p["colour"],
                      title=part_title(p["ref"]), library_only=p["table"] is None)
                 for k, p in enumerate(b.parts)]
        joints = {k: dict(origin=r6(v["origin"]), axis=r6(v["axis"]), parent=v["parent"], child=v["child"],
                          kind=v["kind"], joint="flex_approx" if k in b.flex else "real", connector=v["connector"])
                  for k, v in b.joints.items()}
        contract.save(d / "source/parts.json", dict(case=sc["key"], title=sc["title"], parts=roles, joints=joints,
                                                    reference_checks=b.references, geometry_checks=b.checks))
        summary.append(dict(case=sc["key"], parts=len(b.parts), joints=len(joints),
                            references=[(r["part"], r["position_offset_ldu"], r["rotation_offset"])
                                        for r in b.references]))
    print(json.dumps(summary, indent=1))


# --------------------------------------------------------------------------- plan authoring
def wind_geometry(plan, b):
    """Per control: case-frame x of its joint and the horizontal motion of its body's tip per radian."""
    out = {}
    for name, body in plan["bodies"].items():
        control = b.bodies[name]["control"]
        o = np.array(body["origin"], float)
        a = unit(body["axis"])
        tip = b.tips.get(name)
        p = world_point(b.m(tip[0]), tip[1]) if tip else o
        v = np.cross(a, p - o)
        n = np.linalg.norm(v)
        out[control] = dict(body=name, x=round(float(o[0]), 1), tip=r6(p), swing=[round(float(v[0] / n), 3) if n else 0.0,
                                                                    round(float(v[2] / n), 3) if n else 0.0],
                         lever=round(float(n), 1))
    return out


def roster_check(sc, geometry):
    """The roster's recipes must use the measured joint x and swing (wind direction decides who moves how)."""
    problems = []
    for name, spec in sc["controls"].items():
        g = geometry.get(name)
        if g is None:
            problems.append(f"{name}: no body")
            continue
        r = spec["recipe"]
        if abs(r["x"] - g["x"]) > 15:
            problems.append(f"{name}: recipe x {r['x']} vs joint x {g['x']}")
        if r["kind"] == "osc" and r["drive"] == "drag" and max(abs(r["swing"][0] - g["swing"][0]),
                                                               abs(r["swing"][1] - g["swing"][1])) > 0.08:
            problems.append(f"{name}: recipe swing {r['swing']} vs measured {g['swing']}")
    return problems


def connections(sc, b, contacts):
    ids = {p["role"]: str(k) for k, p in enumerate(b.parts)}
    out = {}
    for name, j in b.joints.items():
        a, c = ids[j["parent"]], ids[j["child"]]
        found = contacts.get(tuple(sorted((a, c), key=int)))
        check = (f"pyldraw3 contact confirmed ({', '.join(sorted(set(found)))})" if found else
                 "not detected by pyldraw3 contacts (no pairing connector kinds, or a placement it does not "
                 "support); placement from the named source")
        out[f"joint_{name}"] = dict(a=a, b=c, kind="revolute", status="reviewed", evidence=f"{j['connector']}. "
                                    f"{check}.", measurements=dict(origin=r6(j["origin"]), axis=r6(j["axis"])),
                                    review="Joint frame measured as stated (scripts/build_plants.py); "
                                           + ("flex_approx: not a real LEGO freedom." if name in b.flex else
                                              "real LEGO freedom."))
    return out


def mechanism_views(sc, b):
    ids = {p["role"]: str(k) for k, p in enumerate(b.parts)}
    views, moving = {}, set()
    for name, spec in b.bodies.items():
        j = b.joints[spec["joint"]]
        support = [ids[j["parent"]]] if j["parent"] in ids and j["parent"] not in spec["roles"] else []
        parts = bm.ordered([*support, *(ids[r] for r in spec["roles"])])
        moving |= {ids[r] for r in spec["roles"]}
        views[name] = dict(label=f"{sc['title']}: {name.replace('_', ' ')}", parts=parts, bodies=[name],
                           inputs=[f"control:{spec['control']}"], outputs=[f"body:{name}"], disposition="planned",
                           notes=[f"{'flex_approx' if spec['joint'] in b.flex else 'real'} {j['kind']} joint: "
                                  f"{j['connector']}"],
                           review="Joint declared in this plan (scripts/build_plants.py); driven by wind clips.")
    static = bm.ordered(ids[r] for r in ids if ids[r] not in moving)
    views["context"] = dict(label=f"{sc['title']}: base and mounts (static)", parts=static, bodies=[], inputs=[],
                            outputs=[], disposition="static", notes=[],
                            review="Base, trunk and mounts built for the catalog; they do not move in this case.")
    return views


def notes(sc, b):
    real = [k for k in b.joints if k not in b.flex]
    return [
        f"Plant wind case {sc['key']} ({sc['title']}) written by scripts/build_plants.py: {sc['element']}. Parts "
        "picked by constant name from data/categories/parts; frame LDU, -Y up, the case front faces -Z, ground "
        "(base top) at y = 0. The wind blows toward +X.",
        "Joints: " + "; ".join(f"{k}: {'flex_approx' if k in b.flex else 'real'} revolute about "
                               f"{r6(v['axis'])} through {r6(v['origin'])} ({v['connector']})"
                               for k, v in b.joints.items()) + ".",
        f"Real LEGO freedoms: {', '.join(real) or 'none'}. flex_approx joints (rigid tilt standing in for bending "
        f"plastic, range <= {wc.FLEX_LIMIT} rad): {', '.join(b.flex) or 'none'}.",
        "Sign convention by meaning (checked with the evaluator, kinematics.json): " +
        "; ".join(f"{k} + = {c['description']}" for k, c in sc["controls"].items()) + ".",
        "Motion comes from wind clips (scripts/wind_clips.py): a damped-response approximation, not aerodynamics. "
        "Ranges are catalog choices narrowed by sampled clearance (scripts/blender/check_plants_clearance.py), not "
        "measured stops. Kinematic and transform checks do not prove collision-free or physically feasible motion.",
    ]


def cmd_plan(ready, only=None):
    out = []
    for sc in wc.CASES:
        if only and sc["key"] not in only:
            continue
        d = case_dir(sc)
        b = assemble(sc)
        study = contract.load(d / "study/plan.json")
        nodes = {n["id"]: n for n in study["source"]["nodes"]}
        for k, prt in enumerate(b.parts):
            if nodes[str(k)]["ref"].lower().removesuffix(".dat") != prt["ref"].lower():
                raise ValueError(f"{sc['key']}: occurrence {k} is not {prt['ref']}; rerun mpd and prepare")
        sc_plan = dict(sc, controls={k: {f: v for f, v in c.items() if f in ("unit", "min", "max", "description")}
                                     for k, c in sc["controls"].items()})
        plan, semantics = author_plan(sc_plan, b, study)
        geometry = wind_geometry(plan, b)
        problems = roster_check(sc, geometry)
        found = analysis.contacts(study["source"], [str(k) for k in range(len(b.parts))])
        pairs = {}
        for c in found["contacts"]:
            if c["status"] == "confirmed":
                kinds = "/".join(getattr(c[k]["kind"], "value", str(c[k]["kind"])) for k in ("first", "second"))
                pairs.setdefault(tuple(sorted((c["a"], c["b"]), key=int)), []).append(kinds)
        plan["connections"] = connections(sc, b, pairs)
        plan["mechanisms"] = mechanism_views(sc, b)
        plan["notes"] = notes(sc, b)
        contract.validate(plan)
        asym = asymmetric(sc_plan)
        result = contract.evaluate(plan, asym)
        if ready and not problems:
            plan["status"] = "ready"
        contract.validate(plan)
        contract.save(d / "plan.json", plan)
        contract.save(d / "kinematics.json", dict(
            semantics=semantics, wind_geometry=geometry, roster_problems=problems, contacts=found["summary"],
            contact_pairs={"-".join(k): v for k, v in pairs.items()},
            joints={k: "flex_approx" if k in b.flex else "real" for k in b.joints},
            asymmetric_sample=dict(controls=asym, transforms={k: [r6(row) for row in v]
                                                              for k, v in result["transforms"].items()})))
        out.append(dict(case=sc["key"], plan=plan["name"], status=plan["status"], bodies=len(plan["bodies"]),
                        flipped=[k for k, v in semantics.items() if v.get("flipped")], roster_problems=problems,
                        joints_without_contact=[k for k, v in plan["connections"].items()
                                                if "not detected" in v["evidence"]]))
    print(json.dumps(out, indent=1))


# --------------------------------------------------------------------------- catalog export
def cmd_catalog():
    import plant_catalog  # noqa: E402  (markdown writer kept separate)
    plant_catalog.write(OUT)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="command", required=True)
    p = sub.add_parser("mpd")
    p.add_argument("--only", nargs="*")
    p = sub.add_parser("plan")
    p.add_argument("--ready", action="store_true")
    p.add_argument("--only", nargs="*")
    p = sub.add_parser("geometry", help="print measured joint x / swing per control (to author recipes)")
    p.add_argument("--only", nargs="*")
    sub.add_parser("catalog")
    args = ap.parse_args()
    if args.command == "mpd":
        cmd_mpd(args.only)
    elif args.command == "plan":
        cmd_plan(args.ready, args.only)
    elif args.command == "geometry":
        cmd_geometry(args.only)
    else:
        cmd_catalog()


def cmd_geometry(only=None):
    """Draft-plan geometry without a study: evaluator-free joint x and tip swing per body."""
    for sc in wc.CASES:
        if only and sc["key"] not in only:
            continue
        b = assemble(sc)
        bodies = {}
        for name, spec in b.bodies.items():
            j = b.joints[spec["joint"]]
            bodies[name] = dict(origin=r6(j["origin"]), axis=r6(j["axis"]))
        # sign as the semantic check will choose it
        for name, spec in b.bodies.items():
            if spec["test"]:
                role, local, comp, sign = spec["test"]
                p = world_point(b.m(role), local)
                o = np.array(bodies[name]["origin"])
                v = np.cross(unit(bodies[name]["axis"]), p - o)
                if v[comp] * sign < 0:
                    bodies[name]["axis"] = [-x for x in bodies[name]["axis"]]
        geo = wind_geometry(dict(bodies=bodies), b)
        print(sc["key"])
        for name, g in geo.items():
            print(f"    {name:16s} x={g['x']:8.1f} swing={g['swing']} lever={g['lever']} tip={g['tip']}")


if __name__ == "__main__":
    main()
