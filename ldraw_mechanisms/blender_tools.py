"""Callable Blender workflows. CLI wrappers delegate here; no argv manipulation.

Import this module in Blender only. Live defaults are additive: no scene reset,
no animation creation and no save unless explicitly requested by the caller.
"""

from pathlib import Path
import importlib.util
import json

import bpy
from mathutils import Vector
from . import blender as adapter, plan as contract


def _plan(value):
    return contract.load(value) if isinstance(value, (str, Path)) else value


def apply_plan(
    plan,
    *,
    glb=None,
    root=None,
    save=None,
    report=None,
    verify_existing=False,
    animate=False,
    new_scene=False,
    tolerance=0.002,
):
    """Import/build or verify a rig; return {'rig': context, 'report': checks}.

    `tolerance` (LDU, default 0.002) bounds matrix errors. Very large models
    can exceed the default through float32 rounding of deep placements; pass a
    larger value only with that measured reason, it is reported with the result.
    """
    plan = _plan(plan)
    contract.validate(plan)
    if root is not None and glb:
        raise ValueError("Pass root or glb, not both")
    if new_scene:
        if not glb:
            raise ValueError("--new-scene requires --glb")
        bpy.ops.wm.read_factory_settings(use_empty=True)
    if glb:
        before = set(bpy.data.objects)
        bpy.ops.import_scene.gltf(filepath=str(Path(glb).resolve()))
        roots = [
            o for o in set(bpy.data.objects) - before if o.get("mecha_id") == "root"
        ]
        if len(roots) != 1:
            raise ValueError("Expected exactly one model root in imported GLB")
        root = roots[0]
    rig = (
        adapter.context_from_scene(plan, root)
        if verify_existing
        else adapter.build(plan, root)
    )
    if "mechanisms" in plan:
        inspect_prepared(plan, root=rig["root"])
    samples = [{}]
    for name, c in plan["controls"].items():
        for v in (c["min"], (c["min"] + c["max"]) / 2, c["max"]):
            samples.append({name: v})
    if "spin_rl" in plan["controls"] and "steering" in plan["controls"]:
        samples += [dict(spin_rl=0.7, spin_rr=-0.2, steering=0.4)]
    if len(plan["controls"]) > 1:
        samples.append(contract.combined_sample(plan))
    result = adapter.verify(rig, plan, samples, tolerance=tolerance)
    if report:
        contract.save(report, result)
    if not result["passed"]:
        raise RuntimeError("Blender verification failed: " + str(result))
    if animate:
        ctrl = rig["controller"]
        for name, c in plan["controls"].items():
            for frame, value in [
                (1, c["default"]),
                (40, c["max"]),
                (80, c["min"]),
                (120, c["default"]),
            ]:
                ctrl[name] = float(value)
                ctrl.keyframe_insert(data_path=f'["{name}"]', frame=frame)
        bpy.context.scene.frame_end = 120
        bpy.context.scene.frame_set(1)
    if save:
        Path(save).resolve().parent.mkdir(parents=True, exist_ok=True)
        # Save a useful initial viewport as well as the rig and active controller.
        points = [
            o.matrix_world @ Vector(c)
            for o in rig["root"].children_recursive
            if o.type == "MESH"
            for c in o.bound_box
        ]
        if points:
            lo = Vector([min(p[i] for p in points) for i in range(3)])
            hi = Vector([max(p[i] for p in points) for i in range(3)])
            for screen in bpy.data.screens:
                for area in screen.areas:
                    if area.type == "VIEW_3D":
                        view = area.spaces.active.region_3d
                        view.view_location = (lo + hi) * 0.5
                        view.view_distance = max(hi - lo) * 1.8
                        view.view_rotation = Vector((1.15, -1.5, 1.05)).to_track_quat(
                            "Z", "Y"
                        )
        bpy.ops.wm.save_as_mainfile(filepath=str(Path(save).resolve()))
    return dict(rig=rig, report=result)


def _ident(obj):
    """Source ID of an imported object; merged primitive meshes report their first leaf."""
    if "mecha_id" in obj:
        return obj["mecha_id"]
    return json.loads(obj["mecha_merged"])[0]


