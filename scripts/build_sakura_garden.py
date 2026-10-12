"""Author motion for the sakura-garden diorama: plant wind sway + 3 minifig clips.

Run from the repo root (pure Python, no Blender):
    .venv/bin/python scripts/build_sakura_garden.py

Reads/writes output/sakura-garden/plan.json in place. Reuses scripts/wind_clips.py's
physics (single "A" breeze regime only) and scripts/minifig_clips.py's channel
vocabulary. Plant joints are all flex_approx (plain stud-stacked bricks, no real
connector). Minifig joints are real connector-measured revolute joints (hip/shoulder/
neck), taken directly from `./ldraw-mecha connectors` evidence already recorded below.
Static architecture: the 5 auto-discovered "Plate 2x2 Round with Axlehole" candidates
(decorative lily pads / torii ornaments) are dispositioned static with a review note.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from ldraw_mechanisms import mechanisms, plan as contract  # noqa: E402
import wind_clips as wc  # noqa: E402

PLAN_PATH = ROOT / "output/sakura-garden/plan.json"

STRUCT_REFS = {"3941.dat", "60474.dat", "74611.dat", "11213.dat", "87580.dat", "2417.dat"}
AXIS_LEAN = [0.0, 0.0, 1.0]  # uniform: rotating about +Z leans the top toward +X (downwind)

TREES = {
    "cherry_large": "21",
    "cherry_medium": "22",
    "cherry_small": "23",
    "garden_pine": "24",
}
BAMBOO = {
    "bamboo_10": "41",  # bamboo-10-10-64219, 10 segments (tallest)
    "bamboo_9": "43",   # bamboo-9-2-93053
    "bamboo_8a": "42",  # bamboo-8-2-89675
    "bamboo_8b": "46",  # bamboo-8-2-61408
    "bamboo_7a": "44",  # bamboo-7-10-51145
    "bamboo_7b": "45",  # bamboo-7-2-53705
    "bamboo_6": "47",   # bamboo-6-10-63775 (shortest)
}
# (f, lag) per bamboo culm: taller canes sway slower; small lag orders the ripple across the
# tightly-clustered grove (ordered roughly by Z, per wind-field.md's traveling-gust style).
BAMBOO_WIND = {
    "bamboo_10": dict(f=0.42, lag=0.0),
    "bamboo_9": dict(f=0.48, lag=0.6),
    "bamboo_8a": dict(f=0.55, lag=1.2),
    "bamboo_8b": dict(f=0.55, lag=1.8),
    "bamboo_7a": dict(f=0.62, lag=2.4),
    "bamboo_7b": dict(f=0.62, lag=3.0),
    "bamboo_6": dict(f=0.70, lag=3.6),
}

# Connector-measured minifig joints (world frame; see docs/reference/minifigs/joints-and-attachments.md
# for the general method, remeasured here against this model's own parts via
# `./ldraw-mecha connectors <source.mpd> --instance <leaf-id>`).
MINIFIGS = {
    "visitor": dict(
        root="48",
        legs={"hip_r": "48/1", "hip_l": "48/2"},  # 3816c=right, 3817c=left
        arms={"shoulder_r": "48/4", "shoulder_l": "48/5"},  # 43368=right, 43369=left
        head="48/6", head_extra="48/7",  # hair bun, "shares the head origin" -- must turn with the head
        joints={
            "hip_r": dict(origin=[-188.8, -84.0, -258.0], axis=[0.0, 0.0, 1.0]),
            "hip_l": dict(origin=[-188.8, -84.0, -262.0], axis=[0.0, 0.0, -1.0]),
            "shoulder_r": dict(origin=[-188.8, -119.0, -244.448], axis=[0.0, 0.1701, -0.9854]),
            "shoulder_l": dict(origin=[-188.8, -119.0, -275.552], axis=[0.0, 0.1701, 0.9854]),
            "neck": dict(origin=[-188.8, -128.0, -260.0], axis=[0.0, -1.0, 0.0]),
        },
    ),
    "gardener": dict(
        root="49",
        legs={"hip_r": "49/1", "hip_l": "49/2"},
        arms={"shoulder_r": "49/4", "shoulder_l": "49/5"},
        head="49/6", head_extra="49/7",  # conical rice hat, "shares the head origin" -- must turn with the head
        joints={
            "hip_r": dict(origin=[268.8, -52.0, -322.0], axis=[0.0, 0.0, -1.0]),
            "hip_l": dict(origin=[268.8, -52.0, -318.0], axis=[0.0, 0.0, 1.0]),
            "shoulder_r": dict(origin=[268.8, -87.0, -335.552], axis=[0.0, 0.1701, 0.9854]),
            "shoulder_l": dict(origin=[268.8, -87.0, -304.448], axis=[0.0, 0.1701, -0.9854]),
            "neck": dict(origin=[268.8, -96.0, -320.0], axis=[0.0, -1.0, 0.0]),
        },
    ),
    "monk": dict(
        root="50",
        legs={"hip_r": "50/1", "hip_l": "50/2"},
        arms={"shoulder_r": "50/4", "shoulder_l": "50/5"},
        head="50/6",
        joints={
            "hip_r": dict(origin=[82.0, -52.0, -131.2], axis=[1.0, 0.0, 0.0]),
            "hip_l": dict(origin=[78.0, -52.0, -131.2], axis=[-1.0, 0.0, 0.0]),
            "shoulder_r": dict(origin=[95.552, -87.0, -131.2], axis=[-0.9854, 0.1701, 0.0]),
            "shoulder_l": dict(origin=[64.448, -87.0, -131.2], axis=[0.9854, 0.1701, 0.0]),
            "neck": dict(origin=[80.0, -96.0, -131.2], axis=[0.0, -1.0, 0.0]),
        },
    ),
}


def children(nodes, parent_id):
    return [n for n in nodes if n.get("parent") == parent_id]


def plant_geometry(nodes):
    """Per-plant partition + world geometry, shared by plan authoring and Blender baking."""
    by_id = {n["id"]: n for n in nodes}
    trees, bamboo = {}, {}
    for name, root in TREES.items():
        kids = children(nodes, root)
        assembly = by_id[root]
        gx, gy, gz = assembly["world"][0][3], assembly["world"][1][3], assembly["world"][2][3]
        struct_ids = [n["id"] for n in kids if n["ref"] in STRUCT_REFS]
        soft_ids = [n["id"] for n in kids if n["ref"] not in STRUCT_REFS]
        canopy_base_y = min(n["world"][1][3] for n in kids if n["ref"] in STRUCT_REFS)
        trees[name] = dict(ground=[gx, gy, gz], canopy_base_y=canopy_base_y,
                            struct_ids=struct_ids, soft_ids=soft_ids)
    for name, root in BAMBOO.items():
        kids = children(nodes, root)
        assembly = by_id[root]
        gx, gy, gz = assembly["world"][0][3], assembly["world"][1][3], assembly["world"][2][3]
        bamboo[name] = dict(ground=[gx, gy, gz], all_ids=[n["id"] for n in kids])
    return trees, bamboo


def plant_specs(nodes):
    """{control_name: wind_clips spec dict} for all 15 plant controls (trunk/canopy/bamboo lean)."""
    trees, bamboo = plant_geometry(nodes)
    specs = {}
    for name, g in trees.items():
        gx = g["ground"][0]
        specs[f"{name}_trunk_lean"] = wc.lean(
            f"{name} trunk: + leans the whole tree downwind (+X); flex_approx (stud-stacked trunk, no connector)",
            -wc.FLEX_LIMIT, wc.FLEX_LIMIT, f=0.45, zeta=0.15, gain=0.09, x=gx, swing=(1.0, 0.0), joint=wc.FLEX,
        )
        specs[f"{name}_canopy_sway"] = wc.lean(
            f"{name} canopy: + leans the canopy further downwind relative to the trunk (two_level); flex_approx",
            -wc.FLEX_LIMIT, wc.FLEX_LIMIT, f=0.95, zeta=0.15, gain=0.07, x=gx, swing=(1.0, 0.0), joint=wc.FLEX,
        )
    for name, g in bamboo.items():
        gx = g["ground"][0]
        wind = BAMBOO_WIND[name]
        specs[f"{name}_lean"] = wc.lean(
            f"{name}: + leans the whole culm downwind (+X); flex_approx (stud-stacked, no connector)",
            -wc.FLEX_LIMIT, wc.FLEX_LIMIT, f=wind["f"], zeta=0.15, gain=0.1, x=gx, swing=(1.0, 0.0),
            lag=wind["lag"], joint=wc.FLEX,
        )
    return specs


def add_view(p, name, label, parts=()):
    """Create a stub view (bodies filled in later, once add_joint has created them)."""
    p["mechanisms"][name] = dict(
        label=label, parts=list(parts), bodies=[], inputs=[], outputs=[],
        disposition="unresolved", notes=[], review="",
    )


def finalize_view(p, name, review, bodies):
    """Attach the now-existing bodies to a stub view and mark it planned."""
    view = p["mechanisms"][name]
    view["bodies"] = list(bodies)
    view["disposition"] = "planned"
    view["review"] = review


def main():
    p = contract.load(str(PLAN_PATH))
    nodes = p["source"]["nodes"]
    by_id = {n["id"]: n for n in nodes}

    # --- 1. Disposition the 5 auto-discovered trivial axlehole-plate candidates as static ---
    axlehole_review = (
        "Round 2x2 plate with axlehole (4032a) used decoratively as a lily pad / torii ornament cap; "
        "a single isolated occurrence with no mating axle or attached part. No real mechanism."
    )
    for mech_id, view in list(p["mechanisms"].items()):
        if view.get("disposition", "unresolved") == "unresolved":
            view["disposition"] = "static"
            view["review"] = axlehole_review

    # --- 2. Plant trunk + canopy joints (all flex_approx) ---
    trees, bamboo = plant_geometry(nodes)
    specs = plant_specs(nodes)
    for name, g in trees.items():
        gx, gy, gz = g["ground"]
        struct_ids, soft_ids, canopy_base_y = g["struct_ids"], g["soft_ids"], g["canopy_base_y"]

        add_view(
            p, f"plant_{name}", f"{name.replace('_', ' ').title()}: trunk lean + canopy sway in the breeze",
            parts=struct_ids + soft_ids,
        )
        spec = specs[f"{name}_trunk_lean"]
        p = mechanisms.add_joint(
            p, mechanism=f"plant_{name}", name=f"{name}_trunk_lean", instances=struct_ids,
            origin=[gx, gy, gz], axis=AXIS_LEAN, minimum=spec["min"], maximum=spec["max"],
            description=spec["description"],
        )
        spec2 = specs[f"{name}_canopy_sway"]
        p = mechanisms.add_joint(
            p, mechanism=f"plant_{name}", name=f"{name}_canopy_sway", instances=soft_ids,
            origin=[gx, canopy_base_y, gz], axis=AXIS_LEAN, minimum=spec2["min"], maximum=spec2["max"],
            description=spec2["description"], parent=f"{name}_trunk_lean",
        )
        finalize_view(
            p, f"plant_{name}",
            review=(
                "Trunk is plain stud-stacked round bricks (3941/60474/74611/11213/87580/2417); no ball, clip-bar "
                "or bar-in-hole connector exists anywhere in this submodel. Both joints are flex_approx rigid-tilt "
                "approximations of plastic bending, not real LEGO rotational freedom."
            ),
            bodies=[f"{name}_trunk_lean", f"{name}_canopy_sway"],
        )

    # --- 3. Bamboo culm lean joints (single rigid body per culm, all flex_approx) ---
    for name, g in bamboo.items():
        gx, gy, gz = g["ground"]
        all_ids = g["all_ids"]
        add_view(p, f"plant_{name}", f"Bamboo culm {name}: whole-culm lean in the breeze", parts=all_ids)
        spec = specs[f"{name}_lean"]
        p = mechanisms.add_joint(
            p, mechanism=f"plant_{name}", name=f"{name}_lean", instances=all_ids,
            origin=[gx, gy, gz], axis=AXIS_LEAN, minimum=spec["min"], maximum=spec["max"],
            description=spec["description"],
        )
        finalize_view(
            p, f"plant_{name}",
            review=(
                "Culm is stud-stacked round bricks (3062b) with leafy nodes (30176) rigidly mid-stack and a cone "
                "tip (4589); no ball/clip/bar connector. Single flex_approx lean for the whole rigid culm."
            ),
            bodies=[f"{name}_lean"],
        )

    # --- 4. Minifig joints (real connector-measured revolute joints) ---
    for fig, data in MINIFIGS.items():
        bodies_for_view = [f"{fig}_{jname}" for jname in list(data["legs"]) + list(data["arms"]) + ["neck"]]

        add_view(
            p, f"minifig_{fig}", f"{fig.title()}: hip/shoulder/neck joints (real, connector-measured)",
            parts=[data["legs"]["hip_r"], data["legs"]["hip_l"],
                   data["arms"]["shoulder_r"], data["arms"]["shoulder_l"], data["head"]]
            + ([data["head_extra"]] if "head_extra" in data else []),
        )
        for jname, leaf in data["legs"].items():
            joint = data["joints"][jname]
            p = mechanisms.add_joint(
                p, mechanism=f"minifig_{fig}", name=f"{fig}_{jname}", instances=[leaf],
                origin=joint["origin"], axis=joint["axis"], minimum=-1.6, maximum=1.6,
                description=f"{fig} {jname}: leg about the hip pin; + swings the leg forward (connector-measured)",
            )
        for jname, leaf in data["arms"].items():
            joint = data["joints"][jname]
            p = mechanisms.add_joint(
                p, mechanism=f"minifig_{fig}", name=f"{fig}_{jname}", instances=[leaf],
                origin=joint["origin"], axis=joint["axis"], minimum=-3.0, maximum=3.0,
                description=f"{fig} {jname}: arm about the shoulder socket; + swings forward/up (connector-measured)",
            )
        neck = data["joints"]["neck"]
        neck_instances = [data["head"]] + ([data["head_extra"]] if "head_extra" in data else [])
        p = mechanisms.add_joint(
            p, mechanism=f"minifig_{fig}", name=f"{fig}_neck", instances=neck_instances,
            origin=neck["origin"], axis=neck["axis"], minimum=-1.6, maximum=1.6,
            description=f"{fig} neck: head (+ hat/hair, same origin) yaw about the neck stud (connector-measured)",
        )
        finalize_view(
            p, f"minifig_{fig}",
            review=(
                "Standard minifig hip pins and shoulder/neck sockets, measured via "
                "`./ldraw-mecha connectors` on this model's own hips/torso parts (3815b/973*). Real revolute "
                "joints, not flex_approx. Wrist joints are not used (clips don't move the hands; no accessory "
                "parts exist on these figures)."
            ),
            bodies=bodies_for_view,
        )

    p["notes"].append(
        "Sakura garden: single-breeze wind sway on 4 trees (trunk_lean + canopy_sway, parented) and 7 bamboo "
        "culms (single lean each), all flex_approx (no real connector in any trunk/culm). 3 minifigs (monk, "
        "gardener, visitor) get real connector-measured hip/shoulder/neck joints, driven by bespoke clips in "
        "scripts/build_sakura_garden_clips.py (monk: walk_to_pagoda gait + whole-figure root motion via the "
        "minifig_clips/animate_minifigs SLOT/MOVE pattern; gardener: garden_idle; visitor: watch_koi, deliberately "
        "touching only neck + a barely-there hip rock to preserve her documented 1 LDU bridge-rail clearance). "
        "Everything else (torii, bridge, lanterns, pagoda, boulders, tsukubai, bench, pond, stepping stones, iris, "
        "petals, ground) is untouched and was never flagged as a mechanism candidate by discovery, so it needs no "
        "static view of its own; the 5 axlehole-plate candidates that WERE flagged are decorative lily pads/torii "
        "ornaments, dispositioned static above."
    )

    contract.save(str(PLAN_PATH), p)
    print("Saved", PLAN_PATH)
    print("controls:", len(p["controls"]), "bodies:", len(p["bodies"]), "mechanisms:", len(p["mechanisms"]))


if __name__ == "__main__":
    main()
