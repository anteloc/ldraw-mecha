"""Blender materialization of the portable contract. Imported only inside Blender.

All geometric decisions are in the plan. The adapter maps LDraw to Blender,
binds verified GLB occurrence IDs, and creates ordinary, persistent drivers.
"""

from __future__ import annotations

import json
from contextlib import contextmanager

import bpy
from mathutils import Matrix, Vector

from . import plan as contract
from .math3d import frame, unit

C = Matrix(((1, 0, 0, 0), (0, 0, -1, 0), (0, 1, 0, 0), (0, 0, 0, 1)))
C_INV = C.inverted()
REST = "mecha_rest"
# Offset in LDU of a rod's roll reference along its declared axis.
ROD_REFERENCE = 100.0


def _tag(obj, rig_id, role):
    obj["mecha_rig"] = rig_id
    obj["mecha_role"] = role


def _driver(obj, path, index, expression, variables):
    fc = obj.driver_add(path) if index is None else obj.driver_add(path, index)
    d = fc.driver
    d.type = "SCRIPTED"
    for name, (target, target_path) in variables.items():
        v = d.variables.new()
        v.name = name
        v.type = "SINGLE_PROP"
        v.targets[0].id = target
        v.targets[0].data_path = target_path
    d.expression = expression
    for modifier in list(fc.modifiers):
        fc.modifiers.remove(modifier)
    if not d.is_simple_expression:
        raise ValueError(f"Not a simple Blender expression: {expression}")


def _objects(root):
    return [root, *root.children_recursive]


def bind(plan, root=None, *, require_ready=True):
    """Preflight before edits; no Blender object-name assumptions."""
    contract.validate(plan)
    if require_ready and plan["status"] != "ready":
        raise ValueError(
            "Draft plan: complete and validate the mechanical decisions first"
        )
    source = plan["source"]
    if root is None:
        roots = [
            o
            for o in bpy.context.scene.objects
            if o.get("mecha_id") == "root"
            and o.get("mecha_source") == source["sha256"]
            and o.get("mecha_section") == source["section"]
        ]
        if len(roots) != 1:
            raise ValueError(
                f"Expected one bound model root, found {len(roots)}; pass root explicitly"
            )
        root = roots[0]
    if (
        root.get("mecha_source") != source["sha256"]
        or root.get("mecha_section") != source["section"]
    ):
        raise ValueError("GLB metadata does not match plan source and section")
    matches = {}
    for o in _objects(root):
        instance = o.get("mecha_id")
        if instance is None:
            continue
        if instance in matches:
            raise ValueError(f"Duplicate imported instance {instance}")
        matches[instance] = o
    missing = [n["id"] for n in source["nodes"] if n["id"] not in matches]
    if missing:
        raise ValueError(f"Missing imported instances: {missing[:8]}")
    # IDs are not enough: catch transforms changed since conversion or unrelated copies.
    inverse = root.matrix_world.inverted()
    rig_id = root.get("mecha_active_rig")
    for n in source["nodes"]:
        o = matches[n["id"]]
        if o.get("mecha_rest_rig") == rig_id and REST in o:
            local = Matrix(json.loads(o[REST])["root_matrix"])
        elif rig_id and n["kind"] == "assembly":
            local = inverse @ o.matrix_world
        else:
            local = inverse @ o.matrix_world
        actual = C_INV @ local @ C
        if (
            max(
                abs(actual[i][j] - n["world"][i][j]) / (0.5 if j == 3 else 0.003)
                for i in range(3)
                for j in range(4)
            )
            > 1
        ):
            raise ValueError(f"Imported rest transform differs from source: {n['id']}")
    return root, matches


def remove(root):
    """Remove only the rig on this root; restore original parent and local matrix."""
    rig_id = root.get("mecha_active_rig")
    if not rig_id:
        return
    # A rebuild/removal should not strand the user in the diagnostic view.
    set_moving_only({"root": root}, False)
    objects = _objects(root)
    by_id = {o.get("mecha_id"): o for o in objects if "mecha_id" in o}
    for o in objects:
        if o.get("mecha_rest_rig") != rig_id:
            continue
        rest = json.loads(o[REST])
        o.parent = by_id[rest["parent"]]
        o.matrix_parent_inverse = Matrix(rest["parent_inverse"])
        o.matrix_basis = Matrix(rest["basis"])
        del o[REST]
        del o["mecha_rest_rig"]
    for o in objects:
        if o.get("mecha_rig") == rig_id:
            bpy.data.objects.remove(o, do_unlink=True)
    for collection in list(bpy.data.collections):
        if collection.get("mecha_rig") == rig_id and not collection.objects:
            bpy.data.collections.remove(collection)
    del root["mecha_active_rig"]
    if "mecha_plan" in root:
        del root["mecha_plan"]
    bpy.context.view_layer.update()


