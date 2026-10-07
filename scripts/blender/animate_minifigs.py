"""Build the minifig movement catalog scene: ten rigged minifigs, three clips each, one Action per clip.

    Blender --background --factory-startup --python-exit-code 1 --python scripts/blender/animate_minifigs.py -- \
        --save output/minifigs/minifigs.blend --report output/minifigs/animation-check.json \
        [--tolerance 0.002] [--render output/minifigs/previews] [--samples 24]

Each figure keeps its own GLB root, rig collection and controller (CTRL_minifig_xx_name), and is parented
SLOT_ (static stage position) -> MOVE_ (whole-figure channels, driven from the controller) -> GLB root. Joint
verification is root-relative, so whole-figure motion does not affect it; the root is separately checked against
minifig_clips.figure_transform. Clips come from scripts/minifig_clips.py: every clip is an Action with one slot
(`minifig_controller`) keyed on the controller's custom properties and placed on its own NLA track.
"""

import argparse
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
import bpy  # noqa: E402
from mathutils import Euler, Matrix, Vector  # noqa: E402

from ldraw_mechanisms import blender as adapter, blender_tools as tools, plan as contract  # noqa: E402
import minifig_clips as mc  # noqa: E402

SLOT_PITCH = (240 * mc.LDU, 400 * mc.LDU)  # metres between figures across / between the two rows
SLOT_NAME = "minifig_controller"


def catalog():
    return json.loads((mc.OUT / "catalog.json").read_text())


def figure_collection(name, parent):
    coll = bpy.data.collections.new(name)
    parent.children.link(coll)
    return coll


def move_to(obj, coll):
    for c in list(obj.users_collection):
        c.objects.unlink(obj)
    coll.objects.link(obj)


def mesh_bounds(objs):
    pts = [o.matrix_world @ Vector(c) for o in objs if o.type == "MESH" for c in o.bound_box]
    lo = Vector([min(p[i] for p in pts) for i in range(3)])
    hi = Vector([max(p[i] for p in pts) for i in range(3)])
    return lo, hi


def add_figure_channels(ctrl):
    for name, spec in mc.FIGURE.items():
        ctrl[name] = 0.0
        ctrl.id_properties_ui(name).update(default=0.0, min=spec["min"], max=spec["max"], soft_min=spec["min"],
                                           soft_max=spec["max"], description=spec["description"] + " (staging)",
                                           subtype="ANGLE" if spec["unit"] == "radian" else "NONE")
    for name in mc.JOINTS:
        ctrl.id_properties_ui(name).update(default=0.0)


def figure_mover(fig, rig, slot_location, coll):
    """SLOT_ (stage position) -> MOVE_ (driven by the six whole-figure channels) -> GLB root."""
    root, ctrl = rig["root"], rig["controller"]
    r0 = root.matrix_world.copy()
    # Root-local space is the glTF-converted LDraw frame: an LDraw point p sits at r0 @ C @ p.
    lin = r0.to_3x3() @ adapter.C.to_3x3()
    axes = dict(forward=(lin @ Vector((0, 0, -1))).normalized(), left=(lin @ Vector((1, 0, 0))).normalized(),
                up=(lin @ Vector((0, -1, 0))).normalized())
    for name, expect in (("forward", (0, -1, 0)), ("left", (1, 0, 0)), ("up", (0, 0, 1))):
        if (axes[name] - Vector(expect)).length > 1e-6:
            raise ValueError(f"{fig['figure']}: figure {name} axis is {tuple(axes[name])}, expected {expect}")
    pivot = r0 @ (adapter.C @ Vector(mc.PIVOT))
    slot = bpy.data.objects.new(f"SLOT_{fig['figure']}", None)
    move = bpy.data.objects.new(f"MOVE_{fig['figure']}", None)
    for o in (slot, move):
        coll.objects.link(o)
        o.empty_display_type = "PLAIN_AXES"
        o.empty_display_size = 0.01
        o["mecha_minifig_role"] = o.name.split("_")[0].lower()
    slot.location = Vector(slot_location) + pivot
    move.parent = slot
    move.rotation_mode = "YXZ"  # roll first, then pitch, then turn (outermost)
    root.parent = move
    root.matrix_parent_inverse = Matrix.Identity(4)
    root.matrix_basis = Matrix.Translation(-pivot) @ r0
    # The evaluated controller must already carry the new properties: a driver that fails its first evaluation
    # stays flagged invalid (skipped) until the file is reloaded.
    ctrl.update_tag()
    bpy.context.view_layer.update()
    for path, index, expression, channel in mc.MOVE_DRIVERS:
        adapter._driver(move, path, index, expression, {"v": (ctrl, f'["{channel}"]')})
    for fc in move.animation_data.drivers:
        fc.driver.is_valid = True
    move.update_tag()
    bpy.context.view_layer.update()
    invalid = [f"{fc.data_path}[{fc.array_index}]" for fc in move.animation_data.drivers if not fc.driver.is_valid]
    if invalid:
        raise ValueError(f"{fig['figure']}: invalid whole-figure drivers {invalid}")
    return slot, move, r0


