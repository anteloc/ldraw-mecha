"""Inspect the selected animated suspension in a separate Blender process; never save it."""
from pathlib import Path
import hashlib
import importlib.util
import json
import sys
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
import bpy
from ldraw_mechanisms import blender as adapter, plan
BASE=ROOT/"output/42110-suspension-standalone"
p=plan.load(BASE/"plan.json");rig=adapter.context_from_scene(p)
embedded=json.loads(rig["root"]["mecha_plan"])
same={k:embedded[k]==p[k] for k in ("controls","signals","bodies","anchors","checks")}
assert all(same.values())
spec=importlib.util.spec_from_file_location("reference_animation",ROOT/"scripts/blender/animate_defender_suspension.py")
anim=importlib.util.module_from_spec(spec);spec.loader.exec_module(anim)
limits={c:p["controls"]["travel_"+c]["max"] for c in anim.CORNERS}
frame_rows=[]
for frame in (1,90,200,300,402,460,612):
    bpy.context.scene.frame_set(frame);bpy.context.view_layer.update()
    actual={c:float(rig["controller"]["travel_"+c]) for c in anim.CORNERS}
    expected=anim.travel(frame,limits)
    error=max(abs(actual[c]-expected[c]) for c in anim.CORNERS)
    assert error<1e-5
    frame_rows.append(dict(frame=frame,actual=actual,max_control_error_ldu=error))
samples=[{f"travel_{c}":f*limits[c] for c,f in zip(anim.CORNERS,fs)}
    for fs in ((0,0,0,0),(1,1,1,1),(.3,1,0,.7),(.9,.05,.6,.25))]
report=adapter.verify(rig,p,samples=samples,tolerance=.01)
assert report["passed"]
result=dict(blender_version=bpy.app.version_string,controller=rig["controller"].name,
    file_sha256=hashlib.sha256(Path(bpy.data.filepath).read_bytes()).hexdigest(),
    embedded_motion_matches=same,animation_control_samples=frame_rows,verification=report,source_blend_saved=False)
(ROOT/"output/42110-suspension-standalone-reference-review/blender-check.json").write_text(json.dumps(result,indent=2)+"\n")
print("SUSPENSION_REFERENCE_REVIEW",json.dumps(dict(passed=report["passed"],animation_samples=len(frame_rows))))
