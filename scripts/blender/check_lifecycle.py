"""Integration check: placed roots, two copies, rebuild and rest restoration.

Moving a whole rig must not change its root-relative kinematics. This catches
world-space rod roll references that only work with a model at the origin.
"""

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import bpy
from mathutils import Euler, Matrix
from ldraw_mechanisms import blender as adapter, plan as contract


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--plan", required=True)
    p.add_argument("--glb", required=True)
    p.add_argument("--report", required=True)
    p.add_argument("--tolerance", type=float, default=0.002, help="Matrix error bound (LDU)")
    args = p.parse_args(sys.argv[sys.argv.index("--") + 1 :])
    plan = contract.load(args.plan)
    bpy.ops.import_scene.gltf(filepath=str(Path(args.glb).resolve()))
    root, mapping = adapter.bind(plan)
    before = {k: (o.parent, o.matrix_basis.copy()) for k, o in mapping.items()}
    rig = adapter.build(plan, root)
    sample = {name: c["max"] * 0.7 for name, c in plan["controls"].items()}
    tol = args.tolerance
    first = adapter.verify(rig, plan, [sample], tolerance=tol)
    adapter.set_controls(rig, **sample)
    counts = (len(bpy.data.objects), len(bpy.data.collections))
    rig = adapter.build(plan, root)
    assert counts == (len(bpy.data.objects), len(bpy.data.collections)), (
        "Rebuild leaked objects or collections"
    )
    second = adapter.verify(rig, plan, [sample], tolerance=tol)
    # Preserve the imported scale/basis; apply presentation placements in metres.
    # A rod's COPY_LOCATION offset must be evaluated in this model root's space.
    root_world = root.matrix_world.copy()
    placements = {}
    try:
        for label, transform in (
            ("translated", Matrix.Translation((0.7, -0.3, 0.2))),
            ("translated_rotated", Matrix.Translation((-0.4, 0.6, 0.3))
             @ Euler((0.31, -0.47, 0.62), "XYZ").to_matrix().to_4x4()),
        ):
            root.matrix_world = transform @ root_world
            bpy.context.view_layer.update()
            check = adapter.verify(rig, plan, [sample], tolerance=tol)
            placements[label] = dict(
                passed=check["passed"],
                max_matrix_error=max(s["max_matrix_error"] for s in check["samples"]),
                max_static_error=max(s["max_static_error"] for s in check["samples"]),
                max_closure_error=max(s["max_closure_error"] for s in check["samples"]),
            )
    finally:
        root.matrix_world = root_world
        bpy.context.view_layer.update()
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
        passed=first["passed"] and second["passed"] and max(errors) < 1e-5
        and all(p["passed"] for p in placements.values()),
        restore_error=max(errors),
        rebuild_no_leaks=True,
        two_copies_isolated=True,
        tolerance=tol,
        root_placements=placements,
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
    defaults = adapter.verify(
        changed, altered, [{}, {control: spec["max"] * 2 + 1}], tolerance=tol
    )
    report["nonzero_default_and_clamp"] = defaults["passed"]
    report["passed"] = report["passed"] and defaults["passed"]
    contract.save(args.report, report)
    if not report["passed"]:
        raise RuntimeError(str(report))


if __name__ == "__main__":
    main()
