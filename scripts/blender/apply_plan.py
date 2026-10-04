"""Headless entry point; the implementation lives in the shared Python package."""

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import bpy
from mathutils import Vector
from ldraw_mechanisms import plan as contract
from ldraw_mechanisms import blender as adapter


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", required=True)
    parser.add_argument("--glb")
    parser.add_argument("--save")
    parser.add_argument("--report")
    parser.add_argument("--verify-existing", action="store_true")
    parser.add_argument("--animate", action="store_true")
    parser.add_argument(
        "--new-scene",
        action="store_true",
        help="Explicitly start an empty scene before importing",
    )
    args = parser.parse_args(
        sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    )
    plan = contract.load(args.plan)
    if args.new_scene:
        if not args.glb:
            raise ValueError("--new-scene requires --glb")
        bpy.ops.wm.read_factory_settings(use_empty=True)
    if args.glb:
        bpy.ops.import_scene.gltf(filepath=str(Path(args.glb).resolve()))
    rig = (
        adapter.context_from_scene(plan)
        if args.verify_existing
        else adapter.build(plan)
    )
    samples = [{}]
    for name, c in plan["controls"].items():
        for v in (c["min"], (c["min"] + c["max"]) / 2, c["max"]):
            samples.append({name: v})
    if "spin_rl" in plan["controls"]:
        samples += [dict(spin_rl=0.7, spin_rr=-0.2, steering=0.4)]
    result = adapter.verify(rig, plan, samples)
    if args.report:
        contract.save(args.report, result)
    if not result["passed"]:
        raise RuntimeError("Blender verification failed: " + str(result))
    if args.animate:
        ctrl = rig["controller"]
        for name, c in plan["controls"].items():
            for frame, value in [
                (1, c["default"]),
                (40, c["max"]),
                (80, c["min"]),
                (120, c["default"]),
            ]:
                ctrl[name] = float(value)
                ctrl.keyframe_insert(data_path=f'["{name}"]', frame=frame)
        bpy.context.scene.frame_end = 120
        bpy.context.scene.frame_set(1)
    if args.save:
        # Save a useful initial viewport as well as the rig and active controller.
        points = [
            o.matrix_world @ Vector(c)
            for o in rig["root"].children_recursive
            if o.type == "MESH"
            for c in o.bound_box
        ]
        if points:
            lo = Vector([min(p[i] for p in points) for i in range(3)])
            hi = Vector([max(p[i] for p in points) for i in range(3)])
            for screen in bpy.data.screens:
                for area in screen.areas:
                    if area.type == "VIEW_3D":
                        view = area.spaces.active.region_3d
                        view.view_location = (lo + hi) * 0.5
                        view.view_distance = max(hi - lo) * 1.8
                        view.view_rotation = Vector((1.15, -1.5, 1.05)).to_track_quat(
                            "Z", "Y"
                        )
        bpy.ops.wm.save_as_mainfile(filepath=str(Path(args.save).resolve()))
    print("MECHA_RESULT", result)


if __name__ == "__main__":
    main()
