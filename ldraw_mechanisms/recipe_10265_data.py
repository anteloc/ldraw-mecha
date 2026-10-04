"""Measured geometry for the 10265 Ford Mustang B-model.

Every coordinate is stated in the ``10265 - Ford Mustang 1967 Complete.ldr``
frame (LDU, -Y up), which is the single assembly the ``Main.ldr`` root places.
The recipe passes that node's world matrix to ``Builder`` as its base, so no
literal here is pre-transformed into the root frame.

Axis directions come from mechanical frames, never from a part's transformed
local X/Y/Z: ``inspect`` reports part-local axes and says so. The gear axis of
``3649``/``94925`` is local Z (teeth lie in the part's XY plane), ``3705`` and
``24316`` run along local X, the ``6628`` towball centre is local (-10,0,0),
``32005`` has ball sockets 100 LDU apart on local Z, and ``15460`` carries ball
centres at local (0,-20,0), (0,0,-20) and (0,20,0).
"""

# --- steering: pitman crank, tie rods and kingpin knuckles ------------------
# The 40T gear, its axle and the crank arm turn about a longitudinal axis.
CRANK_AXIS = [0.0, 0.0, -1.0]
CRANK_CENTRE = [0.0, -54.0, -270.0]
# 94925 (16T, r=20) and 3649 (40T, r=50) sit 70 LDU apart on parallel axes.
GEAR_AXIS = [0.0, 0.0, 1.0]
GEAR16_CENTRE = [70.0, -54.0, -270.0]
GEAR_RATIO = -0.4  # 16T drives 40T: -16/40, an external mesh reverses sense
# Steering column: a straight raked shaft from the wheel to the joint end.
COLUMN_AXIS = [0.0, -0.4902903, 0.8715574]
COLUMN_CENTRE = [70.0, -107.99, -123.95]
# Kingpin: vertical through the two 15460 ball centres that the suspension
# arms hold at y=-14 and y=-54; the steering arm ball is 20 LDU forward.
KINGPIN_AXIS = [0.0, -1.0, 0.0]
KINGPIN = {"l": [-120.0, -34.0, -320.0], "r": [120.0, -34.0, -320.0]}
CRANK_BALL = {"l": [-20.0, -34.0, -340.0], "r": [20.0, -34.0, -340.0]}
KNUCKLE_BALL = {"l": [-120.0, -34.0, -340.0], "r": [120.0, -34.0, -340.0]}
LINK_LENGTH = 100.0  # 32005 socket spacing, exact in the source pose
STEER_ARM = 20.0  # knuckle ball offset forward of the kingpin
# Two separate limits apply, and the tighter one wins.
# Kinematically the linkage saturates near a 36 degree crank angle, where the
# outer knuckle reverses at a dead point; 21 degrees would keep both sides
# monotonic. Physically the source is far tighter: the towballs rest flush
# against the open-centre chassis brick 0/0/21 and clear the suspension arms
# above them by about 3 LDU, so the crank has only a few degrees before the
# sampled surface check reports contact. The declared range follows the
# measured clearance, not the kinematic envelope.
CRANK_LIMIT = 0.072
STEER_LIMIT = 0.18

# --- wheels -----------------------------------------------------------------
SPIN_AXIS = [1.0, 0.0, 0.0]
SPIN_CENTRE = {
    "fl": [-140.0, -34.0, -320.0],
    "fr": [140.0, -34.0, -320.0],
    "rl": [-140.0, -6.9704, 202.1585],
    "rr": [140.0, -6.9704, 202.1585],
}

