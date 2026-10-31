#!/usr/bin/env python3
"""Author the motion plan for set 3625 (Fabuland sea-gull plane and pilot) on a prepared study.

    ./ldraw-mecha prepare output/3625-source/3625-1-split.mpd --output output/3625
    .venv/bin/python scripts/build_plane_3625.py output/3625/plan.json

The split source turns the 4616ac01 and 4613c01 shortcuts into assemblies, so the propeller (3/1) and the two
wheels (0/1, 0/2) are separate physical occurrences. Everything else is static in the source frame; whole-model
staging (climb, bank, lift) is a root transform added by `scripts/blender/animate_plane_3625.py`.
"""

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ldraw_mechanisms import plan as contract  # noqa: E402

# Joint channels: (control, signal-less limits, description).
PROP_RANGE = 1000.0
WHEEL_RANGE = 1000.0

CONTROLS = {
    "prop": (-PROP_RANGE, PROP_RANGE, "Propeller angle about the nose axis; + is clockwise seen from behind"),
    "wheel": (-WHEEL_RANGE, WHEEL_RANGE, "Both main wheels about the axle; + rolls the plane forward"),
    "head": (-1.2, 1.2, "Pilot head yaw about the neck; + looks to the plane's left"),
    "arm_l": (-0.6, 0.6, "Pilot left arm about the shoulder; + swings the hand forward and up"),
    "arm_r": (-0.6, 0.6, "Pilot right arm about the shoulder; + swings the hand forward and up"),
}

# Measured from the source (LDU, LDraw frame: forward -Z, left +X, up -Y).
BODIES = {
    "propeller": dict(instances=["3/1"], origin=[0, -32, -130], axis=[0, 0, -1], signal="prop"),
    "wheel_l": dict(instances=["0/1"], origin=[46, 30, 0], axis=[1, 0, 0], signal="wheel"),
    "wheel_r": dict(instances=["0/2"], origin=[-46, 30, 0], axis=[1, 0, 0], signal="wheel"),
    "head": dict(instances=["6/0"], origin=[0, -56, 14], axis=[0, -1, 0], signal="head"),
    "arm_l": dict(instances=["6/2"], origin=[23, -52, 14], axis=[-1, 0, 0], signal="arm_l"),
    "arm_r": dict(instances=["6/3"], origin=[-23, -52, 14], axis=[-1, 0, 0], signal="arm_r"),
}


def author(path):
    plan = contract.load(path)
    plan["controls"] = {
        name: {"default": 0.0, "min": lo, "max": hi, "unit": "radian", "description": text}
        for name, (lo, hi, text) in CONTROLS.items()
    }
    plan["signals"] = {
        name: {"expression": f"clamp(a,{lo},{hi})", "variables": {"a": f"control:{name}"}}
        for name, (lo, hi, _) in CONTROLS.items()
    }
    plan["bodies"] = {name: dict(kind="revolute", **body) for name, body in BODIES.items()}
    plan["anchors"] = {}
    plan["checks"] = [
        {"kind": "coaxial", "name": "propeller_on_pin",
         "a": {"instance": "3/1", "point": [0, 0, 0], "axis": [0, 0, 1], "span": [-9, 9]},
         "b": {"instance": "3/2", "point": [0, 0, 2], "axis": [0, 0, 1], "span": [-12, 42]},
         "tolerance_ldu": 0.02, "tolerance_degrees": 0.1, "axial_tolerance_ldu": 0.02, "min_overlap_ldu": 8},
    ]
    plan["mechanisms"] = {
        "propeller": dict(label="Propeller on the cowling pin", parts=["3/1", "3/2"], bodies=["propeller"],
                          inputs=["control:prop"], outputs=["body:propeller"], disposition="planned", review="Spin about the pin axis is authored; blade/cowling clearance checked in Blender.", notes=[
            "4617a spins about the nose axis through the 2344 pin at (0,-32,-132); the pin (3/2) and cowling "
            "brick (3/0) stay fixed. Three identical blades, so the pose repeats every 2*pi/3."]),
        "wheels": dict(label="Main wheels on stub axles", parts=["0/1", "0/2"], bodies=["wheel_l", "wheel_r"],
                       inputs=["control:wheel"], outputs=["body:wheel_l", "body:wheel_r"], disposition="planned", review="Axle X confirmed from stub-axle placement at x=+-46.", notes=[
            "u9167 wheels at x=+-46 turn about the X axle at y=30. One control drives both; + rolls forward (-Z). "
            "No ground contact: the plane stays in place, so wheel angle is authored, not rolling-without-slip."]),
        "airframe": dict(label="Static airframe, tail, window and exhausts", parts=["0/0", "3/0", "4", "7", "8"],
                         bodies=[], inputs=[], outputs=[], disposition="static", notes=[
            "Fixed in the source frame; they only move with the whole-model staging transform."],
                         review="No articulation in the set: base, cowling brick, window, tail and twin exhausts are rigid."),
        "pilot": dict(label="Pilot head and arms", parts=["6/0", "6/2", "6/3"], bodies=["head", "arm_l", "arm_r"],
                      inputs=["control:head", "control:arm_l", "control:arm_r"], outputs=["body:head", "body:arm_l", "body:arm_r"], disposition="planned", review="Pivots from the neck stud and shoulder cylinders; legs deferred.", notes=[
            "Fabuland figure: neck yaw about the vertical through (0,-56,14); arms swing about the X shoulder pins "
            "at (+-23,-52,14), starting 60 degrees forward of vertical in the source. Legs (6/4, 6/5) and the hips "
            "hinge (6/6) are deferred: the legs sit inside the cockpit box (4461) and the story needs no pedals."]),
    }
    plan["notes"] = [
        "3625 Fabuland plane and pilot. Source is the split derivative output/3625-source/3625-1-split.mpd of "
        "data/models-annotated/3625-1.mpd (4616ac01 and 4613c01 shortcuts expanded; original untouched).",
        "Joint axes were taken from part geometry and xray-confirmed pivots, not from local matrix columns. "
        "Whole-model climb/bank/lift staging is a root transform, not a plan body: see "
        "scripts/blender/animate_plane_3625.py.",
        "Static: fuselage, cockpit box, window, tail, exhaust pipes, torso, legs, hips hinge, pin 2344.",
    ]
    plan["status"] = "ready"
    contract.save(path, plan)
    return plan


if __name__ == "__main__":
    plan = author(sys.argv[1])
    print(json.dumps({k: len(v) for k, v in plan.items() if isinstance(v, (dict, list))}))
