"""Build the combined 42083 mechanisms scene: five standalone rigs side by side, all animated at once.

    Blender --background --factory-startup --python scripts/blender/animate_42083_mechanisms.py -- \
        --save output/42083-mechanisms/mechanisms.blend --report output/42083-mechanisms/animation-check.json \
        [--tolerance 0.002] [--render output/42083-mechanisms/previews]

Each extract keeps its own GLB root, rig collection and controller (CTRL_chiron_42083_<name>). Roots are
translated to their slots after building; Blender verification is root-relative. Only plan controls are
keyed (one key per frame, from build_42083_mechanisms.timeline); phase carries use constant interpolation.
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
from mathutils import Vector  # noqa: E402

from ldraw_mechanisms import blender as adapter, blender_tools as tools, plan as contract  # noqa: E402
import timeline_42083 as b  # noqa: E402  (Blender-safe: no pyldraw3)

LABELS = dict(drivetrain="AWD drivetrain", gearbox="8-speed gearbox + paddles", dnr="D/N/R selector",
              doors="Opening doors", wing="Rear wing lift")
ORDER = ("doors", "drivetrain", "gearbox", "dnr", "wing")
GAP = 0.06  # metres between extracts


def fcurves_of(action):
    out = []
    if hasattr(action, "layers"):
        for layer in action.layers:
            for strip in layer.strips:
                for slot in action.slots:
                    bag = strip.channelbag(slot)
                    if bag:
                        out += list(bag.fcurves)
    else:
        out = list(action.fcurves)
    return out


def bounds(objs):
    pts = [o.matrix_world @ Vector(c) for o in objs if o.type == "MESH" and not o.hide_render for c in o.bound_box]
    lo = Vector([min(p[i] for p in pts) for i in range(3)])
    hi = Vector([max(p[i] for p in pts) for i in range(3)])
    return lo, hi


def label(text, location, size, collection):
    curve = bpy.data.curves.new(f"LABEL_{text}", type="FONT")
    curve.body = text
    curve.size = size
    curve.align_x = "CENTER"
    obj = bpy.data.objects.new(f"LABEL_{text}", curve)
    collection.objects.link(obj)
    obj.location = location
    obj.rotation_euler = (math.radians(70), 0, 0)
    mat = bpy.data.materials.new(f"LABEL_{text}")
    mat.diffuse_color = (0.95, 0.95, 0.95, 1)
    curve.materials.append(mat)
    return obj


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--save", required=True)
    ap.add_argument("--report", required=True)
    ap.add_argument("--tolerance", type=float, default=0.002)
    ap.add_argument("--render")
    ap.add_argument("--samples", type=int, default=24)
    a = ap.parse_args(sys.argv[sys.argv.index("--") + 1:])
    scene_rows, reports, rigs = {}, {}, {}
    for k, name in enumerate(ORDER):
        d = b.OUT / name
        plan = contract.load(d / "plan.json")
        result = tools.apply_plan(plan, glb=d / "study/model.glb", new_scene=(k == 0), tolerance=a.tolerance)
        rig = result["rig"]
        rig["root"]["mecha_42083"] = name
        reports[name] = dict(passed=result["report"]["passed"], tolerance=a.tolerance,
                             max_matrix_error=max(max(s["max_matrix_error"], s["max_static_error"]) for s in result["report"]["samples"]),
                             max_closure_error=max(s["max_closure_error"] for s in result["report"]["samples"]))
        kin = json.loads((d / "kinematics.json").read_text())
        up = (kin.get("paddle") or {}).get("up_stroke", -0.6)
        rows = b.timeline(name, plan, paddle_up_stroke=up)
        scene_rows[name] = rows
        ctrl = rig["controller"]
        for row in rows:
            for cname, value in row["controls"].items():
                ctrl[cname] = float(value)
                ctrl.keyframe_insert(data_path=f'["{cname}"]', frame=row["frame"])
        for fc in fcurves_of(ctrl.animation_data.action):
            mode = "CONSTANT" if fc.data_path.split('"')[1].startswith("phase_") else "LINEAR"
            for kp in fc.keyframe_points:
                kp.interpolation = mode
        rigs[name] = (plan, rig)
    scene = bpy.context.scene
    scene.render.fps = b.FPS
    scene.frame_start, scene.frame_end = 1, b.FRAMES
    scene.frame_set(1)
    # Lay the extracts out along Blender X (LDraw x), centred on Y, each in its own collection.
    cursor = 0.0
    slots = {}
    labels = bpy.data.collections.new("42083 labels")
    scene.collection.children.link(labels)
    for name in ORDER:
        plan, rig = rigs[name]
        root = rig["root"]
        coll = bpy.data.collections.new(f"42083 {name}")
        scene.collection.children.link(coll)
        for obj in [root, *root.children_recursive]:
            if obj.get("mecha_role"):
                continue  # rig empties stay in their MECHA_ collection
            for c in list(obj.users_collection):
                c.objects.unlink(obj)
            coll.objects.link(obj)
        bpy.context.view_layer.update()
        lo, hi = bounds(root.children_recursive)
        width = hi.x - lo.x
        shift = Vector((cursor - lo.x, -(lo.y + hi.y) / 2, -lo.z))
        root.location += shift
        bpy.context.view_layer.update()
        lo, hi = bounds(root.children_recursive)
        slots[name] = dict(x_min=round(lo.x, 4), x_max=round(hi.x, 4), offset=[round(v, 4) for v in shift])
        label(LABELS[name], Vector(((lo.x + hi.x) / 2, lo.y - 0.06, lo.z)), 0.022, labels)
        cursor += width + GAP
    # Camera, lights and world.
    lo, hi = bounds([o for _, r in rigs.values() for o in r["root"].children_recursive])
    centre, size = (lo + hi) / 2, max(hi - lo)
    cam = bpy.data.objects.new("MechanismsCamera", bpy.data.cameras.new("MechanismsCamera"))
    scene.collection.objects.link(cam)
    cam.location = centre + Vector((0.0, -1.15, 0.55)) * size
    cam.rotation_euler = (centre - cam.location).to_track_quat("-Z", "Y").to_euler()
    cam.data.lens = 40
    cam.data.clip_start = 0.005
    cam.data.clip_end = 50
    scene.camera = cam
    for nm, offset, energy in (("Key", (0.6, -1.0, 1.6), 60), ("Fill", (-1.0, -0.4, 0.8), 25), ("Rim", (0, 1.2, 1.0), 25)):
        light = bpy.data.objects.new(nm, bpy.data.lights.new(nm, "AREA"))
        scene.collection.objects.link(light)
        light.location = centre + Vector(offset) * size
        light.data.energy = energy * size * size
        light.data.size = size * 0.6
        light.rotation_euler = (centre - light.location).to_track_quat("-Z", "Y").to_euler()
    scene.world = bpy.data.worlds.new("MechanismsWorld")
    scene.world.use_nodes = True
    bg = scene.world.node_tree.nodes["Background"]
    bg.inputs["Color"].default_value = (0.16, 0.18, 0.23, 1)
    bg.inputs["Strength"].default_value = 0.7
    # Sampled frames: keyed controls equal the timeline and every rig matches the portable evaluator.
    samples = []
    for frame in (1, 48, 75, 120, 150, 200, 240, 268, 300, 340, 380, 420, 480):
        scene.frame_set(frame)
        for name in ORDER:
            plan, rig = rigs[name]
            ctrl = rig["controller"]
            values = {k: float(ctrl[k]) for k in plan["controls"]}
            expected = scene_rows[name][frame - 1]["controls"]
            key_error = max(abs(values[k] - expected[k]) for k in values)
            check = adapter.verify(rig, plan, [values], tolerance=a.tolerance)
            samples.append(dict(frame=frame, mechanism=name, key_error=key_error,
                                passed=check["passed"] and key_error < 1e-3))
    scene.frame_set(1)
    continuity = {n: b.continuity(rigs[n][0], scene_rows[n]) for n in ORDER}
    report = dict(passed=all(s["passed"] for s in samples) and all(c["passed"] for c in continuity.values())
                  and all(r["passed"] for r in reports.values()),
                  frames=b.FRAMES, fps=b.FPS, tolerance=a.tolerance, build=reports, layout=slots,
                  continuity={n: dict(passed=c["passed"], worst=c["worst"][:3]) for n, c in continuity.items()},
                  samples=samples,
                  coverage="Plan controls keyed per frame; sampled frames re-evaluated against the portable evaluator "
                           "(root-relative); per-frame continuity of every body signal; no collision test of the sequence")
    contract.save(a.report, report)
    Path(a.save).resolve().parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(Path(a.save).resolve()))
    print("MECHA_ANIMATION", report["passed"])
    if a.render:
        out = Path(a.render)
        out.mkdir(parents=True, exist_ok=True)
        scene.render.engine = "CYCLES"
        scene.cycles.device = "CPU"
        scene.cycles.samples = a.samples
        scene.render.resolution_x, scene.render.resolution_y = 1600, 800
        scene.render.image_settings.file_format = "PNG"
        for frame in (1, 140, 240, 360):
            scene.frame_set(frame)
            scene.render.filepath = str((out / f"overview-f{frame:03d}.png").resolve())
            bpy.ops.render.render(write_still=True)
            print("MECHA_RENDER", scene.render.filepath)
        scene.frame_set(1)


if __name__ == "__main__":
    main()
