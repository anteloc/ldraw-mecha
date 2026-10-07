"""Build ten minifigs from data/categories/parts/minifig, author their joint plans and export the clip catalog.

    .venv/bin/python scripts/build_minifigs.py mpd               # output/minifigs/MFxx_*/source/minifig.mpd
    ./ldraw-mecha prepare output/minifigs/MFxx_*/source/minifig.mpd --output output/minifigs/MFxx_*/study
    .venv/bin/python scripts/build_minifigs.py plan [--ready]    # output/minifigs/MFxx_*/plan.json
    .venv/bin/python scripts/build_minifigs.py catalog           # clips/*.json, catalog.json, CATALOG.md

Parts are picked by constant name in the vendored part tables (data/categories/parts/minifig/*.py, plain
`Name = "id"` lines, parsed here because that package needs py4bricks). Placements are composed from LDCad
shadow connector frames read through pyldraw3 (data/offLibShadow): torso shoulder sockets, neck pin and hip
holes; hip leg pins; arm hand sockets; hand clip; item bars; foot holes. Joint axes and origins come from the
same frames; their signs are chosen so that each control means the same thing on both sides, and that meaning is
checked with the portable evaluator.
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
from ldraw_mechanisms.source import jsonable, library_path, parts_library  # noqa: E402
import minifig_clips as clips  # noqa: E402

TABLES = ROOT / "data/categories/parts/minifig"
OUT = clips.OUT
REFERENCE = ROOT / "data/models-annotated/6682-1.mpd"  # official minifig placement used as a cross-check

# Parts shared by every figure (table constant names).
HIPS = "accessories.Hips"
LEG_L, LEG_R = "legs.LegLeft", "legs.LegRight"
ARM_L, ARM_R = "arms.ArmLeft", "arms.ArmRight"
HAND = "hands.Hand"

# Hand items: which connector is gripped (kind + index among that kind), where along it the hand clip sits
# (`grip`, LDU from the connector position along its axis), and which way the working end points
# (`work`: +1 along the connector axis, -1 against it; it is turned to the hand clip's forward direction).
# `spin` rolls the item about the bar (degrees). Working ends were read from the part geometry beyond the bar.
ITEMS = {
    "accessories.SwordShortsword": dict(kind="bar", grip=8.0, work=-1, spin=90),
    "accessories.ShieldTriangularWithBlackFalconBlueBorderPattern": dict(kind="pin", index=0, grip=5.0, work=-1,
                                                                         spin=0),
    "accessories.ToolHammer": dict(kind="bar", grip=8.0, work=1, spin=90),
    # Ladle reversed: the bowl hangs below the fist when the arm is raised forward ~1.05 rad (stirring).
    "accessories.Ladle": dict(kind="bar", grip=15.0, work=1, spin=0),
    # Frypan spin: with shoulder_l=0.45, wrist_l=-1.31 the pan lies level across the belly, opening up
    # (searched with the evaluator; see minifig_clips.PAN_LEVEL).
    "accessories.Frypan": dict(kind="bar", grip=9.0, work=-1, spin=285),
    "accessories.SwordCutlass": dict(kind="bar", grip=0.0, work=1, spin=90),
    "accessories.ToolHoseNozzleWithHandle": dict(kind="pin", index=0, grip=9.0, work=-1, spin=0),
    "accessories.StaffWithSphericalEnd": dict(kind="bar", grip=7.0, work=-1, spin=0),
    "accessories.RadioWithLongHandle": dict(kind="bar", grip=0.0, work=1, spin=0),
}

ROSTER = [
    dict(key="MF01_police", title="Police officer", plan="minifig_01_police",
         head=("heads.HeadWithBlack_SilverSunglasses_ChinDimpleAndGrimMouthPattern", 14),
         headgear=[("hats.PoliceHat", 0)],
         torso=("torsos.TorsoWithButtonsAndPoliceBadgePlainPattern", 0), arms=0, hands=14, hips=0, legs=1,
         left=("accessories.RadioWithLongHandle", 0), right=None, back=[], feet=None),
    dict(key="MF02_spaceman", title="Classic spaceman", plan="minifig_02_spaceman",
         head=("heads.HeadWithStandardGrinPattern_HollowStud_", 14),
         headgear=[("accessories.HelmetClassicWithThinChinGuardAndVisorDimples", 4)],
         torso=("torsos.TorsoWithClassicSpacePattern", 4), arms=4, hands=0, hips=4, legs=4,
         left=None, right=None, back=[("accessories.Airtanks", 71)], feet=None),
    dict(key="MF03_knight", title="Knight", plan="minifig_03_knight",
         head=("heads.HeadWithSternBlackEyebrows_WhitePupilsAndDarkOrangeChinDimplePattern", 14),
         headgear=[("accessories.HelmetCastleWithNeckProtector", 71)],
         torso=("torsos.TorsoWithCastleChainmailPattern", 71), arms=0, hands=0, hips=0, legs=72,
         left=("accessories.ShieldTriangularWithBlackFalconBlueBorderPattern", 15),
         right=("accessories.SwordShortsword", 71), back=[], feet=None),
    dict(key="MF04_builder", title="Construction worker", plan="minifig_04_builder",
         head=("heads.HeadWithBeardStubble_BlackRaisedRightEyebrowAndSmirkAngledToRightPattern", 14),
         headgear=[("accessories.ConstructionHelmet", 14)],
         torso=("torsos.TorsoWithConstructionSafetyVestWithReflectiveStripesPattern", 25), arms=25, hands=14,
         hips=1, legs=1, left=None, right=("accessories.ToolHammer", 72), back=[], feet=None),
    dict(key="MF05_chef", title="Chef", plan="minifig_05_chef",
         head=("heads.HeadWithBlackMoustacheAndEyebrows_NougatCheekLinesAndSmilePattern", 14),
         headgear=[("hats.Cook_SHat", 15)],
         torso=("torsos.TorsoWithChefPattern", 15), arms=15, hands=14, hips=0, legs=0,
         left=("accessories.Frypan", 0), right=("accessories.Ladle", 71), back=[], feet=None),
    dict(key="MF06_pirate", title="Pirate", plan="minifig_06_pirate",
         head=("heads.HeadWithDarkOrangeBeard_GoldTeethAndEyepatchPattern", 14),
         headgear=[("hats.HatBicorne", 0)],
         torso=("torsos.TorsoWithPirateStripesBlue_WhiteAndBlackBucklePattern", 15), arms=15, hands=14, hips=1,
         legs=1, left=None, right=("accessories.SwordCutlass", 72), back=[], feet=None),
    dict(key="MF07_firefighter", title="Firefighter", plan="minifig_07_firefighter",
         head=("heads.HeadWithDarkOrangeEyebrows_Goatee_MoustacheAndDarkBluishGreySootMarksPattern", 14),
         headgear=[("accessories.FireHelmetWithFireLogoShieldPattern", 4)],
         torso=("torsos.TorsoWithFireFighterFiveButtonPattern", 0), arms=0, hands=14, hips=0, legs=0,
         left=None, right=("accessories.ToolHoseNozzleWithHandle", 0), back=[], feet=None),
    dict(key="MF08_athlete", title="Athlete", plan="minifig_08_athlete",
         head=("heads.HeadWithBlackEyebrows_WhitePupils_ChinDimple_OpenMouthSmileWithTeethPattern", 14),
         headgear=[("accessories.HairMale", 70)],
         torso=("torsos.TorsoWithSoccerTeamRed_BlueStripesAndRed_10Pattern", 15), arms=15, hands=14, hips=1,
         legs=1, left=None, right=None, back=[], feet=None),
    dict(key="MF09_wizard", title="Wizard", plan="minifig_09_wizard",
         head=("heads.HeadWithGrin_BrownBeard_WhitePupilsPattern_HollowStud_", 14),
         headgear=[("hats.WizardsHat", 272)],
         torso=("torsos.TorsoWithDarkBluishGreyRobeGatherLines_WrinklesAndClaspAtRightShoulderPattern", 272),
         arms=272, hands=14, hips=272, legs=272, left=None, right=("accessories.StaffWithSphericalEnd", 70),
         back=[], feet=None),
    dict(key="MF10_diver", title="Diver", plan="minifig_10_diver",
         head=("heads.HeadWithBrownEyebrows_Freckles_OpenSmilePattern_HollowStud_", 14),
         headgear=[], torso=("torsos.TorsoWithDivingSuit_OrangeStripes_Belt_PressureGaugeAndBreathingHosePattern", 0),
         arms=0, hands=0, hips=0, legs=0, left=None, right=None, back=[("accessories.Airtanks", 14)],
         feet=("accessories.FlipperThin", 25)),
]


# --------------------------------------------------------------------------- part tables and library
def tables():
    out = {}
    for f in sorted(TABLES.glob("*.py")):
        for m in re.finditer(r'^([A-Za-z_][A-Za-z0-9_]*) = "([^"]+)"', f.read_text(), re.M):
            out[f"{f.stem}.{m.group(1)}"] = m.group(2)
    return out


TABLE = tables()


def part_id(name):
    if name not in TABLE:
        raise ValueError(f"{name} is not in {TABLES.relative_to(ROOT)}")
    return TABLE[name]


def library_title(ref):
    path = library_path() / "parts" / f"{ref}.dat"
    if not path.exists():
        raise ValueError(f"{ref}.dat is not in the LDraw library")
    title = path.read_text(encoding="utf-8-sig", errors="replace").splitlines()[0].removeprefix("0").strip()
    if title.startswith("~") or "Obsolete" in title or "Moved" in title:
        raise ValueError(f"{ref}.dat is obsolete or moved: {title}")
    return title


_PARTS = None


def connectors(ref):
    global _PARTS
    _PARTS = _PARTS or parts_library()
    out = []
    for f in _PARTS.connection_metadata(ref).features:
        j = jsonable(f)
        frame = np.array(j["frame"], dtype=float)
        profile = j.get("profile") or {}
        out.append(dict(kind=getattr(j["kind"], "value", str(j["kind"])),
                        role=getattr(j["role"], "value", str(j["role"])),
                        position=np.array(j["position"], dtype=float), axis=frame[:, 1].copy(),
                        length=sum(s["length"] for s in profile.get("sections", [])),
                        centered=bool(profile.get("centered")), feature=j["feature_id"]))
    return out


def connector(ref, kind, *, role=None, near=None, index=0):
    found = [c for c in connectors(ref) if c["kind"] == kind and (role is None or c["role"] == role)]
    if near is not None:
        found.sort(key=lambda c: np.linalg.norm(c["position"] - np.array(near, float)))
    if len(found) <= index:
        raise ValueError(f"{ref}: no {kind} connector #{index}")
    return found[index]


# --------------------------------------------------------------------------- geometry
def pose(r=None, t=(0, 0, 0)):
    m = np.eye(4)
    if r is not None:
        m[:3, :3] = r
    m[:3, 3] = t
    return m


def arc(a, b):
    """Shortest rotation taking unit vector a onto unit vector b."""
    a, b = a / np.linalg.norm(a), b / np.linalg.norm(b)
    v, c = np.cross(a, b), float(np.dot(a, b))
    if np.linalg.norm(v) < 1e-12:
        if c > 0:
            return np.eye(3)
        p = np.array([1.0, 0, 0]) if abs(a[0]) < 0.9 else np.array([0, 1.0, 0])
        v = np.cross(a, p)
        v /= np.linalg.norm(v)
        return 2 * np.outer(v, v) - np.eye(3)
    k = np.array([[0, -v[2], v[1]], [v[2], 0, -v[0]], [-v[1], v[0], 0]])
    return np.eye(3) + k + k @ k / (1 + c)


def rotation(axis, angle):
    x, y, z = np.asarray(axis, float) / np.linalg.norm(axis)
    c, s, t = math.cos(angle), math.sin(angle), 1 - math.cos(angle)
    return np.array([[t * x * x + c, t * x * y - s * z, t * x * z + s * y],
                     [t * x * y + s * z, t * y * y + c, t * y * z - s * x],
                     [t * x * z - s * y, t * y * z + s * x, t * z * z + c]])


def world_point(m, p):
    return (m @ np.append(np.asarray(p, float), 1.0))[:3]


def world_dir(m, d):
    return m[:3, :3] @ np.asarray(d, float)


def mate(parent, female, male):
    """Placement of a part whose male connector `male` (part-local) enters `female` (parent-local).

    The shortest rotation is taken in the parent's frame, so the free roll about the joint axis keeps the
    parent's orientation (the official arm/hand rest pose)."""
    r = arc(male["axis"], female["axis"])
    return parent @ pose(r, female["position"] - r @ male["position"])


