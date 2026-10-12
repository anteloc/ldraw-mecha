"""Reproduce the 42083 reference review without modifying the selected outputs."""
from pathlib import Path
import hashlib
import json
import math
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
from reference_assets import load_plan
from ldraw_mechanisms import plan, recipes
from ldraw_mechanisms.geometry import gear_meshes, coaxial
from ldraw_mechanisms.math3d import cross, direction, dot, length, point, sub, unit
from ldraw_mechanisms.source import Document

OUT = ROOT / "output/reference-rechecks/42083-w16"
OUT.mkdir(parents=True, exist_ok=True)
BASE = ROOT / "examples/reference/42083-w16"
p = load_plan(BASE / "plan.json")
valid = plan.validate(p, check_source=True)
manifest = Document(p["source"]["path"]).manifest(p["source"]["section"])
built = recipes.w16_42083(manifest)
same = {k: built[k] == p[k] for k in ("controls","signals","bodies","anchors","checks")}
assert all(same.values()), same
nodes = {n["id"]:n for n in manifest["nodes"]}
extracted = Document(BASE/"engine-extracted.mpd").manifest()
fields = ("id","ref","kind","parent","world","colour","effective_colour")
assert [{k:n[k] for k in fields} for n in manifest["nodes"]] == [
    {k:n[k] for k in fields} for n in extracted["nodes"]]
meshes = gear_meshes(manifest)
assert {(m["a"],m["b"]) for m in meshes["meshes"]} == {
    ("68","84/16"),("68","85/16"),("82","83")}
coax = coaxial(manifest, ["38","67","68"])
assert all(r["status"] == "candidate" for r in coax["pairs"])
(OUT/"gear-meshes.json").write_text(json.dumps(meshes,indent=2)+"\n")
(OUT/"coaxial.json").write_text(json.dumps(coax,indent=2)+"\n")
owners = {i:b for b,v in p["bodies"].items() for i in v["instances"]}
gear_by_id = {g["id"]:g for g in meshes["gears"]}
mesh_rows = []
for m in meshes["meshes"]:
    # Discovery ratios use each part's reported axis; the rig uses +Z on all shafts.
    ratio = m["b_per_a"] * dot(gear_by_id[m["a"]]["axis"],[0,0,1]) / dot(
        gear_by_id[m["b"]]["axis"],[0,0,1])
    mesh_rows.append(dict(a=m["a"],b=m["b"],a_body=owners[m["a"]],b_body=owners[m["b"]],
        ratio_about_plus_z=ratio,reported_ratio=m["b_per_a"],
        distance_ldu=m["center_distance_ldu"],plane_error_ldu=m["plane_error_ldu"]))
rows = []
for i in range(16):
    piston, rod = p["bodies"][f"piston{i}"], p["bodies"][f"conrod{i}"]
    pin=p["anchors"][rod["start"]]["point"]
    pp=p["anchors"][rod["end"]]["point"]
    shaft=p["anchors"][rod["start"]]["body"]
    center=p["bodies"][shaft]["origin"]
    cr,pr=sub(pin,center),sub(pp,center)
    radius=math.hypot(*cr[:2]);s0=math.hypot(*pr[:2])
    phase=math.atan2(cr[1],cr[0])-math.atan2(pr[1],pr[0])
    L=length(sub(pp,pin))
    own_axis=unit(direction(nodes[piston["instances"][0]]["world"],[0,1,0]))
    rows.append(dict(index=i,crank=shaft,piston=piston["instances"][0],rod=rod["instances"][0],
        z=pin[2],bank_axis=piston["axis"],phase_radians=phase,
        phase_degrees=math.degrees(phase),throw_ldu=radius,rod_length_ldu=L,
        rest_radius_ldu=s0,expected_stroke_ldu=2*radius,
        source_axis_offset_ldu=length(cross(own_axis,[pr[0],pr[1],0])),
        minimum_displacement_ldu=L-radius-s0,maximum_displacement_ldu=L+radius-s0))
