"""Helpers for rigging LDraw models that were imported into Blender from mpd2glb .glb files.

"LDraw space" below means a submodel's own LDraw frame, in LDU, with -Y up. The glTF
importer turns an LDraw matrix M into the Blender local matrix C @ M @ C^-1, where
C(x, y, z) = (x, -z, y); the LDU -> metre scale lives on the glTF root node. Rig empties
are created under the submodel object, so all rig maths stays in LDU.
"""

import json
import math
from dataclasses import dataclass

import bpy
from bpy_extras import anim_utils
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree

C = Matrix(((1, 0, 0, 0), (0, 0, -1, 0), (0, 1, 0, 0), (0, 0, 0, 1)))
C_INV = C.inverted()

REST_TEXT = "ldraw_mecha_rest.json"


# --- LDraw <-> Blender -----------------------------------------------------------------

def to_blender(m):
    """LDraw-space 4x4 matrix -> Blender local matrix under the submodel object."""
    return C @ m @ C_INV


def to_ldraw(m):
    return C_INV @ m @ C


def vec_b(v):
    """LDraw-space point/direction -> Blender submodel-local."""
    return Vector((v[0], -v[2], v[1]))


def vec_l(v):
    return Vector((v[0], v[2], -v[1]))


@dataclass
class Part:
    idx: int
    file: str
    color: str
    pos: Vector
    rot: Matrix  # 3x3

    @property
    def matrix(self):
        m = self.rot.to_4x4()
        m.translation = self.pos
        return m


def parse_mpd(path, submodel):
    """Type-1 lines of one FILE section of an .mpd, in file order."""
    parts, current = [], None
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            tok = line.split()
            if not tok:
                continue
            if tok[0] == "0" and len(tok) > 2 and tok[1] == "FILE":
                current = line.strip()[7:]
            elif tok[0] == "1" and current == submodel:
                v = [float(t) for t in tok[2:14]]
                rot = Matrix((v[3:6], v[6:9], v[9:12]))
                parts.append(Part(len(parts), " ".join(tok[14:]).lower(), tok[1], Vector(v[0:3]), rot))
    return parts


def part_ldraw_matrix(obj, sub):
    """Current LDraw-space matrix of a part object, relative to its submodel object."""
    return to_ldraw(sub.matrix_world.inverted() @ obj.matrix_world)


def match_parts(sub, parts, pos_tol=0.5, rot_tol=0.02):
    """Map MPD part index -> Blender part object (direct children of `sub` with fileName)."""
    by_file = {}
    for obj in sub.children:
        fn = obj.get("fileName")
        if fn:
            by_file.setdefault(fn.lower(), []).append((obj, part_ldraw_matrix(obj, sub)))
    mapping, used, missing = {}, set(), []
    for p in parts:
        hit = None
        for obj, m in by_file.get(p.file, ()):
            if obj.name in used or (m.translation - p.pos).length > pos_tol:
                continue
            r = m.to_3x3()
            if max(abs(r[i][j] - p.rot[i][j]) for i in range(3) for j in range(3)) <= rot_tol:
                hit = obj
                break
        if hit is None:
            missing.append(p)
        else:
            used.add(hit.name)
            mapping[p.idx] = hit
    return mapping, missing


def find_part(parts, file, pos, tol=1.0):
    """The one part with this file name near this LDraw position."""
    hits = [p for p in parts if p.file == file and (p.pos - Vector(pos)).length <= tol]
    if len(hits) != 1:
        raise LookupError(f"{file} at {pos}: {len(hits)} matches")
    return hits[0]


# --- Gear kinematics -------------------------------------------------------------------

def pitch_radius(teeth):
    """Technic gears and racks share an 8 LDU tooth pitch."""
    return teeth * 8.0 / (2.0 * math.pi)


def _toward(axis, center, other):
    d = other - center
    return (d - axis * d.dot(axis)).normalized()


def signed_ratio(a_axis, a_center, a_teeth, b_axis, b_center, b_teeth):
    """k such that w_b = k * w_a, each angular speed taken about its own body axis.

    The size comes from the tooth counts; the sign comes from matching the tangential
    velocity of both gears at the pitch point, so axis directions and bevel placement
    are handled without hand-made sign rules.
    """
    u = _toward(a_axis, a_center, b_center)
    p = a_center + u * pitch_radius(a_teeth)
    t = a_axis.cross(u)
    lever = b_axis.cross(p - b_center).dot(t)
    return math.copysign(a_teeth / b_teeth, lever)


