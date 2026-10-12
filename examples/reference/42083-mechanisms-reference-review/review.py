"""Read-only curation checks for the selected five-rig 42083 output bundle."""
import hashlib
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT), str(ROOT / "scripts")]
import build_42083_mechanisms as builder
import timeline_42083 as timeline
from reference_assets import load_plan
from ldraw_mechanisms import plan as contract
from ldraw_mechanisms.math3d import point

OUT = ROOT / "output/reference-rechecks/42083-mechanisms"
OUT.mkdir(parents=True, exist_ok=True)
SOURCE = ROOT / "examples/reference/42083-mechanisms"
builder.EVIDENCE = SOURCE / "evidence/contacts-mechanical.json"
src = builder.Source()
plans = {}
report = dict(date="2026-10-07", implementation_commit="079b6c869b7f2ea0ab98489d317d149b09bd7f65",
              source_section=builder.SECTION, cases={}, provenance={})
paths = [builder.SOURCE, ROOT / "scripts/build_42083_mechanisms.py",
         ROOT / "scripts/timeline_42083.py", ROOT / "ldraw_mechanisms/blender.py",
         SOURCE / "mechanisms.blend", SOURCE / "animation-check.json", SOURCE / "reopen-check.json"]
for name in builder.NAMES:
    d = SOURCE / name
    p = load_plan(d / "plan.json")
    plans[name] = p
    contract.validate(p, check_source=True)
    doc = json.loads((d / "source/idmap.json").read_text())
    mapping = dict(doc["idmap"], **doc.get("reconstructed", {}))
    extracted = {n["id"]: n for n in p["source"]["nodes"]}
    identity_error = 0.0
    for old, new in doc["idmap"].items():
        before, after = src.nodes[old], extracted[new]
        assert before["ref"] == after["ref"] and before["effective_colour"] == after["effective_colour"]
        identity_error = max(identity_error, max(abs(x-y) for a,b in zip(before["world"], after["world"]) for x,y in zip(a,b)))
    assert identity_error < 1e-6
    a, extra = builder.build(name, src)
    rebuilt = builder.remap_plan(name, a, extra, load_plan(d / "study/plan.json"), doc["idmap"],
                                 doc.get("reconstructed", {}), json.loads((d / "keep.json").read_text())["parts"])
    same = all(p[k] == rebuilt[k] for k in ("controls", "signals", "bodies", "anchors", "checks"))
    assert same, name
    rows = builder.verify(name, p, a, mapping)
    sweep = contract.sweep(p, steps=65)
    assert sweep["passed"], name
    tl = timeline.timeline(name, p, paddle_up_stroke=getattr(a, "paddle", {}).get("up_stroke", -0.6))
    continuity = timeline.continuity(p, tl)
    assert continuity["passed"], name
    frame_checks = [c for row in tl for c in contract.evaluate(p, row["controls"])["checks"]]
    assert all(c["passed"] for c in frame_checks)
    checks = []
    for i in range(65):
        # Independent controls are explicitly swept by contract.sweep above.
        values = {k: c["min"] + (c["max"] - c["min"]) * i / 64 for k,c in p["controls"].items()}
        checks.extend(contract.evaluate(p, values)["checks"])
    report["cases"][name] = dict(
        plan_digest=contract.digest(p), parts=sum(n["kind"] == "part" for n in p["source"]["nodes"]),
        moving_parts=sum(len(b["instances"]) for b in p["bodies"].values()), bodies=len(p["bodies"]),
        signals=len(p["signals"]), checks=len(p["checks"]), motion_matches_builder=same,
        mapped_source_parts=len(doc["idmap"]), max_extraction_matrix_error=identity_error,
        sweep_passed=True, sweep_samples=len(sweep["samples"]), mechanical_states=rows,
        meshes=len(a.meshes), timeline_frames=len(tl), continuity=continuity,
        max_closure_error_ldu=max((c["error"] for c in checks + frame_checks), default=0),
        saved_clearance=json.loads((d / "clearance.json").read_text())["no_new_surface_crossings"],
    )
    paths += [d / "plan.json", d / "source/idmap.json", Path(p["source"]["path"]),
              d / "kinematics.json", d / "clearance.json", d / "lifecycle.json"]

wing = plans["wing"]
L = wing["bodies"]["wing_crank_lower"]["origin"]
P = wing["bodies"]["wing_lift"]["origin"]
wing_rows = []
for theta in (0, 0.13, 0.27, 0.4):
    e = contract.evaluate(wing, dict(wing=theta))
    t = e["transforms"]["wing_lift"]
    dy, dz = P[1] - L[1], P[2] - L[2]
    expected = [0, dy*(math.cos(theta)-1)-dz*math.sin(theta), dy*math.sin(theta)+dz*(math.cos(theta)-1)]
    assert max(abs(t[i][3]-expected[i]) for i in range(3)) < 1e-9
    rotation_error = max(abs(t[i][j]-int(i == j)) for i in range(3) for j in range(3))
    assert rotation_error < 1e-12
    wing_rows.append(dict(wing=theta, translation_ldu=[t[i][3] for i in range(3)], rotation_error=rotation_error,
                          max_closure_error_ldu=max(c["error"] for c in e["checks"])))
report["wing_translation"] = wing_rows

gearbox = plans["gearbox"]
pawl_rows = []
for side, pin, tip, stroke in (("l", "1/193/47", "1/193/54", -0.6), ("r", "1/193/48", "1/193/59", 0.6)):
    p0 = src.g.one(pin, "pin")["pos"]
    t0 = max([c["pos"] for c in src.g.conn(tip, "axle_hole")], key=lambda p: builder.length(builder.sub(p, src.g.at(pin))))
    arm = math.hypot(t0[0]-p0[0], t0[2]-p0[2])
    radius = math.hypot(t0[0]-140, t0[2]+360)
    samples = []
    for fraction in (0.25, 0.5, 0.75, 1):
        e = contract.evaluate(gearbox, dict(paddle=stroke*fraction))
        s = e["signals"]
        actual = point(e["transforms"][f"pawl_{side}"], t0)
        radius_error = abs(math.hypot(actual[0]-140, actual[2]+360)-radius)
        tip_error = math.hypot(actual[0]-s[f"pw{side}_tx"], actual[2]-s[f"pw{side}_tz"])
        assert max(radius_error, tip_error) < 1e-4
        samples.append(dict(paddle=stroke*fraction, radius_error_ldu=radius_error, tip_error_ldu=tip_error))
    pawl_rows.append(dict(side=side, pivot=p0, rest_tip=t0, arm_length_ldu=arm, tip_radius_ldu=radius,
                         driving_stroke=stroke, samples=samples))
report["pawls"] = pawl_rows
report["paddle_only_ratchet_angle"] = contract.evaluate(gearbox, dict(paddle=-0.6))["signals"]["ratchet"]
assert report["paddle_only_ratchet_angle"] == 0
report["reconstruction"] = json.loads((SOURCE / "gearbox/source/idmap.json").read_text())["report"]["reconstructed"]
for path in paths:
    report["provenance"][str(path.relative_to(ROOT))] = hashlib.sha256(path.read_bytes()).hexdigest()
report["passed"] = True
contract.save(OUT / "review.json", report)
print(json.dumps({k:v for k,v in report.items() if k not in ("cases", "provenance")}, indent=2))
