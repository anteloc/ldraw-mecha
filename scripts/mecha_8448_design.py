"""Layout of the 8448 mecha: which car occurrences go where (single source of geometry decisions).

Robot frame: LDraw units, -Y up, the robot faces -Z, its left is +X. The layout is built top-down from the
pelvis (the car's rear suspension); `build` finally translates everything so the foot soles stand on y = 0.
Part-local facts used below (from the LDraw library files):
- 3703 Technic brick 1x16: origin top centre, length along local X, holes along local Z at x = -140..140 step 20,
  y = 10.  3894 (1x6): holes at x = -40..40.  3738 technic plate 2x8: length along local X, studs at x = -70..70.
- 2780 friction pin, 4519 axle 3: centred, axis local X.  32123a half bush: axis local Z.
"""

from __future__ import annotations

import numpy as np

from build_mecha_8448 import basis, rot, trans

# Car -> robot for the standing drivetrain: car front (-Z) up, car up (-Y) forward, car X mirrored.
CORE_R = np.array([[-1, 0, 0, 0], [0, 0, 1, 0], [0, 1, 0, 0], [0, 0, 0, 1]], float)

STOCK = ("0/0/0",)  # the car's ladder chassis (box1) is dismantled first for skeleton stock

# Torso: the car's front suspension + V8 + gearbox, joined in the car by 1x8 plates and the engine output axles.
STEERING = ["0/0/18", "0/0/19/34", "0/0/19/35", "0/0/19/36", "0/0/20"]
# The engine reaches the plates only through the car chassis (box1): per side an axle pin, cross block, axle 3
# with stud and the 1x10 technic brick under the plate. Those eight box1 parts stay in their car places.
ENGINE_MOUNT = ["0/0/0/121", "0/0/0/122", "0/0/0/119", "0/0/0/120", "0/0/0/105", "0/0/0/106", "0/0/0/77", "0/0/0/78"]
TORSO = ["0/0/19", "0/0/64", "0/0/65", "0/0/66", "0/0/29", "0/0/30", "0/0/24", "0/0/25", "0/0/26",
         "0/0/39", "0/0/40", "0/0/41", "0/0/42"] + ENGINE_MOUNT
GEARBOX = ["0/0/57", "0/0/58", "0/0/59", "0/0/63"]
WAIST_BRIDGE = ["0/0/57/38"]  # box4step18: the blue beams the engine output axles enter, with 3 long pins
PELVIS = ["0/0/1"]
# The rear differential and its drive shafts / U-joints leave the pelvis (stock); only the two hub axles stay.
DIFF = [f"0/0/1/30/{i}" for i in range(14)]

# Per side: robot sign, strut module (box8step5 / box8step2), its brick, seat module and the seat side liftarm
# that faces the shin, hip axle, car wheel set facing outwards on that side (rim, tyre, bush) and its upright.
LEGS = {
    "l": dict(s=1, strut="6", seat="0/1", seat_arm="0/1/7", seat_arm_x=170, hip_axle="0/0/1/30/14",
              wheel=["0/0/46", "0/0/47", "0/0/48"], upright_hole=(230, -30, 370)),
    "r": dict(s=-1, strut="1", seat="0/2", seat_arm="0/2/15", seat_arm_x=-150, hip_axle="0/0/1/30/15",
              wheel=["0/0/49", "0/0/50", "0/0/51"], upright_hole=(-230, -30, 370)),
}
SHIN_DOWN = basis(x=(0, 1, 0), y=(0, 0, 1))  # 1x16 brick hanging: length down, holes along +X, studs forward
FOOT = basis(x=(0, 0, 1), y=(0, 1, 0))  # brick/plate lengthwise front-back, studs up, holes along X


