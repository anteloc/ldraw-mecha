"""Rig the 21318 Tree House (autumn) and bake its wind clips into one scene.

    bin/Blender.app/Contents/MacOS/Blender --background --factory-startup --python-exit-code 1 \
        --python scripts/blender/animate_treehouse_wind.py -- \
        --study output/21318-autumn-wind [--tolerance 0.002] [--render output/21318-autumn-wind/stills]

Reads <study>/plan.json, model.glb and clips.json (written by scripts/build_treehouse_wind.py plan), builds the
rig with blender_tools.apply_plan (matrix verification of every control at its limits), then keys every
controller property with LINEAR keys from the precomputed clips: one Action per regime ("Treehouse.breeze",
".gusty", ".storm", slot `treehouse_controller`) on NLA tracks starting at frames 1, 257 and 513. The WIND
controller and arrow come from scripts/blender/animate_plants.wind_controller (same field, keyed at x = 0).
Saves <study>/ai-animated.blend and <study>/animation-check.json (timeline verification + key agreement).
"""
import argparse
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "scripts/blender"))
import bpy  # noqa: E402
from mathutils import Vector  # noqa: E402

from ldraw_mechanisms import blender as adapter, blender_tools as tools, plan as contract  # noqa: E402
import wind_clips as wc  # noqa: E402
import animate_plants as ap_  # noqa: E402

SLOT_NAME = "treehouse_controller"
SAMPLE_FRAMES = (1, 13, 25, 61, 121, 180, 217, 240, 248, 257, 300, 361, 400, 440, 496, 505, 513, 553, 601, 640,
                 690, 732, 752)
STILLS = dict(rest=1, breeze=121, gusty_peak=361, storm_push=553, storm_gust=601)


def expected(clips, frame):
    """Controller values the NLA stack should give at a timeline frame (each strip holds its last value)."""
    out = {}
    for name, c in clips.items():
        value = 0.0
        for w in "ABC":
            start = wc.WINDOWS[w][0]
            if frame >= start:
                value = c[w][min(frame - start, wc.CLIP_FRAMES - 1)]
        out[name] = value
    return out


def bake(ctrl, clips, plan):
    made = []
    for w in "ABC":
        action, slot, bag = ap_.new_action(f"Treehouse.{wc.REGIMES[w]}", SLOT_NAME)
        for name, c in clips.items():
            ap_.linear_keys(bag, f'["{name}"]', c[w])
        action.use_fake_user = True
        action.use_frame_range = True
        action.frame_range = (1, wc.CLIP_FRAMES)
        action["tw_regime"] = wc.REGIMES[w]
        action["tw_description"] = wc.REGIME_TEXT[w]
        action["tw_window"] = list(wc.WINDOWS[w])
        action["tw_source"] = "scripts/build_treehouse_wind.py -> clips.json (scripts/wind_clips.respond)"
        made.append((w, wc.REGIMES[w], action, slot))
    ap_.place_tracks(ctrl, made)
    for name, c in plan["controls"].items():
        ctrl.id_properties_ui(name).update(description=f"{c['description']} (radians)")


