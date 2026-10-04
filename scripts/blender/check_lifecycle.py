"""Integration check: two imported copies, rebuild, untouched static parts, remove."""

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import bpy
from ldraw_mechanisms import blender as adapter, plan as contract


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--plan", required=True)
    p.add_argument("--glb", required=True)
    p.add_argument("--report", required=True)
    args = p.parse_args(sys.argv[sys.argv.index("--") + 1 :])
    plan = contract.load(args.plan)
    bpy.ops.import_scene.gltf(filepath=str(Path(args.glb).resolve()))
    root, mapping = adapter.bind(plan)
    before = {k: (o.parent, o.matrix_basis.copy()) for k, o in mapping.items()}
    rig = adapter.build(plan, root)
    sample = {name: c["max"] * 0.7 for name, c in plan["controls"].items()}
    first = adapter.verify(rig, plan, [sample])
    adapter.set_controls(rig, **sample)
    counts = (len(bpy.data.objects), len(bpy.data.collections))
    rig = adapter.build(plan, root)
    assert counts == (len(bpy.data.objects), len(bpy.data.collections)), (
        "Rebuild leaked objects or collections"
    )
    second = adapter.verify(rig, plan, [sample])
    bpy.ops.import_scene.gltf(filepath=str(Path(args.glb).resolve()))
    roots = [
        o
        for o in bpy.context.scene.objects
        if o.get("mecha_id") == "root" and o != root
    ]
    other = adapter.build(plan, roots[0])
    other = adapter.context_from_scene(plan, roots[0])
    other_count = len(other["root"].children_recursive)
    adapter.remove(root)
    assert len(other["root"].children_recursive) == other_count, (
        "Removing one rig changed another"
    )
    errors = []
    for key, (parent, matrix) in before.items():
        o = mapping[key]
        assert o.parent == parent, "Parent not restored"
        errors.append(
            max(
                abs(o.matrix_basis[i][j] - matrix[i][j])
                for i in range(4)
                for j in range(4)
            )
        )
    report = dict(
        passed=first["passed"] and second["passed"] and max(errors) < 1e-5,
        restore_error=max(errors),
        rebuild_no_leaks=True,
        two_copies_isolated=True,
    )
    # Nonzero defaults and values outside UI ranges must agree with evaluation.
    import copy

    altered = copy.deepcopy(plan)
    control = next(iter(altered["controls"]))
    spec = altered["controls"][control]
    spec["default"] = (spec["min"] + spec["max"]) / 3
    if spec["default"] == 0:
        spec["default"] = spec["max"] / 3
    changed = adapter.build(altered, root)
    defaults = adapter.verify(changed, altered, [{}, {control: spec["max"] * 2 + 1}])
    report["nonzero_default_and_clamp"] = defaults["passed"]
    report["passed"] = report["passed"] and defaults["passed"]
    contract.save(args.report, report)
    if not report["passed"]:
        raise RuntimeError(str(report))


if __name__ == "__main__":
    main()