def leg(b, side, hip):
    L = LEGS[side]
    s = L["s"]
    sx = np.array([s, 1, 1])
    reg = f"leg_{side}"
    strut = L["strut"]
    # Thigh: the B-pillar strut hangs on the hip axle by its top brick hole, outboard of the hub upright.
    # Its four protruding pins (top pair into the old chassis, bottom pair) are returned to stock.
    hip_slot = np.array([250 * s, hip[1], hip[2]])
    T = b.mate(f"{strut}/4", (110 * s, -270, 240), hip_slot, (1, 0, 0), up_child=(0, -1, 0), up_world=(0, -1, 0))
    b.unit(f"thigh_{side}", [strut], T, region=reg, exclude=[f"{strut}/5", f"{strut}/6", f"{strut}/7", f"{strut}/9"])
    b.connector("32123a", 7, (270 * s, hip[1], hip[2]), (1, 0, 0), unit=f"thigh_{side}", role="hip retainer",
                local_axis="z", prefer=STOCK)
    knee = bm_point(T, (110 * s, -10, 240))
    # Shin: a 1x16 technic brick inboard of the strut, pinned at the knee; its top hole is the knee.
    shin_x = 230 * s
    shin = b.part("3703", 0, SHIN_DOWN, (-140, 10, 0), (shin_x, knee[1], knee[2]), unit=f"shin_{side}",
                  role="shin beam", prefer=STOCK)
    # Knee: a long pin through the strut brick, the shin brick and the seat side liftarm's top hole.
    b.connector("6558", 0, (230 * s, knee[1], knee[2]), (1, 0, 0), unit=f"shin_{side}", role="knee pin",
                prefer=STOCK)
    hole = lambda k: np.array([shin_x, knee[1] + 20 * k, knee[2]])  # noqa: E731
    # Seat as shin guard: its side liftarm pinned to shin holes 2 and 4, backrest vertical.
    arm_x = L["seat_arm_x"]
    Ts = b.mate(L["seat_arm"], (arm_x, -118, 136), hole(2) - (20 * s, 0, 0), (1, 0, 0),
                up_child=(0, -0.8, 0.6), up_world=(0, -1, 0))
    b.unit(f"guard_{side}", [L["seat"]], Ts, region=reg)
    for k in (2, 4):
        b.connector("2780", 0, hole(k) - (10 * s, 0, 0), (1, 0, 0), unit=f"shin_{side}", role="guard pin",
                    prefer=STOCK)
    # Calf wheel: the car wheel facing outwards on this side, 40 further out than on its car upright (the tyre is
    # 80 wide), on an axle 5 through shin hole 8 with two full bushes as spacers.
    up = np.array(L["upright_hole"], float)
    Tw = trans(*(hole(8) + (40 * s, 0, 0) - up))
    b.unit(f"calf_wheel_{side}", L["wheel"], Tw, region=reg)
    b.connector("32073", 0, hole(8) + (40 * s, 0, 0), (1, 0, 0), unit=f"calf_wheel_{side}", role="wheel axle",
                prefer=STOCK)
    for dx in (20, 40):
        b.connector("3713", 7, hole(8) + (dx * s, 0, 0), (1, 0, 0), unit=f"calf_wheel_{side}", role="spacer",
                    local_axis="z", prefer=STOCK)
    # Ankle and foot: 1x6 technic brick lengthwise, middle hole on the ankle, on a 2x8 technic plate sole.
    ankle = hole(14)
    foot_x = 210 * s
    b.part("3894", 0, FOOT, (0, 10, 0), (foot_x, ankle[1], ankle[2]), unit=f"foot_{side}", role="foot brick",
           prefer=STOCK)
    b.connector("2780", 0, (220 * s, ankle[1], ankle[2]), (1, 0, 0), unit=f"foot_{side}", role="ankle pin",
                prefer=STOCK)
    sole_top = ankle[1] + 14  # brick top = ankle - 10, height 24
    b.part("3738", 0, FOOT, (0, 0, 0), (200 * s, sole_top, ankle[2] - 20), unit=f"foot_{side}", role="sole",
           prefer=STOCK)
    return dict(knee=knee, ankle=ankle, sole=sole_top + 8)


# Arms hang from the car's front hub axles (axle 3 with stud through each steering knuckle). Robot +X is car -X.
ARMS = {
    "l": dict(s=1, hub_axle="0/0/41", wheel=["0/0/43", "0/0/44", "0/0/45"]),
    "r": dict(s=-1, hub_axle="0/0/42", wheel=["0/0/52", "0/0/53", "0/0/54"]),
}