def main():
    a = argparse.ArgumentParser()
    a.add_argument("--study", required=True)
    a.add_argument("--tolerance", type=float, default=0.002)
    a.add_argument("--render")
    a.add_argument("--samples", type=int, default=24)
    args = a.parse_args(sys.argv[sys.argv.index("--") + 1:])
    ap_.LINEAR = bpy.types.Keyframe.bl_rna.properties["interpolation"].enum_items["LINEAR"].value
    study = Path(args.study).resolve()
    plan = contract.load(study / "plan.json")
    clips = json.loads((study / "clips.json").read_text())["controls"]
    if set(clips) != set(plan["controls"]):
        raise ValueError("clips.json does not match the plan controls; rerun build_treehouse_wind.py plan")

    result = tools.apply_plan(plan, glb=study / "model.glb", new_scene=True, tolerance=args.tolerance,
                              report=study / "rig-check.json")
    rig = result["rig"]
    ctrl = rig["controller"]
    scene = bpy.context.scene
    scene.name = "Tree House Wind"
    scene.render.fps = wc.FPS
    scene.frame_start, scene.frame_end = 1, wc.FRAMES
    scene["tw_about"] = ("21318 Tree House (autumn) in the wind: breeze 1-240 (loop 25-217), gusty 257-496, "
                         "storm 513-752. Wind toward +X (Blender +X). See output/21318-autumn-wind/REPORT.md.")
    bake(ctrl, clips, plan)
    for w in "ABC":
        scene.timeline_markers.new(f"{w} {wc.REGIMES[w]}", frame=wc.WINDOWS[w][0])
    scene.timeline_markers.new("end", frame=wc.WINDOWS["C"][1])

    meshes = [o for o in rig["root"].children_recursive if o.type == "MESH"]
    lo, hi = ap_.mesh_bounds(meshes)
    stage_coll, overview = ap_.stage(scene, lo, hi)
    ap_.aim(overview, (lo + hi) / 2, (0.0, -1.0, 0.25), 0.5 * (hi - lo).length * 0.62, lens=50, aspect=16 / 9)
    wind = ap_.wind_controller(scene, lo, hi)
    cams = {"CAM_Overview": overview}
    for name, target, direction, radius in (
            ("CAM_Crown", Vector(((lo.x + hi.x) / 2, (lo.y + hi.y) / 2, hi.z - 0.06)), (0.2, -1.0, 0.45), 0.17),
            ("CAM_Swing_Rope", Vector((-0.11, 0.05, 0.09)), (0.15, 1.0, 0.2), 0.12)):
        cam = bpy.data.objects.new(name, bpy.data.cameras.new(name))
        stage_coll.objects.link(cam)
        ap_.aim(cam, target, direction, radius, lens=50, aspect=16 / 9)
        cams[name] = cam
    scene.camera = overview

    # Timeline verification: evaluated matrices against the portable evaluator, and key agreement.
    samples = []
    for frame in SAMPLE_FRAMES:
        scene.frame_set(frame)
        values = {c: float(ctrl[c]) for c in plan["controls"]}
        exp = expected(clips, frame)
        key_error = max(abs(values[c] - exp[c]) for c in values)
        check = adapter.verify(rig, plan, tolerance=args.tolerance, current=True)
        s = check["samples"][0]
        samples.append(dict(frame=frame, key_error=key_error, max_matrix_error=s["max_matrix_error"],
                            max_static_error=s["max_static_error"], invalid_drivers=s["invalid_drivers"],
                            passed=bool(check["passed"] and key_error < 1e-4)))
    timeline = adapter.verify_animation(rig, plan, tolerance=args.tolerance)
    scene.frame_set(1)
    report = dict(passed=bool(result["report"]["passed"] and all(s["passed"] for s in samples)
                              and timeline["passed"]),
                  tolerance_ldu=args.tolerance, rig_samples=len(result["report"]["samples"]),
                  rig_max_matrix_error=max(s["max_matrix_error"] for s in result["report"]["samples"]),
                  frames=samples, timeline=dict(passed=timeline["passed"], samples=len(timeline["samples"]),
                                                max_matrix_error=max(s["max_matrix_error"]
                                                                     for s in timeline["samples"])),
                  controller=ctrl.name, wind_controller=wind.name, cameras=list(cams),
                  nla_tracks=[t.name for t in ctrl.animation_data.nla_tracks])
    (study / "animation-check.json").write_text(json.dumps(report, indent=1))
    save = study / "ai-animated.blend"
    bpy.ops.wm.save_as_mainfile(filepath=str(save))
    print("MECHA_RESULT", json.dumps({k: report[k] for k in ("passed", "rig_max_matrix_error", "timeline")}))

    if args.render:
        out = Path(args.render).resolve()
        out.mkdir(parents=True, exist_ok=True)
        ap_.setup_render(scene, 1280, 900, args.samples)
        for cam_name, cam in cams.items():
            scene.camera = cam
            for label, frame in STILLS.items():
                scene.frame_set(frame)
                scene.render.filepath = str(out / f"{cam_name[4:].lower()}-{label}-f{frame:03d}.png")
                bpy.ops.render.render(write_still=True)
        scene.camera = overview
        scene.frame_set(1)
    if not report["passed"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
