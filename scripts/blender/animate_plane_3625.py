"""Rig and animate the 3625 plane in place: take off, cruise, land, never leaving the spot.

Build (background Blender):

    blender --background --python scripts/blender/animate_plane_3625.py -- \
        --plan output/3625/plan.json --glb output/3625/model.glb \
        --save output/3625/animated.blend --report output/3625/animation-check.json

Verify a saved file in a fresh process:

    blender --background --python scripts/blender/animate_plane_3625.py -- \
        --plan output/3625/plan.json --reopen output/3625/animated.blend --report output/3625/reopen-check.json

The five plan controls and three staging channels (climb, bank, lift) are custom properties on the controller,
keyed one value per frame. A MOVE_ empty above the GLB root carries the staging transform through drivers, as in
scripts/blender/animate_minifigs.py. `plane_clips_3625` is plain Python (no bpy).
"""

import argparse
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
import bpy  # noqa: E402
from mathutils import Matrix, Vector  # noqa: E402

from ldraw_mechanisms import blender as adapter, blender_tools as tools, plan as contract  # noqa: E402
import plane_clips_3625 as pc  # noqa: E402

STAGING_RANGES = dict(climb=(-0.5, 0.5, "radian", "Nose-up pitch about the plane's left axis (staging)"),
                      bank=(-0.8, 0.8, "radian", "Bank; + lowers the plane's left side (staging)"),
                      lift=(-50.0, 400.0, "none", "Height of the airframe above its rest pose, LDU (staging)"))


def add_staging_channels(ctrl):
    for name, (lo, hi, unit, text) in STAGING_RANGES.items():
        ctrl[name] = 0.0
        ctrl.id_properties_ui(name).update(default=0.0, min=lo, max=hi, soft_min=lo, soft_max=hi, description=text,
                                           subtype="ANGLE" if unit == "radian" else "NONE")


def add_mover(rig):
    """MOVE_plane (driven) -> GLB root. Returns (move, r0)."""
    root, ctrl = rig["root"], rig["controller"]
    r0 = root.matrix_world.copy()
    lin = r0.to_3x3() @ adapter.C.to_3x3()
    for name, source, expect in (("forward", (0, 0, -1), (0, -1, 0)), ("left", (1, 0, 0), (1, 0, 0)),
                                 ("up", (0, -1, 0), (0, 0, 1))):
        axis = (lin @ Vector(source)).normalized()
        if (axis - Vector(expect)).length > 1e-6:
            raise ValueError(f"plane {name} axis is {tuple(axis)}, expected {expect}")
    pivot = r0 @ (adapter.C @ Vector(pc.PIVOT))
    move = bpy.data.objects.new("MOVE_plane", None)
    bpy.context.scene.collection.objects.link(move)
    move.empty_display_type = "PLAIN_AXES"
    move.empty_display_size = 0.01
    move.location = pivot
    move.rotation_mode = "YXZ"  # bank (Y) first, then climb (X): same order as staging_matrix
    root.parent = move
    root.matrix_parent_inverse = Matrix.Identity(4)
    root.matrix_basis = Matrix.Translation(-pivot) @ r0
    ctrl.update_tag()
    bpy.context.view_layer.update()
    # Lift drives location[2] absolutely, so the pivot's own height is part of the expression.
    drivers = (("rotation_euler", 0, "-v", "climb"), ("rotation_euler", 1, "v", "bank"),
               ("location", 2, f"{pivot.z!r}+v*{pc.LDU}", "lift"))
    for path, index, expression, channel in drivers:
        adapter._driver(move, path, index, expression, {"v": (ctrl, f'["{channel}"]')})
    for fc in move.animation_data.drivers:
        fc.driver.is_valid = True
    bpy.context.view_layer.update()
    return move, r0, pivot


def key_rows(ctrl, rows, scene):
    if ctrl.animation_data:
        ctrl.animation_data_clear()
    scene.render.fps = pc.FPS
    scene.frame_start, scene.frame_end = 1, rows[-1]["frame"]
    for row in rows:
        for name in pc.CHANNELS:
            ctrl[name] = float(row[name])
            ctrl.keyframe_insert(data_path=f'["{name}"]', frame=row["frame"])
    action = ctrl.animation_data.action
    fcurves = []
    if hasattr(action, "layers"):
        for layer in action.layers:
            for strip in layer.strips:
                for slot in action.slots:
                    bag = strip.channelbag(slot)
                    if bag:
                        fcurves += list(bag.fcurves)
    else:
        fcurves = list(action.fcurves)
    for fc in fcurves:
        for kp in fc.keyframe_points:
            kp.interpolation = "LINEAR"
    return len(fcurves)