def build_action(clip, window_start):
    action = bpy.data.actions.new(clip.id)
    slot = action.slots.new(id_type="OBJECT", name=SLOT_NAME)
    layer = action.layers.new("Layer")
    strip = layer.strips.new(type="KEYFRAME")
    bag = strip.channelbag(slot, ensure=True)
    for channel in mc.CHANNELS:
        keys = clip.keys(channel)
        fc = bag.fcurves.new(f'["{channel}"]')
        fc.keyframe_points.add(len(keys))
        for kp, (frame, value, kind) in zip(fc.keyframe_points, keys):
            interp, easing = mc.INTERPOLATIONS[kind]
            kp.co = (frame, value)
            kp.handle_left = kp.handle_right = (frame, value)
            kp.interpolation = interp
            kp.easing = easing
        fc.update()
    action.use_fake_user = True
    action.use_frame_range = True
    action.frame_range = (1, clip.frames)
    action["mf_figure"] = clip.figure
    action["mf_clip"] = clip.name
    action["mf_title"] = clip.title
    action["mf_description"] = clip.description
    action["mf_window"] = mc.window_of(clip)
    action["mf_timeline_start"] = window_start
    action["mf_loop_range"] = list(clip.loop) if clip.loop else []
    action["mf_channels"] = json.dumps(mc.CHANNELS)
    action["mf_source"] = "scripts/minifig_clips.py"
    return action, slot


def place_clips(ctrl, figure_clips):
    ad = ctrl.animation_data_create()
    ad.action = None
    actions = {}
    for clip in figure_clips:
        w = mc.window_of(clip)
        start = mc.WINDOWS[w][0]
        action, slot = build_action(clip, start)
        track = ad.nla_tracks.new()
        track.name = f"{w} {clip.name}"
        strip = track.strips.new(clip.id, start, action)
        strip.action_slot = slot
        strip.extrapolation = "HOLD" if w == "A" else "HOLD_FORWARD"
        strip.blend_type = "REPLACE"
        actions[clip.id] = action
    return actions


def label(text, location, size, coll, align="CENTER"):
    curve = bpy.data.curves.new(f"LABEL_{text[:40]}", type="FONT")
    curve.body = text
    curve.size = size
    curve.align_x = align
    obj = bpy.data.objects.new(curve.name, curve)
    coll.objects.link(obj)
    obj.location = location
    mat = bpy.data.materials.new(curve.name)
    mat.diffuse_color = (0.08, 0.09, 0.12, 1)
    if mat.node_tree is None:
        mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if bsdf:
        bsdf.inputs["Base Color"].default_value = (0.08, 0.09, 0.12, 1)
    curve.materials.append(mat)
    return obj


def expected_values(clips_by_window, frame):
    """Controller values the NLA stack should produce at a timeline frame (hold between windows)."""
    current = {c: 0.0 for c in mc.CHANNELS}
    for w in "ABC":
        start, _ = mc.WINDOWS[w]
        clip = clips_by_window[w]
        if frame >= start:
            local = min(frame - start + 1, clip.frames)
            current = clip.values(local)
    return current


