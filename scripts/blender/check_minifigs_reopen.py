"""Reopen the saved minifig catalog and re-verify rigs, clips and clip reuse in a fresh process.

    Blender --background output/minifigs/minifigs.blend --python-exit-code 1 \
        --python scripts/blender/check_minifigs_reopen.py -- --report output/minifigs/reopen-check.json \
        [--tolerance 0.002] [--transfer MF03_knight.sword_slash:MF05_chef]

Checks per figure: embedded plan equals the plan file; root -> MOVE_ -> SLOT_ hierarchy with valid drivers;
three NLA tracks holding this figure's clip Actions (one slot, fake user, metadata); at sampled timeline frames
the NLA-evaluated controller equals scripts/minifig_clips.py, the rig matches the portable evaluator
(root-relative) and the root equals rest @ figure_transform. The transfer test plays another figure's clip
Action on a different controller and compares it with the exported clip JSON.
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
import animate_minifigs as am  # noqa: E402
import minifig_clips as mc  # noqa: E402


def figure_objects(figure):
    root = next(o for o in bpy.data.objects if o.get("mecha_minifig") == figure and o.get("mecha_id") == "root")
    slot = bpy.data.objects[f"SLOT_{figure}"]
    move = bpy.data.objects[f"MOVE_{figure}"]
    return root, slot, move


def transfer_test(spec, figures, tolerance):
    clip_id, target = spec.split(":")
    fig = figures[target]
    ctrl, scene = fig["ctrl"], bpy.context.scene
    action = bpy.data.actions[clip_id]
    doc = json.loads((mc.OUT / "clips" / f"{clip_id}.json").read_text())
    ad = ctrl.animation_data
    mutes = [(t, t.mute) for t in ad.nla_tracks]
    samples, users = [], []
    try:
        for t, _ in mutes:
            t.mute = True
        ad.action = action
        ad.action_slot = action.slots[0]
        users = [u.name for u in action.slots[0].users()]  # the clip's own figure (NLA) and the target
        for frame in range(1, doc["frames"] + 1, 11):
            scene.frame_set(frame)
            values = {c: float(ctrl[c]) for c in mc.CHANNELS}
            key_error = max(abs(values[c] - doc["baked"][c][frame - 1]) for c in mc.CHANNELS)
            check = adapter.verify(fig["rig"], fig["plan"], [{c: values[c] for c in mc.JOINTS}], tolerance=tolerance)
            scene.frame_set(frame)
            deps = bpy.context.evaluated_depsgraph_get()
            rel = fig["rest"].inverted() @ fig["root"].evaluated_get(deps).matrix_world
            f = adapter.C @ am.Matrix(mc.figure_transform(values)) @ adapter.C_INV
            moved = (rel.translation - f.translation).length
            samples.append(dict(frame=frame, key_error=key_error, rig_passed=check["passed"],
                                figure_translation_error_ldu=moved,
                                passed=check["passed"] and key_error < 1e-4 and moved < 1e-3))
    finally:
        ad.action = None
        for t, m in mutes:
            t.mute = m
        scene.frame_set(1)
    return dict(clip=clip_id, target_controller=ctrl.name, slot_users_during_transfer=users,
                samples=samples, passed=all(s["passed"] for s in samples))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", required=True)
    ap.add_argument("--bundle", type=Path, default=mc.OUT,
                    help="Read plans/clips from this bundle, e.g. examples/reference/minifigs")
    ap.add_argument("--tolerance", type=float, default=0.002)
    ap.add_argument("--transfer", default="MF03_knight.sword_slash:MF05_chef")
    a = ap.parse_args(sys.argv[sys.argv.index("--") + 1:])
    mc.OUT = a.bundle.resolve()
    cat = am.catalog()
    library = mc.library()
    scene = bpy.context.scene
    scene.frame_set(1)
    figures, out = {}, {}
    for entry in cat["figures"]:
        figure = entry["figure"]
        plan = contract.load(mc.OUT / figure / "plan.json")
        root, slot, move = figure_objects(figure)
        stored = json.loads(root["mecha_plan"])
        same = {k: v for k, v in stored.items() if k != "notes"} == {k: v for k, v in plan.items() if k != "notes"}
        rig = adapter.context_from_scene(plan, root)
        ctrl = rig["controller"]
        mine = [c for c in library if c.figure == figure]
        by_window = {mc.window_of(c, library): c for c in mine}
        tracks = []
        for track in ctrl.animation_data.nla_tracks:
            strips = list(track.strips)
            act = strips[0].action if len(strips) == 1 else None
            tracks.append(dict(track=track.name, strips=len(strips), action=act.name if act else None,
                               slot=strips[0].action_slot.identifier if act else None,
                               start=strips[0].frame_start if act else None,
                               fake_user=bool(act and act.use_fake_user),
                               metadata=bool(act and act.get("mf_clip") and act.get("mf_description"))))
        expected_tracks = [dict(track=f"{w} {by_window[w].name}", action=by_window[w].id,
                                start=float(mc.WINDOWS[w][0])) for w in "ABC"]
        tracks_ok = (len(tracks) == 3 and all(
            t["track"] == e["track"] and t["action"] == e["action"] and t["start"] == e["start"] and t["strips"] == 1
            and t["slot"] == "OBminifig_controller" and t["fake_user"] and t["metadata"]
            for t, e in zip(tracks, expected_tracks)))
        drivers_ok = (root.parent == move and move.parent == slot and move.animation_data is not None
                      and len(move.animation_data.drivers) == 6
                      and all(fc.driver.is_valid for fc in move.animation_data.drivers)
                      and ctrl.animation_data.action is None)
        fig = dict(figure=figure, plan=plan, rig=rig, root=root, ctrl=ctrl, by_window=by_window,
                   rest=slot.matrix_world @ root.matrix_basis)
        figures[figure] = fig
        samples = []
        for frame in (1, 40, 100, 150, 200, 260, 312, 340, 400, 464, 480):
            scene.frame_set(frame)
            samples.append(am.check_frame(fig, frame, a.tolerance))
        out[figure] = dict(embedded_plan_matches=same, controller=ctrl.name, tracks=tracks, tracks_ok=tracks_ok,
                           hierarchy_and_drivers_ok=drivers_ok,
                           worst_key_error=max(s["key_error"] for s in samples),
                           worst_matrix_error=max(s["max_matrix_error"] for s in samples),
                           worst_figure_translation_error_ldu=max(s["figure_translation_error_ldu"] for s in samples),
                           samples=len(samples), passed=same and tracks_ok and drivers_ok and all(
                               s["passed"] for s in samples))
    scene.frame_set(1)
    transfer = transfer_test(a.transfer, figures, a.tolerance)
    actions = sorted(act.name for act in bpy.data.actions if act.get("mf_clip"))
    ok = all(v["passed"] for v in out.values()) and transfer["passed"] and len(actions) == len(library)
    report = dict(passed=ok, blender=bpy.app.version_string, file=bpy.data.filepath,
                  frames=[scene.frame_start, scene.frame_end], fps=scene.render.fps, tolerance=a.tolerance,
                  clip_actions=len(actions), figures=out, transfer=transfer,
                  coverage="Saved file reopened in a fresh process; embedded plans compared with the plan files; "
                           "NLA tracks, Actions and MOVE_ drivers inspected; controller values, root-relative rig "
                           "transforms and whole-figure root transforms checked at sampled frames; one clip played "
                           "on another figure's controller and compared with its exported JSON. No collision test.")
    contract.save(a.report, report)
    print("MECHA_REOPEN", ok)
    if not ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
