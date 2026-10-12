"""Rest-pose interpenetration report for a bound GLB (design/verification helper, nothing saved).

    "$BLENDER_BIN" -b --factory-startup --python scripts/blender/glb_overlaps.py -- \
        --glb output/8448-mecha/design/robot.glb --idmap output/8448-mecha/source/idmap.json \
        --output output/8448-mecha/overlaps.json [--shrink 0.6] [--units a,b]

Every occurrence's meshes are shrunk inward along their normals by `--shrink` LDU so that surfaces that merely
touch (studs in tubes, pins in holes, flush faces) do not count. Candidate pairs come from bounding boxes; each
is then tested with BVH overlap. Pairs are reported with their robot IDs, car IDs and units. A reported pair is
geometry that occupies the same space; it is not a judgement about whether a real model could be built.
"""
import argparse
import json
import sys
from pathlib import Path

import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree

a = argparse.ArgumentParser()
a.add_argument("--glb", required=True)
a.add_argument("--idmap", required=True)
a.add_argument("--output", required=True)
a.add_argument("--shrink", type=float, default=0.6)
a.add_argument("--units", help="Only report pairs touching these units (comma list)")
a = a.parse_args(sys.argv[sys.argv.index("--") + 1:])
idmap = json.loads(Path(a.idmap).read_text())["idmap"]
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=str(Path(a.glb).resolve()))
dg = bpy.context.evaluated_depsgraph_get()
objs = {}
for o in bpy.context.scene.objects:
    mid = o.get("mecha_id")
    if mid is not None and str(mid) in idmap:
        objs[str(mid)] = o


def meshes(o):
    return [m for m in [o, *o.children_recursive] if m.type == "MESH"]


data = {}
for rid, o in objs.items():
    verts, polys = [], []
    lo, hi = Vector((1e9, 1e9, 1e9)), Vector((-1e9, -1e9, -1e9))
    for m in meshes(o):
        ev = m.evaluated_get(dg)
        mesh = ev.to_mesh()
        mw = ev.matrix_world
        # shrink in mesh (LDU) units, then to world
        base = len(verts)
        for v in mesh.vertices:
            w = mw @ (v.co - v.normal * a.shrink)
            verts.append(w)
            lo = Vector(map(min, lo, w))
            hi = Vector(map(max, hi, w))
        polys.extend([base + i for i in p.vertices] for p in mesh.polygons)
        ev.to_mesh_clear()
    if polys:
        data[rid] = (BVHTree.FromPolygons(verts, polys), lo, hi)
keys = sorted(data, key=lambda k: data[k][1].x)
units = set(a.units.split(",")) if a.units else None
pairs = []
for i, ka in enumerate(keys):
    ta, la, ha = data[ka]
    for kb in keys[i + 1:]:
        tb, lb, hb = data[kb]
        if lb.x > ha.x:
            break
        if lb.y > ha.y or hb.y < la.y or lb.z > ha.z or hb.z < la.z:
            continue
        ua, ub = idmap[ka]["unit"], idmap[kb]["unit"]
        if units and ua not in units and ub not in units:
            continue
        if ta.overlap(tb):
            pairs.append(dict(a=ka, b=kb, car_a=idmap[ka]["car"], car_b=idmap[kb]["car"], unit_a=ua, unit_b=ub,
                              ref_a=idmap[ka]["ref"], ref_b=idmap[kb]["ref"]))
out = dict(shrink_ldu=a.shrink, parts=len(data), overlapping_pairs=len(pairs), pairs=pairs)
Path(a.output).write_text(json.dumps(out, indent=1) + "\n")
from collections import Counter
print("OVERLAPS", len(pairs), "of", len(data), "parts")
print("BY_UNITS", dict(Counter(tuple(sorted((p["unit_a"], p["unit_b"]))) for p in pairs).most_common(40)))