def check_clearance(
    plan, *, rig=None, root=None, controls=None, steps=9, report=None, rebuild=False
):
    """Sample surface crossings relative to declared defaults; restore live state.

    This excludes rigid-body and rest-contact pairs and does not test containment.
    Rebuild is explicit and replaces the rig; normal calls preserve animation.
    """
    plan = _plan(plan)
    contract.validate(plan)
    if not 2 <= steps <= 100:
        raise ValueError("steps must be 2..100")
    controls = list(plan["controls"]) if controls is None else list(controls)
    if not controls or set(controls) - set(plan["controls"]):
        raise ValueError("Select known controls")
    if rig is not None and (root is not None or rebuild):
        raise ValueError("Pass rig, or root/rebuild, not both")
    rig = rig or (
        adapter.build(plan, root) if rebuild else adapter.context_from_scene(plan, root)
    )
    stored = json.loads(rig["root"]["mecha_plan"])
    if {k: v for k, v in stored.items() if k != "notes"} != {
        k: v for k, v in plan.items() if k != "notes"
    }:
        raise ValueError(
            "Clearance plan differs from the built rig; rebuild before sampling"
        )
    # Reuse the supplied BVH implementation without putting scripts on sys.path.
    helper = Path(__file__).resolve().parents[1] / "scripts/blender/ldraw_mecha.py"
    spec = importlib.util.spec_from_file_location("_mecha_reference", helper)
    reference = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(reference)
    owner = {i: name for name, b in plan["bodies"].items() for i in b["instances"]}
    # Merged primitive leaves share one object; test each object once.
    moving = list(dict.fromkeys(rig["mapping"][i] for i in owner))
    static = list(
        dict.fromkeys(
            rig["mapping"][n["id"]]
            for n in plan["source"]["nodes"]
            if n["kind"] == "part" and n["id"] not in owner
        )
    )
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
        if _ident(obj) not in owner:
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
            ids = tuple(sorted((_ident(a), _ident(b))))
            if owner.get(ids[0]) == owner.get(ids[1]):
                continue
            if has_positive_extent(a, b):
                result.add(ids)
            else:
                tangencies.add(ids)
        return result

    with adapter.preserve_controls(rig):
        adapter.set_controls(
            rig, **{k: c["default"] for k, c in plan["controls"].items()}
        )
        baseline = crossings()
        samples = []
        for name in controls:
            c = plan["controls"][name]
            for i in range(steps):
                values = {k: v["default"] for k, v in plan["controls"].items()}
                values[name] = c["min"] + (c["max"] - c["min"]) * i / (steps - 1)
                adapter.set_controls(rig, **values)
                hits = crossings() - baseline
                samples.append(
                    dict(
                        control=name,
                        value=values[name],
                        new_surface_crossings=sorted(hits),
                    )
                )
    result = dict(
        no_new_surface_crossings=all(not s["new_surface_crossings"] for s in samples),
        samples=samples,
        excluded_rest_pairs=sorted(baseline),
        shrink_ldu=0.4,
        touching_tolerance_ldu=0.05,
        excluded_touching_pairs=sorted(tangencies),
        coverage="Sampled surface crossings only; excludes rigid-body and rest-contact pairs; containment untested",
    )
    if report:
        contract.save(report, result)
    return result


def inspect_prepared(plan, *, glb=None, root=None):
    """Import/bind a draft for inspection without creating motion or saving.

    Returned mapping uses exactly the occurrence IDs in the Mermaid diagrams.
    Existing scenes are additive; duplicate imports bind to the new root only.
    The root stores the study and its digest, including unresolved evidence.
    """
    from .mechanisms import diagram, members

    plan = _plan(plan)
    contract.validate(plan)
    if "mechanisms" not in plan:
        raise ValueError("Run prepare first to create mechanism views")
    if root is not None and glb:
        raise ValueError("Pass root or glb, not both")
    if glb:
        before = set(bpy.data.objects)
        bpy.ops.import_scene.gltf(filepath=str(Path(glb).resolve()))
        roots = [
            o for o in set(bpy.data.objects) - before if o.get("mecha_id") == "root"
        ]
        if len(roots) != 1:
            raise ValueError("Expected exactly one imported model root")
        root = roots[0]
    root, mapping = adapter.bind(plan, root, require_ready=False)
    root["mecha_study"] = json.dumps(plan, separators=(",", ":"))
    root["mecha_study_digest"] = contract.digest(plan)
    membership = {name: members(plan, name) for name in plan["mechanisms"]}
    for instance, obj in mapping.items():
        obj["mecha_mechanisms"] = json.dumps(
            [name for name, ids in membership.items() if instance in ids]
        )
    # Plain text blocks are review artifacts, never scripts/handlers.
    for text in list(bpy.data.texts):
        if text.get("mecha_study_root") == root.name:
            bpy.data.texts.remove(text)
    for name in plan["mechanisms"]:
        text = bpy.data.texts.new(f"MECHA_{root.name}_{name}.mmd")
        text["mecha_study_root"] = root.name
        text["mecha_plan_digest"] = contract.digest(plan)
        text.write(diagram(plan, name))
    return dict(root=root, mapping=mapping)


def select_mechanism(context, name):
    """Select a diagram's physical instances and meshes in the current view layer."""
    from .mechanisms import members

    plan = json.loads(context["root"]["mecha_study"])
    if name not in plan["mechanisms"]:
        raise ValueError(f"Unknown mechanism {name}")
    ids = sorted(members(plan, name))
    for obj in bpy.context.selected_objects:
        obj.select_set(False)
    selected = []
    for instance in ids:
        obj = context["mapping"][instance]
        for item in [obj, *obj.children_recursive]:
            if (
                item.name in bpy.context.view_layer.objects
                and not item.hide_get()
                and not item.hide_select
            ):
                item.select_set(True)
                selected.append(item)
    if selected:
        bpy.context.view_layer.objects.active = selected[0]
    return dict(mechanism=name, instances=ids, selected_objects=len(selected))
