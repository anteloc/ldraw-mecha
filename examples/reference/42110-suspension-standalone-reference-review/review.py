"""Reproduce the standalone-suspension reference; leave selected outputs untouched."""
from pathlib import Path
import hashlib
import importlib.util
import json
import sys

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT))
sys.path.insert(0,str(ROOT/"scripts"))
from reference_assets import load_plan
from ldraw_mechanisms import plan
from ldraw_mechanisms.math3d import add, length, mul, point, sub, unit
import build_defender_suspension as builder
import build_suspension_standalone as standalone

def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    result=importlib.util.module_from_spec(spec);spec.loader.exec_module(result);return result

anim=module("suspension_reference_animator",ROOT/"scripts/blender/animate_defender_suspension.py")
OUT = ROOT / "output/reference-rechecks/42110-suspension-standalone"
OUT.mkdir(parents=True, exist_ok=True)
BASE=ROOT/"examples/reference/42110-suspension-standalone"
FULL=ROOT/"examples/reference/42110-suspension"
p=load_plan(BASE/"plan.json");full=load_plan(FULL/"plan.json")
valid=plan.validate(p,check_source=True)
idmap=json.loads((BASE/"source/idmap.json").read_text())["idmap"]
keep=json.loads((BASE/"keep.json").read_text())
built=builder.build(load_plan(FULL/"study/plan.json"),
    json.loads((FULL/"evidence/contacts-suspension.json").read_text()),
    stops=dict(fl=30.5,fr=30.5))
fields=("controls","signals","bodies","anchors","checks")
full_same={f:built[f]==full[f] for f in fields};assert all(full_same.values())
mapped=standalone.remap(full,load_plan(BASE/"study/plan.json"),idmap,keep["parts"])
same={f:mapped[f]==p[f] for f in fields};assert all(same.values())
old={n["id"]:n for n in full["source"]["nodes"]}
nodes={n["id"]:n for n in p["source"]["nodes"]}
assert len(set(idmap.values()))==len(idmap)==len(nodes)
assert set(idmap)=={r["id"] for r in keep["parts"]}
matrix_error=0
for a,b in idmap.items():
    assert old[a]["ref"].lower()==nodes[b]["ref"].lower()
    assert old[a]["effective_colour"]==nodes[b]["effective_colour"]
    matrix_error=max(matrix_error,max(abs(x-y) for ar,br in zip(old[a]["world"],nodes[b]["world"]) for x,y in zip(ar,br)))
assert matrix_error<1e-6
samples=[]
fractions=[(0,0,0,0),(1,1,1,1),(.3,1,0,.7),(.9,.05,.6,.25)]
for fs in fractions:
    values={f"travel_{c}":f*p["controls"][f"travel_{c}"]["max"] for c,f in zip(builder.CORNERS,fs)}
    e=plan.evaluate(p,values)
    assert e["transforms"]==plan.evaluate(full,values)["transforms"]
    assert all(c["passed"] for c in e["checks"])
    samples.append(dict(controls=values,max_closure_error=max(c["error"] for c in e["checks"]),
        angles={c:e["signals"]["th_"+c] for c in builder.CORNERS},
        compression={c:-e["signals"]["ext_"+c+"0"] for c in builder.CORNERS},
        spring_scale={c:e["signals"]["k_"+c+"0"] for c in builder.CORNERS}))
sweep=plan.sweep(p,49);assert sweep["passed"]
timeline=anim.timeline(p);continuity=anim.continuity(p,timeline)
assert all(r["checks_passed"] for r in timeline) and continuity["passed"]
corners={}
for c,spec in builder.CORNERS.items():
    roles={k:idmap[spec[k]] for k in ("upper","lower","bearing","yoke")}
    roles.update(wheel=[idmap[i] for i in spec["wheel"]],links=[idmap[i] for i in spec["links"]],
        shocks=[dict(rod=idmap[s+"/0"],cylinder=idmap[s+"/1"],spring=idmap[s+"/2"])
                for s in spec["shocks"]])
    k=built["corners"][c]
    corners[c]=dict(roles=roles,source_roles=spec,geometry=built["review"][c],
        basis=dict(e1=k.e1,e2=k.e2,normal=k.n,vx=k.vx,vy=k.vy))
# Check the spring seat and free end independently against cylinder/rod transforms.
spring_error=0
for fs in fractions[1:]:
    values={f"travel_{c}":f*p["controls"][f"travel_{c}"]["max"] for c,f in zip(builder.CORNERS,fs)}
    e=plan.evaluate(p,values)
    for c in builder.CORNERS:
        for j in range(2):
            tag=f"{c}{j}";b=p["bodies"]["spring_"+tag];seat=b["origin"]
            end=add(seat,mul(unit(b["axis"]),44))
            for q,other in ((seat,"cyl_"+tag),(end,"rod_"+tag)):
                spring_error=max(spring_error,length(sub(point(e["transforms"]["spring_"+tag],q),
                    point(e["transforms"][other],q))))
assert spring_error<1e-6
report=dict(date="2026-10-06",validation=valid,plan_digest=plan.digest(p),
    source_sha256=p["source"]["sha256"],full_builder_matches=full_same,remapped_motion_matches=same,
    extraction=dict(parts=len(idmap),max_world_matrix_error=matrix_error,counts=keep["counts"]),
    corners=corners,samples=samples,
    sweep=dict(passed=sweep["passed"],samples=len(sweep["samples"]),
        max_error=max(s["max_error"] for s in sweep["samples"])),
    timeline=dict(frames=len(timeline),fps=anim.FPS,closures_every_frame=True,continuity=continuity),
    max_spring_endpoint_error_ldu=spring_error,
    bodies={name:dict(instances=b["instances"],kind=b["kind"],parent=b.get("parent"))
            for name,b in p["bodies"].items()},
    coupling_evidence={k:v for k,v in built["connections"].items() if v["kind"] in ("ball","revolute")},
    provenance={str(f.relative_to(ROOT)):hashlib.sha256(f.read_bytes()).hexdigest()
        for f in (BASE/"plan.json",BASE/"source/idmap.json",BASE/"source/42110-suspension-standalone.mpd",
            ROOT/"scripts/build_defender_suspension.py",ROOT/"scripts/build_suspension_standalone.py",
            ROOT/"scripts/blender/animate_defender_suspension.py")})
(OUT/"review.json").write_text(json.dumps(report,indent=2)+"\n")
print(json.dumps({k:report[k] for k in ("validation","full_builder_matches","remapped_motion_matches","extraction","sweep","max_spring_endpoint_error_ldu")}))
print(json.dumps(dict(timeline_frames=len(timeline),continuity=continuity["passed"],samples=samples)))
