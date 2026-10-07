"""Build the movable-element catalog: twenty rigged mock scenarios, three clips each, one Action per clip.

    Blender --background --factory-startup --python-exit-code 1 --python scripts/blender/animate_movables.py -- \
        --save output/movables/movables.blend --report output/movables/animation-check.json \
        [--tolerance 0.002] [--render output/movables/previews] [--samples 16]

Scene layout:
- "Catalog": every scenario on one floor in a 5 x 4 grid (spacing from each scenario's motion envelope), labels on
  the floor, CatalogCamera, shared Stage (floor and lights).
- One scene per scenario ("S07 Treasure chest", ...): links that scenario's collection and the shared Stage, with
  its own framed camera and timeline markers naming its three clips.

Per scenario: collection "Sxx_key Title" holding SLOT_Sxx (static stage position) -> GLB root, the rig collection
and the controller CTRL_<plan> (one custom property per plan control). Clips come from scripts/movable_clips.py:
each clip is an Action with one slot (`movable_controller`) keyed on the controller's properties and placed on its
own NLA track (A/B/C windows). Rig verification is root-relative and uses the portable evaluator; each scenario
scene is checked to evaluate the same pose as the catalog scene.
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
import movable_clips as mv  # noqa: E402

SLOT_NAME = "movable_controller"
COLUMNS = 5
GAP = 80 * mv.LDU  # metres between scenario envelopes across
ROW_GAP = 240 * mv.LDU  # metres between rows (room for the floor labels)
SAMPLE_FRAMES = (1, 20, 40, 60, 80, 100, 120, 144, 152, 161, 180, 200, 220, 240, 260, 280, 304, 312, 321, 340, 360,
                 380, 400, 420, 440, 464, 472, 480)


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


def envelope(rig, clips):
    """World bounds of the scenario over sampled poses of its clips (controls set directly, no animation yet)."""
    meshes = [o for o in rig["root"].children_recursive if o.type == "MESH"]
    lo, hi = mesh_bounds(meshes)
    for clip in clips:
        for f in range(1, clip.frames + 1, 8):
            adapter.set_controls(rig, **clip.values(f))
            deps = bpy.context.evaluated_depsgraph_get()
            a, b = mesh_bounds(meshes, deps)
            lo = Vector([min(lo[i], a[i]) for i in range(3)])
            hi = Vector([max(hi[i], b[i]) for i in range(3)])
    adapter.set_controls(rig, **{k: 0.0 for k in clips[0].channels})
    return lo, hi


def build_action(clip, window, start):
    action = bpy.data.actions.new(clip.id)
    slot = action.slots.new(id_type="OBJECT", name=SLOT_NAME)
    layer = action.layers.new("Layer")
    strip = layer.strips.new(type="KEYFRAME")
    bag = strip.channelbag(slot, ensure=True)
    for channel in clip.channels:
        keys = clip.keys(channel)
        fc = bag.fcurves.new(f'["{channel}"]')
        fc.keyframe_points.add(len(keys))
        for kp, (frame, value, kind) in zip(fc.keyframe_points, keys):
            interp, easing = mv.INTERPOLATIONS[kind]
            kp.co = (frame, value)
            kp.handle_left = kp.handle_right = (frame, value)
            kp.interpolation = interp
            kp.easing = easing
            kp.back = mv.BACK
        fc.update()
    action.use_fake_user = True
    action.use_frame_range = True
    action.frame_range = (1, clip.frames)
    sc = mv.BY_KEY[clip.scenario]
    action["mv_scenario"] = clip.scenario
    action["mv_scenario_title"] = sc["title"]
    action["mv_element"] = sc["element"]
    action["mv_clip"] = clip.name
    action["mv_title"] = clip.title
    action["mv_description"] = clip.description
    action["mv_styles"] = json.dumps(clip.styles)
    action["mv_window"] = window
    action["mv_timeline_start"] = start
    action["mv_loop_range"] = list(clip.loop) if clip.loop else []
    action["mv_channels"] = json.dumps({ch: dict(unit=sc["controls"][ch]["unit"],
                                                 meaning=sc["controls"][ch]["description"])
                                        for ch in clip.channels})
    action["mv_source"] = "scripts/movable_clips.py"
    return action, slot


def place_clips(ctrl, clips):
    ad = ctrl.animation_data_create()
    ad.action = None
    actions = {}
    for w, clip in zip("ABC", clips):
        start = mv.WINDOWS[w][0]
        action, slot = build_action(clip, w, start)
        track = ad.nla_tracks.new()
        track.name = f"{w} {clip.name}"
        strip = track.strips.new(clip.id, start, action)
        strip.action_slot = slot
        strip.extrapolation = "HOLD" if w == "A" else "HOLD_FORWARD"
        strip.blend_type = "REPLACE"
        actions[clip.id] = action
    return actions


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


def label(text, location, size, coll):
    curve = bpy.data.curves.new(f"LABEL_{text[:48]}", type="FONT")
    curve.body = text
    curve.size = size
    curve.align_x = "CENTER"
    obj = bpy.data.objects.new(curve.name, curve)
    coll.objects.link(obj)
    obj.location = location
    curve.materials.append(material(curve.name, (0.06, 0.07, 0.1, 1)))
    return obj


def expected_values(clips, frame):
    """Controller values the NLA stack should produce at a timeline frame (holds between windows)."""
    current = {c: 0.0 for c in clips[0].channels}
    for w, clip in zip("ABC", clips):
        start, _ = mv.WINDOWS[w]
        if frame >= start:
            current = clip.values(min(frame - start + 1, clip.frames))
    return current


def aim(cam, target, direction, radius, lens=50.0, aspect=4 / 3):
    """Frame a bounding sphere; the narrower (vertical, for landscape output) field of view decides."""
    cam.data.lens = lens
    cam.data.clip_start = 0.002
    cam.data.clip_end = 100
    fov = 2 * math.atan(cam.data.sensor_width / (2 * lens) / max(aspect, 1.0))
    distance = radius / math.sin(fov / 2) * 1.05
    cam.location = target + Vector(direction).normalized() * distance
    cam.rotation_euler = (target - cam.location).to_track_quat("-Z", "Y").to_euler()


VIEW = (0.55, -1.4, 0.75)


def stage(scene, lo, hi):
    stage_coll = collection("Stage", scene.collection)
    pad = 0.08
    x0, x1, y0, y1 = lo.x - pad, hi.x + pad, lo.y - pad, hi.y + pad
    mesh = bpy.data.meshes.new("Floor")
    mesh.from_pydata([(x0, y0, 0), (x1, y0, 0), (x1, y1, 0), (x0, y1, 0)], [], [(0, 1, 2, 3)])
    mesh.materials.append(material("Floor", (0.66, 0.68, 0.7, 1)))
    floor = bpy.data.objects.new("Floor", mesh)
    stage_coll.objects.link(floor)
    centre = Vector(((lo.x + hi.x) / 2, (lo.y + hi.y) / 2, 0.0))
    size = max(hi.x - lo.x, hi.y - lo.y)
    for nm, offset, energy in (("Key", (0.6, -1.0, 1.4), 40), ("Fill", (-1.0, -0.5, 0.8), 18),
                               ("Rim", (0.0, 1.2, 1.0), 18)):
        light = bpy.data.objects.new(nm, bpy.data.lights.new(nm, "AREA"))
        stage_coll.objects.link(light)
        light.location = centre + Vector(offset) * size
        light.data.energy = energy * size * size
        light.data.size = size * 0.6
        light.rotation_euler = (centre - light.location).to_track_quat("-Z", "Y").to_euler()
    world = bpy.data.worlds.new("CatalogWorld")
    if world.node_tree is None:
        world.use_nodes = True
    bg = world.node_tree.nodes.get("Background")
    if bg:
        bg.inputs["Color"].default_value = (0.45, 0.48, 0.53, 1)
        bg.inputs["Strength"].default_value = 0.8
    scene.world = world
    cams = collection("Catalog camera", scene.collection)
    cam = bpy.data.objects.new("CatalogCamera", bpy.data.cameras.new("CatalogCamera"))
    cams.objects.link(cam)
    radius = 0.5 * (hi - lo).length
    aim(cam, centre + Vector((0, -0.02, 0.2 * (hi.z - lo.z))), (0.0, -1.0, 1.35), radius * 0.62, lens=35,
        aspect=16 / 9)
    scene.camera = cam
    return stage_coll, world


def scenario_scene(entry, stage_coll, world, fps):
    sc = entry["scenario"]
    scene = bpy.data.scenes.new(f"{sc['key'][:3]} {sc['title']}")
    scene.render.fps = fps
    scene.frame_start, scene.frame_end = 1, mv.FRAMES
    scene.world = world
    scene.collection.children.link(entry["coll"])
    scene.collection.children.link(stage_coll)
    cam_coll = bpy.data.collections.new(f"Camera {sc['key'][:3]}")
    scene.collection.children.link(cam_coll)
    cam = bpy.data.objects.new(f"CAM_{sc['key']}", bpy.data.cameras.new(f"CAM_{sc['key']}"))
    cam_coll.objects.link(cam)
    lo, hi = entry["envelope"]
    aim(cam, (lo + hi) / 2, VIEW, 0.5 * (hi - lo).length)
    scene.camera = cam
    for w, clip in zip("ABC", entry["clips"]):
        scene.timeline_markers.new(f"{w} {clip.name}", frame=mv.WINDOWS[w][0])
    scene.timeline_markers.new("end", frame=mv.WINDOWS["C"][1])
    scene["mv_scenario"] = sc["key"]
    scene["mv_clips"] = json.dumps([c.id for c in entry["clips"]])
    return scene


def check_frame(entry, frame, tolerance):
    ctrl, plan, rig = entry["ctrl"], entry["plan"], entry["rig"]
    values = {c: float(ctrl[c]) for c in plan["controls"]}
    expected = expected_values(entry["clips"], frame)
    key_error = max(abs(values[c] - expected[c]) for c in values)
    check = adapter.verify(rig, plan, [values], tolerance=tolerance)
    s = check["samples"][0]
    return dict(frame=frame, scenario=entry["scenario"]["key"], key_error=key_error,
                max_matrix_error=s["max_matrix_error"], max_static_error=s["max_static_error"],
                invalid_drivers=s["invalid_drivers"], passed=check["passed"] and key_error < 1e-4)


def pose_snapshot(entry, scene):
    deps = scene.view_layers[0].depsgraph
    return {o.name: o.evaluated_get(deps).matrix_world.copy() for o in entry["root"].children_recursive
            if o.type == "MESH"}


def check_scene(entry, scene, frames, catalog):
    """The scenario scene evaluates the same object matrices as the catalog scene at the same frames.

    Reference poses are taken from the catalog first; the catalog is then parked at frame 1 (rest) while the
    scenario scene is evaluated, so a scene that merely reads the catalog's results would show the rest pose.
    The check also requires the sampled poses to differ from rest (otherwise it would be vacuous)."""
    refs = {}
    for f in frames:
        catalog.frame_set(f)
        refs[f] = pose_snapshot(entry, catalog)
    catalog.frame_set(1)
    rest = pose_snapshot(entry, catalog)
    worst, moved = 0.0, 0.0
    for f in frames:
        scene.frame_set(f)
        got = pose_snapshot(entry, scene)
        for name, m in refs[f].items():
            worst = max(worst, max(abs(got[name][i][j] - m[i][j]) for i in range(4) for j in range(4)))
            moved = max(moved, max(abs(rest[name][i][j] - m[i][j]) for i in range(4) for j in range(4)))
    scene.frame_set(1)
    return dict(scene=scene.name, frames=list(frames), max_matrix_difference_m=worst, max_motion_from_rest_m=moved,
                passed=worst < 1e-7 and moved > 1e-4)


def render_engine(scene):
    items = {e.identifier for e in scene.render.bl_rna.properties["engine"].enum_items}
    return next(e for e in ("BLENDER_EEVEE_NEXT", "BLENDER_EEVEE", "CYCLES") if e in items)


def render(catalog, entries, out, samples):
    out.mkdir(parents=True, exist_ok=True)
    written = []

    def setup(scene, x, y):
        scene.render.engine = render_engine(scene)
        if scene.render.engine == "CYCLES":
            scene.cycles.samples = samples
            scene.cycles.device = "CPU"
        else:
            scene.eevee.taa_render_samples = samples
        scene.render.image_settings.file_format = "PNG"
        scene.render.resolution_x, scene.render.resolution_y = x, y
        scene.render.resolution_percentage = 100

    setup(catalog, 1920, 1080)
    for frame in (1, 60, 230, 380):
        catalog.frame_set(frame)
        catalog.render.filepath = str((out / f"catalog-f{frame:03d}.png").resolve())
        bpy.ops.render.render(write_still=True, scene=catalog.name)
        written.append(catalog.render.filepath)
    for entry in entries:
        scene = entry["scene"]
        setup(scene, 480, 360)
        for w, clip in zip("ABC", entry["clips"]):
            start = mv.WINDOWS[w][0]
            frames = [start + max(1, round(clip.frames * p)) - 1 for p in (0.0, 0.33, 0.66)]
            frames[0] = start
            for k, frame in enumerate(frames):
                # In background mode a scene other than the context scene only re-evaluates its animation and
                # drivers for rendering when it is made the context scene.
                with bpy.context.temp_override(scene=scene, view_layer=scene.view_layers[0]):
                    scene.frame_set(frame)
                    scene.render.filepath = str((out / "scenarios" /
                                                 f"{entry['scenario']['key']}-{w}{k + 1}-f{frame:03d}.png").resolve())
                    bpy.ops.render.render(write_still=True, scene=scene.name)
                written.append(scene.render.filepath)
        with bpy.context.temp_override(scene=scene, view_layer=scene.view_layers[0]):
            scene.frame_set(1)
    montage = shutil.which("montage")
    if montage:
        for entry in entries:
            key = entry["scenario"]["key"]
            files = sorted((out / "scenarios").glob(f"{key}-*.png"))
            subprocess.run([montage, *map(str, files), "-tile", "3x3", "-geometry", "320x240+2+2",
                            str(out / f"{key}.png")], check=False)
    catalog.frame_set(1)
    return written


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--save", required=True)
    ap.add_argument("--report", required=True)
    ap.add_argument("--tolerance", type=float, default=0.002)
    ap.add_argument("--render")
    ap.add_argument("--samples", type=int, default=16)
    a = ap.parse_args(sys.argv[sys.argv.index("--") + 1:])
    library = mv.library()
    entries, builds = [], {}
    for k, sc in enumerate(mv.SCENARIOS):
        d = mv.OUT / sc["key"]
        plan = contract.load(d / "plan.json")
        if plan["status"] != "ready":
            raise ValueError(f"{sc['key']}: plan is not ready")
        result = tools.apply_plan(plan, glb=d / "study/model.glb", new_scene=(k == 0), tolerance=a.tolerance)
        rig = result["rig"]
        rig["root"]["mecha_movable"] = sc["key"]
        builds[sc["key"]] = dict(passed=result["report"]["passed"], samples=len(result["report"]["samples"]),
                                 max_matrix_error=max(s["max_matrix_error"] for s in result["report"]["samples"]))
        clips = [c for c in library if c.scenario == sc["key"]]
        entries.append(dict(scenario=sc, plan=plan, rig=rig, root=rig["root"], ctrl=rig["controller"],
                            clips=clips))
    catalog = bpy.context.scene
    catalog.name = "Catalog"
    catalog.render.fps = mv.FPS
    catalog.frame_start, catalog.frame_end = 1, mv.FRAMES
    catalog.frame_set(1)
    top = collection("Movable catalog", catalog.collection)
    # Envelopes at the build position (all roots at the origin), then a grid of rows of five.
    for entry in entries:
        bpy.context.view_layer.update()
        entry["local_envelope"] = envelope(entry["rig"], entry["clips"])
    widths = [max(e["local_envelope"][1].x - e["local_envelope"][0].x for e in entries[c::COLUMNS])
              for c in range(COLUMNS)]
    rows = (len(entries) + COLUMNS - 1) // COLUMNS
    depths = [max(e["local_envelope"][1].y - e["local_envelope"][0].y for e in entries[r * COLUMNS:(r + 1) * COLUMNS])
              for r in range(rows)]
    xs = [sum(widths[:c]) + c * GAP + widths[c] / 2 for c in range(COLUMNS)]
    ys = [-(sum(depths[:r]) + r * ROW_GAP + depths[r] / 2) for r in range(rows)]
    layout = {}
    for k, entry in enumerate(entries):
        sc, root, ctrl = entry["scenario"], entry["root"], entry["ctrl"]
        row, col = divmod(k, COLUMNS)
        coll = collection(f"{sc['key']} {sc['title']}", top)
        coll["mv_scenario"] = sc["key"]
        for obj in [root, *root.children_recursive]:
            if not obj.get("mecha_role"):
                move_to(obj, coll)
        rig_coll = next(c for c in bpy.data.collections if c.get("mecha_rig") == root["mecha_active_rig"])
        for c in [catalog.collection, *bpy.data.collections]:
            if rig_coll.name in c.children:
                c.children.unlink(rig_coll)
        coll.children.link(rig_coll)
        lo, hi = entry["local_envelope"]
        centre = (lo + hi) / 2
        target = Vector((xs[col], ys[row], 0.0))
        offset = Vector((target.x - centre.x, target.y - centre.y, -lo.z))
        slot = bpy.data.objects.new(f"SLOT_{sc['key']}", None)
        slot.empty_display_type = "PLAIN_AXES"
        slot.empty_display_size = 0.01
        coll.objects.link(slot)
        slot.location = offset
        root.parent = slot
        root.matrix_parent_inverse.identity()
        bpy.context.view_layer.update()
        entry["envelope"] = (lo + offset, hi + offset)
        ctrl["mv_scenario"] = sc["key"]
        ctrl["mv_title"] = sc["title"]
        ctrl["mv_element"] = sc["element"]
        for name, c in sc["controls"].items():
            ctrl.id_properties_ui(name).update(description=c["description"] + (
                " (radians)" if c["unit"] == "radian" else " (LDU, 1 LDU = 0.4 mm)"))
        entry["actions"] = place_clips(ctrl, entry["clips"])
        lo_w, hi_w = entry["envelope"]
        label(f"{sc['key'][:3]} {sc['title']}", Vector(((lo_w.x + hi_w.x) / 2, lo_w.y - 0.012, 0.0003)), 0.0085,
              coll)
        label("  ".join(f"{w} {c.name}" for w, c in zip("ABC", entry["clips"])),
              Vector(((lo_w.x + hi_w.x) / 2, lo_w.y - 0.024, 0.0003)), 0.0055, coll)
        entry["coll"] = coll
        layout[sc["key"]] = dict(collection=coll.name, slot=[round(v, 5) for v in slot.location],
                                 controller=ctrl.name, rig_collection=rig_coll.name,
                                 nla_tracks=[t.name for t in ctrl.animation_data.nla_tracks],
                                 actions=list(entry["actions"]),
                                 envelope_m=[[round(v, 4) for v in lo_w], [round(v, 4) for v in hi_w]])
    for w, (start, _) in mv.WINDOWS.items():
        catalog.timeline_markers.new(f"{w} clips", frame=start)
    catalog.timeline_markers.new("end", frame=mv.WINDOWS["C"][1])
    lo = Vector([min(e["envelope"][0][i] for e in entries) for i in range(3)])
    hi = Vector([max(e["envelope"][1][i] for e in entries) for i in range(3)])
    stage_coll, world = stage(catalog, lo - Vector((0, 0.04, 0)), hi)
    for entry in entries:
        entry["scene"] = scenario_scene(entry, stage_coll, world, mv.FPS)
        layout[entry["scenario"]["key"]]["scene"] = entry["scene"].name
    samples = []
    for frame in SAMPLE_FRAMES:
        catalog.frame_set(frame)
        for entry in entries:
            samples.append(check_frame(entry, frame, a.tolerance))
    catalog.frame_set(1)
    scene_checks = [check_scene(e, e["scene"], (40, 60, 200, 230, 360, 380), catalog) for e in entries]
    report = dict(
        passed=all(s["passed"] for s in samples) and all(b["passed"] for b in builds.values())
        and all(s["passed"] for s in scene_checks),
        blender=bpy.app.version_string, frames=mv.FRAMES, fps=mv.FPS, windows=mv.WINDOWS, tolerance=a.tolerance,
        build=builds, layout=layout,
        worst=dict(key_error=max(s["key_error"] for s in samples),
                   max_matrix_error=max(s["max_matrix_error"] for s in samples),
                   max_static_error=max(s["max_static_error"] for s in samples),
                   scene_difference_m=max(s["max_matrix_difference_m"] for s in scene_checks)),
        samples=samples, scene_checks=scene_checks,
        coverage="Plans verified at build (apply_plan sweep of every control's min/mid/max and a combined sample); "
                 "at sampled catalog frames (inside every window and in the gaps) the NLA-evaluated controller equals "
                 "the clip library and every rig matches the portable evaluator root-relative; each scenario scene "
                 "evaluates the same object matrices as the catalog scene. No collision test here (see "
                 "scripts/blender/check_movables_clearance.py).")
    contract.save(a.report, report)
    Path(a.save).resolve().parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(Path(a.save).resolve()))
    print("MECHA_ANIMATION", report["passed"])
    if a.render:
        written = render(catalog, entries, Path(a.render), a.samples)
        print("MECHA_RENDERS", len(written))
    if not report["passed"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
