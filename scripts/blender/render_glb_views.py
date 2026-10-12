"""Render design-review views of a bound GLB in background Blender (no rig, nothing saved).

    "$BLENDER_BIN" -b --factory-startup --python scripts/blender/render_glb_views.py -- \
        --glb output/8448-mecha/car-study/model.glb --output output/8448-mecha/renders/car \
        --views front,side,back,threequarter,top [--highlight ids.json] [--engine eevee|cycles]

`--highlight` is a JSON object {label: [occurrence IDs]}: listed parts keep their colours, everything else is
drawn as translucent grey, so module selections can be checked against the source. `--only` (same format)
hides everything that is not listed. Views are named camera directions in LDraw terms (-Y up, -Z front).
"""

import argparse
import json
import math
from pathlib import Path
import sys

import bpy
from mathutils import Vector

VIEWS = {  # Blender world directions from the target to the camera (Blender: Z up; LDraw -Z front -> Blender +Y?)
    "front": (0.0, -1.0, 0.25),
    "back": (0.0, 1.0, 0.25),
    "side": (1.0, 0.0, 0.2),
    "left": (-1.0, 0.0, 0.2),
    "threequarter": (0.9, -1.1, 0.6),
    "threequarter_back": (-0.9, 1.1, 0.6),
    "top": (0.0, -0.05, 1.0),
}


def args():
    ap = argparse.ArgumentParser()
    ap.add_argument("--glb", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--views", default="front,side,threequarter")
    ap.add_argument("--highlight")
    ap.add_argument("--only")
    ap.add_argument("--each", help="JSON {name: [ids]}: render every group alone into OUTPUT/name-VIEW.png")
    ap.add_argument("--engine", default="eevee")
    ap.add_argument("--size", default="1200x900")
    ap.add_argument("--samples", type=int, default=32)
    ap.add_argument("--flip-front", action="store_true", help="Swap front/back if the model faces +Y")
    return ap.parse_args(sys.argv[sys.argv.index("--") + 1:])


def main():
    a = args()
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=str(Path(a.glb).resolve()))
    scene = bpy.context.scene
    meshes = [o for o in scene.objects if o.type == "MESH"]
    ids = {}
    for o in scene.objects:
        mid = o.get("mecha_id")
        if mid is not None:
            ids.setdefault(str(mid), []).append(o)

    def descendants(objs):
        out = set()
        for o in objs:
            out.add(o)
            out.update(o.children_recursive)
        return out

    if a.only:
        keep = set()
        for lst in json.loads(Path(a.only).read_text()).values():
            for i in lst:
                keep |= descendants(ids.get(str(i), []))
        for o in meshes:
            o.hide_render = o not in keep
    if a.highlight:
        ghost = bpy.data.materials.new("Ghost")
        ghost.use_nodes = True
        bsdf = ghost.node_tree.nodes.get("Principled BSDF")
        bsdf.inputs["Base Color"].default_value = (0.75, 0.75, 0.78, 1)
        bsdf.inputs["Alpha"].default_value = 0.12
        keep = set()
        for lst in json.loads(Path(a.highlight).read_text()).values():
            for i in lst:
                keep |= descendants(ids.get(str(i), []))
        for o in meshes:
            if o not in keep:
                o.data = o.data.copy()
                for slot in range(len(o.data.materials)):
                    o.data.materials[slot] = ghost
    setup(scene, a)
    out = Path(a.output)
    out.mkdir(parents=True, exist_ok=True)
    if a.each:
        groups = json.loads(Path(a.each).read_text())
        for gname, lst in groups.items():
            keep = set()
            for i in lst:
                keep |= descendants(ids.get(str(i), []))
            for o in meshes:
                o.hide_render = o not in keep
            shoot(scene, a, [o for o in meshes if not o.hide_render], out, gname + "-")
    else:
        shoot(scene, a, [o for o in meshes if not o.hide_render], out, "")


def setup(scene, a):
    cam = bpy.data.objects.new("Cam", bpy.data.cameras.new("Cam"))
    scene.collection.objects.link(cam)
    scene.camera = cam
    cam.data.type = "ORTHO"
    cam.data.clip_start = 0.001
    cam.data.clip_end = 100
    world = bpy.data.worlds.new("W")
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs[0].default_value = (0.92, 0.93, 0.95, 1)
    world.node_tree.nodes["Background"].inputs[1].default_value = 0.9
    scene.world = world
    for name, d, e in (("Key", (1.5, -1.5, 2.5), 6.0), ("Fill", (-2, -0.5, 1.0), 2.5), ("Rim", (0.3, 2.0, 1.5), 3.0)):
        light = bpy.data.objects.new(name, bpy.data.lights.new(name, "SUN"))
        light.data.energy = e
        scene.collection.objects.link(light)
        light.rotation_euler = (Vector(d)).to_track_quat("Z", "Y").to_euler()
    w, h = (int(v) for v in a.size.split("x"))
    scene.render.resolution_x, scene.render.resolution_y = w, h
    if a.engine == "cycles":
        scene.render.engine = "CYCLES"
        scene.cycles.samples = a.samples
        scene.cycles.use_denoising = True
    else:
        scene.render.engine = "BLENDER_EEVEE"
        try:
            scene.eevee.taa_render_samples = a.samples
        except AttributeError:
            pass
    scene.render.film_transparent = False
    scene.view_settings.view_transform = "Standard"


def shoot(scene, a, visible, out, prefix):
    cam = scene.camera
    pts = [o.matrix_world @ Vector(c) for o in visible for c in o.bound_box]
    if not pts:
        return
    lo = Vector([min(p[i] for p in pts) for i in range(3)])
    hi = Vector([max(p[i] for p in pts) for i in range(3)])
    center, size = (lo + hi) / 2, max(hi - lo)
    for name in a.views.split(","):
        d = Vector(VIEWS[name])
        if a.flip_front:
            d.y = -d.y
        cam.location = center + d.normalized() * size * 3
        cam.rotation_euler = (center - cam.location).to_track_quat("-Z", "Y").to_euler()
        cam.data.ortho_scale = size * 1.08
        scene.render.filepath = str((out / f"{prefix}{name}.png").resolve())
        bpy.ops.render.render(write_still=True)
        print("WROTE", scene.render.filepath)

main()
