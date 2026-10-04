"""Author motion for 10265 (Ford Mustang) on top of a prepared draft plan.

Usage: python scripts/author_10265.py output/10265/plan.json [output/10265/plan.ready.json]

Only motion with direct evidence is declared; see the plan notes for what is not.
Frames are in the selected section (Main.ldr root frame), LDU, radians.
"""

import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ldraw_mechanisms import mechanisms, plan as contract  # noqa: E402

SRC, DST = sys.argv[1], (sys.argv[2] if len(sys.argv) > 2 else sys.argv[1])
p = contract.load(SRC)
nodes = {n["id"]: n for n in p["source"]["nodes"]}


def pos(i):
    m = nodes[i]["world"]
    return [m[k][3] for k in range(3)]


def unit(v):
    n = math.sqrt(sum(x * x for x in v))
    return [x / n for x in v]


def expect(i, ref):
    assert nodes[i]["ref"].lower() == ref, (i, nodes[i]["ref"], ref)


def control(name, lo, hi, text, unit_name="radian"):
    p["controls"][name] = dict(
        default=0.0, min=lo, max=hi, unit=unit_name, description=text
    )
    p["signals"][name] = dict(
        expression=f"clamp(v,{lo!r},{hi!r})", variables={"v": "control:" + name}
    )


def signal(name, expr, **variables):
    p["signals"][name] = dict(
        expression=expr,
        variables={k: v if ":" in v else "signal:" + v for k, v in variables.items()},
    )


def body(name, ids, origin, axis, sig, parent=None):
    for i in ids:
        assert nodes[i]["kind"] == "part", i
    b = dict(
        instances=list(ids),
        kind="revolute",
        origin=[float(x) for x in origin],
        axis=[float(x) for x in unit(axis)],
        signal=sig,
    )
    if parent:
        b["parent"] = parent
    p["bodies"][name] = b


p["controls"], p["signals"], p["bodies"] = {}, {}, {}
p["anchors"], p["checks"] = {}, []

# ---- wheels: lateral axle through the four hub centres (rims at x=+-140) ----
control("roll", -20 * math.pi, 20 * math.pi,
        "Roll all four wheels; positive rolls the car forward (toward -Z)")
control("front_steer", -0.35, 0.35,
        "Front knuckle yaw about a vertical kingpin; positive steers right (LDraw frame is mirrored, so the +Y-down right-hand rule is clockwise from above)")
wheels = {  # name: (rim, tyre, axle, bevel gear) leaf IDs
    "FR": ("0/453", "0/454", "0/90/18", "0/90/21", "0/445"),
    "FL": ("0/455", "0/456", "0/90/19", "0/90/20", "0/446"),
    "RR": ("0/457", "0/458", "0/88/18", "0/88/21", "0/447"),
    "RL": ("0/459", "0/460", "0/88/15", "0/88/22", "0/448"),
}
for key, (rim, tyre, axle, bevel, *bush) in wheels.items():
    expect(rim, "42716.dat"); expect(tyre, "15413.dat")
    expect(axle, "24316.dat" if key[0] == "F" else "32209.dat")
    expect(bevel, "32198.dat")
    for b in bush:
        expect(b, "32123b.dat")
    c = pos(rim)
    parent = None
    if key[0] == "F":
        arm = "0/90/17" if key == "FR" else "0/90/16"
        expect(arm, "15460.dat")
        kp = pos(arm)
        # Kingpin: vertical line through the suspension-arm ball (x = +-120).
        kx = 120.0 if key == "FR" else -120.0
        body(f"steer_{key}", [arm], [kx, c[1], c[2]], [0, -1, 0], "front_steer")
        parent = f"steer_{key}"
    body(f"spin_{key}", [rim, tyre, axle, bevel, *bush], c, [1, 0, 0], "roll", parent)

# ---- steering wheel -> universal joint -> 16T -> 40T (meshed, ratio measured) ----
control("steering_wheel", -2 * math.pi, 2 * math.pi,
        "Steering wheel angle; positive turns it clockwise for the driver, steering right")
wheel, shaft, uj = "0/312/22", "0/312/21", "0/312/23"
expect(wheel, "2819.dat"); expect(shaft, "60485.dat"); expect(uj, "3712.dat")
a_pos, w_pos = pos(shaft), pos(wheel)
column = [w_pos[k] - a_pos[k] for k in range(3)]  # points toward the driver
body("column", [wheel, shaft, uj], a_pos, column, "steering_wheel")
g16, g16_axle, g40, g40_axle = "0/103", "0/102", "0/91/7", "0/91/8"
expect(g16, "94925.dat"); expect(g40, "3649.dat")
gear_axis = [0.0, 0.05198167968629696, -0.9986480385886667]  # gear-meshes output
# The input and gear axes oppose, so +s about the column is -s about gear_axis.
signal("gear16", "-s", s="steering_wheel")
body("gear16", [g16, g16_axle], pos(g16), gear_axis, "gear16")
# Measured mesh: 16T angle = -2.5 x 40T angle (gear-meshes b_per_a = -2.5).
signal("gear40", "-0.4*g", g="gear16")
body("gear40", [g40, g40_axle], pos(g40), gear_axis, "gear40")

# ---- views ----
def view(name, label, bodies, inputs, outputs, notes):
    p["mechanisms"][name] = dict(
        label=label, parts=[], bodies=bodies,
        inputs=["control:" + c for c in inputs],
        outputs=["body:" + b for b in outputs], notes=notes,
    )


view("wheels", "Wheels and hubs",
     [b for b in p["bodies"] if b.startswith(("spin_", "steer_"))],
     ["roll", "front_steer"], [b for b in p["bodies"] if b.startswith("spin_")],
     ["Rim, tyre, axle stub and bevel gear spin together about lateral X.",
      "Front spin bodies are children of their knuckle, so spin follows steering."])
view("steering_train", "Steering wheel and gear train",
     ["column", "gear16", "gear40"], ["steering_wheel"], ["gear40"],
     ["16T/40T mesh is a reviewed pyldraw3 candidate, ratio -2.5.",
      "Tie-rod linkage from the 40T output to the knuckles is NOT resolved."])

p["status"] = "ready"
p["notes"] = [
    "Declared: four wheel spins; front knuckle yaw; steering wheel -> 16T -> 40T.",
    "front_steer is independent of steering_wheel and NOT validated: the tie rods (steering links 0/92, 0/93, fixed 100 LDU, balls at (+-120,1.1,-20.1) and (+-20,1.1,-20.1)) stay static, so any nonzero yaw makes them cross the knuckles (sampled clearance fails at every nonzero value). The kingpin (vertical through the two arm balls at x=+-120, z=-0.1) is supported by 15460 ball positions, but the pitman drive of the inner towball ends was not found: the 40T gear axis is 22 LDU from the beam 32523/axle 32062 carrying them.",
    "Kingpin is placed vertically through the suspension-arm ball at x=+-120; unverified against clearance.",
    "Rear differential, worm gear, engine, supercharger, gearshift, bonnet, trunk lid and doors are NOT rigged: contacts/coaxial returned no hinge or drive evidence for them.",
    "Right/left rear and front wheels use the same roll angle; no differential action.",
]
contract.validate(p)
mechanisms.validate(p)
contract.save(DST, p)
print("saved", DST, len(p["bodies"]), "bodies")