def arm(b, side):
    A = ARMS[side]
    s = A["s"]
    reg = f"arm_{side}"
    sh = b.line(A["hub_axle"], (250 * s, -1000, 57))["mid"]
    sy, sz = sh[1], sh[2]
    # Upper arm: 1x12 technic brick on the hub axle outboard of the knuckle (round hole: shoulder pitch).
    b.part("3895", 0, SHIN_DOWN, (-100, 10, 0), (250 * s, sy, sz), unit=f"upper_arm_{side}", role="upper arm beam",
           prefer=STOCK)
    b.connector("32123a", 7, (265 * s, sy, sz), (1, 0, 0), unit=f"upper_arm_{side}", role="shoulder retainer",
                local_axis="z", prefer=STOCK)
    # Shoulder pad: the car's front wheel facing out on this side, on an axle 5 through upper-arm hole 2.
    w = np.array([250 * s, sy + 40, sz])
    Tw = trans(*(w + (40 * s, 0, 0) - np.array([230 * s, -30, -350])))
    b.unit(f"shoulder_wheel_{side}", A["wheel"], Tw, region=reg)
    b.connector("32073", 0, w + (40 * s, 0, 0), (1, 0, 0), unit=f"shoulder_wheel_{side}", role="wheel axle",
                prefer=STOCK)
    for dx in (20, 40):  # two 16-tooth gears (20 thick) fill the 40 between the arm brick and the rim hub
        b.connector("4019", 7, w + (dx * s, 0, 0), (1, 0, 0), unit=f"shoulder_wheel_{side}", role="gear spacer",
                    local_axis="z", prefer=STOCK)
    # Elbow: pin from upper-arm hole 10 into a 1x10 forearm brick outboard.
    ey = sy + 200
    b.connector("2780", 0, (260 * s, ey, sz), (1, 0, 0), unit=f"forearm_{side}", role="elbow pin", prefer=STOCK)
    b.part("2730", 0, SHIN_DOWN, (-80, 10, 0), (270 * s, ey, sz), unit=f"forearm_{side}", role="forearm beam",
           prefer=STOCK)
    # Hand: 2-blade rotor claw on an axle 3 through forearm hole 8 (free to spin), retained by a half bush.
    hy = ey + 160
    b.connector("4519", 0, (285 * s, hy, sz), (1, 0, 0), unit=f"hand_{side}", role="wrist axle", prefer=STOCK)
    b.part("32124", 7, basis(x=(0, 1, 0), y=(s, 0, 0)), (0, 0, 0), (282 * s, hy, sz), unit=f"hand_{side}",
           role="rotor claw", prefer=STOCK)
    b.connector("32123a", 7, (300 * s, hy, sz), (1, 0, 0), unit=f"hand_{side}", role="wrist retainer",
                local_axis="z", prefer=STOCK)
    return dict(shoulder=sh, elbow=(260 * s, ey, sz), wrist=(285 * s, hy, sz))


# Wing pack: the car's roof and gull-wing door superstructure (without the windscreen frame, box8step12), one
# connected group of 161 occurrences in the car, turned 180 degrees about Y so the open doors sweep back.
# The door-hinge blocks box8step9/10 and the small triangles box8step3/6 (+ three loose parts held only by them)
# stay in stock: turned around they would sit inside the torso. The remaining 115 stay one connected group.
# Also left out: two loose red bent liftarms with their axles (19-22), two blue beams (43, 48) and the columns'
# outer cross blocks (31/4, 32/4), which would sit inside the torso's engine-mount posts. 107 occurrences remain,
# still one connected group in the car.
WING_PACK = ["24", "31", "32", "44", "49", "51", "25", "26", "27", "28", "29", "30", "33", "34", "35", "36", "37",
             "38", "39", "40", "41", "42", "45", "46", "47", "50", "52"]
WING_PACK_EXCLUDE = ["31/4", "32/4"]


