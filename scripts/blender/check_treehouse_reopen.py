"""Reopen output/21318-autumn-wind/ai-animated.blend in a fresh process and re-verify the rig and its wind clips.

    bin/Blender.app/Contents/MacOS/Blender --background output/21318-autumn-wind/ai-animated.blend \
        --python-exit-code 1 --python scripts/blender/check_treehouse_reopen.py -- \
        --study output/21318-autumn-wind --tolerance 0.05

Checks: embedded plan equals plan.json; every rig driver valid and key-free (Blender 5.2 identity-key snap);
three NLA tracks (A/B/C) with fake-user Actions starting at 1/257/513 and no active Action; at sampled frames the
NLA-evaluated controller equals clips.json (small angles included) and the rig matches the portable evaluator.
"""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "scripts/blender"))
import bpy  # noqa: E402

from ldraw_mechanisms import blender as adapter, plan as contract  # noqa: E402
import animate_treehouse_wind as atw  # noqa: E402

FRAMES = (1, 7, 25, 61, 121, 217, 240, 257, 300, 361, 450, 496, 513, 553, 601, 700, 752)


def main():
    a = argparse.ArgumentParser()
    a.add_argument("--study", required=True)
    a.add_argument("--tolerance", type=float, default=0.002)
    args = a.parse_args(sys.argv[sys.argv.index("--") + 1:])
    study = Path(args.study).resolve()
    plan = contract.load(study / "plan.json")
    clips = json.loads((study / "clips.json").read_text())["controls"]
    root = next(o for o in bpy.data.objects if o.get("mecha_id") == "root")
    stored = json.loads(root["mecha_plan"])
    same_plan = {k: v for k, v in stored.items() if k != "notes"} == {k: v for k, v in plan.items() if k != "notes"}
    rig = adapter.context_from_scene(plan, root)
    ctrl = rig["controller"]
    scene = bpy.context.scene
    fcurves = [fc for o in [root, *root.children_recursive] if o.animation_data for fc in o.animation_data.drivers]
    drivers = dict(count=len(fcurves), invalid=sum(not fc.driver.is_valid for fc in fcurves),
                   with_keys=sum(len(fc.keyframe_points) > 0 for fc in fcurves),
                   with_modifiers=sum(len(fc.modifiers) > 0 for fc in fcurves))
    ad = ctrl.animation_data
    tracks = [dict(name=t.name, strips=len(t.strips), action=t.strips[0].action.name,
                   start=t.strips[0].frame_start, fake_user=t.strips[0].action.use_fake_user) for t in ad.nla_tracks]
    tracks_ok = (ad.action is None and [t["start"] for t in tracks] == [1.0, 257.0, 513.0]
                 and all(t["strips"] == 1 and t["fake_user"] for t in tracks))
    samples = []
    for frame in FRAMES:
        scene.frame_set(frame)
        values = {c: float(ctrl[c]) for c in plan["controls"]}
        exp = atw.expected(clips, frame)
        key_error = max(abs(values[c] - exp[c]) for c in values)
        small = [c for c in values if 0 < abs(exp[c]) < 1e-3]
        check = adapter.verify(rig, plan, tolerance=args.tolerance, current=True)
        s = check["samples"][0]
        samples.append(dict(frame=frame, key_error=key_error, small_angle_channels=len(small),
                            max_matrix_error=s["max_matrix_error"], max_static_error=s["max_static_error"],
                            passed=bool(check["passed"] and key_error < 1e-4)))
    scene.frame_set(1)
    report = dict(same_plan=same_plan, drivers=drivers, tracks=tracks, tracks_ok=tracks_ok,
                  scene=dict(name=scene.name, frame_range=[scene.frame_start, scene.frame_end], fps=scene.render.fps,
                             markers=[m.name for m in scene.timeline_markers]),
                  tolerance_ldu=args.tolerance, samples=samples)
    report["passed"] = bool(same_plan and tracks_ok and drivers["invalid"] == 0 and drivers["with_keys"] == 0
                            and drivers["with_modifiers"] == 0 and all(s["passed"] for s in samples))
    (study / "reopen-check.json").write_text(json.dumps(report, indent=1))
    print("MECHA_RESULT", json.dumps(dict(passed=report["passed"], drivers=drivers, tracks_ok=tracks_ok,
                                          max_key_error=max(s["key_error"] for s in samples))))
    if not report["passed"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
