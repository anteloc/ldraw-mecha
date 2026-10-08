"""Recheck movable or plant examples without importing Blender or changing the bundle.

Use an archived bundle by default; write fresh evidence under output/. Contact
and clearance reports are historical observations, not rerun by this script.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "scripts")]
from ldraw_mechanisms import plan as contract
import build_movables as movable
import movable_clips


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def review(kind, bundle):
    if kind == "plants":
        import build_plants as builder
        import wind_clips as clips
        cases = clips.CASES
    else:
        builder, clips, cases = movable, movable_clips, movable_clips.SCENARIOS
    fields = ("controls", "signals", "bodies", "anchors", "checks")
    report = dict(kind=kind, cases={}, clips={}, coverage="Builder reproduction, source identity, asymmetric "
                  "kinematics and clip data. Existing clearance read, not rerun. No physical proof.")
    for case in cases:
        d = bundle / case["key"]
        p = contract.load(d / "plan.json")
        roles = read(d / "source/parts.json")
        b = builder.assemble(case)
        rebuilt, semantics = movable.author_plan(case, b, contract.load(d / "study/plan.json"))
        assert all(p[f] == rebuilt[f] for f in fields), case["key"]
        assert sha(d / "source/scenario.mpd") == p["source"]["sha256"], case["key"]
        nodes = {n["id"]: n for n in p["source"]["nodes"]}
        for i, part in enumerate(b.parts):
            assert nodes[str(i)]["ref"].lower().removesuffix(".dat") == part["ref"].lower()
            assert max(abs(x-y) for row_a, row_b in zip(nodes[str(i)]["world"], part["matrix"])
                       for x,y in zip(row_a, row_b)) < 1e-6
        values = movable.asymmetric(case)
        contract.evaluate(p, values)
        item = dict(parts=len(roles["parts"]), bodies=len(p["bodies"]), builder_motion_matches=True,
                    source_matches=True, asymmetric_values=values, semantics=semantics,
                    controls=p["controls"], body_frames=p["bodies"], signals=p["signals"],
                    roles=roles["parts"], clearance=read(d / "clearance.json"),
                    hashes={name: sha(d / name) for name in ["plan.json", "source/scenario.mpd", "source/parts.json"]})
        if kind == "plants":
            geometry = builder.wind_geometry(p, b)
            assert not builder.roster_check(case, geometry)
            item.update(wind_geometry=geometry, geometry_checks=b.checks,
                        joint_kinds={k: "flex_approx" if k in b.flex else "real" for k in b.joints},
                        recipe_geometry_check="Within roster_check tolerances: x 15 LDU, swing components 0.08")
        report["cases"][case["key"]] = item
    for clip in clips.library():
        assert not clips.check(clip), clip.id
        document = read(bundle / "clips" / (clip.id + ".json"))
        expected = clips.clip_document(clip)
        assert document["baked"] == expected["baked"], clip.id
        report["clips"][clip.id] = dict(rules_passed=True, baked_values_match=True)
    report["bundle_hashes"] = {name: sha(bundle / name) for name in
                                [kind + ".blend", "catalog.json", "clearance-summary.json"]}
    report["passed"] = True
    return report


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("catalog", choices=("movables", "plants"))
    ap.add_argument("--bundle", type=Path)
    ap.add_argument("--report", type=Path, required=True)
    args = ap.parse_args()
    if not args.report.resolve().is_relative_to(ROOT / "output"):
        ap.error("Write fresh review reports under output/")
    bundle = args.bundle or ROOT / "examples/reference" / args.catalog
    result = review(args.catalog, bundle)
    contract.save(args.report, result)
    print(json.dumps(dict(passed=True, cases=len(result["cases"]), clips=len(result["clips"]))))


if __name__ == "__main__":
    main()