def back(b):
    """Two vertical 1x16 technic bricks plugged into the torso's back (receptacles of the box3 frame bricks and of
    the two engine-mount posts, z = 71); the wing pack's columns pin to their holes."""
    for s in (1, -1):
        b.part("3703", 0, SHIN_DOWN, (0, 0, 0), (50 * s, -1112, 71), unit="back_mount", role="wing mount beam",
               prefer=STOCK)
    ty, tz = -942, 281
    b.unit("wings", WING_PACK, trans(0, ty, tz) @ rot("y", 180), region="wings", exclude=WING_PACK_EXCLUDE)
    for s in (1, -1):
        for cy in (-70, -110):  # free holes of the columns' double-bent liftarms (car y)
            b.connector("2780", 0, (60 * s, cy + ty, -200 + tz), (1, 0, 0), unit="back_mount", role="wing pin",
                        prefer=STOCK)


def belly(b):
    """The gearbox (less its input bridge, which is the waist) hangs in front of the waist bridge plate, turned so
    its old gear-shift line runs front-back through the plate's centre hole. One axle threads both shift gates,
    the changeover catch (axle hole) and the plate: a single-axis mount, held against rotation only by friction
    and by resting on the pelvis plate studs below (reported as such)."""

    T = trans(0, -622, -102) @ rot("y", 90)
    # The two side wing-panel bricks (box4step25) would reach back into the pelvis plates; they stay in stock.
    b.unit("belly", GEARBOX, T, region="torso", exclude=WAIST_BRIDGE + ["0/0/58", "0/0/59"])
    # Axle 8 (160) ending flush with the back of the bridge plate (hole z -5..7), through both gates and the catch.
    b.connector("3707", 0, (0, -692, 7 - 80), (0, 0, 1), unit="belly", role="gear-shift line axle", prefer=STOCK)


def chest(b):
    """The car's red rear bumper (box7step6) as a chest plate, turned to face forward, pinned by two pins into
    the V8's front cross blocks (search: scripts/mecha_8448_attach.py --roots 0/30 --rot y:180). The engine-side
    holes are axle holes (axle/bush connectors), so the joiners are notched axles 2, not pins."""
    b.unit("chest_plate", ["0/30"], trans(0, -873, 482) @ rot("y", 180), region="torso")
    for s in (1, -1):
        b.connector("32062", 0, (40 * s, -1023, -58), (1, 0, 0), unit="chest_plate", role="mount axle",
                    prefer=STOCK)


# Armour found with scripts/mecha_8448_attach.py: (unit, car root, translation, rotation spec, joiner,
# joiner centre, joiner axis). Rotation spec as in the search tool (axis:degrees, applied in order).
ARMOUR = [
    ("forearm_guard_l", "0/44", (80, -732, -103), "", "2780", (280, -722, 57), (1, 0, 0)),
    ("forearm_guard_l", "", None, "", "2780", (280, -762, 57), (1, 0, 0)),
    ("forearm_guard_r", "0/38", (-80, -732, -103), "", "2780", (-280, -722, 57), (1, 0, 0)),
    ("forearm_guard_r", "", None, "", "2780", (-280, -762, 57), (1, 0, 0)),
    # White axle-joiner pairs (box7step3sub1 x2) clipped onto the wing columns like exhaust stubs.
    ("exhaust_l", "0/20", (0, -1492, 171.2), "x:-90", "32062", (80, -972, 161.2), (1, 0, 0)),
    ("exhaust_r", "0/21", (0, -1492, 171.2), "x:-90", "32062", (-80, -972, 161.2), (1, 0, 0)),
    # Shield: the windscreen arch (box8step12 with its ribbed hose and flex axle) pinned to the left forearm guard.
    ("shield", "23", (30, -492, -13), "y:90", "2780", (310, -802, 147), (0, 0, 1)),
    # Spare red fairing units (box7step10/8) as panels on the open doors (wings).
    ("wing_panel_l", "0/39", (-107.8, -1330.4, 341.2), "", "32062",
     (("0/39/13", (122.2, -1460.4, 121.2)), ("49/20", (122.2, -1460.4, 101.2))), None),
    ("wing_panel_r", "0/35", (107.8, -1330.5, 341.2), "", "32062",
     (("0/35/13", (-122.2, -1460.5, 121.2)), ("51/20", (-122.2, -1460.5, 101.2))), None),
    # The car's roof cage (box6-3) as a backpack frame behind the waist, two axles into the left exhaust unit
    # (about 5 LDU off-centre: its holes are 11 LDU further apart than the two exhaust units).
    ("backpack", "0/3", (-5.5, -708.1, 331.9), "", "32062",
     (("0/3/6", (90, -879.6, 199.5)), ("0/20/2", (90, -898.1, 191.8))), None),
    ("backpack", "", None, "", "32062", (("0/3/6", (50, -879.6, 199.5)), ("0/20/3", (50, -898.1, 191.8))), None),
    ("thigh_guard_l", "0/54", (360, -392, 613), "", "32062", (240, -422, 33), (1, 0, 0)),
    ("thigh_guard_r", "0/55", (-360, -392, 613), "", "32062", (-240, -422, 33), (1, 0, 0)),
]


