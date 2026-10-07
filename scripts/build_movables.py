"""Build twenty mock scenarios of classic movable LEGO elements, author their plans and export the clip catalog.

    .venv/bin/python scripts/build_movables.py mpd               # output/movables/Sxx_*/source/scenario.mpd
    ./ldraw-mecha prepare output/movables/Sxx_*/source/scenario.mpd --output output/movables/Sxx_*/study
    .venv/bin/python scripts/build_movables.py plan [--ready]    # output/movables/Sxx_*/plan.json
    .venv/bin/python scripts/build_movables.py catalog           # clips/*.json, catalog.json, CATALOG.md

Every scenario is a small mock: the movable element, the part it is mounted on and just enough context (a wall,
a floor, a chassis) to read. Parts are picked by constant name in the vendored category tables
(data/categories/parts/*.py, parsed as text); a few context parts missing from the tables are named by their
LDraw reference and flagged. Moving parts are placed by mating LDCad shadow connector frames read through
pyldraw3 (data/offLibShadow); where no connector pair exists the placement is taken from an official annotated
model. Where an official model holds the same pair, the composed placement is compared with it
(`source/parts.json` -> `reference_checks`). Joint axes and origins come from the same frames; the sign of each
axis is chosen so that a positive control means what the control description says, checked with the portable
evaluator (`kinematics.json`). Context parts are placed on the stud grid by hand.
"""

from __future__ import annotations

import argparse
import copy
import json
import math
from pathlib import Path
import re
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
from ldraw_mechanisms import analysis, plan as contract  # noqa: E402
from build_minifigs import (connectors, library_title, number, pose, rotation, world_dir,  # noqa: E402
                            world_point)
import movable_clips as mv  # noqa: E402

TABLES = ROOT / "data/categories/parts"
MODELS = ROOT / "data/models-annotated"
OUT = mv.OUT
I3 = np.eye(3)


# --------------------------------------------------------------------------- part tables
def tables():
    """{"file.Constant": ref} for every plain `Name = "ref"` line of the top-level category tables."""
    out = {}
    for f in sorted(TABLES.glob("*.py")):
        if f.name == "__init__.py":
            continue
        for m in re.finditer(r'^([A-Za-z_][A-Za-z0-9_]*) = "([^"]+)"', f.read_text(), re.M):
            out.setdefault(f"{f.stem}.{m.group(1)}", m.group(2))
    return out


TABLE = tables()
# Context parts used by reference because the tables lack them (checked in the library like every other part).
LIBRARY_ONLY = {
    "4600": "Plate 2 x 2 with 2 Wheel Pins (classic; the tables only list the later 4870 mould)",
}


def part_ref(name):
    if name.startswith("ref:"):
        ref = name[4:]
        if ref not in LIBRARY_ONLY:
            raise ValueError(f"{ref} is not an allowed library-only part")
        return ref
    if name not in TABLE:
        raise ValueError(f"{name} is not in {TABLES.relative_to(ROOT)}")
    return TABLE[name]


# --------------------------------------------------------------------------- geometry
def ry(deg):
    return np.round(rotation((0, 1, 0), math.radians(deg)), 12)


def rx(deg):
    return np.round(rotation((1, 0, 0), math.radians(deg)), 12)


def rz(deg):
    return np.round(rotation((0, 0, 1), math.radians(deg)), 12)


def unit(v):
    v = np.asarray(v, float)
    return v / np.linalg.norm(v)


def r6(v):
    return [round(float(x), 6) + 0.0 for x in v]  # + 0.0 turns -0.0 into 0.0


def find_connector(ref, kind, near=None, axis=None, feature=None):
    found = [c for c in connectors(ref) if c["kind"] == kind and (feature is None or feature in c["feature"])]
    if axis is not None:
        found = [c for c in found if abs(abs(np.dot(unit(c["axis"]), unit(axis))) - 1) < 1e-6]
    if near is not None:
        found.sort(key=lambda c: np.linalg.norm(c["position"] - np.array(near, float)))
    if not found:
        raise ValueError(f"{ref}: no {kind} connector near {near} with axis {axis}")
    return found[0]


class Build:
    """Parts of one scenario in its LDraw frame (LDU, -Y up, the scenario front faces -Z, ground at y = 0)."""

    def __init__(self, sc):
        self.sc = sc
        self.parts = []
        self.joints = {}
        self.references = []
        self.bodies = {}
        self.signals = {}

    def m(self, role):
        return next(p for p in self.parts if p["role"] == role)["matrix"]

    def ref(self, role):
        return next(p for p in self.parts if p["role"] == role)["ref"]

    def add(self, role, name, colour, t=(0, 0, 0), r=I3):
        if any(p["role"] == role for p in self.parts):
            raise ValueError(f"{self.sc['key']}: duplicate role {role}")
        ref = part_ref(name)
        library_title(ref)
        m = pose(np.asarray(r, float), np.asarray(t, float))
        self.parts.append(dict(role=role, table=None if name.startswith("ref:") else name, ref=ref, colour=colour,
                               matrix=m))
        return m

    def attach(self, role, name, colour, r, child, parent_role, parent, joint=None, kind="revolute", axis=None):
        """Place a part so that its connector `child` coincides with `parent` on an already placed part.

        `child`/`parent` are (kind, near-position) selectors in the parts' own frames; `r` is the child's world
        rotation. The connector axes must be parallel. With `joint`, records the joint evidence (world origin and
        axis of the parent connector, or `axis` for a slide whose connector only locates the part)."""
        ref = part_ref(name)
        cc = find_connector(ref, child[0], child[1])
        pm = self.m(parent_role)
        pc = find_connector(self.ref(parent_role), parent[0], parent[1])
        origin = world_point(pm, pc["position"])
        joint_axis = axis
        axis = unit(world_dir(pm, pc["axis"]))
        r = np.asarray(r, float)
        if abs(abs(np.dot(unit(r @ cc["axis"]), axis)) - 1) > 1e-6:
            raise ValueError(f"{self.sc['key']} {role}: connector axes not parallel ({r @ cc['axis']} vs {axis})")
        m = self.add(role, name, colour, origin - r @ cc["position"], r)
        if joint:
            how = (f"{self.ref(parent_role)} {pc['kind']} {pc['feature']} receives {ref} {cc['kind']} "
                   f"{cc['feature']}")
            if joint_axis is not None:
                how += f"; slide axis {list(joint_axis)} along the guide (the connector axis only locates the part)"
            self.joint(joint, parent_role, role, origin, axis if joint_axis is None else joint_axis, kind, how)
        return m

    def joint(self, name, parent_role, child_role, origin, axis, kind, how):
        self.joints[name] = dict(origin=np.asarray(origin, float), axis=unit(axis), parent=parent_role,
                                 child=child_role, kind=kind, connector=how)

    def joint_from(self, name, role, kind_sel, parent_role, kind="revolute", how=None):
        """Joint frame from one placed part's own connector (its mate has no usable connector)."""
        c = find_connector(self.ref(role), kind_sel[0], kind_sel[1])
        m = self.m(role)
        self.joint(name, parent_role, role, world_point(m, c["position"]), world_dir(m, c["axis"]), kind,
                   how or f"{self.ref(role)} {c['kind']} {c['feature']}")

    def reference(self, model, a_role, b_role, section=None, note="", a_ref=None, b_ref=None):
        """Compare the placement of b relative to a with every same-section pair in an official model.

        `a_ref`/`b_ref` name the official model's references when it uses a variant (or an embedded copy)."""
        a_ref, b_ref = a_ref or self.ref(a_role), b_ref or self.ref(b_role)
        mine = np.linalg.inv(self.m(a_role)) @ self.m(b_role)
        best = None
        groups = ({k: [(r.removesuffix(".dat"), m) for r, m in v] for k, v in model_sections(model).items()}
                  if section else {"(flattened main model)": flattened(model)})
        for name, items in groups.items():
            if section and section not in name:
                continue
            for ra, ma in items:
                if ra != a_ref:
                    continue
                for rb, mb in items:
                    if rb != b_ref:
                        continue
                    rel = np.linalg.inv(ma) @ mb
                    d = (float(np.linalg.norm(rel[:3, 3] - mine[:3, 3])),
                         float(np.abs(rel[:3, :3] - mine[:3, :3]).max()))
                    if best is None or d < best[0]:
                        best = (d, name)
        if best is None:
            raise ValueError(f"{model}: no {a_ref}/{b_ref} pair")
        self.references.append(dict(model=model, section=best[1], parent=a_role, part=b_role,
                                    official_refs=[a_ref, b_ref],
                                    position_offset_ldu=round(best[0][0], 3), rotation_offset=round(best[0][1], 4),
                                    note=note))

    def body(self, name, roles, joint, control=None, signal=None, parent=None, test=None, kind=None):
        """Declare a moving body: its parts (roles), the joint frame it turns/slides about and its driver.

        `test` = (role, part-local point, component 0/1/2, sign): a small positive control must move that point
        with that sign along x/y/z; the axis is flipped if it does not (the control's meaning is the spec)."""
        self.bodies[name] = dict(roles=list(roles), joint=joint, control=control, signal=signal, parent=parent,
                                 test=test, kind=kind or self.joints[joint]["kind"])

    def signal(self, name, expression, **variables):
        self.signals[name] = dict(expression=expression, variables=variables)

    def transform(self, r, t=(0, 0, 0)):
        """Apply a final rigid placement to the whole scenario (parts and joint frames)."""
        g = pose(np.asarray(r, float), np.asarray(t, float))
        for p in self.parts:
            p["matrix"] = g @ p["matrix"]
        for j in self.joints.values():
            j["origin"] = world_point(g, j["origin"])
            j["axis"] = unit(world_dir(g, j["axis"]))