def rack_ratio(pinion_axis, pinion_center, pinion_teeth, rack_point, slide_dir):
    """v such that rack displacement = v * pinion angle (along `slide_dir`)."""
    u = _toward(pinion_axis, pinion_center, rack_point)
    return pitch_radius(pinion_teeth) * pinion_axis.cross(u).dot(slide_dir)


# --- Scene building ---------------------------------------------------------------------

def frame_matrix(origin, z_axis, x_hint):
    """Submodel-local Blender matrix of a frame whose local Z is the LDraw direction `z_axis`.

    Origin and directions are given in LDraw space; X is as close to x_hint as possible.
    Unlike parts (C @ M @ C^-1), a frame keeps its own axes, so it maps through C only.
    """
    z = Vector(z_axis).normalized()
    x = Vector(x_hint)
    x = (x - z * x.dot(z)).normalized()
    y = z.cross(x)
    m = Matrix((x, y, z)).transposed().to_4x4()
    m.translation = Vector(origin)
    return C @ m


def make_empty(name, parent, matrix_sub, collection, display="PLAIN_AXES", size=10.0, rest=None):
    """Empty placed at `matrix_sub` (submodel-local Blender matrix) under `parent`.

    `rest` maps already-created rig objects to their submodel-local rest matrices; it is
    needed to place children of rig empties without evaluating the depsgraph.
    """
    obj = bpy.data.objects.new(name, None)
    obj.empty_display_type = display
    obj.empty_display_size = size
    collection.objects.link(obj)
    obj.parent = parent
    parent_rest = rest.get(parent.name, Matrix.Identity(4)) if rest is not None else Matrix.Identity(4)
    obj.matrix_basis = parent_rest.inverted() @ matrix_sub
    if rest is not None:
        rest[name] = matrix_sub.copy()
    return obj


def reparent_keep_world(objs, new_parent):
    bpy.context.view_layer.update()
    for obj in objs:
        mw = obj.matrix_world.copy()
        obj.parent = new_parent
        obj.matrix_parent_inverse.identity()
        obj.matrix_world = mw


def save_rest(sub, objs, extra=None):
    """Remember submodel-local matrices of parts before they are re-parented."""
    text = bpy.data.texts.get(REST_TEXT) or bpy.data.texts.new(REST_TEXT)
    data = json.loads(text.as_string() or "{}")
    inv = sub.matrix_world.inverted()
    for obj in objs:
        data.setdefault("parts", {}).setdefault(obj.name, [list(r) for r in inv @ obj.matrix_world])
    for name, value in (extra or {}).items():
        data.setdefault(name, value)
    text.from_string(json.dumps(data))


def load_rest():
    text = bpy.data.texts.get(REST_TEXT)
    return json.loads(text.as_string()) if text and text.as_string() else {}


def remove_rig(sub, prefixes, keep=()):
    """Put re-parented parts back at rest under `sub` and delete the rig objects."""
    data = load_rest()
    for name, m in data.get("parts", {}).items():
        obj = bpy.data.objects.get(name)
        if obj is None:
            continue
        obj.parent = sub
        obj.matrix_parent_inverse.identity()
        obj.matrix_basis = Matrix(m)
    for name, info in data.get("roots", {}).items():
        obj = bpy.data.objects.get(name)
        if obj is not None:
            obj.parent = None
            obj.matrix_world = Matrix(info)
    doomed = [o for o in bpy.data.objects if o.name.startswith(tuple(prefixes)) and o.name not in keep]
    for obj in doomed:
        if obj.animation_data and obj.animation_data.action:
            act = obj.animation_data.action
            obj.animation_data_clear()
            if act.users == 0:
                bpy.data.actions.remove(act)
        bpy.data.objects.remove(obj)
    text = bpy.data.texts.get(REST_TEXT)
    if text:
        bpy.data.texts.remove(text)


# --- Drivers and keys -------------------------------------------------------------------

