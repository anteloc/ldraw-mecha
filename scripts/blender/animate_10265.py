"""Keyframe the 10265 rig controls into a demo clip and verify sampled frames.

blender --background --python scripts/blender/animate_10265.py -- \
  --blend output/10265/rigged.blend --plan output/10265/plan.ready.json \
  --save output/10265/animated.blend

front_steer is deliberately not keyed: its tie-rod linkage is unresolved and the
sampled clearance check fails (see plan notes). Only roll and the steering
wheel/gear train are animated.
"""

import argparse
import math
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import bpy
from ldraw_mechanisms import blender as adapter, plan as contract

FPS, END = 24, 144
# frame: (roll, steering_wheel)
KEYS = {
    1: (0.0, 0.0),
    36: (4 * math.pi, math.pi),
    72: (8 * math.pi, 0.0),
    108: (12 * math.pi, -math.pi),
    144: (16 * math.pi, 0.0),
}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--blend", required=True)
    parser.add_argument("--plan", required=True)
    parser.add_argument("--save", required=True)
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1 :])
    bpy.ops.wm.open_mainfile(filepath=str(Path(args.blend).resolve()))
    plan = contract.load(args.plan)
    rig = adapter.context_from_scene(plan)
    ctrl = rig["controller"]
    scene = bpy.context.scene
    scene.render.fps = FPS
    scene.frame_start, scene.frame_end = 1, END
    for frame, values in KEYS.items():
        for name, value in zip(("roll", "steering_wheel"), values):
            ctrl[name] = float(value)
            ctrl.keyframe_insert(f'["{name}"]', frame=frame)
    errors = []
    for frame in (1, 36, 72, 108, 144):
        scene.frame_set(frame)
        bpy.context.view_layer.update()
        report = adapter.verify(rig, plan, samples=[dict(
            roll=ctrl["roll"], steering_wheel=ctrl["steering_wheel"])])
        if not report["passed"]:
            errors.append(f"frame {frame}: {report['samples']}")
    scene.frame_set(1)
    if errors:
        raise SystemExit("\n".join(errors))
    bpy.ops.wm.save_as_mainfile(filepath=str(Path(args.save).resolve()))
    print("ANIMATION_OK", args.save)


main()