def place_item(hand, item_ref, spec):
    clip = connector("3820", "clip")
    bar = connector(item_ref, spec["kind"], index=spec.get("index", 0))
    # Hand clip forward: the clip axis direction that points forward (-Z) with the arm at rest (checked below).
    forward = clip["axis"]
    work = spec["work"] * bar["axis"]
    r = arc(work, forward)
    # Roll about the bar: item local X (projected) goes to the hand's X, then `spin` about the bar.
    x_item = r @ np.array([1.0, 0, 0])
    x_item -= forward * np.dot(x_item, forward)
    x_hand = np.array([1.0, 0, 0]) - forward * np.dot([1.0, 0, 0], forward)
    if np.linalg.norm(x_item) > 1e-9 and np.linalg.norm(x_hand) > 1e-9:
        x_item, x_hand = x_item / np.linalg.norm(x_item), x_hand / np.linalg.norm(x_hand)
        ang = math.atan2(np.dot(np.cross(x_item, x_hand), forward), np.dot(x_item, x_hand))
        r = rotation(forward, ang) @ r
    r = rotation(forward, math.radians(spec.get("spin", 0))) @ r
    grip = bar["position"] + bar["axis"] * spec["grip"]
    local = pose(r, clip["position"] - r @ grip)
    return hand @ local


