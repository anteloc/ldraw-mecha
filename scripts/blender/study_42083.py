"""Background study of one 42083 plan: build the rig, optional sampled clearance, posed renders.

    Blender --background --factory-startup --python scripts/blender/study_42083.py -- \
        --plan PLAN --glb GLB [--clearance door_left door_right --steps 35 --report R.json] \
        [--pose NAME:ctrl=v,ctrl=v ...] [--outdir DIR] [--focus moving|all] [--view x,y,z]

Renders are evidence images only; nothing is saved to a .blend.
"""

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import bpy  # noqa: E402
from mathutils import Vector  # noqa: E402

from ldraw_mechanisms import blender as adapter, blender_tools as tools, plan as contract  # noqa: E402


def frame_camera(objs, view, scene, margin=1.25):
    pts = [o.matrix_world @ Vector(c) for o in objs if o.type == "MESH" for c in o.bound_box]
    lo = Vector([min(p[i] for p in pts) for i in range(3)])
    hi = Vector([max(p[i] for p in pts) for i in range(3)])
    centre, size = (lo + hi) / 2, max(hi - lo)
    cam = scene.camera
    if cam is None:
        cam = bpy.data.objects.new("StudyCamera", bpy.data.cameras.new("StudyCamera"))
        scene.collection.objects.link(cam)
        scene.camera = cam
    cam.location = centre + Vector(view).normalized() * size * 2.2
    cam.rotation_euler = (centre - cam.location).to_track_quat("-Z", "Y").to_euler()
    cam.data.type = "ORTHO"
    cam.data.ortho_scale = size * margin
    cam.data.clip_start = 0.001
    cam.data.clip_end = 100
    return centre, size


def lights(scene, centre, size):
    for name, offset, energy in (("Key", (1, -1, 2), 80), ("Fill", (-1, 0.6, 1), 35), ("Back", (0, 1.5, 1), 25)):
        light = bpy.data.objects.new(name, bpy.data.lights.new(name, "AREA"))
        scene.collection.objects.link(light)
        light.location = centre + Vector(offset) * size
        light.data.energy = energy * size * size
        light.data.size = size
        light.rotation_euler = (centre - light.location).to_track_quat("-Z", "Y").to_euler()
    scene.world = bpy.data.worlds.new("StudyWorld")
    scene.world.use_nodes = True
    bg = scene.world.node_tree.nodes["Background"]
    bg.inputs["Color"].default_value = (0.16, 0.18, 0.23, 1)
    bg.inputs["Strength"].default_value = 0.7


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan", required=True)
    ap.add_argument("--glb", required=True)
    ap.add_argument("--clearance", nargs="*", default=[])
    ap.add_argument("--steps", type=int, default=17)
    ap.add_argument("--report")
    ap.add_argument("--pose", action="append", default=[])
    ap.add_argument("--outdir")
    ap.add_argument("--focus", default="moving")
    ap.add_argument("--view", default="1.1,-1.4,0.9")
    ap.add_argument("--size", default="1000x750")
    ap.add_argument("--samples", type=int, default=16)
    ap.add_argument("--tolerance", type=float, default=0.01)
    ap.add_argument("--hide", help="Comma-separated source IDs to hide in renders")
    ap.add_argument("--focus-ids", help="Comma-separated source IDs to frame (overrides --focus)")
    ap.add_argument("--margin", type=float, default=1.25)
    a = ap.parse_args(sys.argv[sys.argv.index("--") + 1:])
    plan = contract.load(a.plan)
    result = tools.apply_plan(plan, glb=a.glb, new_scene=True, tolerance=a.tolerance)
    rig = result["rig"]
    print("MECHA_STUDY_VERIFY", result["report"]["passed"])
    if a.clearance:
        report = tools.check_clearance(plan, rig=rig, controls=a.clearance, steps=a.steps, report=a.report)
        print("MECHA_CLEARANCE", report["no_new_surface_crossings"])
    if not a.pose:
        return
    scene = bpy.context.scene
    owned = {i for b in plan["bodies"].values() for i in b["instances"]}
    if a.hide:
        adapter.set_hidden(rig, [i for i in a.hide.split(",") if i])
    if a.focus_ids:
        focus = [rig["mapping"][i] for i in a.focus_ids.split(",") if i]
    else:
        focus = [rig["mapping"][i] for i in owned] if a.focus == "moving" else [rig["root"]]
    objs = [m for o in focus for m in ([o] + list(o.children_recursive)) if m.type == "MESH"]
    centre, size = frame_camera(objs, [float(v) for v in a.view.split(",")], scene, a.margin)
    lights(scene, centre, size)
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = a.samples
    w, h = (int(v) for v in a.size.split("x"))
    scene.render.resolution_x, scene.render.resolution_y = w, h
    scene.render.image_settings.file_format = "PNG"
    out = Path(a.outdir)
    out.mkdir(parents=True, exist_ok=True)
    with adapter.preserve_controls(rig):
        for spec in a.pose:
            name, _, body = spec.partition(":")
            values = {k: float(v) for k, v in (kv.split("=") for kv in body.split(",") if kv)}
            adapter.set_controls(rig, **{k: c["default"] for k, c in plan["controls"].items()})
            adapter.set_controls(rig, **values)
            bpy.context.view_layer.update()
            scene.render.filepath = str((out / f"{name}.png").resolve())
            bpy.ops.render.render(write_still=True)
            print("MECHA_RENDER", scene.render.filepath)


if __name__ == "__main__":
    main()