def build(plan, root=None):
    root, mapping = bind(plan, root)
    remove(root)
    rig_id = root.name + "::" + plan["name"]
    coll = bpy.data.collections.new("MECHA_" + plan["name"])
    coll["mecha_rig"] = rig_id
    bpy.context.scene.collection.children.link(coll)
    root["mecha_active_rig"] = rig_id
    rest_frames = {}
    created = []

    def empty(name, parent, matrix, role="frame"):
        o = bpy.data.objects.new(name, None)
        coll.objects.link(o)
        o.parent = parent
        o.empty_display_type = "PLAIN_AXES"
        o.empty_display_size = 8
        o.matrix_basis = (
            rest_frames.get(parent.name, Matrix.Identity(4)).inverted() @ matrix
        )
        rest_frames[o.name] = matrix.copy()
        _tag(o, rig_id, role)
        created.append(o)
        return o

    try:
        ctrl = empty("CTRL_" + plan["name"], root, Matrix.Identity(4), "controller")
        ctrl.empty_display_type = "SPHERE"
        ctrl.empty_display_size = 20
        # Keep the large manifest on the model root, away from the user's sliders.
        root["mecha_plan"] = json.dumps(plan, separators=(",", ":"))
        for name, c in plan["controls"].items():
            ctrl[name] = float(c["default"])
            ctrl.id_properties_ui(name).update(
                min=c["min"],
                max=c["max"],
                soft_min=c["min"],
                soft_max=c["max"],
                description=c["description"],
                subtype="ANGLE" if c["unit"] == "radian" else "NONE",
            )
        inputs = {}
        for name, c in plan["controls"].items():
            o = empty(
                "INPUT_" + plan["name"] + "_" + name, root, Matrix.Identity(4), "input"
            )
            o.empty_display_size = 0.001
            o["value"] = 0.0
            _driver(
                o,
                '["value"]',
                None,
                f"clamp(v,{c['min']!r},{c['max']!r})",
                {"v": (ctrl, f'["{name}"]')},
            )
            inputs[name] = o
        signal_objects = {}
        for name in contract.signal_order(plan):
            s = plan["signals"][name]
            o = empty(
                "SIG_" + plan["name"] + "_" + name, root, Matrix.Identity(4), "signal"
            )
            o.empty_display_size = 0.001
            o.hide_render = True
            o["value"] = 0.0
            variables = {}
            for var, ref in s["variables"].items():
                prefix, target = ref.split(":", 1)
                variables[var] = (
                    (inputs[target], '["value"]')
                    if prefix == "control"
                    else (signal_objects[target], '["value"]')
                )
            _driver(o, '["value"]', None, s["expression"], variables)
            signal_objects[name] = o
        pivots = {}
        for name in contract.body_order(plan):
            b = plan["bodies"][name]
            m = C @ Matrix(frame(b["origin"], b["axis"], b.get("x_hint")))
            frm = empty(
                "FRM_" + plan["name"] + "_" + name,
                pivots[b["parent"]] if b.get("parent") else root,
                m,
            )
            pivot = empty("PIV_" + plan["name"] + "_" + name, frm, m, "body")
            pivots[name] = pivot
            pivot["mecha_body"] = name
            pivot.rotation_mode = "XYZ"
            pivot.empty_display_type = "ARROWS"
            if b["kind"] in ("revolute", "prismatic"):
                path = "rotation_euler" if b["kind"] == "revolute" else "location"
                _driver(
                    pivot,
                    path,
                    2,
                    "v",
                    {"v": (signal_objects[b["signal"]], '["value"]')},
                )
        anchors = {}
        for name, a in plan["anchors"].items():
            m = C @ Matrix.Translation(a["point"])
            anchors[name] = empty(
                "ANCHOR_" + plan["name"] + "_" + name, pivots[a["body"]], m, "anchor"
            )
            anchors[name].empty_display_size = 3
            anchors[name]["mecha_anchor"] = name
        for name, b in plan["bodies"].items():
            if b["kind"] == "rod":
                p = pivots[name]
                con = p.constraints.new("COPY_LOCATION")
                con.target = anchors[b["start"]]
                # The contract aims local Y exactly at the end anchor and keeps
                # local Z as the declared axis projected perpendicular to Y. A
                # single locked track only rotates about a fixed axis, which
                # matches that just for a rod that stays in one plane; a spatial
                # link needs the aim and the roll separately. The reference
                # follows the start anchor with a constant axis offset, so the
                # roll target direction stays exact as the linkage moves.
                reference = empty(
                    "UP_" + plan["name"] + "_" + name,
                    root,
                    Matrix.Translation(
                        C.to_3x3() @ Vector(unit(b["axis"])) * ROD_REFERENCE
                    ),
                )
                offset = reference.constraints.new("COPY_LOCATION")
                offset.target = anchors[b["start"]]
                offset.use_offset = True
                con = p.constraints.new("DAMPED_TRACK")
                con.target = anchors[b["end"]]
                con.track_axis = "TRACK_Y"
                con = p.constraints.new("LOCKED_TRACK")
                con.target = reference
                con.track_axis = "TRACK_Z"
                con.lock_axis = "LOCK_Y"
        bpy.context.view_layer.update()
        root_inverse = root.matrix_world.inverted()
        for name, b in plan["bodies"].items():
            for instance in b["instances"]:
                o = mapping[instance]
                rest = dict(
                    parent=o.parent["mecha_id"],
                    basis=[list(r) for r in o.matrix_basis],
                    parent_inverse=[list(r) for r in o.matrix_parent_inverse],
                    root_matrix=[list(r) for r in root_inverse @ o.matrix_world],
                )
                o[REST] = json.dumps(rest)
                o["mecha_rest_rig"] = rig_id
                # Parent against the source rest frame, not the evaluated pose:
                # nonzero default control values must move the part immediately.
                o.parent = pivots[name]
                o.matrix_parent_inverse.identity()
                o.matrix_basis = rest_frames[pivots[name].name].inverted() @ Matrix(
                    rest["root_matrix"]
                )
        bpy.context.view_layer.update()
        for o in bpy.context.selected_objects:
            o.select_set(False)
        ctrl.select_set(True)
        bpy.context.view_layer.objects.active = ctrl
        return dict(
            root=root,
            controller=ctrl,
            pivots=pivots,
            anchors=anchors,
            signals=signal_objects,
            mapping=mapping,
        )
    except Exception:
        remove(root)
        raise


