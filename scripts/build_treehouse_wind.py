"""Wind animation for the 21318 Tree House (autumn): joints, plan and baked clips.

Run from the repo root (pure Python, no Blender):
    .venv/bin/python scripts/build_treehouse_wind.py plan      # writes plan.json, wind_specs.json, clips.json
    .venv/bin/python scripts/build_treehouse_wind.py summary   # per-control amplitudes per regime

Scope (user decisions 2026-11-07): whole model in place; houses, trunk, terrain and minifigs static. Moving:
leaf canopies, leaf sprigs on bars, hanging swing/rope/lamps, ground flowers and plants. Three regimes from
scripts/wind_clips.py (A breeze 1-240, B gusty 257-496, C storm 513-752) under one +X wind.

Every joint origin/axis is measured here from pyldraw3 connector frames (`analysis.connectors`), never from
Blender names. Swing directions follow docs/reference/plants/wind-responses.md: v = a x (tip - origin), stored
as the horizontal fraction (v.x, v.z)/|v|. Joint kinds: "real" = an adopted LEGO connection freedom (ball,
clip on bar, pin, chain over a bar); "flex_approx" = a small rotation standing in for bending or play (locking
click hinges, stud-mounted plants, the merged rope mesh). Wind is an artistic model, not measured airflow.
"""
import argparse
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from ldraw_mechanisms import analysis, mechanisms, plan as contract  # noqa: E402
from ldraw_mechanisms.source import parts_library  # noqa: E402
import wind_clips as wc  # noqa: E402

STUDY = ROOT / "output/21318-autumn-wind"
PLAN_PATH = STUDY / "plan.json"
DRAFT_PATH = STUDY / "plan.prepared.json"  # untouched prepare output; each build starts from it
FLEX = wc.FLEX_LIMIT  # 0.17 rad

# Crown: arms on locking hinges at the trunk top, (assembly id, short name)
CROWN_ARMS = [("407", "s"), ("408", "w"), ("409", "n"), ("410", "nw_hi"), ("411", "ne_hi"), ("412", "se_hi"),
              ("413", "sw_hi")]
CROWN_TOPS = [("414", "top_n"), ("415", "top_w"), ("416", "top_s"), ("417", "top_e")]
BALL_BRANCHES = [("405", "branch_low"), ("406", "branch_ball")]
# Sprig pendants: (assembly, members, fixed twig parts) -- the cluster swings on its 48729b clip about the twig.
SPRIGS = [("418", "sprig_a"), ("419", "sprig_b"), ("420", "sprig_c"), ("421", "sprig_d"), ("422", "sprig_e"),
          ("423", "sprig_f")]
SPRIG_FIXED = {"418": ["418/0"], "419": ["419/0"], "420": ["420/0"], "421": [], "422": ["422/0"],
               "423": ["423/1", "423/4"]}
# Clip whose (clip) connector is the pivot; 423's clip grips the 577b hilt on the twig end.
SPRIG_CLIP = {"418": "418/1", "419": "419/1", "420": "420/1", "421": "421/0", "422": "422/1", "423": "423/2"}
CARROT_TOPS = [("330/160/4", "sprout_porch"), ("332/0/7/2", "sprout_roof_1"), ("332/1/6/2", "sprout_roof_2"),
               ("332/2/6/2", "sprout_roof_3"), ("332/3/6/2", "sprout_roof_4"), ("332/4/6/2", "sprout_roof_5"),
               ("333/76/4", "sprout_balcony"), ("367/7", "sprout_stair_1"), ("368/7", "sprout_stair_2"),
               ("369/6", "sprout_stair_3")]
PIN_FLOWERS = [("330/74/2", "flower_pot"), ("371/1", "flower_pole"), ("401/4/2", "flower_bush")]
FLOWER_LIMIT = {"flower_pole": 0.25}  # the pole flower sits beside a stair step tile (clearance pass 1)
# Range overrides from clearance pass 2 (clearance-pass2.json): arm 409 hangs just above the low ball branch 405,
# so the arm may barely drop and the branch barely lift; the tree lamp meets bar 366/2 beyond +0.05; the ball
# branch 406 meets the NE roof below -0.046.
RANGE = {"crown_n": (-0.01, 0.12), "branch_low": (-0.05, 0.012), "branch_ball": (-0.04, 0.06),
         "lamp_tree": (-0.15, 0.045)}