def add_driver(obj, data_path, index, expr, variables):
    """variables: {name: (id, data_path)}; returns the driver for checks."""
    fc = obj.driver_add(data_path, index)
    drv = fc.driver
    drv.type = "SCRIPTED"
    for var in list(drv.variables):
        drv.variables.remove(var)
    for name, (idb, path) in variables.items():
        var = drv.variables.new()
        var.name = name
        var.type = "SINGLE_PROP"
        var.targets[0].id = idb
        var.targets[0].data_path = path
    drv.expression = expr
    for mod in list(fc.modifiers):
        fc.modifiers.remove(mod)
    return drv


def fcurve(idb, data_path, index=0):
    ad = idb.animation_data_create()
    if ad.action is None:
        ad.action = bpy.data.actions.new(f"{idb.name}Action")
    return ad.action.fcurve_ensure_for_datablock(idb, data_path, index=index)


def find_fcurve(idb, data_path, index=0):
    ad = idb.animation_data
    if not ad or not ad.action or not ad.action_slot:
        return None
    bag = anim_utils.action_get_channelbag_for_slot(ad.action, ad.action_slot)
    return bag.fcurves.find(data_path, index=index) if bag else None


def remove_fcurve(idb, data_path, index=0):
    fc = find_fcurve(idb, data_path, index)
    if fc is not None:
        ad = idb.animation_data
        anim_utils.action_get_channelbag_for_slot(ad.action, ad.action_slot).fcurves.remove(fc)


def set_keys(fc, frames, values, interpolation="LINEAR"):
    """Replace all keys of `fc` with (frame, value) pairs."""
    fc.keyframe_points.clear()
    fc.keyframe_points.add(len(frames))
    fc.keyframe_points.foreach_set("co", [c for f, v in zip(frames, values) for c in (f, v)])
    for kp in fc.keyframe_points:
        kp.interpolation = interpolation
    fc.update()


# --- Collisions --------------------------------------------------------------------------

def _mesh_objects(part):
    return [c for c in part.children_recursive if c.type == "MESH"]


def part_bvh(part, depsgraph, shrink=0.0):
    """World-space BVH of all meshes below a part empty.

    `shrink` moves vertices inward along their normals (mesh units, i.e. LDU) so surfaces
    that merely touch, as LEGO parts do at joints, don't count as intersecting.
    """
    verts, polys = [], []
    for m in _mesh_objects(part):
        ev = m.evaluated_get(depsgraph)
        mesh = ev.to_mesh()
        mw = ev.matrix_world
        base = len(verts)
        verts.extend(mw @ (v.co - v.normal * shrink) for v in mesh.vertices)
        polys.extend([base + i for i in p.vertices] for p in mesh.polygons)
        ev.to_mesh_clear()
    return BVHTree.FromPolygons(verts, polys) if polys else None


def near_parts(moving, candidates, margin):
    """Candidates whose world bounding box lies within `margin` (m) of any moving part's."""
    def box(obj):
        pts = [m.matrix_world @ Vector(c) for m in _mesh_objects(obj) for c in m.bound_box]
        if not pts:
            return None
        return (Vector([min(p[i] for p in pts) for i in range(3)]), Vector([max(p[i] for p in pts) for i in range(3)]))
    mboxes = [b for b in map(box, moving) if b]
    out = []
    for obj in candidates:
        b = box(obj)
        if b and any(all(b[0][i] <= mb[1][i] + margin and b[1][i] >= mb[0][i] - margin for i in range(3)) for mb in mboxes):
            out.append(obj)
    return out


def overlapping_pairs(moving, static, depsgraph, static_trees, shrink=0.4):
    """Pairs of part names whose meshes intersect: moving vs moving, and moving vs static.

    `static_trees` caches BVHs of static parts between calls.
    """
    trees = {o.name: part_bvh(o, depsgraph, shrink) for o in moving}
    for o in static:
        if o.name not in static_trees:
            static_trees[o.name] = part_bvh(o, depsgraph, shrink)
    names = list(trees)
    pairs = set()
    for i, a in enumerate(names):
        ta = trees[a]
        if ta is None:
            continue
        for b in names[i + 1:]:
            if trees[b] is not None and ta.overlap(trees[b]):
                pairs.add(tuple(sorted((a, b))))
        for o in static:
            tb = static_trees[o.name]
            if tb is not None and ta.overlap(tb):
                pairs.add((a, o.name))
    return pairs
