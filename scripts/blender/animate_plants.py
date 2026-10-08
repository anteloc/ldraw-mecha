"""Build the plant wind catalog: twenty rigged plant cases in one scene, three wind clips each.

    Blender --background --factory-startup --python-exit-code 1 --python scripts/blender/animate_plants.py -- \
        --save output/plants/plants.blend --report output/plants/animation-check.json \
        [--tolerance 0.002] [--render output/plants/previews] [--samples 16] [--video]

One scene, "Wind": the twenty cases stand in a 5 x 4 grid on one floor (slots fixed in scripts/wind_clips.py, so
the gust front reaches each case at the delay its clips were computed with). The wind blows toward +X.

Per case: collection "Pxx_key Title" holding SLOT_Pxx (grid position) -> GLB root, the rig collection, the
controller CTRL_<plan> (one custom property per plan control, radians), the floor labels and its own camera
CAM_Pxx. Clips come from scripts/wind_clips.py: one Action per clip ("P07_grass_meadow.storm"), slot
`plant_controller`, one LINEAR key per frame, on its own NLA track ("A breeze", "B gusty", "C storm").
The shared wind is on the WIND controller (speed, u, v at the field centre; Actions "WIND.breeze" ...), which also
drives the length of the wind arrow. Rig verification is root-relative against the portable evaluator.
"""

import argparse
import json
import math
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
import bpy  # noqa: E402
from mathutils import Vector  # noqa: E402

from ldraw_mechanisms import blender as adapter, blender_tools as tools, plan as contract  # noqa: E402
import wind_clips as wc  # noqa: E402

SLOT_NAME = "plant_controller"
WIND_SLOT = "wind_controller"
LINEAR = None  # enum value of LINEAR keyframe interpolation (resolved at run time)
SAMPLE_FRAMES = (1, 13, 25, 61, 121, 180, 217, 230, 240, 248, 257, 290, 320, 361, 400, 440, 476, 496, 505, 513, 553,
                 601, 640, 690, 732, 752)


def collection(name, parent):
    coll = bpy.data.collections.new(name)
    parent.children.link(coll)
    return coll


def move_to(obj, coll):
    for c in list(obj.users_collection):
        c.objects.unlink(obj)
    coll.objects.link(obj)


def mesh_bounds(objs, deps=None):
    pts = []
    for o in objs:
        if o.type != "MESH":
            continue
        e = o.evaluated_get(deps) if deps else o
        pts += [e.matrix_world @ Vector(c) for c in e.bound_box]
    lo = Vector([min(p[i] for p in pts) for i in range(3)])
    hi = Vector([max(p[i] for p in pts) for i in range(3)])
    return lo, hi


def envelope(rig, clips, step=12):
    """World bounds of the case over sampled poses of its clips (controls set directly, no animation yet)."""
    meshes = [o for o in rig["root"].children_recursive if o.type == "MESH"]
    lo, hi = mesh_bounds(meshes)
    for clip in clips:
        for f in range(1, clip.frames + 1, step):
            adapter.set_controls(rig, **clip.values(f))
            deps = bpy.context.evaluated_depsgraph_get()
            a, b = mesh_bounds(meshes, deps)
            lo = Vector([min(lo[i], a[i]) for i in range(3)])
            hi = Vector([max(hi[i], b[i]) for i in range(3)])
    adapter.set_controls(rig, **{k: 0.0 for k in clips[0].channels})
    return lo, hi


def linear_keys(bag, path, values, start=1):
    fc = bag.fcurves.new(path)
    n = len(values)
    fc.keyframe_points.add(n)
    co = []
    for i, v in enumerate(values):
        co += [start + i, v]
    fc.keyframe_points.foreach_set("co", co)
    fc.keyframe_points.foreach_set("handle_left", co)
    fc.keyframe_points.foreach_set("handle_right", co)
    fc.keyframe_points.foreach_set("interpolation", [LINEAR] * n)
    fc.update()
    return fc


def new_action(name, slot_name):
    action = bpy.data.actions.new(name)
    slot = action.slots.new(id_type="OBJECT", name=slot_name)
    layer = action.layers.new("Layer")
    strip = layer.strips.new(type="KEYFRAME")
    return action, slot, strip.channelbag(slot, ensure=True)