# Candidates studied but withheld (static) after clearance pass 1 (clearance-pass1.json); reasons by part prefix.
WITHHELD = {
    "334": "Dark-blue house roof (the annotation calls the panels branch segments): four angled panels on Ball "
           "Joint-8s, wedged against the roof plates and each other; any wind tilt cut the roof even in the breeze.",
    "335": "Dark-blue house roof on ball joints, wedged against roof plates and neighbouring panels (as 334).",
    "336": "Dark-blue house roof on ball joints, wedged against roof plates and neighbouring panels (as 334).",
    "367": "Spiral-stair step on the vertical bar 364: steps touch each other and the headlight brick 365; "
           "a stair does not turn in the wind (its carrot top is animated separately).",
    "368": "Spiral-stair step on bar 364 (as 367).",
    "369": "Spiral-stair step on bar 364 (as 367).",
    "250/6": "Swing hanger and chains: minifigs 3 and 4 stand against the seat, so any swing beyond 0.007 rad cut "
             "their torso/hands; the swing stays at rest.",
    "257": "Swing seat: held at rest by the two minifigs standing against it.",
    "372": "Roof lamp: its dish rests against plate 333/81; swings beyond 0.012 rad cut it.",
    "333/79": "Roof leaf 4x3 nestled against an arch and a side-stud brick; leaning cut them.",
}


class Source:
    def __init__(self, plan):
        self.manifest = plan["source"]
        self.nodes = plan["source"]["nodes"]
        self.by_id = {n["id"]: n for n in self.nodes}
        self.parts = [n for n in self.nodes if n["kind"] == "part"]
        self._lib = None

    def leaves(self, *prefixes, exclude=()):
        out = []
        for n in self.parts:
            i = n["id"]
            if any(i == p or i.startswith(p + "/") for p in prefixes) and not any(
                    i == e or i.startswith(e + "/") for e in exclude):
                out.append(i)
        return out

    def pos(self, oid):
        w = self.by_id[oid]["world"]
        return [w[0][3], w[1][3], w[2][3]]

    def centroid(self, ids):
        ps = [self.pos(i) for i in ids]
        return [sum(p[k] for p in ps) / len(ps) for k in range(3)]

    def features(self, oid, kind=None, name=None):
        if self._lib is None:
            self._lib = parts_library(None, None)
        r = analysis.connectors(self.manifest, oid, parts=self._lib)
        return [f for f in r["features"] if (kind is None or f["kind"] == kind)
                and (name is None or f["name"] == name)]


def sub(a, b):
    return [x - y for x, y in zip(a, b)]


def cross(a, b):
    return [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]


def norm(v):
    m = math.sqrt(sum(x * x for x in v))
    return [x / m for x in v]


def rnd(v, k=4):
    return [round(x, k) + 0.0 for x in v]


def motion(axis, origin, tip):
    """Tip velocity per radian v = a x (tip - origin) -> (horizontal swing fraction, rises?, lever)."""
    v = cross(axis, sub(tip, origin))
    m = math.sqrt(sum(x * x for x in v)) or 1.0
    return (round(v[0] / m, 3) + 0.0, round(v[2] / m, 3) + 0.0), v[1] < 0, m


def lift_axis(axis, origin, tip):
    """Flip a measured hinge axis so that + lifts the tip (LDraw -Y is up)."""
    _, rises, _ = motion(axis, origin, tip)
    return axis if rises else [-x for x in axis]