def set_controls(rig, **values):
    ctrl = rig["controller"]
    plan = json.loads(rig["root"]["mecha_plan"])
    applied = contract.evaluate(plan, values)["controls"]
    for k in values:
        ctrl[k] = float(applied[k])
    ctrl.update_tag()
    bpy.context.view_layer.update()


def verify(rig, plan, samples=None, tolerance=0.002):
    """Compare the evaluated Blender scene with the independent numeric contract."""
    samples = samples or [{}]
    ctrl = rig["controller"]
    moving = {i for b in plan["bodies"].values() for i in b["instances"]}
    source_nodes = {n["id"]: n for n in plan["source"]["nodes"]}
    reports = []
    with preserve_controls(rig):
        for values in samples:
            expected = contract.evaluate(plan, values)
            for k, v in expected["controls"].items():
                # Exercise raw values too: the Blender input driver must enforce
                # the same range as the independent evaluator.
                ctrl[k] = float(values.get(k, v))
            ctrl.update_tag()
            bpy.context.view_layer.update()
            deps = bpy.context.evaluated_depsgraph_get()
            root_inverse = rig["root"].evaluated_get(deps).matrix_world.inverted()
            errors = []
            for name, b in plan["bodies"].items():
                for instance in b["instances"]:
                    n = source_nodes[instance]
                    expected_m = (
                        C
                        @ Matrix(expected["transforms"][name])
                        @ Matrix(n["world"])
                        @ C_INV
                    )
                    actual = (
                        root_inverse
                        @ rig["mapping"][instance].evaluated_get(deps).matrix_world
                    )
                    errors.append(
                        max(
                            abs(actual[i][j] - expected_m[i][j])
                            for i in range(4)
                            for j in range(4)
                        )
                    )
            static_errors = []
            for instance, n in source_nodes.items():
                if instance in moving:
                    continue
                expected_m = C @ Matrix(n["world"]) @ C_INV
                actual = (
                    root_inverse
                    @ rig["mapping"][instance].evaluated_get(deps).matrix_world
                )
                static_errors.append(
                    max(
                        abs(actual[i][j] - expected_m[i][j])
                        for i in range(4)
                        for j in range(4)
                    )
                )
            closure = []
            for c in plan["checks"]:
                a = (
                    root_inverse
                    @ rig["anchors"][c["a"]]
                    .evaluated_get(deps)
                    .matrix_world.translation
                )
                b = (
                    root_inverse
                    @ rig["anchors"][c["b"]]
                    .evaluated_get(deps)
                    .matrix_world.translation
                )
                closure.append(abs((a - b).length - c["length"]))
            invalid = [
                o.name
                for o in _objects(rig["root"])
                if o.get("mecha_rig") == rig["root"]["mecha_active_rig"]
                and o.animation_data
                and any(not f.driver.is_valid for f in o.animation_data.drivers)
            ]
            reports.append(
                dict(
                    controls=values,
                    max_matrix_error=max(errors, default=0),
                    max_static_error=max(static_errors, default=0),
                    max_closure_error=max(closure, default=0),
                    invalid_drivers=invalid,
                    passed=max(errors, default=0) <= tolerance
                    and max(static_errors, default=0) <= tolerance
                    and max(closure, default=0) <= 0.02
                    and not invalid,
                )
            )
    return dict(
        passed=all(r["passed"] for r in reports),
        samples=reports,
        units="LDU",
        coverage="Evaluated transforms, driver validity and declared link closure; no mesh collision test",
    )


