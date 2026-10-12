"""Print LDraw-frame bounding boxes of occurrence groups from a bound GLB (design helper, nothing saved).

    "$BLENDER_BIN" -b --factory-startup --python scripts/blender/glb_bounds.py -- --glb G.glb --groups g.json [--slab y0,y1]
`--slab` restricts the reported bounds to mesh vertices with LDraw y inside [y0, y1].
"""
import argparse, json, sys
from pathlib import Path
import bpy
from mathutils import Vector

a = argparse.ArgumentParser()
a.add_argument("--glb", required=True)
a.add_argument("--groups", required=True)
a.add_argument("--slab")
a = a.parse_args(sys.argv[sys.argv.index("--") + 1:])
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=str(Path(a.glb).resolve()))
ids = {}
for o in bpy.context.scene.objects:
    if o.get("mecha_id") is not None:
        ids.setdefault(str(o["mecha_id"]), []).append(o)
root = next(o for o in bpy.context.scene.objects if o.parent is None and o.children)
inv = root.matrix_world.inverted()
slab = [float(v) for v in a.slab.split(",")] if a.slab else None
dg = bpy.context.evaluated_depsgraph_get()
for name, lst in json.loads(Path(a.groups).read_text()).items():
    pts = []
    for i in lst:
        for o in ids.get(str(i), []):
            for m in [o] + list(o.children_recursive):
                if m.type != "MESH":
                    continue
                ev = m.evaluated_get(dg)
                mw = inv @ m.matrix_world
                for v in ev.data.vertices:
                    p = mw @ v.co  # root-local = C-converted LDraw: (x, -z, y)?? resolved below
                    pts.append(p)
    if not pts:
        print(name, "no geometry"); continue
    # root local space is C(LDraw) with C(x,y,z) = (x,-z,y); invert: LDraw = (px, pz, -py)
    L = [(p.x, p.z, -p.y) for p in pts]
    if slab:
        L = [q for q in L if slab[0] <= q[1] <= slab[1]]
    if not L:
        print(name, "nothing in slab"); continue
    lo = [round(min(q[k] for q in L), 1) for k in range(3)]
    hi = [round(max(q[k] for q in L), 1) for k in range(3)]
    print("BOUNDS", name, lo, hi)
