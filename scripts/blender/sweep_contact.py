"""Find the first control value at which given part pairs start crossing (fine sampled BVH).

Use after `check_clearance` reports a crossing between samples, to measure a
contact stop precisely. Uses the same BVH helper and 0.4 LDU inward shrink as
the clearance check; a result is the first sampled crossing, not an exact
contact solution.

    blender --background output/42110-suspension/rigged.blend \
        --python scripts/blender/sweep_contact.py -- \
        --plan output/42110-suspension/plan.json --control travel_fl \
        --pair 0/0/86 0/0/15 --pair 0/0/85 0/0/15 --range 28 40.5 0.25 \
        --report output/42110-suspension/stop-sweep.json
"""

import argparse
import importlib.util
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import bpy  # noqa: E402
from ldraw_mechanisms import blender as adapter, plan as contract  # noqa: E402


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--plan", required=True)
    p.add_argument("--control", required=True)
    p.add_argument("--pair", nargs=2, action="append", required=True, metavar=("MOVING", "OTHER"))
    p.add_argument("--range", nargs=3, type=float, required=True, metavar=("FROM", "TO", "STEP"))
    p.add_argument("--report", required=True, help="JSON file; existing entries for other controls are kept")
    p.add_argument("--shrink", type=float, default=0.4)
    args = p.parse_args(sys.argv[sys.argv.index("--") + 1 :])
    spec = importlib.util.spec_from_file_location("_mecha_reference", ROOT / "scripts/blender/ldraw_mecha.py")
    reference = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(reference)
    plan = contract.load(args.plan)
    rig = adapter.context_from_scene(plan)
    lo, hi, step = args.range
    first = {}
    with adapter.preserve_controls(rig):
        n = 0
        while lo + n * step <= hi + 1e-9:
            value = lo + n * step
            adapter.set_controls(rig, **{args.control: value})
            deps = bpy.context.evaluated_depsgraph_get()
            for a, b in args.pair:
                if f"{a}|{b}" in first:
                    continue
                ta = reference.part_bvh(rig["mapping"][a], deps, args.shrink)
                tb = reference.part_bvh(rig["mapping"][b], deps, args.shrink)
                if ta and tb and ta.overlap(tb):
                    first[f"{a}|{b}"] = value
            n += 1
    path = Path(args.report)
    report = json.loads(path.read_text()) if path.exists() else {}
    report[args.control] = dict(
        first_crossing=first,
        never_crossed=[f"{a}|{b}" for a, b in args.pair if f"{a}|{b}" not in first],
        range=[lo, hi, step],
        shrink_ldu=args.shrink,
        coverage="Sampled BVH overlap of the named pairs only, other controls at their defaults",
    )
    contract.save(path, report)
    print("MECHA_CONTACT", json.dumps(first))


if __name__ == "__main__":
    main()
