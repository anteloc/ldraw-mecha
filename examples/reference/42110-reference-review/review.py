"""Reproduce the evidence used by the curated 42110 documents; never writes a rig."""
from pathlib import Path
import importlib.util
import hashlib
import json
import math
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
from reference_assets import load_plan
from ldraw_mechanisms import plan
from ldraw_mechanisms.math3d import dot

OUT = ROOT / "output/reference-rechecks/42110"
OUT.mkdir(parents=True, exist_ok=True)
BASE = ROOT / "examples/reference/42110"

def module(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result

builder = module("defender_builder", "scripts/build_defender_rig.py")
animator = module("defender_animator", "scripts/blender/animate_defender.py")
p = load_plan(BASE / "plan.json")
valid = plan.validate(p, check_source=True)
built = builder.build(load_plan(BASE / "study/plan.json"), json.loads((BASE / "evidence/contacts-mechanical.json").read_text()))
same = {k: built[k] == p[k] for k in ("controls", "signals", "bodies", "anchors", "checks")}
assert all(same.values()), same
states = builder.verify_kinematics(p, built["meshes"], built["locks"], built["axes"]["ZC"])
rows = animator.timeline(p)
continuity = animator.continuity(p, rows)
owner = {i: name for name, b in p["bodies"].items() for i in b["instances"]}
meshes = [dict(a=a, b=b, a_body=owner.get(a), b_body=owner.get(b),
               axis_a=aa, axis_b=ab, b_per_a=k,
               carrier=builder.PLANETS.get(a) or builder.PLANETS.get(b))
          for a, aa, b, ab, k in built["meshes"]]
samples = []
for values in (
    dict(drive=.37, diff_front=.13, diff_rear=-.09, diff_center=.07, direction_select=1, range_select=-1, gear_select=math.pi/2, steering=1.2, winch=.7),
    dict(drive=-1.7, diff_front=-.2, diff_rear=.16, diff_center=-.05, direction_select=-1, range_select=1, gear_select=math.pi, steering=-1.4, winch=-.6),
    dict(drive=2*math.pi),
):
    r = plan.evaluate(p, values)
    samples.append(dict(controls=r["controls"], signals={k:r["signals"][k] for k in
       ("m_front","m_rear","side_fl","side_fr","side_rl","side_rr","front_spider","rear_spider","cdiff_carrier","cdiff_spider","out","engine",
        "uj_fl_out","wheel_fl","wheel_fr","wheel_rl","wheel_rr","rack","knuckle_l_angle","knuckle_r_angle","winch_mid","winch_drum")},
        checks=r["checks"]))
    assert all(c["passed"] for c in r["checks"])

gears = []
for j in range(4):
    r=plan.evaluate(p, dict(drive=.4,direction_select=1,range_select=-1,gear_select=j*math.pi/2))["signals"]
    gears.append(dict(gear=j+1, angle=j*math.pi/2, input_body="seq_input", output_body="seq_output",
                      output_per_input=r["g_k"], ring_a_absolute_ldu=r["ring20"],
                      ring_a_from_source_ldu=r["ring20_rel"], ring_b_ldu=r["ring40"],
                      locked_parts=built["locks"][j], engaged=r["g_on"]))

neutral = []
for d,r,g in ((0,-1,0),(1,0,0),(1,-1,math.pi/4),(-1,0,math.pi/4)):
    s=plan.evaluate(p, dict(drive=.5,direction_select=d,range_select=r,gear_select=g))["signals"]
    neutral.append(dict(direction=d,range=r,gear_select=g,engine_per_output=s["ratio_e"],
                        middle_per_output=s["ratio_m"],range_shaft_per_output=s["ratio_c26"]))

report = dict(plan_digest=plan.digest(p), source_sha256=p["source"]["sha256"], validation=valid,
    rebuild_matches_saved_plan=same, axes=built["axes"], states=states, gear_states=gears, neutral_cases=neutral,
    meshes=meshes, clutch_locks={str(k):v for k,v in built["locks"].items()},
    timeline=dict(frames=len(rows),fps=animator.FPS,state_changes=[b["frame"] for a,b in zip(rows,rows[1:]) if a["state"]!=b["state"]],continuity=continuity),
    samples=samples, cv_projection_factor=dot(p["bodies"]["front_halfshaft_l"]["axis"],[1,0,0]),
    findings=[
        "Wheel spin uses +/-0.978102966480559 times the halfshaft signal. This is a projection approximation, not exact 1:1 CV angular transfer.",
        "Winch contains two checked bevel meshes linking three rotating bodies, despite older prose saying three meshes.",
        "Internal propshaft phase corrections are 0.0117/0.0191 degrees; the old within-0.01-degree summary is too tight.",
        "Forward engine_per_drive is negative about +ZC; reverse is positive. Values in the old overview were magnitudes.",
        "Suspension, rope/hose/bands, ratchet clicking and body openings are not implemented motion examples.",
        "Passing differential/mesh/clutch checks does not prove tooth phase, full CV behavior, cam contact, transition synchronization or clearance."
    ],
    provenance={str(f.relative_to(ROOT)):hashlib.sha256(f.read_bytes()).hexdigest() for f in
       [BASE/"plan.json",BASE/"kinematics.json",BASE/"animation-check.json",ROOT/"scripts/build_defender_rig.py",ROOT/"scripts/blender/animate_defender.py",ROOT/"ldraw_mechanisms/linkages.py"]})
(OUT/"review.json").write_text(json.dumps(report,indent=2)+"\n")
print(json.dumps(dict(rebuild_matches=same,states=len(states),meshes=len(meshes),timeline_frames=len(rows),
                     continuity=continuity["passed"],cv_factor=report["cv_projection_factor"],report=str(OUT/"review.json"))))