def assemble(fig):
    """Return [(role, table name, ref, colour, 4x4 world)] in MPD order, plus measured joint evidence."""
    torso_ref = part_id(fig["torso"][0])
    parts = []

    def add(role, name, ref, colour, m):
        library_title(ref)
        parts.append(dict(role=role, table=name, ref=ref, colour=colour, matrix=m))
        return m

    torso = add("torso", fig["torso"][0], torso_ref, fig["torso"][1], pose())
    neck = connector(torso_ref, "pin", near=(0, 0, 0))
    head_ref = part_id(fig["head"][0])
    head = add("head", fig["head"][0], head_ref, fig["head"][1],
               mate(torso, neck, connector(head_ref, "pin_hole", near=(0, 24, 0))))
    for k, (name, colour) in enumerate(fig["headgear"]):
        add(f"headgear{k}", name, part_id(name), colour, head)  # headgear origin = head top stud (LDraw convention)
    hips_ref = part_id(HIPS)
    hip_hole = connector(torso_ref, "pin_hole", near=(10, 32, 0))
    hips = add("hips", HIPS, hips_ref, fig["hips"],
               mate(torso, hip_hole, connector(hips_ref, "pin", near=(10, 0, 0))))
    evidence = {}
    legs = {}
    for side, name, x in (("l", LEG_L, 2), ("r", LEG_R, -2)):
        ref = part_id(name)
        pin = connector(hips_ref, "pin", near=(x, 12, 0))
        hole = connector(ref, "pin_hole", near=(x, 0, 0))
        legs[side] = add(f"leg_{side}", name, ref, fig["legs"], mate(hips, pin, hole))
        evidence[f"hip_{side}"] = dict(origin=world_point(hips, pin["position"]), axis=world_dir(hips, pin["axis"]),
                                       parent="hips", connector=(pin["feature"], hole["feature"]))
    arms, hands = {}, {}
    for side, name, x in (("l", ARM_L, 15.552), ("r", ARM_R, -15.552)):
        ref = part_id(name)
        socket = connector(torso_ref, "pin_hole", near=(x, 9, 0))
        pin = connector(ref, "pin", near=(0, 0, 0))
        arms[side] = add(f"arm_{side}", name, ref, fig["arms"], mate(torso, socket, pin))
        evidence[f"shoulder_{side}"] = dict(origin=world_point(torso, socket["position"]),
                                            axis=world_dir(torso, socket["axis"]), parent="torso",
                                            connector=(socket["feature"], pin["feature"]))
        wrist = connector(ref, "pin_hole")
        hand_pin = connector("3820", "pin", near=(0, 0, 0))
        hands[side] = add(f"hand_{side}", HAND, part_id(HAND), fig["hands"], mate(arms[side], wrist, hand_pin))
        evidence[f"wrist_{side}"] = dict(origin=world_point(arms[side], wrist["position"]),
                                         axis=world_dir(arms[side], wrist["axis"]), parent=f"arm_{side}",
                                         connector=(wrist["feature"], hand_pin["feature"]))
        item = fig["left" if side == "l" else "right"]
        if item:
            name_i, colour = item
            add(f"item_{side}", name_i, part_id(name_i), colour, place_item(hands[side], part_id(name_i),
                                                                             ITEMS[name_i]))
    for k, (name, colour) in enumerate(fig["back"]):
        ref = part_id(name)
        add(f"back{k}", name, ref, colour, mate(torso, neck, connector(ref, "pin_hole", near=(0, 0, 0))))
    if fig["feet"]:
        name, colour = fig["feet"]
        ref = part_id(name)
        for side in ("l", "r"):
            leg_ref = part_id(LEG_L if side == "l" else LEG_R)
            hole = connector(leg_ref, "pin_hole", near=(10 if side == "l" else -10, 28, 0))
            add(f"foot_{side}", name, ref, colour, mate(legs[side], hole, connector(ref, "stud")))
    evidence["neck"] = dict(origin=world_point(torso, neck["position"]), axis=world_dir(torso, neck["axis"]),
                            parent="torso", connector=(neck["feature"], "head pin_hole"))
    return parts, evidence


