"""Write part-local LDraw bounding boxes {reference: [min, max]} from a bound GLB (design helper).

    "$BLENDER_BIN" -b --factory-startup --python scripts/blender/part_bounds.py -- --glb G.glb --idmap I.json --output B.json
The idmap gives each mecha_id's reference. Blender object space is C(LDraw) with C(x, y, z) = (x, -z, y).
"""
import argparse, json, sys
from pathlib import Path
import bpy
from mathutils import Vector

a = argparse.ArgumentParser()
a.add_argument("--glb", required=True)
a.add_argument("--idmap", required=True)
a.add_argument("--output", required=True)
a = a.parse_args(sys.argv[sys.argv.index("--") + 1:])
idmap = json.loads(Path(a.idmap).read_text())["idmap"]
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=str(Path(a.glb).resolve()))
dg = bpy.context.evaluated_depsgraph_get()
out = {}
for o in bpy.context.scene.objects:
    mid = o.get("mecha_id")
    if mid is None or str(mid) not in idmap:
        continue
    ref = idmap[str(mid)]["ref"].lower()
    if ref in out:
        continue
    inv = o.matrix_world.inverted()
    pts = []
    for m in [o, *o.children_recursive]:
        if m.type != "MESH":
            continue
        rel = inv @ m.matrix_world
        ev = m.evaluated_get(dg)
        pts.extend(rel @ v.co for v in ev.data.vertices)
    if not pts:
        continue
    L = [(p.x, p.z, -p.y) for p in pts]
    out[ref] = [[min(q[k] for q in L) for k in range(3)], [max(q[k] for q in L) for k in range(3)]]
Path(a.output).write_text(json.dumps(out, indent=0))
print("BOUNDS", len(out))