def build_action(clip):
    action, slot, bag = new_action(clip.id, SLOT_NAME)
    case = wc.BY_KEY[clip.case]
    for channel in clip.channels:
        linear_keys(bag, f'["{channel}"]', clip.series(channel))
    action.use_fake_user = True
    action.use_frame_range = True
    action.frame_range = (1, clip.frames)
    sx, sz = wc.case_slot(case)
    action["pw_case"] = clip.case
    action["pw_case_title"] = case["title"]
    action["pw_element"] = case["element"]
    action["pw_regime"] = clip.regime
    action["pw_title"] = clip.title
    action["pw_description"] = clip.description
    action["pw_styles"] = json.dumps(clip.styles)
    action["pw_window"] = clip.window
    action["pw_timeline_start"] = wc.WINDOWS[clip.window][0]
    action["pw_loop_range"] = list(clip.loop) if clip.loop else []
    action["pw_channels"] = json.dumps({ch: dict(unit=spec["unit"], meaning=spec["description"], joint=spec["joint"],
                                                 recipe=spec["recipe"])
                                        for ch, spec in case["controls"].items()})
    action["pw_wind"] = json.dumps(dict(regime=clip.regime, direction=wc.WIND_DIR, slot_ldu=[sx, sz],
                                        case_delay_frames=round(wc.delay(sx), 3),
                                        gust_speed_ldu_per_frame=wc.GUST_SPEED))
    action["pw_source"] = "scripts/wind_clips.py"
    return action, slot


def place_tracks(obj, made):
    """made = [(window, name, action, slot)]: one NLA track per clip, A/B/C windows, no active Action."""
    ad = obj.animation_data_create()
    ad.action = None
    for w, name, action, slot in made:
        track = ad.nla_tracks.new()
        track.name = f"{w} {name}"
        strip = track.strips.new(action.name, wc.WINDOWS[w][0], action)
        strip.action_slot = slot
        strip.extrapolation = "HOLD" if w == "A" else "HOLD_FORWARD"
        strip.blend_type = "REPLACE"


def material(name, colour):
    mat = bpy.data.materials.new(name)
    mat.diffuse_color = colour
    if mat.node_tree is None:
        mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if bsdf:
        bsdf.inputs["Base Color"].default_value = colour
        bsdf.inputs["Roughness"].default_value = 0.8
    return mat


def label(text, location, size, coll, colour=(0.06, 0.07, 0.1, 1)):
    curve = bpy.data.curves.new(f"LABEL_{text[:48]}", type="FONT")
    curve.body = text
    curve.size = size
    curve.align_x = "CENTER"
    obj = bpy.data.objects.new(curve.name, curve)
    coll.objects.link(obj)
    obj.location = location
    curve.materials.append(material(curve.name, colour))
    return obj


def expected_values(clips, frame):
    """Controller values the NLA stack should produce at a timeline frame (holds between windows)."""
    current = {c: 0.0 for c in clips[0].channels}
    for clip in clips:
        start, _ = wc.WINDOWS[clip.window]
        if frame >= start:
            current = clip.values(min(frame - start + 1, clip.frames))
    return current


def aim(cam, target, direction, radius, lens=50.0, aspect=4 / 3):
    cam.data.lens = lens
    cam.data.clip_start = 0.002
    cam.data.clip_end = 100
    fov = 2 * math.atan(cam.data.sensor_width / (2 * lens) / max(aspect, 1.0))
    distance = radius / math.sin(fov / 2) * 1.05
    cam.location = target + Vector(direction).normalized() * distance
    cam.rotation_euler = (target - cam.location).to_track_quat("-Z", "Y").to_euler()


CASE_VIEW = (-0.55, -1.4, 0.8)  # from the front-left: the wind blows from the viewer's left to the right