def number(v):
    s = f"{0.0 if abs(v) < 1e-9 else v:.10g}"
    return "0" if s in ("-0", "0") else s


def write_mpd(fig, parts, path):
    name = f"{fig['key'].lower()}.ldr"
    lines = [
        f"0 FILE {name}",
        f"0 Minifig {fig['key']} {fig['title']}",
        f"0 Name: {name}",
        "0 Author: ldraw-mecha scripts/build_minifigs.py",
        "0 // Generated minifig: parts picked by constant name from data/categories/parts/minifig; placements "
        "composed from LDCad shadow connector frames (data/offLibShadow) read through pyldraw3. Frame: torso "
        "origin at the neck, -Y up, the face looks along -Z, the figure's left is +X; feet at y=+72.",
        "",
    ]
    for p in parts:
        m = p["matrix"]
        values = [m[0, 3], m[1, 3], m[2, 3], *m[0, :3], *m[1, :3], *m[2, :3]]
        lines.append(f"0 // {p['role']}: {p['table']}")
        lines.append(f"1 {p['colour']} " + " ".join(number(v) for v in values) + f" {p['ref']}.dat")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n")


def reference_placement():
    """Torso-relative placements of the official 6682 minifig (y offset of its torso removed)."""
    text = REFERENCE.read_text(encoding="utf-8-sig", errors="replace").splitlines()
    rows = {}
    inside = False
    for line in text:
        if line.startswith("0 FILE"):
            inside = "minifig" in line.lower()
        t = line.split()
        if inside and len(t) >= 15 and t[0] == "1":
            rows.setdefault(t[14].lower().removesuffix(".dat"), []).append(
                (np.array([float(v) for v in t[2:5]]), np.array([float(v) for v in t[5:14]]).reshape(3, 3)))
    torso = rows[next(k for k in rows if k.startswith("973"))][0][0]
    return {k: [(p - torso, r) for p, r in v] for k, v in rows.items()}


def compare_reference(parts):
    ref = reference_placement()
    report = {}
    for role, key, pick in (("arm_l", "3819", 0), ("arm_r", "3818", 0), ("hips", "3815", 0), ("leg_l", "3817", 0),
                            ("leg_r", "3816", 0), ("hand_l", "3820", 0), ("hand_r", "3820", 1)):
        mine = next(p for p in parts if p["role"] == role)["matrix"]
        candidates = ref[key]
        if key == "3820":
            candidates = sorted(candidates, key=lambda c: -c[0][0])  # +X (left) first
        p, r = candidates[pick]
        report[role] = dict(position_offset=round(float(np.linalg.norm(mine[:3, 3] - p)), 3),
                            rotation_offset=round(float(np.abs(mine[:3, :3] - r).max()), 3))
    return report


