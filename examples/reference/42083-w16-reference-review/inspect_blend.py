"""Read the selected saved rig in background Blender; write only a review report."""
from pathlib import Path
import hashlib
import json
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
import bpy
from ldraw_mechanisms import blender as adapter, plan

p=plan.load(ROOT/"output/42083-w16/plan.json")
rig=adapter.context_from_scene(p)
ctrl=rig["controller"]
embedded=json.loads(rig["root"]["mecha_plan"])
fields=("controls","signals","bodies","anchors","checks")
same={k:p[k]==embedded[k] for k in fields}
assert all(same.values()),same
action=ctrl.animation_data.action if ctrl.animation_data else None
curves=[]
if action:
    # Legacy and layered actions are both found in saved Blender files.
    candidates=list(getattr(action,"fcurves",[]))
    if not candidates:
        for layer in action.layers:
            for strip in layer.strips:
                for bag in getattr(strip,"channelbags",[]):
                    candidates.extend(bag.fcurves)
    for c in candidates:
        curves.append(dict(path=c.data_path,index=c.array_index,
            keys=[dict(frame=k.co.x,value=k.co.y,interpolation=k.interpolation)
                  for k in c.keyframe_points]))
report=adapter.verify(rig,p,samples=[{},{"drive":.37},{"drive":-2.9},{"drive":7.3},{"drive":20}])
assert report["passed"]
result=dict(blender_version=bpy.app.version_string,
    file_sha256=hashlib.sha256(Path(bpy.data.filepath).read_bytes()).hexdigest(),
    embedded_motion_matches=same,controller=ctrl.name,frame_range=[bpy.context.scene.frame_start,bpy.context.scene.frame_end],
    fps=bpy.context.scene.render.fps/bpy.context.scene.render.fps_base,
    action=action.name if action else None,curves=curves,verification=report,
    source_blend_saved=False)
target=ROOT/"output/42083-w16-reference-review/blender-check.json"
target.write_text(json.dumps(result,indent=2)+"\n")
print("W16_REFERENCE_REVIEW",json.dumps(dict(passed=report["passed"],action=result["action"],curves=curves)))