_SECTIONS = {}
_FLAT = {}


def flattened(model):
    """[(ref, world matrix)] of every leaf placement of the model's first FILE, submodels composed."""
    if model not in _FLAT:
        secs = model_sections(model)
        out = []

        def walk(name, m, depth):
            if depth > 20:
                raise ValueError(f"{model}: submodel nesting too deep at {name}")
            for raw, local in secs.get(name, []):
                # .dat references are parts (embedded copies included); other FILEs are submodels.
                if not raw.endswith(".dat") and raw in secs and raw != name:
                    walk(raw, m @ local, depth + 1)
                else:
                    out.append((raw.removesuffix(".dat"), m @ local))

        walk(next(iter(secs)), np.eye(4), 0)
        _FLAT[model] = out
    return _FLAT[model]


def model_sections(model):
    if model not in _SECTIONS:
        secs, cur = {}, None
        for line in (MODELS / model).read_text(encoding="utf-8", errors="replace").splitlines():
            t = line.split()
            if len(t) >= 3 and t[0] == "0" and t[1].upper() == "FILE":
                cur = " ".join(t[2:]).lower()
            elif len(t) >= 15 and t[0] == "1":
                v = [float(x) for x in t[2:14]]
                m = np.eye(4)
                m[:3, 3] = v[:3]
                m[:3, :3] = np.array(v[3:]).reshape(3, 3)
                secs.setdefault(cur, []).append((" ".join(t[14:]).lower(), m))
        _SECTIONS[model] = secs
    return _SECTIONS[model]


# Colours (LDraw codes)
BLACK, BLUE, GREEN, RED, BROWN, LGREY, DGREY, YELLOW, WHITE, TAN = 0, 1, 2, 4, 6, 7, 8, 14, 15, 19
ORANGE, LBG, DBG, RBROWN, TCLEAR, TBLUE, TLBLUE, DTAN, SGREEN, DRED = 25, 71, 72, 70, 47, 33, 43, 28, 378, 320
BRIGHT_GREEN, MEDIUM_BLUE, PEARL_GOLD = 10, 73, 297


def wall_column(b, prefix, x, z, rows, colour, y0=0, width=4, start=0):
    """Stack of 1-wide bricks along x (centre x), rows of 24 LDU from y0 upwards."""
    names = {1: "bricks.Brick1X1", 2: "bricks.Brick1X2", 3: "bricks.Brick1X3", 4: "bricks.Brick1X4",
             6: "bricks.Brick1X6", 8: "bricks.Brick1X8"}
    for k in range(rows):
        y = y0 - 24 * (k + 1)
        if width in (4, 6, 8) and (k + start) % 2 == 1:
            half = width // 2
            b.add(f"{prefix}{k}a", names[half], colour, (x - 10 * half, y, z))
            b.add(f"{prefix}{k}b", names[half], colour, (x + 10 * half, y, z))
        else:
            b.add(f"{prefix}{k}", names[width], colour, (x, y, z))


# --------------------------------------------------------------------------- scenarios
# Levels: a part's LDraw origin is its top face, so a base plate at y = 0 spans 0..8 and a brick standing on it
# has its origin at y = -24 (plates and tiles: -8).
def s01_house_door(b):
    b.add("base", "plates.Plate6X12", GREEN, (0, 0, 0))
    b.add("frame", "doors.Door1X4X6Frame", WHITE, (0, -144, 0))
    b.attach("door", "doors.Door1X4X6SmoothWithChamferedHandlePlinth", RBROWN, I3, ("hinge", None), "frame",
             ("hinge", (-32, 70, 5)), joint="door")
    for side, x in (("l", -80), ("r", 80)):
        wall_column(b, f"wall_{side}", x, 0, 6, TAN)
    b.add("lintel", "bricks.Brick1X12", TAN, (0, -168, 0))
    b.add("lintel_top", "plates.Plate1X12", DTAN, (0, -176, 0))
    b.reference("10185-1.mpd", "frame", "door", b_ref="60616a",
                note="10185 places 60616a; 60616b has the same hinge geometry")
    b.body("door", ["door"], "door", control="door", test=("door", (60, 70, 0), 2, -1))


def s02_casement_window(b):
    b.add("base", "plates.Plate4X8", GREEN, (0, 0, 0))
    b.add("window", "windows.Window1X4X3WithoutShutterTabs", WHITE, (0, -120, 0))
    # Built from the frame's back; after the final half turn pane_l is on the viewer's left.
    b.attach("pane_l", "windows.Window1X2X3PaneWithThickCornerTabs", WHITE, ry(90), ("hinge", None), "window",
             ("hinge", (32, 34, 5)), joint="pane_l")
    b.attach("pane_r", "windows.Window1X2X3PaneWithThickCornerTabs", WHITE, ry(-90), ("hinge", None), "window",
             ("hinge", (-32, 34, 5)), joint="pane_r")
    wall_column(b, "sill", 0, 0, 2, SGREEN)
    for side, x in (("l", -60), ("r", 60)):
        wall_column(b, f"wall_{side}", x, 0, 5, SGREEN, width=2)
    b.add("lintel", "bricks.Brick1X8", SGREEN, (0, -144, 0))
    b.add("cap", "plates.Plate1X8", DTAN, (0, -152, 0))
    b.reference("10224-1.mpd", "window", "pane_l")
    b.reference("10224-1.mpd", "window", "pane_r")
    # The panes clear the frame only when opening toward the frame's back (+Z): turn the scenario so that side
    # faces the viewer (-Z).
    b.transform(ry(180))
    for side in ("l", "r"):
        b.body(f"pane_{side}", [f"pane_{side}"], f"pane_{side}", control=f"pane_{side}",
               test=(f"pane_{side}", (0, 30, -30), 2, -1))


def s03_shuttered_window(b):
    b.add("base", "plates.Plate4X10", GREEN, (0, 0, 0))
    b.add("window", "windows.Window1X4X3", WHITE, (0, -120, 0))
    b.attach("shutter_l", "windows.Window1X2X3Shutter", RED, ry(-90), ("hinge", None), "window",
             ("hinge", (-40, 34, -12)), joint="shutter_l")
    b.attach("shutter_r", "windows.Window1X2X3Shutter", RED, ry(90), ("hinge", None), "window",
             ("hinge", (40, 34, -12)), joint="shutter_r")
    wall_column(b, "sill", 0, 0, 2, YELLOW)
    for side, x in (("l", -70), ("r", 70)):
        wall_column(b, f"wall_{side}", x, 0, 5, YELLOW, width=3)
    b.add("lintel", "bricks.Brick1X10", YELLOW, (0, -144, 0))
    b.reference("6350-1.mpd", "window", "shutter_l", note="6350 shows the shutters closed")
    b.reference("6350-1.mpd", "window", "shutter_r", note="6350 shows the shutters closed")
    for side in ("l", "r"):
        b.body(f"shutter_{side}", [f"shutter_{side}"], f"shutter_{side}", control=f"shutter_{side}",
               test=(f"shutter_{side}", (0, 34, -36), 2, -1))