def stage(scene, lo, hi):
    stage_coll = collection("Stage", scene.collection)
    pad = 0.05
    x0, x1, y0, y1 = lo.x - pad, hi.x + pad, lo.y - pad - 0.06, hi.y + pad
    mesh = bpy.data.meshes.new("Floor")
    mesh.from_pydata([(x0, y0, 0), (x1, y0, 0), (x1, y1, 0), (x0, y1, 0)], [], [(0, 1, 2, 3)])
    mesh.materials.append(material("Floor", (0.33, 0.4, 0.3, 1)))
    floor = bpy.data.objects.new("Floor", mesh)
    stage_coll.objects.link(floor)
    centre = Vector(((lo.x + hi.x) / 2, (lo.y + hi.y) / 2, 0.0))
    size = max(hi.x - lo.x, hi.y - lo.y)
    for nm, offset, energy in (("Key", (0.5, -1.0, 1.4), 14), ("Fill", (-1.0, -0.5, 0.8), 6),
                               ("Rim", (0.0, 1.2, 1.0), 6)):
        light = bpy.data.objects.new(nm, bpy.data.lights.new(nm, "AREA"))
        stage_coll.objects.link(light)
        light.location = centre + Vector(offset) * size
        light.data.energy = energy * size * size
        light.data.size = size * 0.6
        light.rotation_euler = (centre - light.location).to_track_quat("-Z", "Y").to_euler()
    world = bpy.data.worlds.new("WindWorld")
    if world.node_tree is None:
        world.use_nodes = True
    bg = world.node_tree.nodes.get("Background")
    if bg:
        bg.inputs["Color"].default_value = (0.5, 0.6, 0.75, 1)
        bg.inputs["Strength"].default_value = 0.5
    scene.world = world
    cam = bpy.data.objects.new("CAM_Overview", bpy.data.cameras.new("CAM_Overview"))
    stage_coll.objects.link(cam)
    radius = 0.5 * (hi - lo).length
    aim(cam, centre + Vector((0, 0.02, 0.2 * (hi.z - lo.z))), (0.0, -1.0, 0.8), radius * 0.5, lens=35,
        aspect=16 / 9)
    scene.camera = cam
    return stage_coll, cam


def wind_controller(scene, lo, hi):
    """WIND: the shared wind (speed, u, v at the field centre) keyed per regime, and an arrow driven by speed."""
    coll = collection("Wind", scene.collection)
    ctrl = bpy.data.objects.new("WIND", None)
    ctrl.empty_display_type = "SINGLE_ARROW"
    ctrl.empty_display_size = 0.05
    coll.objects.link(ctrl)
    ctrl.location = Vector((lo.x - 0.02, lo.y - 0.07, 0.02))
    ctrl.rotation_euler = (0, math.pi / 2, 0)  # arrow (local Z) along +X
    for name, desc in (("speed", "Wind speed |W| at the field centre (normalised; storm gusts reach about 1.1)"),
                       ("u", "Wind component toward +X at the field centre"),
                       ("v", "Cross-wind component toward +Z (LDraw) / +Y (Blender) at the field centre")):
        ctrl[name] = 0.0
        ctrl.id_properties_ui(name).update(min=-2.0, max=2.0, description=desc)
    ctrl["direction"] = list(wc.WIND_DIR)
    ctrl["gust_speed_ldu_per_frame"] = wc.GUST_SPEED
    ctrl["field_origin_x_ldu"] = wc.X0
    ctrl["note"] = ("Every case's clips were computed from this field: a case at LDraw x feels it "
                    "(x - field_origin_x) / gust_speed frames after the field origin; the keys here are at x = 0.")
    made = []
    for w in "ABC":
        action, slot, bag = new_action(f"WIND.{wc.REGIMES[w]}", WIND_SLOT)
        series = wc.wind_series(w)
        linear_keys(bag, '["u"]', [u for u, _ in series])
        linear_keys(bag, '["v"]', [v for _, v in series])
        linear_keys(bag, '["speed"]', [math.hypot(u, v) for u, v in series])
        action.use_fake_user = True
        action.use_frame_range = True
        action.frame_range = (1, wc.CLIP_FRAMES)
        action["pw_regime"] = wc.REGIMES[w]
        action["pw_description"] = wc.REGIME_TEXT[w]
        action["pw_spec"] = json.dumps(wc.REGIME_SPECS[w])
        made.append((w, wc.REGIMES[w], action, slot))
    place_tracks(ctrl, made)
    # Arrow whose length follows the wind speed (a visual cue only).
    mesh = bpy.data.meshes.new("WIND_arrow")
    s = 0.04
    verts = [(0, -0.004, 0), (s, -0.004, 0), (s, -0.01, 0), (s + 0.016, 0, 0), (s, 0.01, 0), (s, 0.004, 0),
             (0, 0.004, 0)]
    mesh.from_pydata(verts, [], [(0, 1, 5, 6), (2, 3, 4)])
    mesh.materials.append(material("WIND_arrow", (0.15, 0.35, 0.85, 1)))
    arrow = bpy.data.objects.new("WIND_arrow", mesh)
    coll.objects.link(arrow)
    arrow.location = Vector((lo.x + 0.02, lo.y - 0.07, 0.001))
    drv = arrow.driver_add("scale", 0).driver
    drv.type = "SCRIPTED"
    var = drv.variables.new()
    var.name = "s"
    var.targets[0].id = ctrl
    var.targets[0].data_path = '["speed"]'
    drv.expression = "0.3 + 2.2 * s"
    label("WIND", Vector((lo.x + 0.03, lo.y - 0.085, 0.001)), 0.012, coll, (0.1, 0.25, 0.7, 1))
    return ctrl