def stage(scene, figures):
    lo, hi = mesh_bounds([o for f in figures for o in f["root"].children_recursive])
    stage_coll = figure_collection("Stage", scene.collection)
    floor_mesh = bpy.data.meshes.new("Floor")
    pad = 0.12
    x0, x1, y0, y1 = lo.x - pad, hi.x + pad, lo.y - pad, hi.y + pad
    floor_mesh.from_pydata([(x0, y0, 0), (x1, y0, 0), (x1, y1, 0), (x0, y1, 0)], [], [(0, 1, 2, 3)])
    floor = bpy.data.objects.new("Floor", floor_mesh)
    stage_coll.objects.link(floor)
    mat = bpy.data.materials.new("Floor")
    if mat.node_tree is None:
        mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if bsdf:
        bsdf.inputs["Base Color"].default_value = (0.62, 0.64, 0.66, 1)
        bsdf.inputs["Roughness"].default_value = 0.8
    mat.diffuse_color = (0.62, 0.64, 0.66, 1)
    floor_mesh.materials.append(mat)
    centre = Vector(((lo.x + hi.x) / 2, (lo.y + hi.y) / 2, 0.02))
    size = max(hi.x - lo.x, hi.y - lo.y)
    cam = bpy.data.objects.new("CatalogCamera", bpy.data.cameras.new("CatalogCamera"))
    stage_coll.objects.link(cam)
    centre.y -= 0.03  # include the floor labels in front of each row
    cam.location = centre + Vector((0.0, -0.88, 0.64)) * size
    cam.rotation_euler = (centre - cam.location).to_track_quat("-Z", "Y").to_euler()
    cam.data.lens = 30
    cam.data.clip_start = 0.005
    cam.data.clip_end = 50
    scene.camera = cam
    for nm, offset, energy in (("Key", (0.6, -1.0, 1.4), 40), ("Fill", (-1.0, -0.5, 0.8), 18),
                               ("Rim", (0.0, 1.2, 1.0), 18)):
        light = bpy.data.objects.new(nm, bpy.data.lights.new(nm, "AREA"))
        stage_coll.objects.link(light)
        light.location = centre + Vector(offset) * size
        light.data.energy = energy * size * size
        light.data.size = size * 0.6
        light.rotation_euler = (centre - light.location).to_track_quat("-Z", "Y").to_euler()
    scene.world = bpy.data.worlds.new("CatalogWorld")
    if scene.world.node_tree is None:
        scene.world.use_nodes = True
    bg = scene.world.node_tree.nodes.get("Background")
    if bg:
        bg.inputs["Color"].default_value = (0.42, 0.46, 0.52, 1)
        bg.inputs["Strength"].default_value = 0.8
    return cam


def check_frame(fig, frame, tolerance):
    scene = bpy.context.scene
    ctrl, plan, rig = fig["ctrl"], fig["plan"], fig["rig"]
    values = {c: float(ctrl[c]) for c in mc.CHANNELS}
    expected = expected_values(fig["by_window"], frame)
    key_error = max(abs(values[c] - expected[c]) for c in mc.CHANNELS)
    joints = {c: values[c] for c in mc.JOINTS}
    check = adapter.verify(rig, plan, [joints], tolerance=tolerance)
    scene.frame_set(frame)  # verify restored the controls; re-evaluate the NLA stack before reading the root
    deps = bpy.context.evaluated_depsgraph_get()
    root = fig["root"].evaluated_get(deps).matrix_world
    f = adapter.C @ Matrix(mc.figure_transform(values)) @ adapter.C_INV  # LDraw transform in root-local space
    rel = fig["rest"].inverted() @ root
    figure_error = max(abs(rel[i][j] - f[i][j]) * (1.0 if j < 3 else 0.0) for i in range(3) for j in range(4))
    translation_error = (rel.translation - f.translation).length  # LDU
    s = check["samples"][0]
    passed = (check["passed"] and key_error < 1e-4 and figure_error < 1e-5 and translation_error < 1e-3)
    return dict(frame=frame, figure=fig["figure"], key_error=key_error, max_matrix_error=s["max_matrix_error"],
                max_static_error=s["max_static_error"], invalid_drivers=s["invalid_drivers"],
                figure_rotation_error=figure_error, figure_translation_error_ldu=translation_error,
                passed=passed)