def s04_garden_gate(b):
    b.add("base", "plates.Plate4X12", GREEN, (0, 0, 0))
    b.add("gate_base", "fences.Gate1X4X2Base", WHITE, (-30, -48, 0), ry(90))
    b.attach("gate", "fences.Gate1X4X2", RBROWN, ry(90), ("pin_hole", None), "gate_base", ("pin", (0, 40, 0)),
             joint="gate")
    b.add("fence_l", "fences.FenceLattice1X4X2", WHITE, (-80, -48, 0))
    b.add("fence_r", "fences.FenceLattice1X4X2", WHITE, (80, -48, 0))
    b.add("path", "tiles.Tile2X2WithGroove", TAN, (0, -8, -20))
    b.reference("6379-1.mpd", "gate_base", "gate")
    b.body("gate", ["gate"], "gate", control="gate", test=("gate", (0, 20, 60), 2, -1))


def s05_kitchen_cupboard(b):
    b.add("base", "plates.Plate4X6", LBG, (0, 0, 0))
    b.add("cupboard_low", "containers.ContainerCupboard2X3X2WithSolidStuds", WHITE, (0, -48, 0))
    b.attach("door", "containers.ContainerCupboard2X3X2Door", RED, ry(90), ("hinge", None), "cupboard_low",
             ("hinge", (-24, 22, -17)), joint="door")
    b.add("cupboard_high", "containers.ContainerCupboard2X3X2WithSolidStuds", WHITE, (0, -96, 0))
    b.attach("drawer_top", "containers.ContainerCupboard2X3X2Drawer", YELLOW, I3, ("generic", None),
             "cupboard_high", ("generic", (0, 15, -2)), joint="drawer_top", kind="prismatic", axis=(0, 0, -1))
    b.attach("drawer_low", "containers.ContainerCupboard2X3X2Drawer", YELLOW, I3, ("generic", None),
             "cupboard_high", ("generic", (0, 33, -2)), joint="drawer_low", kind="prismatic", axis=(0, 0, -1))
    b.reference("10197-1.mpd", "cupboard_low", "door")
    b.reference("6416-1.mpd", "cupboard_high", "drawer_top")
    b.reference("6416-1.mpd", "cupboard_high", "drawer_low")
    b.body("door", ["door"], "door", control="door", test=("door", (2, 18, 45), 2, -1))
    for name in ("drawer_top", "drawer_low"):
        b.body(name, [name], name, control=name, test=(name, (0, 0, 0), 2, -1))


def s06_double_cabinet(b):
    b.add("base", "plates.Plate4X8", LBG, (0, 0, 0))
    cab = b.add("cabinet", "containers.ContainerCupboard2X6X7", YELLOW, (0, -168, 0))
    # 2042 has no hinge connector: both doors are placed as in set 3636 (left as-is, right turned 180 deg about Z).
    b.add("door_l", "containers.ContainerCupboard2X6X7Door", RED, world_point(cab, (-52, 135, -16)))
    b.add("door_r", "containers.ContainerCupboard2X6X7Door", RED, world_point(cab, (52, 135, -16)), rz(180))
    for side in ("l", "r"):
        b.joint_from(f"door_{side}", f"door_{side}", ("hinge", None), "cabinet",
                     how="2043 hinge snap_fgr (2042 has no shadow hinge); door placement from set 3636")
    for side in ("l", "r"):
        b.reference("3636-1.mpd", "cabinet", f"door_{side}", a_ref="3636 - 2042", b_ref="3636 - 2043",
                    note="3636 embeds its own copies of 2042/2043")
    for side in ("l", "r"):
        b.body(f"door_{side}", [f"door_{side}"], f"door_{side}", control=f"door_{side}",
               test=(f"door_{side}", (45, 0, 0), 2, -1))


def s07_treasure_chest(b):
    b.add("base", "plates.Plate6X8", TAN, (0, 0, 0))
    b.add("chest", "containers.ContainerTreasureChestWithSlots", RBROWN, (0, -32, 0))
    b.attach("lid", "containers.ContainerTreasureChestWithSlotsLid", RBROWN, I3, ("hinge", None), "chest",
             ("hinge", (0, 4, 16)), joint="lid")
    for k, (x, z) in enumerate(((-70, -50), (70, -30), (-50, 50))):
        b.add(f"coin{k}", "tiles.Tile1X1RoundWithGroove", PEARL_GOLD, (x, -8, z))
    b.body("lid", ["lid"], "lid", control="lid", test=("lid", (0, 0, -18), 1, -1))


def s08_mailbox(b):
    b.add("base", "plates.Plate4X4", GREEN, (0, 0, 0))
    for k in range(3):
        b.add(f"post{k}", "bricks.Brick2X2RoundWithoutReinforcement", DGREY, (0, -24 * (k + 1), 0))
    b.add("cap", "plates.Plate2X2", DGREY, (0, -80, 0))
    b.add("box", "containers.ContainerBox2X2X2WithSolidStuds", RED, (0, -128, 0))
    b.attach("door", "containers.ContainerBox2X2X2DoorWithSlot", RED, I3, ("hinge", None), "box",
             ("hinge", (0, 44, -26)), joint="door")
    b.reference("1490-1.mpd", "box", "door")
    b.body("door", ["door"], "door", control="door", test=("door", (0, 4, -26), 2, -1))


def s09_trap_door(b):
    b.add("base", "plates.Plate6X8", DGREY, (0, 0, 0))
    for k, (x, z) in enumerate(((-70, -50), (70, -50), (-70, 50), (70, 50))):
        b.add(f"pillar{k}", "bricks.Brick1X1X5WithSolidStud", LBG, (x, -120, z))
    frame = b.add("frame", "plates.Plate6X8TrapDoorFrame", DGREY, (0, -138, 0))
    # The frame's clips carry no hinge frame: the trap door is placed as in sets 6769/7657 (t = (-50, 10, 0)).
    b.add("trapdoor", "plates.Plate4X5TrapDoor", RBROWN, world_point(frame, (-50, 10, 0)))
    pin = find_connector("30042", "pin", (0, 0, 26))
    m = b.m("trapdoor")
    b.joint("trapdoor", "frame", "trapdoor", world_point(m, pin["position"]), world_dir(m, pin["axis"]),
            "revolute", "30042 pin snap_cyl pair (z = +/-26) in the 30041 clips; placement from sets 6769/7657")
    b.reference("6769-1.mpd", "frame", "trapdoor")
    b.body("trapdoor", ["trapdoor"], "trapdoor", control="trap", test=("trapdoor", (100, 0, 0), 1, 1))


def wheels(b, xs=None, zs=None, y=8):
    """Wheel sets on 4600 holders under a chassis whose bottom is at `y` (set 106 pattern)."""
    if xs is not None:  # axles across Z (car along X)
        for k, x in enumerate(xs):
            b.add(f"axle{k}", "ref:4600", BLACK, (x, y, 0), ry(90))
            for side, z in (("l", -30), ("r", 30)):
                r = I3 if z < 0 else ry(180)
                b.add(f"rim{k}{side}", "wheels.WheelRim6_4X8", LGREY, (x, y + 5, z), r)
                b.add(f"tyre{k}{side}", "tyres.Tyre8_75X8OffsetTread", BLACK, (x, y + 5, z), r)
    else:  # axles across X (vehicle along Z)
        for k, z in enumerate(zs):
            b.add(f"axle{k}", "ref:4600", BLACK, (0, y, z))
            for side, x in (("l", -30), ("r", 30)):
                r = ry(90) if x < 0 else ry(-90)
                b.add(f"rim{k}{side}", "wheels.WheelRim6_4X8", LGREY, (x, y + 5, z), r)
                b.add(f"tyre{k}{side}", "tyres.Tyre8_75X8OffsetTread", BLACK, (x, y + 5, z), r)