# --------------------------------------------------------------------------- plan authoring
def r6(v):
    return [round(float(x), 6) for x in v]


def author_plan(fig, study, roles, evidence):
    plan = copy.deepcopy(study)
    plan["name"] = fig["plan"]
    plan["status"] = "draft"
    ids = {r["role"]: r["id"] for r in roles}

    def members(*names):
        return sorted({ids[n] for n in names if n in ids}, key=lambda s: [int(x) for x in s.split("/")])

    head_parts = ["head"] + [r for r in ids if r.startswith("headgear")]
    bodies = {
        "head": dict(instances=members(*head_parts), kind="revolute", signal="neck_angle"),
        "arm_l": dict(instances=members("arm_l"), kind="revolute", signal="shoulder_l_angle"),
        "hand_l": dict(instances=members("hand_l", "item_l"), kind="revolute", signal="wrist_l_angle",
                       parent="arm_l"),
        "arm_r": dict(instances=members("arm_r"), kind="revolute", signal="shoulder_r_angle"),
        "hand_r": dict(instances=members("hand_r", "item_r"), kind="revolute", signal="wrist_r_angle",
                       parent="arm_r"),
        "leg_l": dict(instances=members("leg_l", "foot_l"), kind="revolute", signal="hip_l_angle"),
        "leg_r": dict(instances=members("leg_r", "foot_r"), kind="revolute", signal="hip_r_angle"),
    }
    joint_of = dict(head="neck", arm_l="shoulder_l", hand_l="wrist_l", arm_r="shoulder_r", hand_r="wrist_r",
                    leg_l="hip_l", leg_r="hip_r")
    for body, joint in joint_of.items():
        e = evidence[joint]
        bodies[body]["origin"] = r6(e["origin"])
        bodies[body]["axis"] = r6(e["axis"] / np.linalg.norm(e["axis"]))
    controls = {name: dict(default=0, min=j["min"], max=j["max"], unit="radian", description=j["description"])
                for name, j in clips.JOINTS.items()}
    signals = {f"{name}_angle": dict(expression="a", variables=dict(a=f"control:{name}")) for name in controls}
    plan.update(controls=controls, signals=signals, bodies=bodies, anchors={}, checks=[])
    # Semantic signs: flip any measured axis whose positive rotation does not mean what the control says.
    semantics = {}
    for body, joint in joint_of.items():
        for attempt in range(2):
            ok, detail = semantic_check(plan, fig, roles, body, joint)
            if ok:
                break
            bodies[body]["axis"] = [-v for v in bodies[body]["axis"]]
        if not ok:
            raise ValueError(f"{fig['key']}: {joint} sign check failed: {detail}")
        semantics[joint] = dict(detail, flipped=attempt == 1)
    return plan, semantics


def semantic_check(plan, fig, roles, body, joint):
    """Positive control moves a test point the way the control description says."""
    nodes = {n["id"]: n for n in plan["source"]["nodes"]}
    ids = {r["role"]: r["id"] for r in roles}
    world = lambda role: np.array(nodes[ids[role]]["world"], float)  # noqa: E731
    if joint == "neck":
        point, test = world_point(world("head"), (0, 12, -13)), lambda d: d[0] > 0  # nose to the left (+X)
    elif joint.startswith("shoulder"):
        side = joint[-1]
        point, test = world_point(world(f"hand_{side}"), (0, 0, 0)), lambda d: d[2] < 0  # hand forward
    elif joint.startswith("wrist"):
        side = joint[-1]
        clip = connector("3820", "clip")
        tip = clip["position"] + clip["axis"] * 20.0
        point = world_point(world(f"hand_{side}"), tip)
        out_sign = 1 if side == "l" else -1
        test = lambda d: d[0] * out_sign > 0  # noqa: E731  item tip rolls outward
    else:
        side = joint[-1]
        point, test = world_point(world(f"leg_{side}"), (0, 28, 0)), lambda d: d[2] < 0  # foot forward
    result = contract.evaluate(plan, {joint: 0.3})
    moved = world_point(np.array(result["transforms"][body], float), point)
    d = moved - point
    return bool(test(d)), dict(test_point=r6(point), displacement_at_0_3=r6(d))