def rot_spec(spec):
    m = np.eye(4)
    for item in filter(None, spec.split(",")):
        ax, deg = item.split(":")
        m = rot(ax.strip(), float(deg)) @ m
    return m


def armour(b):
    for name, root, t, spec, joiner, centre, axis in ARMOUR:
        region = ("wings" if name.startswith(("exhaust", "wing_panel", "backpack")) else
                  "head" if name == "crest" else
                  "arm_l" if name == "shield" else
                  "arm_l" if name.endswith("_l") and "arm" in name else "arm_r" if "arm" in name else
                  "leg_l" if name.endswith("_l") else "leg_r" if name.endswith("_r") else "torso")
        if root:  # an empty root adds a further joiner to the unit above
            b.unit(name, [root], trans(*t) @ rot_spec(spec), region=region)
        role = "mount " + ("pin" if joiner == "2780" else "axle")
        if axis is None:  # centre holds the two holes (cid, near point): joiner placed across their faces
            b.joiner_between(joiner, 0, centre[0], centre[1], unit=name, role=role, prefer=STOCK)
        else:
            b.connector(joiner, 0, centre, axis, unit=name, role=role, prefer=STOCK)


NECK_Y, NECK_Z = -1172, 57  # middle holes of the two 1x10 bricks that stand above the engine (car z -500)
IDENT = np.eye(4)


def head(b):
    """Neck pitch on an axle through the two posts; a cross block turns it into a vertical yaw pin; the head is a
    2x4 technic plate on that pin carrying a 1x2 brick whose two holes face forward as eyes, a 1x4 brick behind and a
    2x2 slope on top."""
    y, z = NECK_Y, NECK_Z
    b.connector("3708", 0, (0, y, z), (1, 0, 0), unit="neck", role="neck pitch axle", prefer=STOCK)
    b.part("6536", [0, 7], basis(x=(1, 0, 0), y=(0, 0, -1)), (0, 0, 0), (0, y, z), unit="neck", role="neck yaw block",
           prefer=STOCK)
    for s in (1, -1):
        # Spacers between the yaw block and the post: a 40-long axle-hole tube, a bush and a half bush (= 70).
        b.connector("6538b", [0, 7], (30 * s, y, z), (1, 0, 0), unit="neck", role="neck spacer", local_axis="z",
                    prefer=STOCK)
        b.connector("3713", 7, (60 * s, y, z), (1, 0, 0), unit="neck", role="neck spacer", local_axis="z",
                    prefer=STOCK)
        b.connector("32123a", 7, (75 * s, y, z), (1, 0, 0), unit="neck", role="neck spacer", local_axis="z",
                    prefer=STOCK)
        b.connector("32123a", 7, (105 * s, y, z), (1, 0, 0), unit="neck", role="neck retainer", local_axis="z",
                    prefer=STOCK)
    zp = z - 20  # the cross block's pin hole, vertical, 20 in front of the axle
    # 3/4 pin: its long end in the cross block, the short end in the head plate (no stub into the bricks above).
    b.connector("32002", 8, (0, y - 10, zp), (0, -1, 0), unit="head", role="neck yaw pin", prefer=STOCK)
    top = y - 18  # plate 32001 resting on the cross block (bottom at y - 10)
    b.part("3709b", 0, IDENT, (0, 0, 0), (0, top, zp), unit="head", role="head base", prefer=STOCK)
    b.part("32000", [15, 7, 0], IDENT, (0, 0, 0), (0, top - 24, zp - 10), unit="head", role="eyes (two front holes)",
           prefer=STOCK)
    b.part("3701", [0, 7], IDENT, (0, 0, 0), (0, top - 24, zp + 10), unit="head", role="back of head", prefer=STOCK)
    b.part("3039", 7, IDENT, (0, 0, 0), (0, top - 48, zp + 10), unit="head", role="helmet", prefer=STOCK)
    return dict(pitch=(0, y, z), yaw=(0, y, zp))