def s10_car_doors(b):
    b.add("chassis", "plates.Plate4X8", BLUE, (0, 0, 0))
    wheels(b, xs=(-50, 50))
    b.add("nose", "bricks.Brick2X4", BLUE, (-60, -24, 0), ry(90))
    # The doors' bottom hinge tubes sit on chassis studs; the windscreen above retains their top studs (set 106).
    b.add("door_l", "doors.Door1X3X1Left", BLUE, (-30, -24, -30), ry(90))
    b.add("door_r", "doors.Door1X3X1Right", BLUE, (-30, -24, 30), ry(90))
    for side in ("l", "r"):
        b.joint_from(f"door_{side}", f"door_{side}", ("pin_hole", None), "chassis",
                     how="3821/3822 bottom pin_hole (s/3822s01 hinge tube) on a chassis stud; placement as set 106")
    b.add("windscreen", "windscreens.Windscreen2X4X2", TCLEAR, (-30, -72, 0), ry(90))
    b.add("seat", "bricks.Brick2X2", WHITE, (10, -24, 0))
    b.add("rear", "bricks.Brick2X4", BLUE, (40, -24, 0), ry(90))
    b.add("boot", "plates.Plate2X4", BLUE, (40, -32, 0), ry(90))
    b.add("tail", "bricks.Brick1X4", BLUE, (70, -24, 0), ry(90))
    b.reference("106-1.mpd", "windscreen", "door_l", note="106 places the doors under its windscreen")
    b.reference("106-1.mpd", "windscreen", "door_r", note="106 places the doors under its windscreen")
    b.body("door_l", ["door_l"], "door_l", control="door_l", test=("door_l", (0, 10, 45), 2, -1))
    b.body("door_r", ["door_r"], "door_r", control="door_r", test=("door_r", (0, 10, 45), 2, 1))


def s11_car_roof(b):
    b.add("chassis", "plates.Plate4X8", RED, (0, 0, 0))
    wheels(b, xs=(-50, 50))
    b.add("nose", "bricks.Brick2X4", RED, (-60, -24, 0), ry(90))
    for side, z in (("l", -30), ("r", 30)):
        b.add(f"side_{side}", "bricks.Brick1X4", RED, (0, -24, z), ry(90))
    b.add("rear", "bricks.Brick2X4", RED, (60, -24, 0), ry(90))
    b.add("windscreen", "windscreens.Windscreen2X4X2", TCLEAR, (-30, -72, 0), ry(90))
    b.add("holder", "hinges.HingeCarRoofHolder1X4X2", RED, (30, -72, 0), ry(90))
    b.attach("roof", "hinges.HingeCarRoof4X4", RED, ry(90), ("hinge", None), "holder", ("hinge", None),
             joint="roof")
    b.reference("106-1.mpd", "holder", "roof")
    b.reference("106-1.mpd", "windscreen", "holder")
    b.body("roof", ["roof"], "roof", control="roof", test=("roof", (0, 0, -36), 1, -1))


def s12_canopy(b):
    # Built nose toward -Z, then turned so the nose points to -X (side view of the opening canopy). The canopy hangs
    # from its top-rear hinge: opening swings its lower edge forward and up, so the deck ahead of it stays flat
    # (tiles) and the hinge plate rests on a rear deck, clear of the cockpit.
    b.add("wings", "plates.Plate4X8", LGREY, (0, 8, 0))
    b.add("hull", "plates.Plate4X10", LGREY, (0, 0, 0), ry(90))
    b.add("nose", "tiles.Tile1X4WithGroove", DGREY, (0, -8, -90))
    for k in range(2):
        b.add(f"back_wall{k}", "bricks.Brick1X4", LGREY, (0, -24 * (k + 1), 90))
    b.add("back_plate", "plates.Plate1X4", LGREY, (0, -56, 90))
    b.add("deck", "plates.Plate4X4", LGREY, (0, -64, 60))
    b.add("holder", "hinges.HingePlate1X4WithCarRoofHolder", LGREY, (0, -72, 30))
    b.attach("canopy", "windscreens.Windscreen4X4X3WithHinge", TBLUE, I3, ("hinge", None), "holder",
             ("hinge", None), joint="canopy")
    for side, x in (("l", -20), ("r", 20)):
        b.add(f"engine_{side}", "bricks.Brick2X2RoundWithoutReinforcement", DGREY, (x, -88, 70))
    b.reference("6351-1.mpd", "holder", "canopy")
    b.body("canopy", ["canopy"], "canopy", control="canopy", test=("canopy", (0, 60, -70), 1, -1))
    b.transform(ry(90))


def s13_forklift(b):
    # Shortcut 3430c00-f2 (lowered) split into rails 3430, forks 3431 and the extended spring u9529-f2.
    b.add("chassis", "plates.Plate4X6", YELLOW, (0, 0, 40), ry(90))
    wheels(b, zs=(10, 70))
    b.add("body", "bricks.Brick2X4", YELLOW, (0, -24, 50), ry(90))
    b.add("seat", "bricks.Brick2X2", BLACK, (0, -48, 60))
    b.add("rails", "vehicles.ForkliftRails2X4X5_667", BLACK, (0, -40, 0))
    rails = b.m("rails")
    b.add("forks", "vehicles.ForkliftForks2X4", LGREY, world_point(rails, (0, -4, -56)))
    b.add("spring", "vehicles.Forklift2X7Spring_Extended_", BLACK, world_point(rails, (0, -88.8, -51.05)))
    b.joint("forks", "rails", "forks", world_point(rails, (0, -4, -56)), (0, -1, 0), "prismatic",
            "3430c00-f1/-f2 shortcut positions: forks at y = -104 (raised) and -4 (lowered) in the rails frame")
    b.joint("spring", "rails", "spring", world_point(rails, (0, -88.8, -51.05)), (0, 1, 0), "stretch",
            "u9529-f2 extended spring: seats at local y = 0 (rails) and 136 (forks); u9529-f1 compressed "
            "seats 0 and 36")
    b.body("forks", ["forks"], "forks", control="lift", test=("forks", (0, 0, 0), 1, -1))
    # The spring is stretched (here: compressed) between its fixed top seat and the forks: scale about the top seat.
    b.signal("spring_scale", "(136 - a) / 136", a="control:lift")
    b.body("spring", ["spring"], "spring", signal="spring_scale")


def s14_sliding_door(b):
    # Two door-rail plates end to end top and bottom (set 7735: door t = (62, -59, -13) from a 4510 rail).
    b.add("base", "plates.Plate6X16", DGREY, (0, 0, 10))
    for name, x in (("a", -80), ("b", 80)):
        b.add(f"rail_low_{name}", "plates.Plate1X8WithDoorRail", RED, (x, -8, 0))
    rail = b.m("rail_low_a")
    b.add("door", "doors.Door6_5X5SlidingWithCorrugatedSurface", LBG, world_point(rail, (62, -59, -13)))
    b.joint("door", "rail_low_a", "door", world_point(rail, (62, -59, -13)), (1, 0, 0), "prismatic",
            "4511 has no connectors: placement and sliding direction from set 7735 (door in the 4510 rail "
            "grooves, slides along the rails)")
    for k in range(5):
        y = -8 - 24 * (k + 1)
        b.add(f"wall{k}", "bricks.Brick1X8", RED, (80, y, 20))
        b.add(f"post{k}", "bricks.Brick1X1", RED, (-150, y, 20))
    b.add("wall_cap", "plates.Plate1X8", RED, (80, -136, 20))
    b.add("post_cap", "plates.Plate1X1", RED, (-150, -136, 20))
    for name, x in (("a", -80), ("b", 80)):
        b.add(f"rail_top_{name}", "plates.Plate1X8WithDoorRail", RED, (x, -136, 0))
    b.add("roof", "plates.Plate2X16", DGREY, (0, -144, 10))
    b.reference("7735-1.mpd", "rail_low_a", "door")
    b.body("door", ["door"], "door", control="slide", test=("door", (0, 0, 0), 0, 1))