def connections(fig, roles, evidence, contacts):
    """Reviewed evidence edges; `contacts` are pyldraw3-confirmed occurrence pairs {(a, b): [kinds]}."""
    ids = {r["role"]: r["id"] for r in roles}
    out = {}

    def edge(cid, a, b, kind, text, measurements=None):
        if a in ids and b in ids:
            pair = tuple(sorted((ids[a], ids[b]), key=int))
            found = contacts.get(pair)
            check = (f"pyldraw3 contact confirmed ({', '.join(sorted(set(found)))})" if found else
                     "not detected by pyldraw3 contacts (connector kinds do not pair); placement composed from the "
                     "named frames")
            out[cid] = dict(a=ids[a], b=ids[b], kind=kind, status="reviewed", evidence=f"{text}. {check}.",
                            measurements=measurements or {},
                            review="Measured from LDCad shadow connector frames; placement composed so the frames "
                                   "coincide (scripts/build_minifigs.py).")

    for joint, (a, b) in dict(neck=("torso", "head"), shoulder_l=("torso", "arm_l"), shoulder_r=("torso", "arm_r"),
                              wrist_l=("arm_l", "hand_l"), wrist_r=("arm_r", "hand_r"), hip_l=("hips", "leg_l"),
                              hip_r=("hips", "leg_r")).items():
        e = evidence[joint]
        edge(f"joint_{joint}", a, b, "revolute", f"{joint}: {e['connector'][0]} receives {e['connector'][1]}",
             dict(origin=r6(e["origin"]), axis=r6(e["axis"] / np.linalg.norm(e["axis"]))))
    edge("fixed_hips", "torso", "hips", "fixed", "Hip pins in the torso's bottom holes (s/973s01, s/3815bs01)")
    for role in ids:
        if role.startswith("headgear"):
            edge(f"fixed_{role}", "head", role, "fixed", "Headgear on the head's top stud (LDraw headgear origin)")
        if role.startswith("item_"):
            edge(f"fixed_{role}", f"hand_{role[-1]}", role, "fixed", "Item bar held in the hand clip (3820 snap_clp)")
        if role.startswith("back"):
            edge(f"fixed_{role}", "torso", role, "fixed", "Back item ring on the torso neck pin, under the head")
        if role.startswith("foot_"):
            edge(f"fixed_{role}", f"leg_{role[-1]}", role, "fixed", "Flipper stud in the foot hole")
    return out


def notes(fig):
    return [
        f"Generated minifig {fig['key']} ({fig['title']}) written by scripts/build_minifigs.py: parts picked by "
        "constant name from data/categories/parts/minifig, placements composed from LDCad shadow connector frames "
        "(data/offLibShadow via pyldraw3). Frame: torso origin at the neck, -Y up, face along -Z, figure's left "
        "+X, feet at y=+72.",
        "Seven revolute joints shared by every catalog figure: neck (head + headgear, vertical axis through the "
        "neck pin), shoulder_l/r (arm about the torso socket axis, tilted 9.79 deg), wrist_l/r (hand + held item "
        "about the arm socket axis, 45 deg; parent = arm), hip_l/r (leg about the hip pin axis through y=44).",
        "Sign convention by meaning (checked with the evaluator, kinematics.json): neck + = face turns to the "
        "figure's left; shoulder + = arm forward/up; wrist + = held item's tip rolls outward; hip + = leg "
        "forward (+pi/2 seated). Mirrored sides therefore have mirrored axes.",
        "Ranges: neck and wrists +/-pi, shoulders +/-4pi (free spin for arm circles/swimming), hips +/-pi/2. The "
        "real joints turn freely; these ranges are catalog choices, not measured stops.",
        "Torso, hips and back items are static. Whole-figure motion in the animation (move_forward, move_left, "
        "move_up, turn, pitch, roll on the controller, pivot = hip-axis centre (0,44,0)) is staging, not a "
        "mechanism: it parents the model root and is not part of this plan.",
        "Kinematic and transform checks do not prove collision-free or physically feasible motion; ground and "
        "prop contact in the clips are not simulated.",
    ]


def mechanism_views(roles):
    ids = {r["role"]: r["id"] for r in roles}
    views = {}
    for joint, body, label, support in (
            ("neck", "head", "Neck: head and headgear yaw", "torso"),
            ("shoulder_l", "arm_l", "Left shoulder", "torso"), ("shoulder_r", "arm_r", "Right shoulder", "torso"),
            ("wrist_l", "hand_l", "Left wrist (hand and held item)", "arm_l"),
            ("wrist_r", "hand_r", "Right wrist (hand and held item)", "arm_r"),
            ("hip_l", "leg_l", "Left hip", "hips"), ("hip_r", "leg_r", "Right hip", "hips")):
        views[joint] = dict(label=label, parts=[ids[support]], bodies=[body], inputs=[f"control:{joint}"],
                            outputs=[f"body:{body}"], disposition="planned",
                            notes=[f"Axis and origin from the {joint} connector pair; see connections.joint_{joint}."],
                            review="Measured revolute joint declared in this plan (scripts/build_minifigs.py).")
    core = [ids[r] for r in ids if r in ("torso", "hips") or r.startswith("back")]
    views["core"] = dict(label="Torso, hips and back items (static)", parts=sorted(core, key=int), bodies=[],
                         inputs=[], outputs=[], disposition="static", notes=[],
                         review="Rigid core: the hips are clutch-fixed to the torso and back items sit on the neck "
                                "pin; nothing in a minifig moves them relative to the torso.")
    return views


# --------------------------------------------------------------------------- commands
def figure_dir(fig):
    return OUT / fig["key"]


def cmd_mpd():
    summary = []
    for fig in ROSTER:
        parts, evidence = assemble(fig)
        d = figure_dir(fig)
        write_mpd(fig, parts, d / "source/minifig.mpd")
        roles = [dict(role=p["role"], id=str(k), table=p["table"], ref=p["ref"], colour=p["colour"],
                      title=library_title(p["ref"])) for k, p in enumerate(parts)]
        reference = compare_reference(parts)
        ev = {k: dict(origin=r6(v["origin"]), axis=r6(v["axis"]), parent=v["parent"], connector=list(v["connector"]))
              for k, v in evidence.items()}
        contract.save(d / "source/parts.json", dict(figure=fig["key"], title=fig["title"], parts=roles, joints=ev,
                                                    reference_6682=reference))
        summary.append(dict(figure=fig["key"], parts=len(parts),
                            worst_reference=max(v["position_offset"] for v in reference.values())))
    print(json.dumps(summary, indent=1))