def context_from_scene(plan, root=None):
    root, mapping = bind(plan, root)
    objects = [
        o for o in _objects(root) if o.get("mecha_rig") == root["mecha_active_rig"]
    ]
    ctrl = next(o for o in objects if o.get("mecha_role") == "controller")
    return dict(
        root=root,
        mapping=mapping,
        controller=ctrl,
        pivots={o["mecha_body"]: o for o in objects if o.get("mecha_role") == "body"},
        anchors={
            o["mecha_anchor"]: o for o in objects if o.get("mecha_role") == "anchor"
        },
    )


@contextmanager
def preserve_controls(rig):
    """Temporarily release animation for diagnostic samples; always restore it.

    Keep action slots, NLA tracks, controller drivers, raw slider values and time.
    This context does not rebuild the rig or change selection/visibility.
    """
    ctrl = rig["controller"]
    plan = json.loads(rig["root"]["mecha_plan"])
    values = {k: ctrl[k] for k in plan["controls"]}
    scene = bpy.context.scene
    time = (scene.frame_current, scene.frame_subframe)
    animation = ctrl.animation_data
    if animation and animation.use_tweak_mode:
        raise ValueError("Exit NLA tweak mode before sampling controller motion")
    action = animation.action if animation else None
    slot = animation.action_slot if action else None
    tracks = [(t, t.mute) for t in animation.nla_tracks] if animation else []
    drivers = [(f, f.mute) for f in animation.drivers] if animation else []
    try:
        if action:
            animation.action = None
        for item, _ in tracks + drivers:
            item.mute = True
        yield
    finally:
        if action:
            animation.action = action
            animation.action_slot = slot
        for item, mute in tracks + drivers:
            item.mute = mute
        if time != (scene.frame_current, scene.frame_subframe):
            scene.frame_set(time[0], subframe=time[1])
        for k, v in values.items():
            ctrl[k] = v
        ctrl.update_tag()
        bpy.context.view_layer.update()


def update_plan_notes(rig, notes):
    """Update embedded prose without changing drivers, animation or geometry.

    Only notes are accepted, so mechanical edits cannot bypass a rebuild.
    Saving the .blend (and the external plan JSON) is the caller's choice.
    """
    if not isinstance(notes, list) or any(not isinstance(n, str) for n in notes):
        raise ValueError("notes must be a list of strings")
    plan = json.loads(rig["root"]["mecha_plan"])
    plan["notes"] = notes
    contract.validate(plan)
    rig["root"]["mecha_plan"] = json.dumps(plan, separators=(",", ":"))
    return plan


def set_moving_only(rig, enabled=True):
    """Reversible viewport/render view of parts assigned to rig bodies.

    The first enable stores prior mesh visibility on the root (survives saving).
    Repeated enables retain that snapshot. Other models are never touched.
    Collection exclusions and a hidden model root still take precedence.
    """
    root = rig["root"]
    key = "mecha_visibility"
    if not enabled:
        if key in root:
            meshes = {o.name: o for o in root.children_recursive if o.type == "MESH"}
            for name, state in json.loads(root[key]).items():
                if name in meshes:
                    o = meshes[name]
                    o.hide_set(state[0])
                    o.hide_render, o.hide_viewport = state[1:]
            del root[key]
        return
    if key in root:
        return
    plan = json.loads(root["mecha_plan"])
    moving = {i for b in plan["bodies"].values() for i in b["instances"]}
    meshes = {o for o in root.children_recursive if o.type == "MESH"}
    visible = {
        o for i in moving for o in _objects(rig["mapping"][i]) if o.type == "MESH"
    }
    root[key] = json.dumps(
        {o.name: [o.hide_get(), o.hide_render, o.hide_viewport] for o in meshes}
    )
    for o in meshes:
        o.hide_set(o not in visible)
        o.hide_render = o not in visible
        o.hide_viewport = False


@contextmanager
def moving_only(rig):
    already_enabled = "mecha_visibility" in rig["root"]
    set_moving_only(rig)
    try:
        yield
    finally:
        if not already_enabled:
            set_moving_only(rig, False)