def s15_radar(b):
    b.add("base", "plates.Plate4X4", DGREY, (0, 0, 0))
    for k in range(2):
        b.add(f"pedestal{k}", "bricks.Brick2X2", LBG, (0, -24 * (k + 1), 0))
    b.add("turntable_base", "turntables.Turntable2X2PlateBase", DGREY, (0, -56, 0))
    b.attach("turntable_top", "turntables.Turntable2X2PlateTop", LBG, I3, ("pin", None), "turntable_base",
             ("pin_hole", (0, 6, 0)), joint="spin")
    b.add("mount", "plates.Plate2X2WithGrooveWith1CentreStud", LBG, (0, -64, 0))
    b.add("mast0", "bricks.Brick1X1", WHITE, (0, -88, 0))
    b.add("mast1", "bricks.Brick1X1", WHITE, (0, -112, 0))
    b.add("head", "bricks.Brick1X1WithStudOn1Side", WHITE, (0, -136, 0))
    head = b.m("head")
    side = find_connector("87087", "stud", (0, 10, -10))
    recep = find_connector("3960", "stud_receptacle", (0, 16, 0))
    r = rx(90)
    b.add("dish", "dishes.Dish4X4Inverted", WHITE, world_point(head, side["position"]) - r @ recep["position"], r)
    b.add("beacon", "plates.Plate1X1Round", RED, (0, -144, 0))
    b.body("radar", ["turntable_top", "mount", "mast0", "mast1", "head", "dish", "beacon"], "spin",
           control="spin", test=("dish", (0, 0, 0), 0, 1))


def s16_crane(b):
    b.add("base", "plates.Plate6X6", DGREY, (0, 0, 0))
    for row in range(2):
        for k, z in enumerate((-20, 20)):
            b.add(f"pedestal{row}{k}", "bricks.Brick2X4", YELLOW, (0, -24 * (row + 1), z))
    b.add("turntable_base", "turntables.Turntable4X4Base", DGREY, (0, -72, 0))
    b.attach("turntable_top", "turntables.Turntable4X4Top", DGREY, I3, ("pin", None), "turntable_base",
             ("pin_hole", None), joint="slew")
    # 1-wide cab at the back: the boom's tail (10 LDU behind its hinge) dips backward as the boom rises.
    b.add("cab", "bricks.Brick1X4", YELLOW, (0, -96, 30))
    b.add("cab_window", "bricks.Brick1X4", BLACK, (0, -120, 30))
    b.add("cab_roof", "plates.Plate1X4", YELLOW, (0, -128, 30))
    b.add("hinge_base", "hinges.Hinge1X2Base", DGREY, (0, -96, -10))
    b.attach("hinge_top", "hinges.Hinge2X2Top", DGREY, ry(180), ("hinge", None), "hinge_base", ("hinge", None),
             joint="luff")
    # The hinge top's back stud row sits over the axis and overhangs it by 10 LDU: a riser on the front row carries
    # the boom so that nothing above it reaches behind the axis (the boom would otherwise dip into the hinge base).
    b.add("boom_riser", "plates.Plate1X2", DGREY, (0, -104, -30))
    b.add("boom", "plates.Plate2X10", YELLOW, (0, -112, -120), ry(90))
    b.add("boom_tip", "technic.TechnicBrick1X2WithHole", DGREY, (10, -104, -200), ry(90))
    tip = b.m("boom_tip")
    hole = find_connector("3700", "pin_hole", None, axis=(0, 0, 1))
    centre = world_point(tip, hole["position"])
    b.add("hook", "cranes.CraneHookWith4Studs", DGREY, centre)
    b.joint("hook", "boom_tip", "hook", centre, world_dir(tip, hole["axis"]), "revolute",
            "3136 hook pins (local x) in the 3700 hole; the hook hangs freely and is kept plumb by hook = -luff")
    b.body("superstructure", ["turntable_top", "cab", "cab_window", "cab_roof", "hinge_base"], "slew",
           control="slew",
           test=("hinge_base", (0, 0, 0), 0, 1))
    b.body("boom", ["hinge_top", "boom_riser", "boom", "boom_tip"], "luff", control="luff", parent="superstructure",
           test=("boom_tip", (0, 0, 0), 1, -1))
    b.signal("hook_angle", "-a", a="control:luff")
    b.body("hook", ["hook"], "hook", signal="hook_angle", parent="boom")


def s17_tipper(b):
    # Rear of set 6532 (dumper back + movable): hinge tiles 4531 on a 2x4 bed, the bucket's 4275b hinge plates
    # at the same place, bucket 20 LDU ahead of the bed (all relative placements from 6532).
    b.add("chassis", "plates.Plate4X10", DGREY, (0, 0, 60), ry(90))
    wheels(b, zs=(20, 120))
    b.add("cab", "bricks.Brick2X4", YELLOW, (0, -24, -20), ry(90))
    b.add("cab_roof", "plates.Plate2X4", YELLOW, (0, -32, -20), ry(90))
    b.add("bed", "plates.Plate2X4", DGREY, (0, -8, 140), ry(90))
    r = ry(-90)
    for side, x in (("l", -10), ("r", 10)):
        b.add(f"hinge_tile_{side}", "hinges.HingeTile1X2With2Fingers", DGREY, (x, -24, 140), r)
        b.add(f"hinge_plate_{side}", "hinges.HingePlate1X2With3FingersAndHollowStuds", DGREY, (x, -24, 140), r)
    b.add("bucket", "others.TipperBucket4X6WithOpenStudsFrontLip", YELLOW, (0, -32, 120))
    b.joint_from("tip", "hinge_tile_l", ("hinge", None), "chassis",
                 how="4531 hinge snap_fgr (finger axis); the 4275b shadow hinge frame lies along the plate, not "
                     "the finger axis; placement as set 6532")
    b.joints["tip"]["child"] = "hinge_plate_l"
    b.reference("6532-1.mpd", "hinge_tile_l", "hinge_plate_l")
    b.reference("6532-1.mpd", "hinge_plate_l", "bucket")
    b.body("bucket", ["hinge_plate_l", "hinge_plate_r", "bucket"], "tip", control="tip",
           test=("bucket", (0, 0, -90), 1, -1))


def s18_barrier(b):
    b.add("road", "plates.Plate4X12", DGREY, (0, 0, 0))
    for k in range(2):
        b.add(f"post{k}", "bricks.Brick2X2", WHITE, (-100, -24 * (k + 1), 0))
    b.add("hinge_base", "hinges.Hinge1X2Base", DGREY, (-100, -72, 0), ry(90))
    b.attach("hinge_top", "hinges.Hinge1X2Top", DGREY, ry(90), ("hinge", None), "hinge_base", ("hinge", None),
             joint="boom")
    b.add("boom", "plates.Plate2X10", WHITE, (-10, -80, 0))
    for k, x in enumerate((-50, 10, 70)):
        b.add(f"stripe{k}", "tiles.Tile2X2WithGroove", RED, (x, -88, 0))
    for k in range(3):
        b.add(f"rest{k}", "bricks.Brick1X1", WHITE, (70, -24 * (k + 1), -10))
    b.body("boom", ["hinge_top", "boom", "stripe0", "stripe1", "stripe2"], "boom", control="boom",
           test=("boom", (90, 0, 0), 1, -1))


def s19_drawbridge(b):
    # Built with the hinge axis along Z and the deck pointing to +X, then turned so the deck comes toward -Z.
    # Two hinge 1x2 pairs (3937 base on the threshold, 3938 top under the deck) share one axis.
    b.add("ground", "baseplates.Baseplate16X16", GREEN, (60, 0, 0))
    b.add("moat", "plates.Plate6X6", MEDIUM_BLUE, (80, -8, 0))
    for side, z in (("l", -50), ("r", 50)):
        b.add(f"hinge_wall_{side}", "hinges.Hinge1X2Base", DGREY, (0, -24, z), ry(90))
        b.attach(f"hinge_deck_{side}", "hinges.Hinge1X2Top", DGREY, ry(90), ("hinge", None), f"hinge_wall_{side}",
                 ("hinge", None), joint=f"bridge_{side}")
    b.add("deck", "plates.Plate6X8", RBROWN, (70, -32, 0))
    b.add("bank", "bricks.Brick1X6", DGREY, (140, -24, 0), ry(90))
    for k in range(7):
        y = -24 * (k + 1)
        for side, z in (("l", -80), ("r", 80)):
            b.add(f"tower_{side}{k}", "bricks.Brick2X2", LBG, (-20, y, z))
    b.add("lintel", "bricks.Brick1X8", LBG, (-20, -192, 0), ry(90))
    b.add("lintel_cap", "plates.Plate2X10", DGREY, (-20, -200, 0), ry(90))
    b.transform(ry(90))
    b.body("deck", ["hinge_deck_l", "hinge_deck_r", "deck"], "bridge_l", control="bridge",
           test=("deck", (70, 0, 0), 1, -1))


