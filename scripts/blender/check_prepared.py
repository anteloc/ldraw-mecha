"""End-to-end regression: inspect draft, author a joint, rig without reconversion.

Use a disposable background process with a prepared 106 car. Existing lifecycle
and reopening scripts then check the saved motion plan and unchanged GLB.
"""

import argparse
import json
import math
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import bpy
from ldraw_mechanisms import blender as adapter, blender_tools as workflows
from ldraw_mechanisms import mechanisms, plan as contract


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--study", required=True)
    parser.add_argument("--glb", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1 :])
    out = Path(args.output).resolve()
    study = contract.load(args.study)
    before = set(bpy.data.objects)
    user_text = bpy.data.texts.new("USER_NOTES")
    user_text.use_fake_user = True
    user_text.write("Preserve these notes through inspection and reopening.")
    other_text = bpy.data.texts.new("OTHER_MODEL.mmd")
    other_text.use_fake_user = True
    other_text["mecha_study_root"] = "another-model-root"
    preserved_texts = {t.name: t.as_string() for t in (user_text, other_text)}
    text_names = set(bpy.data.texts.keys())
    context = workflows.inspect_prepared(study, glb=args.glb)
    assert set(bpy.data.texts.keys()) == text_names, "Inspection generated text blocks"
    assert before <= set(bpy.data.objects), "Inspection removed unrelated objects"
    assert "mecha_active_rig" not in context["root"], "Draft inspection created a rig"
    try:
        adapter.build(study, context["root"])
    except ValueError as exc:
        assert "Draft plan" in str(exc)
    else:
        raise AssertionError("A draft was accepted for rigging")
    edge_id, hinge = next(
        (k, e)
        for k, e in study["connections"].items()
        if e["kind"] == "revolute" and {e["a"], e["b"]} == {"0/39", "0/40"}
    )
    mechanism = next(
        k
        for k in study["mechanisms"]
        if {"0/39", "0/40"} <= mechanisms.members(study, k)
    )
    selected = workflows.select_mechanism(context, mechanism)
    assert set(selected["instances"]) == {"0/39", "0/40"}
    assert json.loads(context["mapping"]["0/40"]["mecha_mechanisms"]) == [mechanism]
    # Deliberate mechanical decisions: roof moves, holder stays fixed. Limits
    # reuse the previously clearance-tested 106 range; no contact infers limits.
    # Reverse the connector axis so positive angles open outward. An axis line
    # alone does not tell us which rotation direction avoids the surrounding car.
    p = mechanisms.add_joint(
        study,
        mechanism=mechanism,
        name="roof",
        instances=["0/40"],
        origin=hinge["measurements"]["position"],
        axis=[-v for v in hinge["measurements"]["axis"]],
        minimum=0,
        maximum=math.radians(75),
        description="Open the roof",
    )
    p["connections"][edge_id].update(
        status="reviewed",
        review="Roof rotates around holder finger hinge; only roof 0/40 moves. Axis reversed for outward opening; range from existing 106 clearance study.",
    )
    p["status"] = "ready"
    p["notes"].append(
        "This study implements the roof only; other candidate mechanisms remain unrigged."
    )
    contract.validate(p)
    contract.save(out / "plan.json", p)
    # Simulate a cache produced by the retired automatic diagram workflow.
    stale = bpy.data.texts.new("OLD_GENERATED.mmd")
    stale["mecha_study_root"] = context["root"].name
    stale["mecha_plan_digest"] = "stale"
    stale_name = stale.name
    result = workflows.apply_plan(p, root=context["root"], animate=True)
    rig = result["rig"]
    assert context["root"] == rig["root"], "Building replaced the imported model"
    assert json.loads(rig["root"]["mecha_study"]) == p, (
        "Embedded study is stale"
    )
    assert stale_name not in bpy.data.texts, "Obsolete generated cache survived refresh"
    assert not any(t.get("mecha_study_root") == rig["root"].name for t in bpy.data.texts)
    for name, content in preserved_texts.items():
        assert bpy.data.texts[name].as_string() == content
    assert adapter.verify(rig, p, [{"roof": 0.731}])["passed"]
    bpy.context.scene.frame_set(23)
    action = rig["controller"].animation_data.action
    value = rig["controller"]["roof"]
    clearance = workflows.check_clearance(
        p, rig=rig, controls=["roof"], steps=9, report=out / "clearance.json"
    )
    assert (
        rig["controller"].animation_data.action == action
        and rig["controller"]["roof"] == value
    )
    assert clearance["no_new_surface_crossings"], (
        "Reviewed roof motion introduces surface crossings"
    )
    bpy.ops.wm.save_as_mainfile(filepath=str(out / "rigged.blend"))
    bpy.ops.wm.open_mainfile(filepath=str(out / "rigged.blend"))
    rig = adapter.context_from_scene(p)
    assert adapter.verify(rig, p, [{"roof": 0.41}])["passed"]
    assert rig["root"]["mecha_study_digest"] == contract.digest(p)
    assert not any(t.get("mecha_study_root") == rig["root"].name for t in bpy.data.texts)
    for name, content in preserved_texts.items():
        assert bpy.data.texts[name].as_string() == content
    report = dict(
        passed=True,
        source_ids_preserved=True,
        draft_inspection_without_rig=True,
        mechanism_selection=True,
        existing_import_reused=True,
        nonzero_motion=True,
        embedded_study_current=True,
        no_automatic_diagrams=True,
        obsolete_diagram_cache_removed=True,
        unrelated_text_preserved=True,
        reopened=True,
        no_new_surface_crossings=clearance["no_new_surface_crossings"],
    )
    contract.save(out / "workflow-check.json", report)
    print("MECHA_PREPARED", report)


if __name__ == "__main__":
    main()
