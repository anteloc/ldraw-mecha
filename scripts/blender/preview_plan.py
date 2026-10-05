"""Render an evidence image of an existing rig without altering its saved blend."""

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import bpy
from mathutils import Vector
from ldraw_mechanisms import blender as adapter, plan as contract


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--set", action="append", default=[])
    parser.add_argument("--focus", help="Source occurrence ID to frame")
    parser.add_argument("--moving-only", action="store_true")
    parser.add_argument(
        "--hide", help="JSON file whose 'hidden' list names occurrences to hide (e.g. bodywork)"
    )
    parser.add_argument(
        "--view", default="1.15,-1.5,1.05", help="Camera direction in Blender world axes"
    )
    parser.add_argument("--size", default="960x720", help="Resolution WIDTHxHEIGHT")
    parser.add_argument("--samples", type=int, default=24, help="Cycles samples")
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1 :])
    plan = contract.load(args.plan)
    rig = adapter.context_from_scene(plan)
    if args.moving_only:
        adapter.set_moving_only(rig)
    if args.hide:
        adapter.set_hidden(rig, json.loads(Path(args.hide).read_text())["hidden"])
    included = set(rig["root"].children_recursive)
    for obj in bpy.context.scene.objects:
        if obj.type == "MESH" and obj not in included:
            obj.hide_render = True
    with adapter.preserve_controls(rig):
        adapter.set_controls(
            rig, **{k: float(v) for s in args.set for k, v in [s.split("=", 1)]}
        )
        root = rig["mapping"][args.focus] if args.focus else rig["root"]
        meshes = [o for o in root.children_recursive if o.type == "MESH"]
        # Moving parts are reparented; focus bounds include all selected source descendants.
        if args.focus:
            for n in plan["source"]["nodes"]:
                if n["kind"] == "part" and n["id"].startswith(args.focus + "/"):
                    meshes.extend(
                        o
                        for o in rig["mapping"][n["id"]].children_recursive
                        if o.type == "MESH"
                    )
        pts = [
            o.matrix_world @ Vector(c)
            for o in set(meshes)
            if not o.hide_render
            for c in o.bound_box
        ]
        lo = Vector([min(v[i] for v in pts) for i in range(3)])
        hi = Vector([max(v[i] for v in pts) for i in range(3)])
        center = (lo + hi) * 0.5
        size = max(hi - lo)
        scene = bpy.context.scene
        camera = bpy.data.objects.new(
            "EvidenceCamera", bpy.data.cameras.new("EvidenceCamera")
        )
        scene.collection.objects.link(camera)
        view = Vector([float(v) for v in args.view.split(",")])
        camera.location = center + view * size
        camera.rotation_euler = (
            (center - camera.location).to_track_quat("-Z", "Y").to_euler()
        )
        camera.data.type = "ORTHO"
        camera.data.ortho_scale = size * 1.5
        camera.data.clip_start = 0.001
        scene.camera = camera
        for name, offset, energy in [("Key", (1, -1, 2), 80), ("Fill", (-1, 0, 1), 40)]:
            light = bpy.data.objects.new(name, bpy.data.lights.new(name, "AREA"))
            scene.collection.objects.link(light)
            light.location = center + Vector(offset) * size
            light.data.energy = energy * size * size
            light.data.shape = "DISK"
            light.data.size = size
            light.rotation_euler = (
                (center - light.location).to_track_quat("-Z", "Y").to_euler()
            )
        scene.world = bpy.data.worlds.new("EvidenceWorld")
        scene.world.use_nodes = True
        scene.world.node_tree.nodes["Background"].inputs["Color"].default_value = (
            0.16,
            0.18,
            0.23,
            1,
        )
        scene.world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.6
        scene.render.engine = "CYCLES"
        scene.cycles.device = "CPU"
        scene.cycles.samples = args.samples
        width, height = (int(v) for v in args.size.split("x"))
        scene.render.resolution_x = width
        scene.render.resolution_y = height
        scene.render.resolution_percentage = 100
        scene.render.image_settings.file_format = "PNG"
        scene.render.filepath = str(Path(args.output).resolve())
        bpy.ops.render.render(write_still=True)


if __name__ == "__main__":
    main()