def s20_levers(b):
    b.add("base", "plates.Plate4X6", DGREY, (0, 0, 0))
    b.add("desk", "bricks.Brick2X4", LBG, (0, -24, 10))
    for side, x in (("l", -30), ("r", 30)):
        b.add(f"lever_base_{side}", "hinges.HingeControlStickBase", BLACK, (x, -32, 0))
        b.attach(f"stick_{side}", "hinges.HingeControlStick", RED if side == "l" else BLUE, I3, ("hinge", None),
                 f"lever_base_{side}", ("hinge", None), joint=f"lever_{side}")
    b.add("screen", "tiles.Tile1X2GrilleWithGroove", DGREY, (0, -32, 20))
    for side in ("l", "r"):
        b.body(f"stick_{side}", [f"stick_{side}"], f"lever_{side}", control=f"lever_{side}",
               test=(f"stick_{side}", (0, -38, 0), 2, -1))


BUILDERS = {
    "S01_house_door": s01_house_door, "S02_casement_window": s02_casement_window,
    "S03_shuttered_window": s03_shuttered_window, "S04_garden_gate": s04_garden_gate,
    "S05_kitchen_cupboard": s05_kitchen_cupboard, "S06_double_cabinet": s06_double_cabinet,
    "S07_treasure_chest": s07_treasure_chest, "S08_mailbox": s08_mailbox, "S09_trap_door": s09_trap_door,
    "S10_car_doors": s10_car_doors, "S11_car_roof": s11_car_roof, "S12_canopy": s12_canopy,
    "S13_forklift": s13_forklift, "S14_sliding_door": s14_sliding_door, "S15_radar": s15_radar,
    "S16_crane": s16_crane, "S17_tipper": s17_tipper, "S18_barrier": s18_barrier, "S19_drawbridge": s19_drawbridge,
    "S20_levers": s20_levers,
}


def assemble(sc):
    b = Build(sc)
    BUILDERS[sc["key"]](b)
    return b


# --------------------------------------------------------------------------- MPD
def write_mpd(sc, b, path):
    name = f"{sc['key'].lower()}.ldr"
    lines = [
        f"0 FILE {name}",
        f"0 Movable element scenario {sc['key']} {sc['title']}",
        f"0 Name: {name}",
        "0 Author: ldraw-mecha scripts/build_movables.py",
        "0 // Generated mock scenario: parts picked by constant name from data/categories/parts (a few context "
        "parts by LDraw reference); moving parts placed from LDCad shadow connector frames (data/offLibShadow) via "
        "pyldraw3 or from official annotated models where no connector pair exists. Frame: LDU, -Y up, the "
        "scenario front faces -Z, ground (base top) at y = 0.",
        "",
    ]
    for p in b.parts:
        m = p["matrix"]
        values = [m[0, 3], m[1, 3], m[2, 3], *m[0, :3], *m[1, :3], *m[2, :3]]
        lines.append(f"0 // {p['role']}: {p['table'] or 'library ' + p['ref']}")
        lines.append(f"1 {p['colour']} " + " ".join(number(v) for v in values) + f" {p['ref']}.dat")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n")


def scenario_dir(sc):
    return OUT / sc["key"]


def cmd_mpd(only=None):
    summary = []
    for sc in mv.SCENARIOS:
        if only and sc["key"] not in only:
            continue
        b = assemble(sc)
        d = scenario_dir(sc)
        write_mpd(sc, b, d / "source/scenario.mpd")
        roles = [dict(role=p["role"], id=str(k), table=p["table"], ref=p["ref"], colour=p["colour"],
                      title=library_title(p["ref"]), library_only=p["table"] is None)
                 for k, p in enumerate(b.parts)]
        joints = {k: dict(origin=r6(v["origin"]), axis=r6(v["axis"]), parent=v["parent"], child=v["child"],
                          kind=v["kind"], connector=v["connector"]) for k, v in b.joints.items()}
        contract.save(d / "source/parts.json", dict(scenario=sc["key"], title=sc["title"], parts=roles,
                                                    joints=joints, reference_checks=b.references))
        summary.append(dict(scenario=sc["key"], parts=len(b.parts), joints=list(joints),
                            references=[(r["part"], r["position_offset_ldu"], r["rotation_offset"])
                                        for r in b.references]))
    print(json.dumps(summary, indent=1))


# --------------------------------------------------------------------------- plan authoring
def ordered(ids):
    return sorted(set(ids), key=int)


def author_plan(sc, b, study):
    """Draft plan from the study: controls from movable_clips, bodies from the scenario's joints and roles."""
    plan = copy.deepcopy(study)
    plan["name"] = sc["plan"]
    plan["status"] = "draft"
    ids = {p["role"]: str(k) for k, p in enumerate(b.parts)}
    controls = {name: dict(default=0, min=c["min"], max=c["max"], unit=c["unit"], description=c["description"])
                for name, c in sc["controls"].items()}
    signals, bodies = {}, {}
    for name, spec in b.bodies.items():
        j = b.joints[spec["joint"]]
        sig = spec["signal"]
        if sig is None:
            sig = f"{spec['control']}_{'angle' if spec['kind'] == 'revolute' else 'offset'}"
            signals[sig] = dict(expression="a", variables=dict(a=f"control:{spec['control']}"))
        body = dict(instances=ordered(ids[r] for r in spec["roles"]), kind=spec["kind"], origin=r6(j["origin"]),
                    axis=r6(j["axis"]), signal=sig)
        if spec["parent"]:
            body["parent"] = spec["parent"]
        bodies[name] = body
    for name, sig in b.signals.items():
        signals[name] = copy.deepcopy(sig)
    plan.update(controls=controls, signals=signals, bodies=bodies, anchors={}, checks=[])
    semantics = {}
    for name, spec in b.bodies.items():
        if not spec["test"]:
            continue
        for attempt in range(2):
            ok, detail = semantic_check(plan, b, name, spec)
            if ok:
                break
            bodies[name]["axis"] = [-v for v in bodies[name]["axis"]]
        if not ok:
            raise ValueError(f"{sc['key']}: {name} sign check failed: {detail}")
        semantics[name] = dict(detail, flipped=attempt == 1)
    semantics.update(dependent_checks(sc, plan, b))
    return plan, semantics


def semantic_check(plan, b, name, spec):
    role, local, comp, sign = spec["test"]
    point = world_point(b.m(role), local)
    control = spec["control"]
    c = plan["controls"][control]
    value = 0.2 if c["unit"] == "radian" else 4.0
    if c["max"] <= 0:
        value = -value
    result = contract.evaluate(plan, {control: value})
    moved = world_point(np.array(result["transforms"][name], float), point)
    d = moved - point
    return bool(d[comp] * sign * np.sign(value) > 1e-6), dict(
        control=control, value=value, test_point=r6(point), displacement=r6(d),
        expected=f"{'+-'[sign < 0]}{'xyz'[comp]}")