def bm_point(T, p):
    return (np.asarray(T) @ np.append(np.asarray(p, float), 1.0))[:3]


HIP_Y = -562  # hip axles; legs below are 562 long to the soles


# Modules kept whole for later placement (robot armour or the display base): never loose stock.
RESERVED = ["0/0/57", "0/0/58", "0/0/59", "0/0/63", "0/3", "0/30", "0/35", "0/38", "0/39", "0/44", "0/53", "0/54",
            "0/55", "0/58", "0/59", "0/60", "0/61", "0/62", "0/63", "0/20", "0/21", "0/24", "0/25", "0/31", "0/32",
            "23"]


def unit_roots():
    """Every car root that some unit below reuses whole (reserved before any loose part is handed out)."""
    roots = [r for r in TORSO if r != "0/0/19"] + [f"0/0/19/{i}" for i in range(36) if f"0/0/19/{i}" not in STEERING]
    roots += WAIST_BRIDGE + [f"0/0/1/{i}" for i in range(70) if i != 30] + ["0/0/1/30/14", "0/0/1/30/15"]
    roots += [r for r in WING_PACK]
    for L in LEGS.values():
        roots += [L["strut"], L["seat"], *L["wheel"]]
    for A in ARMS.values():
        roots += [*A["wheel"]]
    return roots


def build(b):
    b.reserve(RESERVED + unit_roots())
    # Trunk: car front suspension + V8 + gearbox exactly as joined in the car, stood on its nose.
    # Trunk: car front suspension + V8 + the gearbox's input bridge (box4step18), stood on its nose. The bridge's
    # lower 1x2/1x1 bricks go back to stock; a 1x6 technic brick threaded on its three long pins turns their
    # even hole grid into an odd stud grid facing forward, matching the pelvis's 1x10 plate studs.
    ty = -672
    b.unit("torso", TORSO + WAIST_BRIDGE, trans(0, ty, 87) @ CORE_R, region="torso",
           exclude=STEERING + ["0/0/57/38/7", "0/0/57/38/8"])
    waist_y = -30 + ty  # car z of the removed lower bricks
    b.part("3894", 0, basis(x=(1, 0, 0), z=(0, -1, 0)), (0, 10, 0), (0, waist_y, 17), unit="torso",
           role="waist stud adapter", prefer=STOCK)
    # Pelvis: rear suspension, its front 1x10 plate studs coplanar with the adapter studs (z = 7).
    b.unit("pelvis", PELVIS, trans(0, HIP_Y - 370, 63) @ CORE_R, region="pelvis", exclude=DIFF)
    # Vertical 2x6 technic plate across the waist: receptacles on 2 adapter studs and 2 pelvis plate studs.
    b.part("32001", 0, basis(x=(0, 1, 0), y=(0, 0, 1)), (0, 8, 0), (0, waist_y + 50, 7), unit="pelvis",
           role="waist bridge plate", prefer=STOCK)
    hip = b.line("0/0/1/30/14", (240, HIP_Y, 33))["mid"]
    for side in ("l", "r"):
        leg(b, side, hip)
        arm(b, side)
    head(b)
    back(b)
    belly(b)
    chest(b)
    armour(b)
