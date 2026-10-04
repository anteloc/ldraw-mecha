"""Key the controls of the built 10265 rig into a short demonstration animation.

Run in a Blender session that already holds the rig (for example rigged.blend):

    blender --background rigged.blend --python scripts/blender/animate_mustang.py -- \
        --plan output/10265-v3/plan.json --save output/10265-v3/animated.blend \
        --report output/10265-v3/animation-check.json

Only plan controls are keyed, so every frame is an input the portable evaluator
accepts. Wheels roll by distance / tyre radius measured from the imported tyre.
"""

import argparse
import math
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import bpy
from ldraw_mechanisms import blender as adapter, plan as contract

FRAMES = 192


def smooth(u):
    u = min(max(u, 0.0), 1.0)
    return u * u * (3 - 2 * u)


def tyre_radius_ldu(rig, tyre_id):
    obj = rig["mapping"][tyre_id]
    meshes = [obj] if obj.type == "MESH" else []
    meshes += [o for o in obj.children_recursive if o.type == "MESH"]
    from mathutils import Vector

    zs = [(m.matrix_world @ Vector(c)).z for m in meshes for c in m.bound_box]
    scale = rig["root"].matrix_world.to_scale()[0]
    return (max(zs) - min(zs)) / 2 / scale


def key(ctrl, name, frame, value):
    ctrl[name] = float(value)
    ctrl.keyframe_insert(data_path=f'["{name}"]', frame=frame)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", required=True)
    parser.add_argument("--save", required=True)
    parser.add_argument("--report", required=True)
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1 :])
    plan = contract.load(args.plan)
    rig = adapter.context_from_scene(plan)
    ctrl = rig["controller"]
    if ctrl.animation_data:
        ctrl.animation_data_clear()
    radius = tyre_radius_ldu(rig, "0/454")
    turns = 6
    travel = turns * 2 * math.pi * radius
    scene = bpy.context.scene
    scene.render.fps = 24
    scene.frame_start, scene.frame_end = 1, FRAMES
    limits = {k: (c["min"], c["max"]) for k, c in plan["controls"].items()}
    for name in plan["controls"]:
        key(ctrl, name, 1, plan["controls"][name]["default"])
    # Rolling: all four wheels share the same distance profile; the rear worm shaft is separate.
    for frame in range(1, FRAMES + 1, 6):
        u = smooth((frame - 1) / (FRAMES - 1))
        for w in ("fl", "fr", "rl", "rr"):
            key(ctrl, "spin_" + w, frame, travel * u / radius)
        key(ctrl, "rear_shaft", frame, 4 * 2 * math.pi * u)
    key(ctrl, "spin_fl", FRAMES, turns * 2 * math.pi)
    key(ctrl, "spin_fr", FRAMES, turns * 2 * math.pi)
    key(ctrl, "spin_rl", FRAMES, turns * 2 * math.pi)
    key(ctrl, "spin_rr", FRAMES, turns * 2 * math.pi)
    key(ctrl, "rear_shaft", FRAMES, 4 * 2 * math.pi)
    lock = limits["steering_wheel"][1]
    for frame, v in [(1, 0), (36, lock), (84, -lock), (132, 0.5 * lock), (FRAMES, 0)]:
        key(ctrl, "steering_wheel", frame, v)
    lever = limits["gear_lever"][1]
    for frame, v in [(1, 0), (20, -lever), (50, lever), (80, 0), (FRAMES, 0)]:
        key(ctrl, "gear_lever", frame, v)
    low = limits["spoiler"][0]
    for frame, v in [(1, 0), (100, 0), (130, low), (160, low), (FRAMES - 2, 0), (FRAMES, 0)]:
        key(ctrl, "spoiler", frame, v)
    action = ctrl.animation_data.action
    fcurves = []
    if hasattr(action, "layers"):
        for layer in action.layers:
            for strip in layer.strips:
                for slot in action.slots:
                    channelbag = strip.channelbag(slot)
                    if channelbag:
                        fcurves += list(channelbag.fcurves)
    else:
        fcurves = list(action.fcurves)
    for fc in fcurves:
        name = fc.data_path.split('"')[1]
        if name.startswith(("spin_", "rear_shaft")):
            for kp in fc.keyframe_points:
                kp.interpolation = "LINEAR"
    scene.frame_set(1)
    samples = []
    for frame in (1, 36, 84, 100, 132, 145, 170, FRAMES):
        scene.frame_set(frame)
        values = {k: float(ctrl[k]) for k in plan["controls"]}
        check = adapter.verify(rig, plan, [values])
        samples.append(dict(frame=frame, controls=values, passed=check["passed"], detail=check["samples"][0]))
    scene.frame_set(1)
    contract.save(
        args.report,
        dict(
            passed=all(s["passed"] for s in samples),
            tyre_radius_ldu=radius,
            travel_ldu=travel,
            frames=FRAMES,
            fps=24,
            keyed_controls=sorted(plan["controls"]),
            samples=samples,
            coverage="Keys are plan controls only; sampled frames re-evaluated against the portable evaluator; no collision test of the whole sequence",
        ),
    )
    Path(args.save).resolve().parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(Path(args.save).resolve()))
    print("MECHA_ANIMATION", all(s["passed"] for s in samples), radius)


if __name__ == "__main__":
    main()
