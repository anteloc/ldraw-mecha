"""Background integration regression for callable workflows and live state.

Run in a disposable process, never in a user's open scene. Exercises animated
poses, NLA, exception cleanup, visibility, notes, and duplicate model imports.
"""

import argparse
from copy import deepcopy
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import bpy
from ldraw_mechanisms import blender as adapter, plan as contract
from ldraw_mechanisms import blender_tools as workflows


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", required=True)
    parser.add_argument("--glb", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1 :])
    out = Path(args.output).resolve()
    out.mkdir(parents=True, exist_ok=True)
    plan = contract.load(args.plan)
    result = workflows.apply_plan(plan, glb=args.glb, animate=True, new_scene=True)
    rig, ctrl = result["rig"], result["rig"]["controller"]
    control = next(iter(plan["controls"]))
    bpy.context.scene.frame_set(23, subframe=0.25)
    animation = ctrl.animation_data
    track = animation.nla_tracks.new()
    strip = track.strips.new("Test NLA", 1, animation.action)
    strip.blend_type = "REPLACE"
    ctrl["diagnostic_driver"] = 0.0
    driver = ctrl.driver_add('["diagnostic_driver"]')
    driver.driver.expression = "2.0"
    bpy.context.view_layer.update()

    def state():
        return dict(
            values={k: ctrl[k] for k in plan["controls"]},
            frame=(bpy.context.scene.frame_current, bpy.context.scene.frame_subframe),
            action=animation.action,
            slot=animation.action_slot,
            tracks=[t.mute for t in animation.nla_tracks],
            drivers=[f.mute for f in animation.drivers],
            matrices={
                k: [tuple(row) for row in o.matrix_world]
                for k, o in rig["mapping"].items()
            },
            selected=set(bpy.context.selected_objects),
            active=bpy.context.view_layer.objects.active,
        )

    before = state()
    mismatched = deepcopy(plan)
    mismatched["controls"][control]["max"] += 1
    try:
        workflows.check_clearance(mismatched, rig=rig, controls=[control])
    except ValueError as exc:
        assert "differs from the built rig" in str(exc)
    else:
        raise AssertionError("Mismatched mechanical plan was accepted")
    assert before == state()
    checks = workflows.apply_plan(plan, root=rig["root"], verify_existing=True)[
        "report"
    ]
    assert checks["passed"] and before == state(), "Verification changed live state"
    clearance = workflows.check_clearance(
        plan, rig=rig, controls=[control], steps=9, report=out / "clearance.json"
    )
    assert before == state(), "Clearance changed live state"
    # Inject a failure after the context has sampled controls.
    original = adapter.set_controls
    calls = []

    def fail_after_change(rig, **values):
        original(rig, **values)
        calls.append(1)
        if len(calls) == 2:
            raise RuntimeError("Injected sample failure")

    adapter.set_controls = fail_after_change
    try:
        try:
            workflows.check_clearance(plan, rig=rig, controls=[control], steps=2)
        except RuntimeError as exc:
            assert str(exc) == "Injected sample failure"
        else:
            raise AssertionError("Failure was not injected")
    finally:
        adapter.set_controls = original
    assert before == state(), "Failed clearance changed live state"

    meshes = [o for o in rig["root"].children_recursive if o.type == "MESH"]
    meshes[0].hide_set(True)
    meshes[1].hide_render = True
    meshes[2].hide_viewport = True

    def visibility():
        return {o.name: (o.hide_get(), o.hide_render, o.hide_viewport) for o in meshes}

    old_visibility = visibility()
    try:
        with adapter.moving_only(rig):
            assert any(o.hide_render for o in meshes), "No static geometry hidden"
            assert any(not o.hide_render for o in meshes), "Moving geometry hidden"
            raise RuntimeError("Injected view failure")
    except RuntimeError:
        pass
    assert visibility() == old_visibility
    notes = [*plan["notes"], "Workflow regression: notes updated without rebuilding."]
    object_count = len(bpy.data.objects)
    revised = adapter.update_plan_notes(rig, notes)
    assert len(bpy.data.objects) == object_count and state() == before
    assert json.loads(rig["root"]["mecha_plan"])["notes"] == notes
    plan_before = dict(plan)
    plan_before["notes"] = notes
    assert revised == plan_before, "Notes update changed mechanical plan"
    contract.save(out / "plan.json", revised)
    adapter.set_moving_only(rig)
    adapter.set_moving_only(rig)  # idempotent snapshot
    # Save the animated, nonzero pose while the reversible view is active.
    bpy.ops.wm.save_as_mainfile(filepath=str(out / "rigged.blend"))
    bpy.ops.wm.open_mainfile(filepath=str(out / "rigged.blend"))
    rig = adapter.context_from_scene(revised)
    assert rig["controller"].animation_data.action is not None
    adapter.set_moving_only(rig, False)
    meshes = [o for o in rig["root"].children_recursive if o.type == "MESH"]
    assert visibility() == old_visibility, "Saved visibility did not restore"
    assert adapter.verify(rig, revised, [{control: 0.731}])["passed"]
    # Hide chosen static occurrences (e.g. bodywork); rigged parts are refused.
    owned = {i for b in revised["bodies"].values() for i in b["instances"]}
    statics = [
        n["id"]
        for n in revised["source"]["nodes"]
        if n["kind"] == "part" and n["id"] not in owned
    ][:5]
    try:
        adapter.set_hidden(rig, [next(iter(owned))])
    except ValueError:
        pass
    else:
        raise AssertionError("A rigged part was hidden")
    adapter.set_hidden(rig, statics)
    hidden = {
        o for i in statics for o in rig["mapping"][i].children_recursive if o.type == "MESH"
    }
    assert hidden and all(o.hide_render for o in hidden), "Static part still visible"
    bpy.ops.wm.save_as_mainfile(filepath=str(out / "hidden.blend"))
    bpy.ops.wm.open_mainfile(filepath=str(out / "hidden.blend"))
    rig = adapter.context_from_scene(revised)
    meshes = [o for o in rig["root"].children_recursive if o.type == "MESH"]
    assert rig["root"]["mecha_hidden"] == len(statics), "Hidden set not persisted"
    adapter.set_hidden(rig, [], enabled=False)
    assert visibility() == old_visibility, "Hidden view did not restore after reopen"
    second = workflows.apply_plan(plan, glb=args.glb)["rig"]
    assert second["root"] != rig["root"], "Import bound to existing copy"
    assert rig["controller"].animation_data.action is not None
    adapter.set_moving_only(second)
    adapter.remove(second["root"])
    assert "mecha_visibility" not in second["root"]
    report = dict(
        passed=True,
        animated_pose_restored=True,
        nla_and_drivers_restored=True,
        exception_state_restored=True,
        visibility_restored_after_reopen=True,
        hidden_view_restored_after_reopen=True,
        notes_only_update=True,
        duplicate_import_isolated=True,
        no_new_surface_crossings=clearance["no_new_surface_crossings"],
    )
    contract.save(out / "workflow-check.json", report)
    print("MECHA_WORKFLOW", report)


if __name__ == "__main__":
    main()
