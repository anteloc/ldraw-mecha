"""Build + bake the sakura-garden diorama: plant wind sway + 3 minifig clips, one scene.

    Blender --background --factory-startup --python-exit-code 1 \
        --python scripts/blender/animate_sakura_garden.py -- \
        --plan output/sakura-garden/plan.json --glb output/sakura-garden/model.glb \
        --save output/sakura-garden/rigged.blend --report output/sakura-garden/animation-check.json \
        [--tolerance 0.002]

One scene, "Sakura Garden", 240 frames at 24 fps (matches the single breeze regime's 10 s cycle,
frames 25-217 loop seamlessly). All 30 plant/minifig-joint controls live as custom properties on one
controller (CTRL_<plan name>) and are baked as ordinary keyframes (LINEAR), exactly like
scripts/blender/animate_plants.py's plant_controller pattern, just on a single shared object instead
of one controller per demo case. Gardener/visitor idle clips (144 frames, looped) repeat across the
240-frame scene by re-sampling clip-local frame ((f-1) % 144) + 1. The monk's one-shot walk clip holds
its frame-144 arrival pose for the remainder. The monk's whole-figure root motion (walking from his
placed position toward the pagoda) is NOT part of the plan.json body/control system (it is a rigid
translation+turn of his entire figure, not a joint of the source model) -- it is baked directly as
ordinary location/rotation_euler keyframes on his own GLB root object, computed from his actual rest
matrix_world so it is correct regardless of his placed yaw (the minifig catalog's own SLOT/MOVE/driver
chain in scripts/blender/animate_minifigs.py assumes every figure faces one fixed catalog-grid
direction, which does not hold for a minifig placed at an arbitrary yaw inside a larger scene).
"""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
import bpy  # noqa: E402
from mathutils import Matrix, Vector  # noqa: E402

from ldraw_mechanisms import blender as adapter, blender_tools as tools, plan as contract  # noqa: E402
import wind_clips as wc  # noqa: E402
import build_sakura_garden as bsg  # noqa: E402
import sakura_garden_clips as sgc  # noqa: E402

SLOT_NAME = "garden_controller"
LINEAR = None  # resolved at run time
LOOP_FIGS = ("gardener", "visitor")
MONK_CHANNELS = ("hip_l", "hip_r", "shoulder_l", "shoulder_r")


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


def bake_controller(ctrl, plan):
    action, slot, bag = new_action("SakuraGarden.wind_and_clips", SLOT_NAME)
    specs = bsg.plant_specs(plan["source"]["nodes"])
    for name, spec in specs.items():
        values = wc.respond(spec, "A", slot_x=0.0)
        linear_keys(bag, f'["{name}"]', values)

    clips, monk_end = sgc.all_clips()
    for fig in LOOP_FIGS:
        clip = clips[fig]
        for ch in ("hip_l", "hip_r", "shoulder_l", "shoulder_r", "neck"):
            values = [clip.value(ch, ((f - 1) % clip.frames) + 1) for f in range(1, wc.CLIP_FRAMES + 1)]
            linear_keys(bag, f'["{fig}_{ch}"]', values)
    monk_clip = clips["monk"]
    for ch in MONK_CHANNELS:
        values = [monk_clip.value(ch, min(f, monk_clip.frames)) for f in range(1, wc.CLIP_FRAMES + 1)]
        linear_keys(bag, f'["monk_{ch}"]', values)
    # monk_neck is never moved by the clip (always 0): leave it at its control default, no fcurve needed.

    action.use_fake_user = True
    action.use_frame_range = True
    action.frame_range = (1, wc.CLIP_FRAMES)
    ad = ctrl.animation_data_create()
    ad.action = None
    track = ad.nla_tracks.new()
    track.name = "A breeze + clips"
    strip = track.strips.new(action.name, 1, action)
    strip.action_slot = slot
    strip.extrapolation = "HOLD"
    strip.blend_type = "REPLACE"
    return clips, monk_end