def dependent_checks(sc, plan, b):
    """Checks of dependent signals (plumb hook, spring seat) with the portable evaluator."""
    out = {}
    if sc["key"] == "S16_crane":
        for values in (dict(luff=0.6), dict(luff=1.0, slew=0.7), dict(luff=0.3, slew=-1.2)):
            for attempt in range(2):
                t = contract.evaluate(plan, values)["transforms"]
                hook = np.array(t["hook"], float)[:3, :3]
                sup = np.array(t["superstructure"], float)[:3, :3]
                err = float(np.abs(hook - sup).max())
                if err < 1e-9:
                    break
                plan["signals"]["hook_angle"]["expression"] = "a" if attempt == 0 else "-a"
            if err > 1e-9:
                raise ValueError(f"S16 hook not plumb: {err}")
            out[f"hook_plumb_{values}"] = dict(expression=plan["signals"]["hook_angle"]["expression"],
                                               hook_vs_superstructure_rotation_error=err)
    if sc["key"] == "S13_forklift":
        rails = b.m("rails")
        top = world_point(rails, (0, -88.8, -51.05))
        for lift in (25.0, 60.0, 100.0):
            t = contract.evaluate(plan, dict(lift=lift))["transforms"]
            seat = world_point(np.array(t["spring"], float), top + np.array([0, 136.0, 0]))
            fork = world_point(np.array(t["forks"], float), top + np.array([0, 136.0, 0]))
            err = float(np.linalg.norm(seat - fork))
            if err > 1e-6:
                raise ValueError(f"S13 spring seat does not follow the forks: {err}")
            out[f"spring_seat_lift_{lift:g}"] = dict(seat=r6(seat), follows_forks_error=err)
    return out


def connections(sc, b, contacts):
    """Reviewed evidence edges: one per joint; `contacts` are pyldraw3-confirmed pairs {(a, b): [kinds]}."""
    ids = {p["role"]: str(k) for k, p in enumerate(b.parts)}
    out = {}
    for name, j in b.joints.items():
        a, c = ids[j["parent"]], ids[j["child"]]
        found = contacts.get(tuple(sorted((a, c), key=int)))
        check = (f"pyldraw3 contact confirmed ({', '.join(sorted(set(found)))})" if found else
                 "not detected by pyldraw3 contacts (no pairing connector kinds); placement from the named source")
        kind = {"revolute": "revolute", "prismatic": "prismatic"}.get(j["kind"], "fixed")
        out[f"joint_{name}"] = dict(a=a, b=c, kind=kind, status="reviewed", evidence=f"{j['connector']}. {check}.",
                                    measurements=dict(origin=r6(j["origin"]), axis=r6(j["axis"])),
                                    review="Joint frame measured as stated (scripts/build_movables.py); see "
                                           "source/parts.json reference_checks for official placements.")
    return out


def mechanism_views(sc, b):
    ids = {p["role"]: str(k) for k, p in enumerate(b.parts)}
    views, moving = {}, set()
    for name, spec in b.bodies.items():
        j = b.joints[spec["joint"]]
        support = [ids[j["parent"]]] if j["parent"] in ids and j["parent"] not in spec["roles"] else []
        parts = ordered([*support, *(ids[r] for r in spec["roles"])])
        moving |= {ids[r] for r in spec["roles"]}
        driver = f"control:{spec['control']}" if spec["control"] else f"control:{next(iter(sc['controls']))}"
        views[name] = dict(label=f"{sc['title']}: {name.replace('_', ' ')}", parts=parts, bodies=[name],
                           inputs=[driver], outputs=[f"body:{name}"], disposition="planned",
                           notes=[f"{j['kind']} joint: {j['connector']}"],
                           review="Measured joint declared in this plan (scripts/build_movables.py).")
    static = ordered(ids[r] for r in ids if ids[r] not in moving)
    views["context"] = dict(label=f"{sc['title']}: mounting and mock context (static)", parts=static, bodies=[],
                            inputs=[], outputs=[], disposition="static", notes=[],
                            review="Mock context built for the catalog (walls, floor, chassis, mounts); it does "
                                   "not move in this scenario.")
    return views


def notes(sc, b, semantics):
    joints = "; ".join(f"{k}: {v['kind']} about {r6(v['axis'])} through {r6(v['origin'])} ({v['connector']})"
                       for k, v in b.joints.items())
    return [
        f"Mock scenario {sc['key']} ({sc['title']}) written by scripts/build_movables.py: {sc['element']}. Parts "
        "picked by constant name from data/categories/parts; frame LDU, -Y up, the scenario front faces -Z, "
        "ground (base top) at y = 0.",
        f"Joints: {joints}.",
        "Sign convention by meaning (checked with the evaluator, kinematics.json): " +
        "; ".join(f"{k} + = {c['description']}" for k, c in sc["controls"].items()) + ".",
        "Ranges are catalog choices, narrowed by sampled clearance against the mock context "
        "(scripts/blender/check_movables_clearance.py); they are not measured mechanical stops.",
        "Kinematic and transform checks do not prove collision-free or physically feasible motion.",
    ]


def asymmetric(sc):
    """Nonzero, unequal test values inside every control range."""
    out = {}
    for k, (name, c) in enumerate(sc["controls"].items()):
        frac = (0.63, 0.37, 0.81)[k % 3]
        out[name] = round(c["min"] + (c["max"] - c["min"]) * frac, 6) if c["min"] >= 0 else round(c["max"] * frac * (
            -1 if k % 2 else 1), 6)
    return out


def cmd_plan(ready, only=None):
    out = []
    for sc in mv.SCENARIOS:
        if only and sc["key"] not in only:
            continue
        d = scenario_dir(sc)
        b = assemble(sc)
        study = contract.load(d / "study/plan.json")
        nodes = {n["id"]: n for n in study["source"]["nodes"]}
        for k, prt in enumerate(b.parts):
            if nodes[str(k)]["ref"].lower().removesuffix(".dat") != prt["ref"].lower():
                raise ValueError(f"{sc['key']}: occurrence {k} is not {prt['ref']}; rerun mpd and prepare")
        plan, semantics = author_plan(sc, b, study)
        found = analysis.contacts(study["source"], [str(k) for k in range(len(b.parts))])
        pairs = {}
        for c in found["contacts"]:
            if c["status"] == "confirmed":
                kinds = "/".join(getattr(c[k]["kind"], "value", str(c[k]["kind"])) for k in ("first", "second"))
                pairs.setdefault(tuple(sorted((c["a"], c["b"]), key=int)), []).append(kinds)
        plan["connections"] = connections(sc, b, pairs)
        plan["mechanisms"] = mechanism_views(sc, b)
        plan["notes"] = notes(sc, b, semantics)
        contract.validate(plan)
        asym = asymmetric(sc)
        result = contract.evaluate(plan, asym)
        if ready:
            plan["status"] = "ready"
        contract.validate(plan)
        contract.save(d / "plan.json", plan)
        contract.save(d / "kinematics.json", dict(
            semantics=semantics, contacts=found["summary"], contact_pairs={"-".join(k): v for k, v in pairs.items()},
            asymmetric_sample=dict(controls=asym, transforms={k: [r6(row) for row in v]
                                                              for k, v in result["transforms"].items()})))
        out.append(dict(scenario=sc["key"], plan=plan["name"], status=plan["status"], bodies=len(plan["bodies"]),
                        flipped=[k for k, v in semantics.items() if v.get("flipped")],
                        joints_without_contact=[k for k, v in plan["connections"].items()
                                                if "not detected" in v["evidence"]]))
    print(json.dumps(out, indent=1))


# --------------------------------------------------------------------------- catalog export
def clearance_summary():
    path = OUT / "clearance-summary.json"
    return json.loads(path.read_text())["scenarios"] if path.exists() else {}


def fmt(v):
    return f"{v:.4g}"


