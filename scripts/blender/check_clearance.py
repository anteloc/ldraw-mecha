"""Optional sampled mesh diagnostic, reusing the supplied rig's BVH helpers.

Rest-contact pairs and pairs within a rigid body are excluded. This detects new
surface crossings, not containment or worsening of an existing contact. It is
not a substitute for joint fit and physical clearance review.
"""

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts/blender"))
import bpy
from mathutils import Vector
import ldraw_mecha as reference
from ldraw_mechanisms import blender as adapter, plan as contract


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--plan", required=True)
    p.add_argument("--report", required=True)
    p.add_argument("--controls", nargs="+", required=True)
    p.add_argument("--steps", type=int, default=9)
    p.add_argument(
        "--rebuild",
        action="store_true",
        help="Study a revised plan in this background process",
    )
    args = p.parse_args(sys.argv[sys.argv.index("--") + 1 :])
    if not 2 <= args.steps <= 100:
        raise ValueError("--steps must be 2..100")
    plan = contract.load(args.plan)
    rig = adapter.build(plan) if args.rebuild else adapter.context_from_scene(plan)
    ctrl = rig["controller"]
    if ctrl.animation_data:
        ctrl.animation_data.action = None
    owner = {i: name for name, b in plan["bodies"].items() for i in b["instances"]}
    moving = [rig["mapping"][i] for i in owner]
    static = [
        rig["mapping"][n["id"]]
        for n in plan["source"]["nodes"]
        if n["kind"] == "part" and n["id"] not in owner
    ]
    deps = bpy.context.evaluated_depsgraph_get()
    cache = {}
    inv = adapter.C_INV @ rig["root"].matrix_world.inverted()
    static_bounds = {}
    tangencies = set()

    def projected_bounds(obj):
        key = obj.name
        if key in static_bounds:
            return static_bounds[key]
        points = [
            inv @ mesh.matrix_world @ Vector(c)
            for mesh in obj.children_recursive
            if mesh.type == "MESH"
            for c in mesh.bound_box
        ]
        matrix = inv @ obj.matrix_world
        axes = [matrix.to_3x3().col[i].normalized() for i in range(3)]
        result = (points, axes)
        if obj["mecha_id"] not in owner:
            static_bounds[key] = result
        return result

    def has_positive_extent(a, b):
        # Broad-phase separation in each part's directed axes. Coplanar touching
        # faces can flicker in triangle-BVH overlap after Draco quantization.
        # Reject only an actual separating/touching projection, not an AABB hit.
        pa, aa = projected_bounds(a)
        pb, ab = projected_bounds(b)
        for axis in aa + ab:
            ap = [p.dot(axis) for p in pa]
            bp = [p.dot(axis) for p in pb]
            if min(max(ap), max(bp)) - max(min(ap), min(bp)) <= 0.05:
                return False
        return True

    def crossings():
        pairs = reference.overlapping_pairs(moving, static, deps, cache, shrink=0.4)
        result = set()
        for a, b in pairs:
            a, b = bpy.data.objects[a], bpy.data.objects[b]
            ids = tuple(sorted((a["mecha_id"], b["mecha_id"])))
            if owner.get(ids[0]) == owner.get(ids[1]):
                continue
            if has_positive_extent(a, b):
                result.add(ids)
            else:
                tangencies.add(ids)
        return result

    baseline = crossings()
    samples = []
    for name in args.controls:
        c = plan["controls"][name]
        for i in range(args.steps):
            values = {k: v["default"] for k, v in plan["controls"].items()}
            values[name] = c["min"] + (c["max"] - c["min"]) * i / (args.steps - 1)
            adapter.set_controls(rig, **values)
            hits = crossings() - baseline
            samples.append(
                dict(
                    control=name, value=values[name], new_surface_crossings=sorted(hits)
                )
            )
    contract.save(
        args.report,
        dict(
            no_new_surface_crossings=all(
                not s["new_surface_crossings"] for s in samples
            ),
            samples=samples,
            excluded_rest_pairs=sorted(baseline),
            shrink_ldu=0.4,
            touching_tolerance_ldu=0.05,
            excluded_touching_pairs=sorted(tangencies),
            coverage="Sampled surface crossings only; excludes rigid-body and rest-contact pairs; containment untested",
        ),
    )


if __name__ == "__main__":
    main()
