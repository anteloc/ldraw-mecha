"""Reopen the saved plant wind catalog and re-verify rigs, clips, the scene and clip reuse in a fresh process.

    Blender --background output/plants/plants.blend --python-exit-code 1 \
        --python scripts/blender/check_plants_reopen.py -- --report output/plants/reopen-check.json \
        [--tolerance 0.002] [--transfer P02_swordleaf_palm.storm:P13_fern]

Checks per case: embedded plan equals the plan file; root under SLOT_Pxx in the case collection, valid drivers whose
F-curves pass values through (no keys, no modifiers), no active Action; three NLA tracks holding this case's clip
Actions (one slot, fake user, metadata); the case camera; at sampled timeline frames the NLA-evaluated controller
equals scripts/wind_clips.py and the rig matches the portable evaluator (root-relative). Scene-wide: one scene,
regime markers, the WIND controller tracks and the arrow driver. The transfer test plays one case's clip Action on
another case's controller with the same channel names and compares it with the exported clip JSON.
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
import animate_plants as ap_  # noqa: E402
import wind_clips as wc  # noqa: E402


def transfer_test(spec, entries, tolerance):
    clip_id, target = spec.split(":")
    entry = entries[target]
    ctrl, scene = entry["ctrl"], bpy.data.scenes["Wind"]
    action = bpy.data.actions[clip_id]
    doc = json.loads((wc.OUT / "clips" / f"{clip_id}.json").read_text())
    channels = list(doc["channels"])
    missing = [c for c in channels if c not in entry["plan"]["controls"]]
    if missing:
        raise ValueError(f"{target} lacks channels {missing}")
    ad = ctrl.animation_data
    mutes = [(t, t.mute) for t in ad.nla_tracks]
    samples = []
    try:
        for t, _ in mutes:
            t.mute = True
        ad.action = action
        ad.action_slot = action.slots[0]
        for frame in range(1, doc["frames"] + 1, 11):
            scene.frame_set(frame)
            values = {c: float(ctrl[c]) for c in entry["plan"]["controls"]}
            limits = entry["plan"]["controls"]
            # The target controller's property range clamps keyed values (Blender hard min/max): a clip played
            # on a joint with a narrower range is cut at that range.
            expected = {c: min(max(doc["baked"][c][frame - 1], limits[c]["min"]), limits[c]["max"]) for c in channels}
            clamped = [c for c in channels if expected[c] != doc["baked"][c][frame - 1]]
            key_error = max(abs(values[c] - expected[c]) for c in channels)
            check = adapter.verify(entry["rig"], entry["plan"], [values], tolerance=tolerance)
            samples.append(dict(frame=frame, key_error=key_error, clamped_channels=clamped,
                                rig_passed=check["passed"], passed=bool(check["passed"] and key_error < 1e-4)))
    finally:
        ad.action = None
        for t, m in mutes:
            t.mute = m
        scene.frame_set(1)
    return dict(clip=clip_id, target_controller=ctrl.name, channels=channels, samples=samples,
                clamped_samples=sum(1 for s in samples if s["clamped_channels"]),
                note="Expected values are the exported clip clamped to the target controller's ranges.",
                passed=all(s["passed"] for s in samples))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", required=True)
    ap.add_argument("--tolerance", type=float, default=0.002)
    ap.add_argument("--transfer", default="P02_swordleaf_palm.storm:P13_fern")
    a = ap.parse_args(sys.argv[sys.argv.index("--") + 1:])
    library = wc.library()
    scene = bpy.data.scenes["Wind"]
    scene.frame_set(1)
    entries, out = {}, {}
    for case in wc.CASES:
        key = case["key"]
        plan = contract.load(wc.OUT / key / "plan.json")
        root = next(o for o in bpy.data.objects if o.get("mecha_plant") == key and o.get("mecha_id") == "root")
        stored = json.loads(root["mecha_plan"])
        same = {k: v for k, v in stored.items() if k != "notes"} == {k: v for k, v in plan.items() if k != "notes"}
        rig = adapter.context_from_scene(plan, root)
        ctrl = rig["controller"]
        clips = [c for c in library if c.case == key]
        coll = bpy.data.collections[f"{key} {case['title']}"]
        slot = bpy.data.objects[f"SLOT_{key[:3]}"]
        tracks = []
        for track in ctrl.animation_data.nla_tracks:
            strips = list(track.strips)
            act = strips[0].action if len(strips) == 1 else None
            tracks.append(dict(track=track.name, strips=len(strips), action=act.name if act else None,
                               slot=strips[0].action_slot.identifier if act else None,
                               start=strips[0].frame_start if act else None,
                               fake_user=bool(act and act.use_fake_user),
                               metadata=bool(act and act.get("pw_regime") and act.get("pw_description")
                                             and act.get("pw_styles") and act.get("pw_channels"))))
        expected = [dict(track=f"{c.window} {c.name}", action=c.id, start=float(wc.WINDOWS[c.window][0]))
                    for c in clips]
        tracks_ok = len(tracks) == 3 and all(
            t["track"] == e["track"] and t["action"] == e["action"] and t["start"] == e["start"] and t["strips"] == 1
            and t["slot"] == "OBplant_controller" and t["fake_user"] and t["metadata"]
            for t, e in zip(tracks, expected))
        fcurves = [fc for o in [root, *root.children_recursive] if o.animation_data for fc in o.animation_data.drivers]
        drivers_ok = all(fc.driver.is_valid for fc in fcurves)
        passthrough_ok = all(len(fc.keyframe_points) == 0 and len(fc.modifiers) == 0 for fc in fcurves)
        hierarchy_ok = (root.parent == slot and slot.name in coll.objects and ctrl.animation_data.action is None
                        and f"CAM_{key[:3]}" in coll.objects)
        entry = dict(case=case, plan=plan, rig=rig, root=root, ctrl=ctrl, clips=clips)
        entries[key] = entry
        samples = []
        for frame in (1, 25, 121, 217, 240, 250, 300, 361, 450, 505, 553, 601, 700, 752):
            scene.frame_set(frame)
            samples.append(ap_.check_frame(entry, frame, a.tolerance))
        scene.frame_set(1)
        out[key] = dict(embedded_plan_matches=same, controller=ctrl.name, tracks=tracks, tracks_ok=tracks_ok,
                        drivers_ok=drivers_ok, driver_passthrough_ok=passthrough_ok, hierarchy_ok=hierarchy_ok,
                        worst_key_error=max(s["key_error"] for s in samples),
                        worst_matrix_error=max(s["max_matrix_error"] for s in samples), samples=len(samples),
                        passed=bool(same and tracks_ok and drivers_ok and passthrough_ok and hierarchy_ok
                                    and all(s["passed"] for s in samples)))
    wind = bpy.data.objects["WIND"]
    wind_tracks = [t.name for t in wind.animation_data.nla_tracks]
    arrow = bpy.data.objects["WIND_arrow"]
    arrow_ok = bool(arrow.animation_data and all(fc.driver.is_valid for fc in arrow.animation_data.drivers))
    markers = sorted(m.name for m in scene.timeline_markers)
    scene_ok = (len(bpy.data.scenes) == 1 and markers == sorted(["A breeze", "B gusty", "C storm", "end"])
                and wind_tracks == ["A breeze", "B gusty", "C storm"] and arrow_ok
                and scene.camera is not None and scene.camera.name == "CAM_Overview")
    transfer = transfer_test(a.transfer, entries, a.tolerance)
    actions = sorted(act.name for act in bpy.data.actions if act.get("pw_case"))
    ok = bool(all(v["passed"] for v in out.values()) and transfer["passed"] and len(actions) == len(library)
              and scene_ok)
    report = dict(passed=ok, blender=bpy.app.version_string, file=bpy.data.filepath,
                  scenes=sorted(s.name for s in bpy.data.scenes), frames=[scene.frame_start, scene.frame_end],
                  fps=scene.render.fps, tolerance=a.tolerance, clip_actions=len(actions), markers=markers,
                  wind_tracks=wind_tracks, scene_ok=scene_ok, cases=out, transfer=transfer,
                  coverage="Saved file reopened in a fresh process; embedded plans compared with the plan files; "
                           "hierarchy, drivers (valid, pass-through F-curves), NLA tracks, Actions, cameras, "
                           "markers and the WIND controller inspected; controller values and root-relative rig "
                           "transforms checked at sampled timeline frames; one clip played on another case's "
                           "controller and compared with its exported JSON. No collision test.")
    contract.save(a.report, report)
    print("MECHA_REOPEN", ok)
    if not ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
