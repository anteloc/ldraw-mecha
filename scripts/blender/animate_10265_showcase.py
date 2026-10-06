"""Keyframe the 10265 B-model rig into a showcase clip and verify every key frame.

blender --background --python scripts/blender/animate_10265_showcase.py -- \
  --blend output/10265-v2/rigged.blend --plan output/10265-v2/plan.json \
  --save output/10265-v2/animated.blend

This clip targets the studied 10265 CLI recipe. The steering wheel
drives the universal joint, the 16T/40T mesh, the crank, both steering links and
both knuckles, so the front wheels actually turn. The declared travel is small
because the source packs the crank tightly; see the plan notes and clearance
report. The four wheels roll through several full turns, which is the only
motion the sampled clearance check reports as clean.
"""

import argparse
import math
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import bpy
from ldraw_mechanisms import blender as adapter, plan as contract

FPS, END = 24, 192
ROLL = 6 * math.pi
STEER = 0.18
VALVE = 0.15
# frame: steering, valve_covers, and the shared rolling angle for all wheels.
KEYS = {
    1: (0.0, 0.0, 0.0),
    48: (STEER, 0.0, ROLL * 0.25),
    96: (0.0, 0.0, ROLL * 0.5),
    144: (-STEER, 0.0, ROLL * 0.75),
    168: (0.0, VALVE, ROLL),
    192: (0.0, 0.0, ROLL),
}
WHEELS = ("spin_fl", "spin_fr", "spin_rl", "spin_rr")


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
    for frame, (steering, valve, roll) in KEYS.items():
        # Wheel controls are clamped to one turn, so roll is wrapped rather
        # than accumulated; the clip shows rotation, not distance travelled.
        wrapped = (roll + math.pi) % (2 * math.pi) - math.pi
        values = dict(steering=steering, valve_covers=valve)
        values.update({name: wrapped for name in WHEELS})
        for name, value in values.items():
            ctrl[name] = float(value)
            ctrl.keyframe_insert(f'["{name}"]', frame=frame)
    errors = []
    for frame in sorted(KEYS):
        scene.frame_set(frame)
        bpy.context.view_layer.update()
        sample = {name: ctrl[name] for name in plan["controls"]}
        report = adapter.verify(rig, plan, samples=[sample])
        if not report["passed"]:
            errors.append(f"frame {frame}: {report['samples']}")
    scene.frame_set(1)
    if errors:
        raise SystemExit("\n".join(errors))
    bpy.ops.wm.save_as_mainfile(filepath=str(Path(args.save).resolve()))
    print("ANIMATION_OK", args.save)


main()