# Rigid groups by occurrence id. Each id is checked against the reference
# below, so a changed source fails loudly instead of rigging the wrong part.
WHEELS = {
    "fl": [
        ("0/455", "42716.dat"),
        ("0/456", "15413.dat"),
        ("0/90/19", "24316.dat"),
        ("0/90/20", "32198.dat"),
        ("0/446", "32123b.dat"),
    ],
    "fr": [
        ("0/453", "42716.dat"),
        ("0/454", "15413.dat"),
        ("0/90/18", "24316.dat"),
        ("0/90/21", "32198.dat"),
        ("0/445", "32123b.dat"),
    ],
    "rl": [
        ("0/459", "42716.dat"),
        ("0/460", "15413.dat"),
        ("0/88/15", "32209.dat"),
        ("0/88/22", "32198.dat"),
        ("0/448", "32123b.dat"),
    ],
    "rr": [
        ("0/457", "42716.dat"),
        ("0/458", "15413.dat"),
        ("0/88/18", "32209.dat"),
        ("0/88/21", "32198.dat"),
        ("0/447", "32123b.dat"),
    ],
}

KNUCKLES = {"l": [("0/90/16", "15460.dat")], "r": [("0/90/17", "15460.dat")]}
TIERODS = {"l": [("0/92", "32005.dat")], "r": [("0/93", "32005.dat")]}

# Steering wheel, axle 9 and the column-side universal-joint end. The joint
# centre 0/307 lies on the column axis, so it turns with the column; a real
# universal joint also swings on its cross pin, which no single revolute can
# express.
COLUMN = [
    ("0/312/22", "2819.dat"),
    ("0/312/21", "60485.dat"),
    ("0/312/23", "3712.dat"),
    ("0/307", "3326b.dat"),
]
# Longitudinal side: the joint's other end, its axle and the 16T gear.
GEAR16 = [("0/308", "3712.dat"), ("0/102", "24316.dat"), ("0/103", "94925.dat")]
# The 40T gear and axle on the rotation axis, plus the offset crank arm that
# carries both towballs: beam 32523, notched axle, two liftarms, two towballs.
CRANK = [
    ("0/91/7", "3649.dat"),
    ("0/91/8", "3705.dat"),
    ("0/91/5", "32523.dat"),
    ("0/91/9", "32062.dat"),
    ("0/91/4", "41677.dat"),
    ("0/91/14", "41677.dat"),
    ("0/91/2", "6628.dat"),
    ("0/91/3", "6628.dat"),
]


# --- engine valve covers ----------------------------------------------------
# 3937 bases on the engine and 3938 tops on each cover both carry their hinge
# cylinder on part-local X at local (.,10,0). Placed, the two halves meet at
# the same pin point, which fixes the pivot without guessing: (-+30,-86,.)
# with the pin running along Z. Each cover is a whole submodel, so its rigid
# group needs no splitting.
# Sign chosen by clearance sweep, not by connector alignment: the opposite
# sense drives both covers straight into the block and the hoses.
VALVE_AXIS = {"l": [0.0, 0.0, -1.0], "r": [0.0, 0.0, 1.0]}
VALVE_PIVOT = {"l": [-30.0, -86.0, -340.0], "r": [30.0, -86.0, -340.0]}
VALVE_COVERS = {
    "l": [
        ("0/284/0/0", "3666.dat"),
        ("0/284/0/1", "3069b.dat"),
        ("0/284/0/2", "2431.dat"),
        ("0/284/0/3", "3938.dat"),
        ("0/284/0/4", "3938.dat"),
        ("0/284/0/5", "6258203l.dat"),
    ],
    "r": [
        ("0/284/1/0", "3666.dat"),
        ("0/284/1/1", "15573.dat"),
        ("0/284/1/2", "2431.dat"),
        ("0/284/1/3", "98138p09.dat"),
        ("0/284/1/4", "3938.dat"),
        ("0/284/1/5", "3938.dat"),
        ("0/284/1/6", "6258203l.dat"),
    ],
}
# Sampled clearance is clean to about 3 degrees and shows two contacts by
# 8.6 degrees, where the covers meet the engine block and the flexible
# hose 0/284/2. The engine bay has almost no room.
VALVE_LIMIT = 0.15