def cmd_plan(ready):
    out = []
    for fig in ROSTER:
        d = figure_dir(fig)
        study = contract.load(d / "study/plan.json")
        info = json.loads((d / "source/parts.json").read_text())
        nodes = {n["id"]: n for n in study["source"]["nodes"]}
        for r in info["parts"]:
            if nodes[r["id"]]["ref"].lower().removesuffix(".dat") != r["ref"].lower():
                raise ValueError(f"{fig['key']}: occurrence {r['id']} is not {r['ref']}")
        evidence = {k: dict(v, origin=np.array(v["origin"]), axis=np.array(v["axis"])) for k, v in
                    info["joints"].items()}
        plan, semantics = author_plan(fig, study, info["parts"], evidence)
        found = analysis.contacts(study["source"], [r["id"] for r in info["parts"]])
        pairs = {}
        for c in found["contacts"]:
            if c["status"] == "confirmed":
                kinds = "/".join(getattr(c[k]["kind"], "value", str(c[k]["kind"])) for k in ("first", "second"))
                pairs.setdefault(tuple(sorted((c["a"], c["b"]), key=int)), []).append(kinds)
        plan["connections"] = connections(fig, info["parts"], evidence, pairs)
        missing_joints = [j for j in clips.JOINTS if "pyldraw3 contact confirmed" not in
                          plan["connections"][f"joint_{j}"]["evidence"]]
        plan["mechanisms"] = mechanism_views(info["parts"])
        plan["notes"] = notes(fig)
        contract.validate(plan)
        asym = dict(neck=0.8, shoulder_l=1.2, shoulder_r=-0.7, wrist_l=-0.4, wrist_r=0.9, hip_l=0.5, hip_r=-0.3)
        result = contract.evaluate(plan, asym)
        if ready:
            plan["status"] = "ready"
        contract.validate(plan)
        contract.save(d / "plan.json", plan)
        contract.save(d / "kinematics.json", dict(semantics=semantics, contacts=found["summary"],
                                                  contact_pairs={"-".join(k): v for k, v in pairs.items()},
                                                  asymmetric_sample=dict(
            controls=asym, transforms={k: [r6(row) for row in v] for k, v in result["transforms"].items()})))
        out.append(dict(figure=fig["key"], plan=plan["name"], status=plan["status"], bodies=len(plan["bodies"]),
                        moving=sum(len(b["instances"]) for b in plan["bodies"].values()),
                        flipped=[k for k, v in semantics.items() if v["flipped"]],
                        joints_without_contact=missing_joints,
                        undetected_fixed=[k for k, v in plan["connections"].items()
                                          if "not detected" in v["evidence"]]))
    print(json.dumps(out, indent=1))