def check_frame(entry, frame, tolerance):
    ctrl, plan, rig = entry["ctrl"], entry["plan"], entry["rig"]
    values = {c: float(ctrl[c]) for c in plan["controls"]}
    expected = expected_values(entry["clips"], frame)
    key_error = max(abs(values[c] - expected[c]) for c in values)
    check = adapter.verify(rig, plan, [values], tolerance=tolerance)
    s = check["samples"][0]
    return dict(frame=frame, case=entry["case"]["key"], key_error=float(key_error),
                max_matrix_error=s["max_matrix_error"], max_static_error=s["max_static_error"],
                invalid_drivers=s["invalid_drivers"], passed=bool(check["passed"] and key_error < 1e-4))


def render_engine(scene):
    items = {e.identifier for e in scene.render.bl_rna.properties["engine"].enum_items}
    return next(e for e in ("BLENDER_EEVEE_NEXT", "BLENDER_EEVEE", "CYCLES") if e in items)


def setup_render(scene, x, y, samples):
    scene.render.engine = render_engine(scene)
    if scene.render.engine == "CYCLES":
        scene.cycles.samples = samples
        scene.cycles.device = "CPU"
    else:
        scene.eevee.taa_render_samples = samples
    scene.render.image_settings.file_format = "PNG"
    scene.render.resolution_x, scene.render.resolution_y = x, y
    scene.render.resolution_percentage = 100


OVERVIEW_FRAMES = (1, 121, 361, 553, 601)  # rest, breeze, gusty peak, storm push, storm gust