SAMPLE_FRAMES = (1, 24, 48, 72, 96, 120, 144, 152, 161, 190, 220, 250, 280, 304, 312, 321, 350, 380, 410, 440,
                 464, 470, 480)


def render(scene, figures, out, samples):
    out.mkdir(parents=True, exist_ok=True)
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = samples
    scene.cycles.use_denoising = True
    scene.render.image_settings.file_format = "PNG"
    written = []
    scene.render.resolution_x, scene.render.resolution_y = 1920, 1080
    for frame in (60, 100, 232, 260, 380, 420):
        scene.frame_set(frame)
        scene.render.filepath = str((out / f"overview-f{frame:03d}.png").resolve())
        bpy.ops.render.render(write_still=True)
        written.append(scene.render.filepath)
    # Per-figure close-ups: three phases of each clip, the other figures and the labels hidden. The camera follows
    # the hip-axis centre across the floor at a fixed height, so jumps and lifts stay visible.
    cam = bpy.data.objects.new("CloseupCamera", bpy.data.cameras.new("CloseupCamera"))
    scene.collection.objects.link(cam)
    cam.data.lens = 50
    main_camera = scene.camera
    scene.camera = cam
    scene.render.resolution_x, scene.render.resolution_y = 480, 600
    shown = {o: o.hide_render for o in bpy.data.objects}
    for fig in figures:
        mine = set(fig["coll"].all_objects)
        for o in shown:
            if o.type in ("MESH", "FONT") and o.name != "Floor":
                o.hide_render = o not in mine or o.type == "FONT"
        for w in "ABC":
            clip = fig["by_window"][w]
            start = mc.WINDOWS[w][0]
            for k, phase in enumerate((0.3, 0.55, 0.8)):
                local = max(1, round(clip.frames * phase))
                frame = start + local - 1
                scene.frame_set(frame)
                hip = fig["move"].matrix_world.translation
                target = Vector((hip.x, hip.y - 0.006, 0.028))
                cam.location = target + Vector((0.075, -0.15, 0.055))
                cam.rotation_euler = (target - cam.location).to_track_quat("-Z", "Y").to_euler()
                scene.render.filepath = str((out / "figures" / f"{fig['figure']}-{w}{k + 1}-f{frame:03d}.png").resolve())
                bpy.ops.render.render(write_still=True)
                written.append(scene.render.filepath)
    for o, hidden in shown.items():
        o.hide_render = hidden
    scene.camera = main_camera
    bpy.data.objects.remove(cam)
    scene.frame_set(1)
    return written


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--save", required=True)
    ap.add_argument("--report", required=True)
    ap.add_argument("--tolerance", type=float, default=0.002)
    ap.add_argument("--render")
    ap.add_argument("--samples", type=int, default=24)
    a = ap.parse_args(sys.argv[sys.argv.index("--") + 1:])
    cat = catalog()
    library = mc.library()
    figures, builds = [], {}
    for k, entry in enumerate(cat["figures"]):
        d = mc.OUT / entry["figure"]
        plan = contract.load(d / "plan.json")
        if plan["status"] != "ready":
            raise ValueError(f"{entry['figure']}: plan is not ready")
        result = tools.apply_plan(plan, glb=d / "study/model.glb", new_scene=(k == 0), tolerance=a.tolerance)
        rig = result["rig"]
        rig["root"]["mecha_minifig"] = entry["figure"]
        builds[entry["figure"]] = dict(passed=result["report"]["passed"], samples=len(result["report"]["samples"]),
                                       max_matrix_error=max(s["max_matrix_error"] for s in result["report"]["samples"]))
        figures.append(dict(figure=entry["figure"], title=entry["title"], plan=plan, rig=rig, root=rig["root"],
                            ctrl=rig["controller"]))
    scene = bpy.context.scene
    scene.render.fps = mc.FPS
    scene.frame_start, scene.frame_end = 1, mc.FRAMES
    scene.frame_set(1)
    top = figure_collection("Minifig catalog", scene.collection)
    labels = figure_collection("Labels", scene.collection)
    layout = {}
    for k, fig in enumerate(figures):
        row, col = divmod(k, 5)
        coll = figure_collection(f"{fig['figure']} {fig['title']}", top)
        root, ctrl = fig["root"], fig["ctrl"]
        for obj in [root, *root.children_recursive]:
            if not obj.get("mecha_role"):
                move_to(obj, coll)
        rig_coll = next(c for c in bpy.data.collections if c.get("mecha_rig") == root["mecha_active_rig"])
        for c in [scene.collection, *bpy.data.collections]:
            if rig_coll.name in c.children:
                c.children.unlink(rig_coll)
        coll.children.link(rig_coll)
        add_figure_channels(ctrl)
        ctrl["mecha_minifig"] = fig["figure"]
        # Slot on the floor: x across, back row further from the camera; feet (lowest point) at z = 0.
        location = Vector((col * SLOT_PITCH[0], (1 - row) * SLOT_PITCH[1], 0.0))
        bpy.context.view_layer.update()
        lo, _ = mesh_bounds(root.children_recursive)
        location.z = -lo.z
        slot, move, _ = figure_mover(fig, fig["rig"], location, coll)
        bpy.context.view_layer.update()
        fig.update(slot=slot, move=move, coll=coll, rest=root.matrix_world.copy())
        mine = [c for c in library if c.figure == fig["figure"]]
        fig["by_window"] = {mc.window_of(c, library): c for c in mine}
        fig["actions"] = place_clips(ctrl, mine)
        home = slot.matrix_world.translation
        label(f"{fig['figure']} {fig['title']}", Vector((home.x, home.y - 0.042, 0.0003)), 0.0048, labels)
        label("  ".join(f"{w} {fig['by_window'][w].name}" for w in "ABC"),
              Vector((home.x, home.y - 0.050, 0.0003)), 0.0028, labels)
        layout[fig["figure"]] = dict(collection=coll.name, slot=[round(v, 5) for v in home],
                                     controller=ctrl.name, mover=move.name, rig_collection=rig_coll.name,
                                     nla_tracks=[t.name for t in ctrl.animation_data.nla_tracks],
                                     actions=list(fig["actions"]))
    for w, (start, _) in mc.WINDOWS.items():
        scene.timeline_markers.new(f"{w} clips", frame=start)
    scene.timeline_markers.new("end", frame=mc.WINDOWS["C"][1])
    stage(scene, figures)
    samples = []
    for frame in SAMPLE_FRAMES:
        scene.frame_set(frame)
        for fig in figures:
            samples.append(check_frame(fig, frame, a.tolerance))
    scene.frame_set(1)
    report = dict(
        passed=all(s["passed"] for s in samples) and all(b["passed"] for b in builds.values()),
        blender=bpy.app.version_string, frames=mc.FRAMES, fps=mc.FPS, windows=mc.WINDOWS, tolerance=a.tolerance,
        build=builds, layout=layout,
        worst=dict(key_error=max(s["key_error"] for s in samples),
                   max_matrix_error=max(s["max_matrix_error"] for s in samples),
                   figure_rotation_error=max(s["figure_rotation_error"] for s in samples),
                   figure_translation_error_ldu=max(s["figure_translation_error_ldu"] for s in samples)),
        samples=samples,
        coverage="Plans verified at build (apply_plan sweep); at sampled timeline frames (inside every window and in "
                 "the gaps) the NLA-evaluated controller equals the clip library, every rig matches the portable "
                 "evaluator root-relative, and each root equals rest @ figure_transform(whole-figure channels). No "
                 "collision or ground-contact test of the clips.")
    contract.save(a.report, report)
    Path(a.save).resolve().parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(Path(a.save).resolve()))
    print("MECHA_ANIMATION", report["passed"])
    if a.render:
        written = render(scene, figures, Path(a.render), a.samples)
        print("MECHA_RENDERS", len(written))
    if not report["passed"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