def catalog_markdown(docs, figures):
    lines = [
        "# Minifig movement catalog",
        "",
        "Ten minifigs built from `data/categories/parts/minifig`, three movement clips each. Generated by "
        "`scripts/build_minifigs.py catalog` from `scripts/minifig_clips.py`; see `REPORT.md` for how they were "
        "built and checked.",
        "",
        "## Channels (identical on every figure)",
        "",
        "| Channel | Kind | Unit | Range | Meaning |",
        "| --- | --- | --- | --- | --- |",
    ]
    for name, j in clips.JOINTS.items():
        lines.append(f"| `{name}` | joint (plan control) | rad | {j['min']:.4g} … {j['max']:.4g} | {j['description']} |")
    for name, j in clips.FIGURE.items():
        unit = "LDU" if j["unit"] == "ldu" else "rad"
        lines.append(f"| `{name}` | whole figure (staging) | {unit} | {j['min']:.4g} … {j['max']:.4g} | "
                     f"{j['description']} |")
    lines += [
        "",
        "Figure frame: LDraw LDU, torso origin at the neck, −Y up, face along −Z, the figure's left is +X, feet at "
        "y = +72. Whole-figure channels rotate and move the figure about its hip-axis centre (0, 44, 0), "
        "28 LDU above the ground. Order: translate, then turn, then pitch, then roll.",
        "",
        "## Figures",
        "",
        "| Figure (collection) | Controller | Parts by role (LDraw IDs; table constants in `MFxx_*/source/parts.json`) |",
        "| --- | --- | --- |",
    ]
    for fig in figures:
        info = json.loads((figure_dir(fig) / "source/parts.json").read_text())
        parts = ", ".join(f"{p['role']} `{p['ref']}`" for p in info["parts"])
        lines.append(f"| {fig['key']} {fig['title']} | `CTRL_{fig['plan']}` | {parts} |")
    lines += [
        "",
        "## Clips",
        "",
        "All clips are 144 frames at 24 fps (6 s). Each figure plays its clips back to back in windows A (frames "
        "1–144), B (161–304) and C (321–464).",
        "",
        "| Clip (Action) | Window / NLA track | Loop range | What it does |",
        "| --- | --- | --- | --- |",
    ]
    for d in docs:
        loop = f"{d['loop_range'][0]}–{d['loop_range'][1]}" if d["loop_range"] else "—"
        lines.append(f"| `{d['id']}` | {d['window']} `{d['blender']['nla_track']}` | {loop} | {d['description']} |")
    lines += [
        "",
        "## Reusing a clip",
        "",
        "- **Data only:** `clips/<id>.json` has the sparse keys (frame, value, Blender interpolation and easing) "
        "and the value baked at every frame for each of the 13 channels.",
        "- **Blender:** every clip is an Action with one slot (`minifig_controller`) keyed on the controller's "
        "custom properties, so it plays on any minifig controller that has the same property names:",
        "",
        "```python",
        "import bpy",
        "with bpy.data.libraries.load('/abs/path/output/minifigs/minifigs.blend', link=False) as (src, dst):",
        "    dst.actions = ['MF03_knight.sword_slash']",
        "action = dst.actions[0]",
        "ctrl = bpy.data.objects['CTRL_minifig_05_chef']  # or any controller with the 13 properties",
        "ad = ctrl.animation_data_create()",
        "track = ad.nla_tracks.new()",
        "strip = track.strips.new(action.name, 1, action)",
        "strip.action_slot = action.slots[0]",
        "```",
        "",
        "Joint channels drive the plan's revolute bodies. The six whole-figure channels need the `MOVE_` empty "
        "and its drivers (see `scripts/blender/animate_minifigs.py`, `figure_mover`, and "
        "`minifig_clips.MOVE_DRIVERS`) or an equivalent transform on another rig.",
        "- **Another model's minifig:** rig its seven joints with the same meanings (axes and origins from the "
        "same connector pairs, signs fixed by the tests in `author_plan`/`semantic_check`), name the controls as "
        "above, and the clip values apply unchanged. Clip keys are in radians/LDU in the figure's own frame.",
    ]
    matrix = compatibility()
    if matrix:
        keys = [f["key"] for f in figures]
        lines += [
            "",
            "## Joint clearance of every clip on every figure",
            "",
            "Sampled every 6 frames with `scripts/blender/check_minifigs_clearance.py --all-clips` (joint channels "
            "only; rest contacts and same-body pairs excluded). ✓ no new mesh crossing; ~ shallow crossing only "
            "(gone at 1.5 LDU shrink, i.e. under about 3 LDU); ✗ deeper crossing. Held items and wide headgear "
            "decide most results; the three clips that swing arms overhead (`wave`, `high_jump`, `swim_crawl`) brush "
            "the head on every figure while passing about 2.1–2.9 rad.",
            "",
            "| Clip | " + " | ".join(k.split("_")[0] for k in keys) + " |",
            "| --- | " + " | ".join("---" for _ in keys) + " |",
        ]
        for d in docs:
            row = matrix.get(d["id"], {})
            lines.append(f"| `{d['id']}` | " + " | ".join(dict(clear="✓", contact="~", deep="✗").get(row.get(k), "?")
                                                         for k in keys) + " |")
    return "\n".join(lines) + "\n"


def compatibility():
    """{clip: {figure: clear|contact|deep}} from the all-clips clearance run, if it exists."""
    path = OUT / "clearance-summary-all-clips.json"
    if not path.exists():
        return {}
    figures = json.loads(path.read_text())["figures"]
    out = {}
    for c in clips.library():
        for fig, v in figures.items():
            state = ("deep" if c.id in v["clips_with_deep_crossings"] else
                     "contact" if c.id in v["clips_with_crossings"] else "clear")
            out.setdefault(c.id, {})[fig] = state
    return out


def cmd_catalog():
    docs = clips.export(OUT)
    figures = []
    for fig in ROSTER:
        info = json.loads((figure_dir(fig) / "source/parts.json").read_text())
        plan = contract.load(figure_dir(fig) / "plan.json")
        figures.append(dict(figure=fig["key"], title=fig["title"], plan=fig["plan"], controller=f"CTRL_{fig['plan']}",
                            collection=f"{fig['key']} {fig['title']}", parts=info["parts"],
                            joints={b: dict(origin=v["origin"], axis=v["axis"], parent=v.get("parent"),
                                            instances=v["instances"])
                                    for b, v in plan["bodies"].items()},
                            clips=[d["id"] for d in docs if d["figure"] == fig["key"]]))
    contract.save(OUT / "catalog.json", dict(conventions=clips.conventions(), figures=figures,
                                             clips=[{k: d[k] for k in ("id", "figure", "clip", "title", "description",
                                                                      "window", "timeline_start", "frames",
                                                                      "loop_range", "blender")} for d in docs],
                                             joint_clearance=compatibility()))
    (OUT / "CATALOG.md").write_text(catalog_markdown(docs, ROSTER))
    print(json.dumps(dict(clips=len(docs), catalog=str(OUT / "catalog.json"))))


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="command", required=True)
    sub.add_parser("mpd")
    p = sub.add_parser("plan")
    p.add_argument("--ready", action="store_true")
    sub.add_parser("catalog")
    args = ap.parse_args()
    if args.command == "mpd":
        cmd_mpd()
    elif args.command == "plan":
        cmd_plan(args.ready)
    else:
        cmd_catalog()


if __name__ == "__main__":
    main()