def reparent_monk_joints(rig, monk_root):
    """`build()` parents every body's joint frame directly under the plan's overall root (see
    ldraw_mechanisms/blender.py: `empty(..., root, ...)` when a body has no `parent` body), not under
    the leaf figure's own GLB assembly object. That's correct for a joint that only rotates in place,
    but the monk also *translates* as a whole figure (see animate_monk_root): without this step his
    hip/shoulder/neck joint frames -- and the limbs/head parented under them -- would stay behind while
    only his torso (still a child of his own root, owned by no body) walked off. Reparent monk's 5 joint
    frames under his own root, preserving their world transform, so the whole figure walks together."""
    bpy.context.view_layer.update()
    for name in ("monk_hip_l", "monk_hip_r", "monk_shoulder_l", "monk_shoulder_r", "monk_neck"):
        frm = rig["pivots"][name].parent
        world = frm.matrix_world.copy()
        frm.parent = monk_root
        frm.matrix_parent_inverse.identity()
        frm.matrix_basis = monk_root.matrix_world.inverted() @ world
        bpy.context.view_layer.update()


def animate_monk_root(monk_root, monk_clip):
    """Bake the monk's whole-figure walk directly on his own GLB root object (see module docstring)."""
    r0 = monk_root.matrix_world.copy()
    lin = r0.to_3x3() @ adapter.C.to_3x3()
    forward = (lin @ Vector((0, 0, -1))).normalized()
    left = (lin @ Vector((1, 0, 0))).normalized()
    up = Vector((0.0, 0.0, 1.0))  # vertical is invariant under any yaw-only placement
    origin = r0.translation.copy()
    LDU = wc.LDU
    scene = bpy.context.scene
    for f in range(1, wc.CLIP_FRAMES + 1):
        cf = min(f, monk_clip.frames)
        fwd_v = monk_clip.value("move_forward", cf)
        left_v = monk_clip.value("move_left", cf)
        up_v = monk_clip.value("move_up", cf)
        turn_v = monk_clip.value("turn", cf)
        new_translation = origin + (fwd_v * forward + left_v * left + up_v * up) * LDU
        new_rotation = Matrix.Rotation(turn_v, 4, up) @ r0
        new_rotation.translation = new_translation
        monk_root.matrix_world = new_rotation
        bpy.context.view_layer.update()
        monk_root.keyframe_insert(data_path="location", frame=f)
        monk_root.keyframe_insert(data_path="rotation_euler", frame=f)
    action = monk_root.animation_data.action
    fcurves = []
    if hasattr(action, "layers"):
        for layer in action.layers:
            for strip in layer.strips:
                for slot in action.slots:
                    channelbag = strip.channelbag(slot)
                    if channelbag:
                        fcurves += list(channelbag.fcurves)
    else:
        fcurves = list(action.fcurves)
    for fc in fcurves:
        for kp in fc.keyframe_points:
            kp.interpolation = "LINEAR"
    action.use_fake_user = True
    monk_root.matrix_world = r0  # restore rest pose before frame_set(1) below


def main():
    global LINEAR
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan", required=True)
    ap.add_argument("--glb", required=True)
    ap.add_argument("--save", required=True)
    ap.add_argument("--report", required=True)
    ap.add_argument("--tolerance", type=float, default=0.002)
    a = ap.parse_args(sys.argv[sys.argv.index("--") + 1:])
    LINEAR = bpy.types.Keyframe.bl_rna.properties["interpolation"].enum_items["LINEAR"].value

    plan = contract.load(a.plan)
    if plan["status"] != "ready":
        plan["status"] = "ready"
        contract.save(a.plan, plan)

    result = tools.apply_plan(plan, glb=a.glb, new_scene=True, tolerance=a.tolerance, report=a.report)
    rig = result["rig"]
    ctrl = rig["controller"]
    mapping = rig["mapping"]

    scene = bpy.context.scene
    scene.name = "Sakura Garden"
    scene.render.fps = wc.FPS
    scene.frame_start, scene.frame_end = 1, wc.CLIP_FRAMES
    scene.frame_set(1)
    scene["sg_catalog"] = "Sakura garden: single-breeze plant sway + 3 minifig clips (monk/gardener/visitor)."

    reparent_monk_joints(rig, mapping["50"])
    clips, monk_end = bake_controller(ctrl, plan)
    animate_monk_root(mapping["50"], clips["monk"])
    scene.frame_set(1)

    Path(a.save).resolve().parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(Path(a.save).resolve()))
    print("MECHA_RESULT", a.report)
    print("Saved", a.save)


if __name__ == "__main__":
    main()