# --------------------------------------------------------------------------- joint table
def joints(src):
    """Measured joints: list of dicts (name, view, instances, origin, axis, parent, spec, evidence)."""
    J = []

    def add(name, view, ids, origin, axis, spec_fn, evidence, parent=None, tip=None):
        axis = norm(axis)
        tip = tip or src.centroid(ids)
        swing, rises, lever = motion(axis, origin, tip)
        spec = spec_fn(swing, origin[0])
        J.append(dict(name=name, view=view, instances=ids, origin=rnd(origin, 3), axis=rnd(axis), parent=parent,
                      spec=spec, evidence=evidence, tip=rnd(tip, 1), swing=list(swing), lever=round(lever, 1),
                      rises=rises))

    # A. Crown arms and top modules on locking click hinges (flex_approx: the click hinge holds its angle; the
    #    small bounce stands in for hinge play and branch bending, about the real hinge line).
    def hinge_root(prefix):
        ids = src.leaves(prefix)
        cand = []
        for i in ids:
            if src.by_id[i]["ref"] != "44302a.dat":
                continue
            for f in src.features(i, "hinge", "lckHng"):
                p = f["world_position"]
                cand.append((math.hypot(p[0], p[2]), p, f["world_axis"], i))
        cand.sort()
        r0 = cand[0][0]
        pair = [c for c in cand if abs(c[0] - r0) < 1.0]
        origin = [sum(c[1][k] for c in pair) / len(pair) for k in range(3)]
        return ids, origin, cand[0][2], [c[3] for c in pair]

    for prefix, short in CROWN_ARMS + CROWN_TOPS:
        ids, origin, axis, plates = hinge_root(prefix)
        tip = src.centroid(ids)
        axis = lift_axis(axis, origin, tip)
        top = short.startswith("top")
        f_hz = 0.75 if top else 0.55

        def spec_fn(swing, x, f_hz=f_hz, short=short, top=top):
            return wc.lean(f"Crown {'top module' if top else 'arm'} {short} on its locking click hinge; {wc.RISE} "
                           "(flex_approx: click hinge play + branch bending)", *RANGE.get(f"crown_{short}", (-0.1, 0.12)),
                           f_hz, 0.08, 0.35, x=x,
                           swing=swing, joint=wc.FLEX, lift=0.22, flutter=wc.FL)
        add(f"crown_{short}", "crown", ids, origin, axis, spec_fn,
            f"lckHng of 44302a {plates} mates the trunk's 44301b/30383 single-finger half; "
            f"root hinge pair nearest the trunk axis")

    # B. Ball/socket branches 405, 406: the whole branch (socket plate included) tilts on the Ball Joint-8
    #    about a horizontal axis perpendicular to the branch (+ lifts the tip). One of the ball's freedoms (real);
    #    small range because 405 sits just under crown arm 409 (clearance pass 1).
    for prefix, short in BALL_BRANCHES:
        ids = src.leaves(prefix)
        joint_part = [i for i in ids if src.by_id[i]["ref"] == "14418.dat"][0]
        origin = src.features(joint_part, "generic")[0]["world_position"]
        tip = src.centroid(ids)
        horiz = sub(tip, origin)
        horiz[1] = 0.0
        laxis = lift_axis(norm([horiz[2], 0.0, -horiz[0]]), origin, tip)

        def ball_fn(swing, x, short=short):
            return wc.lean(f"{short}: branch tilts on its ball joint (real Ball Joint-8 freedom); {wc.RISE}",
                           *RANGE[short], 1.1, 0.1, 0.25, x=x, swing=swing, lift=0.15, flutter=wc.FL)
        add(short, "ball_branches", ids, origin, laxis, ball_fn,
            f"ball centre from {joint_part} (14418 socket) generic connector on the trunk's ball plate")

    # C. Sprig pendants: leaf cluster (+ small lamp) on its 48729b clip around the twig bar (real clip-on-bar).
    for prefix, short in SPRIGS:
        clip = SPRIG_CLIP[prefix]
        f = src.features(clip, "clip")[0]
        ids = src.leaves(prefix, exclude=SPRIG_FIXED[prefix])

        def spec_fn(swing, x, short=short):
            return wc.lean(f"Sprig {short}: leaf cluster swings on its clip around the twig (real); "
                           "+ right-hand about the twig", -0.25, 0.25, 1.1, 0.1, 0.35, x=x, swing=swing,
                           flutter=wc.FL)
        add(short, "sprigs", ids, f["world_position"], f["world_axis"], spec_fn,
            f"{clip} 48729b clip frame on the twig; twig parts {SPRIG_FIXED[prefix] or ['333/23 handle']} fixed")

    # F. Winch rope + hook + treasure chest: rope segments are one merged mesh, so the whole hangs from the
    #    reel->pulley run and rocks about that line (flex_approx: real rope bends at the pulley).
    rope_ids = src.leaves("331/135/2", "404")
    run0 = src.pos("331/135/2/1")
    run1 = src.pos("331/135/2/15")

    def rope_fn(swing, x):
        return wc.lean("Winch rope with hook and chest rocks about the reel-to-pulley run (flex_approx: merged "
                       "rope mesh); + right-hand about the run", -0.12, 0.12, 0.85, 0.05, 0.6, x=x, swing=swing,
                       joint=wc.FLEX)
    add("rope_chest", "rope", rope_ids, run0, sub(run1, run0), rope_fn,
        "axis through rope segments 331/135/2/1 (reel) and /15 (pulley top); 37 cylinder primitives merged")

    # G. Hanging lamp on the stair-side tree (the roof lamp 372/8 is withheld: its dish rests against 333/81).
    f = src.features("370/3", "clip")[0]

    def lamp_fn(swing, x):
        return wc.lean("Hanging lamp on its clip around the bar (real)", *RANGE["lamp_tree"], 1.5, 0.08, 0.3, x=x,
                       swing=swing)
    add("lamp_tree", "lamps", src.leaves("370"), f["world_position"], f["world_axis"], lamp_fn,
        "48729b clip on the 92690 bar 366/3")

    # H. Carrot tops in clips (real rotation about the clip bar) and flowers on pins (real twist).
    for oid, short in CARROT_TOPS:
        f = src.features(oid, "bar")[0]

        def spec_fn(swing, x, short=short):
            return wc.twist(f"{short}: carrot top turns in its clip about the bar (real); asymmetric-drag twist",
                            -0.35, 0.35, 1.6, 0.12, 1.0, 0.25, x=x, flutter=((0.05, 3.4, 0.4),))
        add(short, "sprouts", [oid], f["world_position"], f["world_axis"], spec_fn,
            f"33183 bar in its clip ({f['name']}); a one-part body has no lever, so drive is asymmetric drag")
    for oid, short in PIN_FLOWERS:
        f = src.features(oid, "pin")[0]

        def spec_fn(swing, x, short=short):
            lim = FLOWER_LIMIT.get(short, 0.5)
            return wc.twist(f"{short}: flower head turns on its pin (real)", -lim, lim, 1.3, 0.1, 1.2, 0.3, x=x,
                            flutter=((0.06, 3.0, 1.0),))
        add(short, "flowers", [oid], f["world_position"], f["world_axis"], spec_fn, "32606 pin")

    # I. Stud-mounted ground plants: flex_approx lean about +Z (+ leans the top downwind).
    def ground(name, ids, origin, f_hz, evidence, parent=None, height=None):
        def spec_fn(swing, x):
            return wc.lean(f"{name}: leans downwind on its stud (flex_approx: plastic bending)", -0.1, 0.14, f_hz,
                           0.15, 0.15, x=x, swing=swing, joint=wc.FLEX, flutter=wc.FL)
        tip = [origin[0], origin[1] - height, origin[2]] if height else None
        add(name, "ground_plants", ids, origin, [0.0, 0.0, 1.0], spec_fn, evidence, parent=parent, tip=tip)

    ground("plant_path", ["402"], src.pos("402"), 1.2, "6255 on a stud, origin at its base",
           height=20)
    ground("plant_rock", ["403"], src.pos("403"), 1.2, "6255 on a stud, origin at its base", height=20)
    ground("plant_shoot", ["357/1", "357/2"], [176.0, -70.0, 10.0], 1.4, "32607 leaf plates on the T-piece 357/0")
    bush = src.leaves("401", exclude=["401/0", "401/4/2"])
    ground("flower_bush_stem", bush, src.pos("401/1"), 0.9, "19119 stem on the 24866 base plate 401/0")
    # the pin flower 401/4/2 rides on the bush stem
    for j in J:
        if j["name"] == "flower_bush":
            j["parent"] = "flower_bush_stem"
    return J


