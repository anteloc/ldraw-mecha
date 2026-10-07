"""Reopen the saved movable catalog and re-verify rigs, clips, scenes and clip reuse in a fresh process.

    Blender --background output/movables/movables.blend --python-exit-code 1 \
        --python scripts/blender/check_movables_reopen.py -- --report output/movables/reopen-check.json \
        [--tolerance 0.002] [--transfer S10_car_doors.both_doors:S06_double_cabinet]

Checks per scenario: embedded plan equals the plan file; root under SLOT_ in the scenario collection, valid
drivers, no active Action; three NLA tracks holding this scenario's clip Actions (one slot, fake user, metadata);
the scenario scene links the scenario collection, has its camera and clip markers; at sampled timeline frames the
NLA-evaluated controller equals scripts/movable_clips.py and the rig matches the portable evaluator (root-relative);
the scenario scene evaluates the same object matrices as the catalog. The transfer test plays one scenario's clip
Action on another scenario's controller with the same channel names and compares it with the exported clip JSON.
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
import animate_movables as am  # noqa: E402
import movable_clips as mv  # noqa: E402


def transfer_test(spec, entries, tolerance):
    clip_id, target = spec.split(":")
    entry = entries[target]
    ctrl, scene = entry["ctrl"], bpy.data.scenes["Catalog"]
    action = bpy.data.actions[clip_id]
    doc = json.loads((mv.OUT / "clips" / f"{clip_id}.json").read_text())
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
            key_error = max(abs(values[c] - doc["baked"][c][frame - 1]) for c in channels)
            check = adapter.verify(entry["rig"], entry["plan"], [values], tolerance=tolerance)
            samples.append(dict(frame=frame, key_error=key_error, rig_passed=check["passed"],
                                passed=check["passed"] and key_error < 1e-4))
    finally:
        ad.action = None
        for t, m in mutes:
            t.mute = m
        scene.frame_set(1)
    return dict(clip=clip_id, target_controller=ctrl.name, channels=channels, samples=samples,
                passed=all(s["passed"] for s in samples))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", required=True)
    ap.add_argument("--tolerance", type=float, default=0.002)
    ap.add_argument("--transfer", default="S10_car_doors.both_doors:S06_double_cabinet")
    a = ap.parse_args(sys.argv[sys.argv.index("--") + 1:])
    library = mv.library()
    catalog = bpy.data.scenes["Catalog"]
    catalog.frame_set(1)
    entries, out = {}, {}
    for sc in mv.SCENARIOS:
        key = sc["key"]
        plan = contract.load(mv.OUT / key / "plan.json")
        root = next(o for o in bpy.data.objects if o.get("mecha_movable") == key and o.get("mecha_id") == "root")
        stored = json.loads(root["mecha_plan"])
        same = {k: v for k, v in stored.items() if k != "notes"} == {k: v for k, v in plan.items() if k != "notes"}
        rig = adapter.context_from_scene(plan, root)
        ctrl = rig["controller"]
        clips = [c for c in library if c.scenario == key]
        coll = bpy.data.collections[f"{key} {sc['title']}"]
        slot = bpy.data.objects[f"SLOT_{key}"]
        tracks = []
        for track in ctrl.animation_data.nla_tracks:
            strips = list(track.strips)
            act = strips[0].action if len(strips) == 1 else None
            tracks.append(dict(track=track.name, strips=len(strips), action=act.name if act else None,
                               slot=strips[0].action_slot.identifier if act else None,
                               start=strips[0].frame_start if act else None,
                               fake_user=bool(act and act.use_fake_user),
                               metadata=bool(act and act.get("mv_clip") and act.get("mv_description")
                                             and act.get("mv_styles"))))
        expected = [dict(track=f"{w} {c.name}", action=c.id, start=float(mv.WINDOWS[w][0]))
                    for w, c in zip("ABC", clips)]
        tracks_ok = len(tracks) == 3 and all(
            t["track"] == e["track"] and t["action"] == e["action"] and t["start"] == e["start"] and t["strips"] == 1
            and t["slot"] == "OBmovable_controller" and t["fake_user"] and t["metadata"]
            for t, e in zip(tracks, expected))
        drivers_ok = all(fc.driver.is_valid for o in [root, *root.children_recursive] if o.animation_data
                         for fc in o.animation_data.drivers)
        hierarchy_ok = root.parent == slot and slot.name in coll.objects and ctrl.animation_data.action is None
        scene = bpy.data.scenes[f"{key[:3]} {sc['title']}"]
        markers = sorted(m.name for m in scene.timeline_markers)
        scene_ok = (coll.name in scene.collection.children and scene.camera is not None
                    and markers == sorted([*(e["track"] for e in expected), "end"])
                    and scene.get("mv_scenario") == key)
        entry = dict(scenario=sc, plan=plan, rig=rig, root=root, ctrl=ctrl, clips=clips, scene=scene)
        entries[key] = entry
        samples = []
        for frame in (1, 40, 100, 150, 200, 260, 312, 340, 400, 464, 480):
            catalog.frame_set(frame)
            samples.append(am.check_frame(entry, frame, a.tolerance))
        catalog.frame_set(1)
        scene_check = am.check_scene(entry, scene, (40, 200, 360), catalog)
        out[key] = dict(embedded_plan_matches=same, controller=ctrl.name, tracks=tracks, tracks_ok=tracks_ok,
                        drivers_ok=drivers_ok, hierarchy_ok=hierarchy_ok, scene=scene.name, scene_ok=scene_ok,
                        scene_check=scene_check, worst_key_error=max(s["key_error"] for s in samples),
                        worst_matrix_error=max(s["max_matrix_error"] for s in samples), samples=len(samples),
                        passed=same and tracks_ok and drivers_ok and hierarchy_ok and scene_ok
                        and scene_check["passed"] and all(s["passed"] for s in samples))
    transfer = transfer_test(a.transfer, entries, a.tolerance)
    actions = sorted(act.name for act in bpy.data.actions if act.get("mv_clip"))
    ok = all(v["passed"] for v in out.values()) and transfer["passed"] and len(actions) == len(library)
    report = dict(passed=ok, blender=bpy.app.version_string, file=bpy.data.filepath,
                  scenes=sorted(s.name for s in bpy.data.scenes), frames=[catalog.frame_start, catalog.frame_end],
                  fps=catalog.render.fps, tolerance=a.tolerance, clip_actions=len(actions), scenarios=out,
                  transfer=transfer,
                  coverage="Saved file reopened in a fresh process; embedded plans compared with the plan files; "
                           "hierarchy, drivers, NLA tracks, Actions, scenario scenes and markers inspected; "
                           "controller values and root-relative rig transforms checked at sampled catalog frames; "
                           "each scenario scene compared with the catalog at three frames; one clip played on "
                           "another scenario's controller and compared with its exported JSON. No collision test.")
    contract.save(a.report, report)
    print("MECHA_REOPEN", ok)
    if not ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