def catalog_markdown(docs, scenarios, clearance):
    by_scenario = {}
    for d in docs:
        by_scenario.setdefault(d["scenario"], []).append(d)
    lines = [
        "# Movable-element catalog",
        "",
        "Twenty mock scenarios of classic (non-Technic) movable LEGO elements, three animation clips each, in one "
        "file: [`movables.blend`](movables.blend). Generated by `scripts/build_movables.py catalog` from "
        "`scripts/movable_clips.py`. See [`REPORT.md`](REPORT.md) for how the scenarios were built and checked.",
        "",
        "## How to find a how-to",
        "",
        "1. Pick a scenario by element (table below), or a movement style from the style index.",
        "2. In `movables.blend`, open the scene of the same name (scene list: `S07 Treasure chest` …) to see that "
        "case alone, or the `Catalog` scene to see all twenty. Each scene's timeline markers name its clips.",
        "3. Reuse the clip's Action (Blender) or its JSON keys (`clips/<scenario>.<clip>.json`); see *Reusing a "
        "clip*.",
        "",
        "Timeline (24 fps): clip A plays in frames 1–144, B in 161–304, C in 321–464; between windows each element "
        "holds its rest pose. Every clip starts and ends at rest (all controls 0; spins end on whole turns).",
        "",
        "## Scenarios",
        "",
        "| Scenario (collection / scene) | Moving element → mount | Controls (+ meaning, range) | Joint (frame LDU, "
        "scenario axes) |",
        "| --- | --- | --- | --- |",
    ]
    for sc in scenarios:
        info = json.loads((scenario_dir(sc) / "source/parts.json").read_text())
        plan = contract.load(scenario_dir(sc) / "plan.json")
        controls = "<br>".join(
            f"`{k}` {fmt(c['min'])}…{fmt(c['max'])} {'rad' if c['unit'] == 'radian' else 'LDU'}: {c['description']}"
            for k, c in sc["controls"].items())
        joints = "<br>".join(f"{name}: {b['kind']} axis {b['axis']} through {b['origin']}"
                             + (f" (parent {b['parent']})" if b.get("parent") else "")
                             for name, b in plan["bodies"].items())
        lines.append(f"| **{sc['key']}** {sc['title']} | {sc['element']} ({len(info['parts'])} parts) | {controls} | "
                     f"{joints} |")
    lines += [
        "",
        "## Clips",
        "",
        "| Clip (Action) | Window / NLA track | Styles | Loop | What it does |",
        "| --- | --- | --- | --- | --- |",
    ]
    for d in docs:
        loop = f"{d['loop_range'][0]}–{d['loop_range'][1]}" if d["loop_range"] else "—"
        lines.append(f"| `{d['id']}` | {d['window']} `{d['blender']['nla_track']}` | "
                     f"{', '.join(d['styles'])} | {loop} | {d['description']} |")
    lines += ["", "## Style index", "", "| Style | Meaning | Clips |", "| --- | --- | --- |"]
    for style, meaning in mv.STYLES.items():
        clips = [d["id"] for d in docs if style in d["styles"]]
        lines.append(f"| `{style}` | {meaning} | {', '.join(f'`{c}`' for c in clips) or '—'} |")
    lines += [
        "",
        "## Easing used by the clips",
        "",
        "Each key's interpolation applies to the segment that starts at it (Blender semantics). The Python "
        "evaluator `movable_clips.value_at` uses Blender's own easing equations, so the JSON values equal what "
        "Blender plays.",
        "",
        "| Key name | Blender interpolation / easing | Typical use |",
        "| --- | --- | --- |",
        "| `SINE_IN_OUT` | SINE / EASE_IN_OUT | smooth start and stop (default) |",
        "| `QUAD_IN` / `QUAD_OUT` | QUAD / EASE_IN, EASE_OUT | gravity fall; fast start, soft stop |",
        "| `CUBIC_IN_OUT` | CUBIC / EASE_IN_OUT | slow, motorised moves |",
        "| `LINEAR` | LINEAR | winches, motors, constant spins |",
        "| `CONSTANT` | CONSTANT | holds (the value stays until the next key) |",
        "| `BOUNCE_OUT` | BOUNCE / EASE_OUT | hitting a stop: falls, rebounds twice, settles |",
        "| `BACK_OUT` | BACK / EASE_OUT (back = 1.70158) | overshoot about 10 % past the target, settle back |",
        "",
        "## Clearance",
        "",
        "Sampled with `scripts/blender/check_movables_clearance.py` (every 4 frames of every clip, rest-contact "
        "pairs such as a hinge and its frame excluded). Depth = deepest vertex of one part inside the other. This "
        "is sampled evidence, not a proof of collision-free motion.",
        "",
        "| Scenario | Result | Pairs (worst vertex depth) |",
        "| --- | --- | --- |",
    ]
    for sc in scenarios:
        c = clearance.get(sc["key"])
        if not c:
            lines.append(f"| {sc['key']} | not run | — |")
            continue
        pairs = {}
        for clip, v in c.get("vertex_penetration", {}).items():
            for pair, m in v.items():
                pairs[pair] = max(pairs.get(pair, 0.0), m["max_vertex_depth_ldu"])
        text = ", ".join(f"{p} ({d:.2f} LDU)" for p, d in sorted(pairs.items())) or "—"
        lines.append(f"| {sc['key']} | {c.get('worst_kind', '?')} | {text} |")
    lines += [
        "",
        "## Reusing a clip",
        "",
        "- **Data only:** `clips/<id>.json` holds the sparse keys (frame, value, Blender interpolation and easing), "
        "the value baked at every frame, and each channel's unit, range and meaning.",
        "- **Blender:** every clip is an Action with one slot (`movable_controller`) keyed on the controller's "
        "custom properties (`[\"door\"]`, `[\"lift\"]` …). It plays on any controller with the same property names "
        "and meanings:",
        "",
        "```python",
        "import bpy",
        "src = '/abs/path/output/movables/movables.blend'",
        "with bpy.data.libraries.load(src, link=False) as (data_from, data_to):",
        "    data_to.actions = ['S10_car_doors.both_doors']",
        "action = data_to.actions[0]",
        "ctrl = bpy.data.objects['CTRL_movable_06_double_cabinet']  # any controller with door_l / door_r",
        "ad = ctrl.animation_data_create()",
        "track = ad.nla_tracks.new()",
        "strip = track.strips.new(action.name, 1, action)",
        "strip.action_slot = action.slots[0]",
        "```",
        "",
        "- **Whole scenario:** append the collection `Sxx_key Title` (it holds the model, its rig collection, the "
        "controller with its NLA tracks and the SLOT_ empty); the Actions come along through the NLA strips.",
        "- **On a new model:** rig the element with the same joint (axis and origin from the same connector pair, "
        "see the table and `Sxx_*/plan.json`), give the control the same name, unit and sign, and the clip values "
        "apply unchanged. Remeasure the target; check ranges against its own surroundings.",
    ]
    return "\n".join(lines) + "\n"


def cmd_catalog():
    docs = mv.export(OUT)
    clearance = clearance_summary()
    scenarios = []
    for sc in mv.SCENARIOS:
        info = json.loads((scenario_dir(sc) / "source/parts.json").read_text())
        plan = contract.load(scenario_dir(sc) / "plan.json")
        scenarios.append(dict(
            scenario=sc["key"], title=sc["title"], element=sc["element"], plan=sc["plan"],
            controller=f"CTRL_{sc['plan']}", collection=f"{sc['key']} {sc['title']}",
            scene=f"{sc['key'][:3]} {sc['title']}", controls=sc["controls"], parts=info["parts"],
            reference_checks=info["reference_checks"],
            bodies={b: dict(kind=v["kind"], origin=v["origin"], axis=v["axis"], parent=v.get("parent"),
                            signal=v["signal"], instances=v["instances"]) for b, v in plan["bodies"].items()},
            signals=plan["signals"], clips=[d["id"] for d in docs if d["scenario"] == sc["key"]],
            clearance=clearance.get(sc["key"], {}).get("worst_kind")))
    contract.save(OUT / "catalog.json", dict(
        conventions=mv.conventions(), scenarios=scenarios,
        clips=[{k: d[k] for k in ("id", "scenario", "clip", "title", "description", "styles", "window",
                                  "timeline_start", "frames", "loop_range", "blender")} for d in docs],
        clearance=clearance))
    (OUT / "CATALOG.md").write_text(catalog_markdown(docs, mv.SCENARIOS, clearance))
    print(json.dumps(dict(clips=len(docs), catalog=str(OUT / "catalog.json"))))


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="command", required=True)
    p = sub.add_parser("mpd")
    p.add_argument("--only", nargs="*")
    p = sub.add_parser("plan")
    p.add_argument("--ready", action="store_true")
    p.add_argument("--only", nargs="*")
    sub.add_parser("catalog")
    args = ap.parse_args()
    if args.command == "mpd":
        cmd_mpd(args.only)
    elif args.command == "plan":
        cmd_plan(args.ready, args.only)
    else:
        cmd_catalog()


if __name__ == "__main__":
    main()