# --------------------------------------------------------------------------- dispositions of discovered views
DEFERRED = [
    ("Hinge Plate  1 x  4", "House wall/roof hinge plates: the set's opening play feature or angled construction. "
                            "Not wind-driven (latched by the surrounding bricks); out of scope for the wind request."),
    ("Door", "Door or door frame: a real opening freedom, but not requested and not wind-driven here."),
    ("Turntable", "Turntable: a real rotation in the build, not wind-driven; out of scope."),
    ("Hinge  1 x  2 Base", "Hinge 1x2: construction angle in a house section; not wind-driven."),
    ("Hinge  2 x  2 Top", "Hinge 2x2: construction angle in a house section; not wind-driven."),
]
STATIC_TEXT = {
    "Hinge Plate  1 x  2 Locking": "Locking click hinge holding a fixed construction angle (trunk top, arm "
                                   "mid-hinges); only the arm root hinges are animated.",
    "Plate  1 x  2 with Door Rail": "Door rail plate used as a ledge/sill; nothing slides on it.",
    "Plate  2 x  2 Round with Axlehole": "Round plate with axlehole used decoratively; no mating axle motion.",
    "Socket Joint": "Ball/socket counterpart fixed to its support; the moving side is animated in its own body.",
    "Ball Joint": "Ball counterpart fixed to its support; the moving side is animated in its own body.",
    "Bar  1.5L with Clip": "Bar-clip used as a rigid connector here.",
}
WINCH = ("Technic", "Barrel", "Brick  2 x  2 with Slots", "Brick  2 x  4 with  3 Axleholes", "Cylinder  2 x  2",
         "Circular ring")