samples=[]
for drive in (0,.37,-2.9,7.3,-4*math.pi,4*math.pi,20):
    pose=plan.evaluate(p,dict(drive=drive));s=pose["signals"]
    residuals=[]
    for m in mesh_rows:
        def angle(body):
            return s[p["bodies"][body]["signal"]]
        residuals.append(abs(angle(m["b_body"])-m["ratio_about_plus_z"]*angle(m["a_body"])))
    assert max(residuals)<1e-10
    assert all(c["passed"] for c in pose["checks"])
    samples.append(dict(requested_drive=drive,controls=pose["controls"],signals=s,
        max_closure_error_ldu=max(c["error"] for c in pose["checks"]),
        max_mesh_angle_error_rad=max(residuals)))
sweep=plan.sweep(p,97)
assert sweep["passed"]
# Stroke extrema occur at phase+crank_angle = 0 or pi. Test exact phases rather
# than hoping a coarse, evenly-spaced sweep includes every cylinder's extrema.
for r in rows:
    factor=-5/3 if r["crank"]=="crank_c" else 5/3
    values=[plan.evaluate(p,dict(drive=(angle-r["phase_radians"])/factor))["signals"][f"piston{r['index']}"]
            for angle in (0,math.pi)]
    r["checked_stroke_ldu"]=max(values)-min(values)
    assert abs(r["checked_stroke_ldu"]-r["expected_stroke_ldu"])<1e-10
def transform_error(a,b,names):
    return max(abs(a[n][i][j]-b[n][i][j]) for n in names for i in range(4) for j in range(4))
rest=plan.evaluate(p)["transforms"]
cycle=plan.evaluate(p,dict(drive=6*math.pi/5))["transforms"]
engine_bodies=set(p["bodies"])-{"input_shaft"}
cycle_error=transform_error(rest,cycle,engine_bodies)
assert cycle_error<1e-10
before=plan.evaluate(p,dict(drive=-3*math.pi))["transforms"]
after=plan.evaluate(p,dict(drive=3*math.pi))["transforms"]
whole_error=transform_error(before,after,p["bodies"])
assert whole_error<1e-10
summary=dict(date="2026-10-06",plan_digest=plan.digest(p),source_sha256=manifest["sha256"],
    validation=valid,recipe_matches_saved_motion=same,extracted_manifest_matches=True,
    inventory=dict(parts=sum(n["kind"]=="part" for n in manifest["nodes"]),nodes=len(nodes),
        moving=len(owners),bodies=len(p["bodies"]),signals=len(p["signals"]),checks=len(p["checks"])),
    meshes=mesh_rows,cylinders=rows,samples=samples,
    sweep=dict(passed=sweep["passed"],samples=len(sweep["samples"]),
        max_closure_error_ldu=max(r["max_error"] for r in sweep["samples"])),
    cycles=dict(piston_and_crank_input_increment=6*math.pi/5,engine_transform_error=cycle_error,
        all_body_input_increment=6*math.pi,all_body_transform_error=whole_error),
    findings=[
        "The source description says V8/two cranks; the selected section contains 16 pistons and 3 crankshafts.",
        "The 20T/12T double-bevel pair is used on parallel shafts, not as a right-angle bevel drive.",
        "Raw gear-mesh ratios use part-local axis directions; convert to the common +Z body axes.",
        "No new sampled surface crossings in the retained clearance report does not establish bore containment.",
        "The slider-crank helper assumes a +Z planar crank and a cylinder line through its centre.",
    ],
    provenance={str(f.relative_to(ROOT)):hashlib.sha256(f.read_bytes()).hexdigest()
        for f in (BASE/"plan.json",BASE/"engine-extracted.mpd",BASE/"clearance.json",
            ROOT/"ldraw_mechanisms/recipes.py",ROOT/"ldraw_mechanisms/plan.py")})
(OUT/"review.json").write_text(json.dumps(summary,indent=2)+"\n")
print(json.dumps({k:summary[k] for k in ("inventory","recipe_matches_saved_motion","sweep","cycles")}))