def staging_error(rig, r0, frame_row):
    """Largest distance (LDU) between evaluated part origins and the portable staging transform."""
    f = pc.staging_matrix(frame_row["climb"], frame_row["bank"], frame_row["lift"])
    worst = 0.0
    for instance in ("0/0", "1", "2", "4", "5", "7", "8", "6/1", "6/4"):
        obj = rig["mapping"][instance]
        src = rig["source_origin"][instance]
        p = [sum(f[i][j] * (src[j] if j < 3 else 1.0) for j in range(4)) for i in range(3)]
        expected = r0 @ (adapter.C @ Vector(p))
        got = obj.evaluated_get(bpy.context.evaluated_depsgraph_get()).matrix_world.translation
        worst = max(worst, (expected - got).length / pc.LDU)
    return worst


def check_frames(rig, plan, rows, r0, tolerance, frames):
    scene, ctrl = bpy.context.scene, rig["controller"]
    out = []
    for frame in frames:
        scene.frame_set(frame)
        bpy.context.view_layer.update()
        row = rows[frame - 1]
        values = {k: float(ctrl[k]) for k in plan["controls"]}
        key_error = max(abs(float(ctrl[c]) - row[c]) for c in pc.CHANNELS)
        joints = adapter.verify(rig, plan, [values], tolerance=tolerance)
        stage = staging_error(rig, r0, row)
        out.append(dict(frame=frame, key_error=key_error, joints_passed=joints["passed"], staging_error_ldu=stage,
                        passed=key_error < 1e-4 and joints["passed"] and stage < tolerance))
    scene.frame_set(1)
    return out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", required=True)
    parser.add_argument("--glb")
    parser.add_argument("--reopen", help="verify this saved .blend instead of building")
    parser.add_argument("--save")
    parser.add_argument("--report", required=True)
    parser.add_argument("--tolerance", type=float, default=0.01)
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1:])
    plan = contract.load(args.plan)
    rows = pc.timeline()
    errors = pc.check(rows)
    frames = sorted({1, 24, 72, 100, 150, 170, 200, 240, 262, 290, 320, 350, 380, 410, 436, 446, 458, 480, 520, 560, 570})
    if args.reopen:
        bpy.ops.wm.open_mainfile(filepath=str(Path(args.reopen).resolve()))
        rig = adapter.context_from_scene(plan)
        rig["source_origin"] = source_origins(plan)
        move = bpy.data.objects["MOVE_plane"]
        r0 = reopen_r0(rig)
        invalid = [f"{fc.data_path}[{fc.array_index}]" for fc in move.animation_data.drivers
                   if not fc.driver.is_valid]
        samples = check_frames(rig, plan, rows, r0, args.tolerance, frames)
        report = dict(passed=not errors and not invalid and all(s["passed"] for s in samples), mode="reopen",
                      invalid_drivers=invalid, samples=samples, timeline_errors=errors)
        contract.save(args.report, report)
        print("MECHA_REOPEN", report["passed"])
        return
    result = tools.apply_plan(plan, glb=args.glb, new_scene=True, tolerance=args.tolerance)
    rig = result["rig"]
    rig["source_origin"] = source_origins(plan)
    ctrl = rig["controller"]
    add_staging_channels(ctrl)
    move, r0, pivot = add_mover(rig)
    curves = key_rows(ctrl, rows, bpy.context.scene)
    samples = check_frames(rig, plan, rows, r0, args.tolerance, frames)
    invalid = [f"{fc.data_path}[{fc.array_index}]" for fc in move.animation_data.drivers if not fc.driver.is_valid]
    xs = [r["lift"] for r in rows]
    report = dict(passed=not errors and not invalid and all(s["passed"] for s in samples), mode="build",
                  frames=rows[-1]["frame"], fps=pc.FPS, keyed_channels=list(pc.CHANNELS), fcurves=curves,
                  max_lift_ldu=max(xs), in_place="no horizontal translation channel exists; lift is the only translation",
                  invalid_drivers=invalid, timeline_errors=errors, samples=samples, tolerance=args.tolerance,
                  pivot_world=list(pivot), plan_verify=result["report"].get("passed", None) if isinstance(
                      result["report"], dict) else None,
                  coverage="Keys re-evaluated against the portable evaluator and staging matrix at sampled frames; "
                           "no whole-sequence collision test")
    contract.save(args.report, report)
    if args.save:
        Path(args.save).resolve().parent.mkdir(parents=True, exist_ok=True)
        bpy.ops.wm.save_as_mainfile(filepath=str(Path(args.save).resolve()))
    print("MECHA_ANIMATION", report["passed"], report["frames"])


def source_origins(plan):
    out = {}
    for node in plan["source"]["nodes"]:
        if node["kind"] == "part":
            out[node["id"]] = [row[3] for row in node["world"][:3]]
    return out


def reopen_r0(rig):
    """Rest root matrix of the saved file: undo MOVE at frame 1 (all staging channels are zero there)."""
    bpy.context.scene.frame_set(1)
    bpy.context.view_layer.update()
    return rig["root"].matrix_world.copy()


if __name__ == "__main__":
    main()