def disposition(view, owner):
    label = view["label"]
    for key, text in DEFERRED:
        if label.startswith(key):
            return "deferred", text
    for key, text in STATIC_TEXT.items():
        if key in label:
            return "static", text
    if label.startswith(WINCH):
        return "deferred", ("Technic axle/bush/gear or barrel in the winch, trunk frame or base: the winch crank "
                            "is a real hand-driven freedom, not wind-driven; structural axles are fixed.")
    return "static", "Decorative or structural element with no wind-driven freedom in this scope."


# --------------------------------------------------------------------------- build
def build():
    p = contract.load(str(DRAFT_PATH if DRAFT_PATH.exists() else PLAN_PATH))
    src = Source(p)
    J = joints(src)
    # reset any previous authoring, keep the discovery views
    p["controls"], p["signals"], p["bodies"] = {}, {}, {}
    p["mechanisms"] = {k: v for k, v in p["mechanisms"].items() if k.startswith("m_")}
    views = {}
    for j in J:
        views.setdefault(j["view"], []).append(j)
    for view, js in views.items():
        p["mechanisms"][view] = dict(label=f"Wind: {view.replace('_', ' ')}",
                                     parts=sorted({i for j in js for i in j["instances"]}),
                                     bodies=[], inputs=[], outputs=[], disposition="unresolved", notes=[],
                                     review="")
    order = [j for j in J if not j["parent"]] + [j for j in J if j["parent"]]
    for j in order:
        s = j["spec"]
        p = mechanisms.add_joint(p, mechanism=j["view"], name=j["name"], instances=j["instances"],
                                 origin=j["origin"], axis=j["axis"], minimum=s["min"], maximum=s["max"],
                                 description=s["description"], parent=j["parent"])
    for view, js in views.items():
        m = p["mechanisms"][view]
        m["disposition"] = "planned"
        m["review"] = "; ".join(f"{j['name']}: {j['spec']['joint']}, {j['evidence']}" for j in js)
        m["notes"] = [f"{j['name']}: origin {j['origin']} axis {j['axis']} tip {j['tip']} swing {j['swing']}"
                      for j in js]
    owner = {i: b for b, body in p["bodies"].items() for i in body["instances"]}
    counts = {}
    for name, view in p["mechanisms"].items():
        if not name.startswith("m_"):
            continue
        moving = sorted({owner[i] for i in view["parts"] if i in owner})
        if moving:
            view["disposition"], view["bodies"] = "planned", moving
            view["review"] = "Part of the wind-animated bodies " + ", ".join(moving)
        else:
            withheld = [t for k, t in WITHHELD.items() if any(i == k or i.startswith(k + "/") for i in view["parts"])]
            view["disposition"], view["review"] = ("static", withheld[0]) if withheld else disposition(view, owner)
        counts[view["disposition"]] = counts.get(view["disposition"], 0) + 1
    p["name"] = "treehouse_21318_autumn_wind"
    p["notes"] = [
        "Wind animation of the whole 21318 Tree House (autumn) in place; user scope 2026-11-07.",
        "Moving: 7 crown arms + 4 crown top modules (locking click hinges, flex_approx lift), 2 ball branches "
        "(Ball Joint-8 tilt, real), 6 leaf sprigs (clip on twig, real), the winch rope with hook and chest "
        "(flex_approx, merged rope mesh), 1 hanging lamp (clip, real), 10 carrot-top sprouts (clip, real), "
        "3 pin flowers (real twist) and 4 stud-mounted ground plants (flex_approx).",
        "Static: houses (including their dark-blue ball-jointed roofs), trunk, terrain, spiral stair, the 4 "
        "minifigs, the swing (held by two minifigs), the roof lamp, mushrooms, pumpkin, domed flower. Withheld "
        "candidates and why: WITHHELD in scripts/build_treehouse_wind.py and clearance-pass1.json. Deferred (not "
        "wind-driven): house hinges, doors, turntables, winch crank.",
        "Animation: controller custom properties keyed from output/21318-autumn-wind/clips.json, computed by "
        "scripts/wind_clips.respond for regimes A (1-240), B (257-496), C (513-752). Wind toward +X; gusts travel "
        "+X, so the west (−X) side reacts first.",
        "Contacts: bounded pyldraw3 query in evidence-contacts.json (1442 parts; stud features partly rejected, "
        "so geometry and xray boards were used too). Renders are not clearance proof.",
        f"Discovered views: {counts}.",
    ]
    p["status"] = "ready"
    contract.save(str(PLAN_PATH), p)
    specs = {j["name"]: j["spec"] for j in J}
    (STUDY / "wind_specs.json").write_text(json.dumps(
        dict(joints=[{k: v for k, v in j.items() if k != "instances"} | dict(parts=len(j["instances"]))
                     for j in J]), indent=1))
    clips = {name: {reg: [round(v, 6) for v in wc.respond(spec, reg, 0.0)] for reg in "ABC"}
             for name, spec in specs.items()}
    (STUDY / "clips.json").write_text(json.dumps(dict(
        windows=wc.WINDOWS, fps=wc.FPS, loop=wc.LOOP, regimes=wc.REGIMES, wind="+X; gust front from field x "
        f"{wc.X0} at {wc.GUST_SPEED} LDU/frame; joint field x = its world X", controls=clips)))
    print(json.dumps(dict(controls=len(specs), bodies=len(p["bodies"]), views=counts), indent=1))
    return J


def summary():
    clips = json.loads((STUDY / "clips.json").read_text())["controls"]
    specs = {j["name"]: j for j in json.loads((STUDY / "wind_specs.json").read_text())["joints"]}
    print(f"{'control':22} {'range':>13} {'swing':>15} {'A':>6} {'B':>6} {'C':>6}  joint")
    for name, c in clips.items():
        s = specs[name]["spec"]
        amp = {r: max(abs(v) for v in c[r]) for r in "ABC"}
        print(f"{name:22} {s['min']:6.2f}…{s['max']:<5.2f} {str(specs[name]['swing']):>15} "
              f"{amp['A']:6.3f} {amp['B']:6.3f} {amp['C']:6.3f}  {s['joint']}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("command", choices=["plan", "summary"])
    a = ap.parse_args()
    build() if a.command == "plan" else summary()
