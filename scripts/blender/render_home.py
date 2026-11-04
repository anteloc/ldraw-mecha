"""Render one "home" still of a .blend for web publishing: everything visible, framed in perspective.

    "$BLENDER_BIN" -b --factory-startup FILE.blend --python-exit-code 1 \
        --python scripts/blender/render_home.py -- --output NAME.png [--size 1600x1200] [--samples 128]

Like pressing Home (Frame All) in the viewport, from a three-quarter view above the front-right
(the same direction as render_glb_views.py "threequarter"). It renders the file's active scene at
its saved frame, with the objects that are visible and renderable there (hidden bodywork stays
hidden). Flat sheets, such as catalog floors, render but don't count for the framing.

Every sample gets the same studio look, whatever lights the file has:
- Cycles, denoised, on the GPU when there is one;
- soft key, fill and rim sun lights (scale-free) with real shadows; the file's own lights are off;
- a mid-grey backdrop, so white and black parts both stand out, with a shadow catcher on the
  ground, so the model casts a contact shadow onto the backdrop;
- AgX colour management, which keeps bright parts from clipping to white.
The output is an 8-bit RGB PNG. The .blend is never saved.
"""

import argparse
import math
import sys

import bpy
from mathutils import Vector

DIRECTION = Vector((0.9, -1.1, 0.6))  # from the model towards the camera (Blender Z up, front -Y)
MARGIN = 1.08  # breathing room around the framed bounds
BACKDROP = (0.30, 0.32, 0.35)  # linear RGB: a mid, slightly cool grey (about #959aa0 on screen)
# Sun lights: (name, elevation, azimuth around the model, strength, angular size), in degrees.
# Azimuth is measured from the camera's side, so the key light always comes from front-left.
SUNS = (("Key", 50, -40, 3.0, 12), ("Fill", 25, 70, 0.8, 30), ("Rim", 35, 160, 1.6, 8))


def args():
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", required=True)
    ap.add_argument("--size", default="1600x1200")
    ap.add_argument("--samples", type=int, default=128)
    return ap.parse_args(sys.argv[sys.argv.index("--") + 1:])


def use_gpu(scene):
    """Cycles on the first GPU backend that has a device, else the CPU."""
    prefs = bpy.context.preferences.addons["cycles"].preferences
    for backend in ("METAL", "OPTIX", "CUDA", "HIP", "ONEAPI"):
        try:
            prefs.compute_device_type = backend
        except TypeError:
            continue
        prefs.get_devices()
        gpus = [d for d in prefs.devices if d.type == backend]
        if gpus:
            for d in prefs.devices:
                d.use = d.type == backend
            scene.cycles.device = "GPU"
            return gpus[0].name
    scene.cycles.device = "CPU"
    return "CPU"