def render(scene, entries, overview, out, samples, video):
    out.mkdir(parents=True, exist_ok=True)
    written = []
    setup_render(scene, 1920, 1080, samples)
    scene.camera = overview
    for frame in OVERVIEW_FRAMES:
        scene.frame_set(frame)
        scene.render.filepath = str((out / f"overview-f{frame:03d}.png").resolve())
        bpy.ops.render.render(write_still=True)
        written.append(scene.render.filepath)
    setup_render(scene, 480, 360, samples)
    for entry in entries:
        scene.camera = entry["camera"]
        for clip in entry["clips"]:
            start = wc.WINDOWS[clip.window][0]
            series = [sum(abs(v) for ch, v in clip.values(f).items() if not wc.BY_KEY[clip.case]["controls"][ch][
                "periodic"]) for f in range(1, clip.frames + 1)]
            peak = max(range(len(series)), key=series.__getitem__) + 1
            for k, local in enumerate((1, 121 if clip.window == "A" else max(2, peak - 30), peak)):
                frame = start + local - 1
                scene.frame_set(frame)
                scene.render.filepath = str((out / "cases" /
                                             f"{entry['case']['key']}-{clip.window}{k + 1}-f{frame:03d}.png").resolve())
                bpy.ops.render.render(write_still=True)
                written.append(scene.render.filepath)
    scene.camera = overview
    scene.frame_set(1)
    montage = shutil.which("montage")
    if montage:
        for entry in entries:
            key = entry["case"]["key"]
            files = sorted((out / "cases").glob(f"{key}-*.png"))
            subprocess.run([montage, *map(str, files), "-tile", "3x3", "-geometry", "320x240+2+2",
                            str(out / f"{key}.png")], check=False)
    if video:
        frames_dir = out / "video_frames"
        frames_dir.mkdir(exist_ok=True)
        setup_render(scene, 960, 540, max(4, samples // 2))
        for frame in range(1, wc.FRAMES + 1, 2):
            scene.frame_set(frame)
            scene.render.filepath = str((frames_dir / f"f{frame:04d}.png").resolve())
            bpy.ops.render.render(write_still=True)
        ffmpeg = shutil.which("ffmpeg")
        if ffmpeg:
            subprocess.run([ffmpeg, "-y", "-framerate", "12", "-pattern_type", "glob", "-i",
                            str(frames_dir / "f*.png"), "-c:v", "libx264", "-pix_fmt", "yuv420p",
                            str(out / "overview.mp4")], check=False, capture_output=True)
            written.append(str(out / "overview.mp4"))
        scene.frame_set(1)
    return written


def main():
    global LINEAR
    ap = argparse.ArgumentParser()
    ap.add_argument("--save", required=True)
    ap.add_argument("--report", required=True)
    ap.add_argument("--tolerance", type=float, default=0.002)
    ap.add_argument("--render")
    ap.add_argument("--samples", type=int, default=16)
    ap.add_argument("--video", action="store_true")
    ap.add_argument("--only", nargs="*")
    a = ap.parse_args(sys.argv[sys.argv.index("--") + 1:])
    LINEAR = bpy.types.Keyframe.bl_rna.properties["interpolation"].enum_items["LINEAR"].value
    library = wc.library()
    entries, builds = [], {}
    cases = [c for c in wc.CASES if not a.only or c["key"] in a.only]
    for k, case in enumerate(cases):
        d = wc.OUT / case["key"]
        plan = contract.load(d / "plan.json")
        if plan["status"] != "ready":
            raise ValueError(f"{case['key']}: plan is not ready")
        result = tools.apply_plan(plan, glb=d / "study/model.glb", new_scene=(k == 0), tolerance=a.tolerance)
        rig = result["rig"]
        rig["root"]["mecha_plant"] = case["key"]
        builds[case["key"]] = dict(passed=result["report"]["passed"], samples=len(result["report"]["samples"]),
                                   max_matrix_error=max(s["max_matrix_error"] for s in result["report"]["samples"]))
        clips = [c for c in library if c.case == case["key"]]
        entries.append(dict(case=case, plan=plan, rig=rig, root=rig["root"], ctrl=rig["controller"], clips=clips))
    scene = bpy.context.scene
    scene.name = "Wind"
    scene.render.fps = wc.FPS
    scene.frame_start, scene.frame_end = 1, wc.FRAMES
    scene.frame_set(1)
    scene["pw_catalog"] = "Plant wind catalog: see output/plants/CATALOG.md"
    top = collection("Plant wind catalog", scene.collection)
    layout, fits = {}, []
    for entry in entries:
        bpy.context.view_layer.update()
        lo, hi = envelope(entry["rig"], entry["clips"])
        half_x, half_y = wc.PITCH_X / 2 * wc.LDU, wc.PITCH_Z / 2 * wc.LDU
        fits.append(dict(case=entry["case"]["key"], envelope_m=[[round(v, 4) for v in lo], [round(v, 4) for v in hi]],
                         passed=bool(lo.x > -half_x and hi.x < half_x and lo.y > -half_y and hi.y < half_y)))
        entry["local_envelope"] = (lo, hi)
    for entry in entries:
        case, root, ctrl = entry["case"], entry["root"], entry["ctrl"]
        coll = collection(f"{case['key']} {case['title']}", top)
        coll["pw_case"] = case["key"]
        for obj in [root, *root.children_recursive]:
            if not obj.get("mecha_role"):
                move_to(obj, coll)
        rig_coll = next(c for c in bpy.data.collections if c.get("mecha_rig") == root["mecha_active_rig"])
        for c in [scene.collection, *bpy.data.collections]:
            if rig_coll.name in c.children:
                c.children.unlink(rig_coll)
        coll.children.link(rig_coll)
        sx, sz = wc.case_slot(case)
        slot = bpy.data.objects.new(f"SLOT_{case['key'][:3]}", None)
        slot.empty_display_type = "PLAIN_AXES"
        slot.empty_display_size = 0.01
        coll.objects.link(slot)
        slot.location = Vector((sx * wc.LDU, sz * wc.LDU, 0.0))
        slot["pw_slot_ldu"] = [sx, sz]
        root.parent = slot
        root.matrix_parent_inverse.identity()
        bpy.context.view_layer.update()
        lo, hi = entry["local_envelope"]
        entry["envelope"] = (lo + slot.location, hi + slot.location)
        ctrl["pw_case"] = case["key"]
        ctrl["pw_title"] = case["title"]
        ctrl["pw_element"] = case["element"]
        ctrl["pw_how"] = case["how"]
        for name, c in case["controls"].items():
            ctrl.id_properties_ui(name).update(description=f"{c['description']} [{c['joint']}] (radians)")
        made = []
        actions = []
        for clip in entry["clips"]:
            action, aslot = build_action(clip)
            made.append((clip.window, clip.name, action, aslot))
            actions.append(action.name)
        place_tracks(ctrl, made)
        lo_w, hi_w = entry["envelope"]
        front = (sz - wc.PITCH_Z / 2 + 40) * wc.LDU
        label(f"{case['key'][:3]} {case['title']}", Vector((slot.location.x, front, 0.0003)), 0.0085, coll)
        label(" / ".join(case["styles"]), Vector((slot.location.x, front - 0.011, 0.0003)), 0.0055, coll)
        cam = bpy.data.objects.new(f"CAM_{case['key'][:3]}", bpy.data.cameras.new(f"CAM_{case['key'][:3]}"))
        coll.objects.link(cam)
        aim(cam, (lo_w + hi_w) / 2, CASE_VIEW, 0.36 * (hi_w - lo_w).length)
        entry["camera"] = cam
        entry["coll"] = coll
        layout[case["key"]] = dict(collection=coll.name, slot_ldu=[sx, sz], controller=ctrl.name,
                                   rig_collection=rig_coll.name, camera=cam.name,
                                   nla_tracks=[t.name for t in ctrl.animation_data.nla_tracks], actions=actions,
                                   envelope_m=[[round(v, 4) for v in lo_w], [round(v, 4) for v in hi_w]])
    for w in "ABC":
        scene.timeline_markers.new(f"{w} {wc.REGIMES[w]}", frame=wc.WINDOWS[w][0])
    scene.timeline_markers.new("end", frame=wc.WINDOWS["C"][1])
    lo = Vector([min(e["envelope"][0][i] for e in entries) for i in range(3)])
    hi = Vector([max(e["envelope"][1][i] for e in entries) for i in range(3)])
    lo = Vector((min(lo.x, -wc.COLUMNS * wc.PITCH_X / 2 * wc.LDU), min(lo.y, -wc.ROWS * wc.PITCH_Z / 2 * wc.LDU), lo.z))
    hi = Vector((max(hi.x, wc.COLUMNS * wc.PITCH_X / 2 * wc.LDU), max(hi.y, wc.ROWS * wc.PITCH_Z / 2 * wc.LDU), hi.z))
    _, overview = stage(scene, lo, hi)
    wind = wind_controller(scene, lo, hi)
    samples = []
    for frame in SAMPLE_FRAMES:
        scene.frame_set(frame)
        for entry in entries:
            samples.append(check_frame(entry, frame, a.tolerance))
    wind_err = 0.0
    for frame in SAMPLE_FRAMES:
        scene.frame_set(frame)
        exp = dict(u=0.0, v=0.0)
        for w in "ABC":
            start = wc.WINDOWS[w][0]
            if frame >= start:
                u, v = wc.wind(w, min(frame - start + 1, wc.CLIP_FRAMES) - 1, 0.0)
                exp = dict(u=u, v=v)
        wind_err = max(wind_err, abs(wind["u"] - exp["u"]), abs(wind["v"] - exp["v"]))
    scene.frame_set(1)
    report = dict(
        passed=all(s["passed"] for s in samples) and all(b["passed"] for b in builds.values())
        and all(f["passed"] for f in fits) and bool(wind_err < 1e-4),
        blender=bpy.app.version_string, frames=wc.FRAMES, fps=wc.FPS, windows=wc.WINDOWS, tolerance=a.tolerance,
        build=builds, layout=layout, slot_fit=fits, wind_controller_error=float(wind_err),
        worst=dict(key_error=max(s["key_error"] for s in samples),
                   max_matrix_error=max(s["max_matrix_error"] for s in samples),
                   max_static_error=max(s["max_static_error"] for s in samples)),
        samples=samples,
        coverage="Plans verified at build (apply_plan sweep of every control's min/mid/max and a combined sample); "
                 "at sampled timeline frames (inside every window and in the gaps) the NLA-evaluated controller "
                 "equals the clip library and every rig matches the portable evaluator root-relative; the WIND "
                 "controller equals wind_clips.wind at x = 0; every case's motion envelope stays inside its grid "
                 "slot. No collision test here (see scripts/blender/check_plants_clearance.py).")
    contract.save(a.report, report)
    Path(a.save).resolve().parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(Path(a.save).resolve()))
    print("MECHA_ANIMATION", report["passed"])
    if a.render:
        written = render(scene, entries, overview, Path(a.render), a.samples, a.video)
        print("MECHA_RENDERS", len(written))
    if not report["passed"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