def main():
    a = args()
    scene = bpy.context.scene
    layer = bpy.context.view_layer
    depsgraph = bpy.context.evaluated_depsgraph_get()
    shown = [o for o in scene.objects if o.visible_get(view_layer=layer) and not o.hide_render]
    geometry = [o for o in shown if o.type in {"MESH", "CURVE", "SURFACE", "META", "FONT"}]
    boxes = []
    for o in geometry:
        e = o.evaluated_get(depsgraph)
        box = [e.matrix_world @ Vector(c) for c in e.bound_box]
        extent = [max(p[i] for p in box) - min(p[i] for p in box) for i in range(3)]
        boxes.append((box, extent[2] < 0.005 * max(extent)))
    if not boxes:
        raise SystemExit("render_home: no visible geometry in scene " + scene.name)
    # Frame the models, not catalog floors or text labels: flat sheets still render, but are left
    # out of the framing (unless the scene has nothing else).
    corners = [p for box, flat in boxes if not flat for p in box] or [p for box, _ in boxes for p in box]
    lo = Vector([min(p[i] for p in corners) for i in range(3)])
    hi = Vector([max(p[i] for p in corners) for i in range(3)])
    center = (lo + hi) / 2
    radius = (hi - lo).length
    ground = min(p.z for box, _ in boxes for p in box)

    # Camera: aim at the centre of the bounds, then back off until every corner is in the frame.
    w, h = (int(v) for v in a.size.split("x"))
    scene.render.resolution_x, scene.render.resolution_y = w, h
    scene.render.resolution_percentage = 100
    scene.render.pixel_aspect_x = scene.render.pixel_aspect_y = 1
    cam = bpy.data.objects.new("HomeCamera", bpy.data.cameras.new("HomeCamera"))
    scene.collection.objects.link(cam)
    scene.camera = cam
    back = DIRECTION.normalized()
    turn = (-back).to_track_quat("-Z", "Y")
    right, up = turn @ Vector((1, 0, 0)), turn @ Vector((0, 1, 0))
    cam.data.lens = 50
    cam.data.sensor_fit = "AUTO"  # the sensor width spans the longer side of the image
    half = cam.data.sensor_width / 2 / cam.data.lens / MARGIN
    tan_x, tan_y = (half, half * h / w) if w >= h else (half * w / h, half)
    distance = max(max((p - center).dot(back) + abs((p - center).dot(right)) / tan_x,
                       (p - center).dot(back) + abs((p - center).dot(up)) / tan_y) for p in corners)
    cam.location = center + back * distance
    cam.rotation_euler = turn.to_euler()
    cam.data.clip_start = max(radius / 1000, 1e-4)
    cam.data.clip_end = distance + radius * 50

    # Lights: the same studio set for every sample.
    for o in shown:
        if o.type == "LIGHT":
            o.hide_render = True
    view_azimuth = math.atan2(back.y, back.x)
    for name, elevation, azimuth, strength, angle in SUNS:
        sun = bpy.data.objects.new("Home" + name, bpy.data.lights.new("Home" + name, "SUN"))
        sun.data.energy = strength
        sun.data.angle = math.radians(angle)
        sun.data.use_shadow = name != "Fill"
        scene.collection.objects.link(sun)
        # A sun shines along its local -Z, so its +Z points from the model towards the light.
        el, az = math.radians(elevation), view_azimuth + math.radians(azimuth)
        to_light = Vector((math.cos(el) * math.cos(az), math.cos(el) * math.sin(az), math.sin(el)))
        sun.rotation_euler = to_light.to_track_quat("Z", "Y").to_euler()

    # World: soft ambient light; the camera sees the plain backdrop colour.
    world = bpy.data.worlds.new("HomeWorld")
    world.use_nodes = True
    nodes, links = world.node_tree.nodes, world.node_tree.links
    nodes.clear()
    ambient = nodes.new("ShaderNodeBackground")
    ambient.inputs["Color"].default_value = (0.8, 0.82, 0.85, 1)
    ambient.inputs["Strength"].default_value = 0.35
    backdrop = nodes.new("ShaderNodeBackground")
    backdrop.inputs["Color"].default_value = (*BACKDROP, 1)
    backdrop.inputs["Strength"].default_value = 1.0
    path = nodes.new("ShaderNodeLightPath")
    mix = nodes.new("ShaderNodeMixShader")
    out = nodes.new("ShaderNodeOutputWorld")
    links.new(path.outputs["Is Camera Ray"], mix.inputs["Fac"])
    links.new(ambient.outputs["Background"], mix.inputs[1])
    links.new(backdrop.outputs["Background"], mix.inputs[2])
    links.new(mix.outputs["Shader"], out.inputs["Surface"])
    scene.world = world

    # Ground: an invisible shadow catcher just under the lowest part (or under the file's floor).
    bpy.ops.mesh.primitive_plane_add(size=radius * 100, location=(center.x, center.y, ground - radius * 1e-4))
    catcher = bpy.context.active_object
    catcher.name = "HomeShadowCatcher"
    catcher.is_shadow_catcher = True
    matte = bpy.data.materials.new("HomeMatte")  # catch shadows only, not mirrored reflections
    matte.use_nodes = True
    bsdf = matte.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Roughness"].default_value = 1.0
    bsdf.inputs["Specular IOR Level"].default_value = 0.0
    catcher.data.materials.append(matte)

    scene.render.engine = "CYCLES"
    device = use_gpu(scene)
    scene.cycles.samples = a.samples
    scene.cycles.use_adaptive_sampling = True
    scene.cycles.use_denoising = True
    scene.cycles.max_bounces = 8
    scene.render.film_transparent = False
    scene.view_settings.view_transform = "AgX"
    try:
        scene.view_settings.look = "AgX - Medium High Contrast"
    except TypeError:
        scene.view_settings.look = "None"
    scene.view_settings.exposure = 0
    scene.view_settings.gamma = 1
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    scene.render.image_settings.color_depth = "8"
    scene.render.image_settings.compression = 90
    scene.render.filepath = a.output
    bpy.ops.render.render(write_still=True)
    print("WROTE", a.output, f"{w}x{h}", f"scene {scene.name!r} frame {scene.frame_current}",
          f"cycles {a.samples} samples on {device}")


main()
