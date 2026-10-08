"""Sampled mesh-crossing diagnostic for every plant case: controls swept, then wind-clip poses.

    Blender --background --factory-startup --python-exit-code 1 \
        --python scripts/blender/check_plants_clearance.py -- [--cases P07_grass_meadow ...] [--every 4]

For each case a fresh scene imports its GLB and builds its plan. Each control is swept alone over its plan range
(17 steps), then the control values of every clip frame (every `--every` frames) are sampled as combined poses at
the default 0.4 LDU shrink. Rest-contact and same-body pairs are excluded (blender_tools.check_clearance): a hinge
leaf and the clip or bar it touches at rest are not tested against each other.

Every reported crossing pair is then measured at its frames: the deepest vertex of either part lying inside the
other (ray-parity inside test, distance to the other surface, LDU). That vertex depth classifies the crossing as
contact (<= 0.5 LDU), shallow (<= 2) or deep. It is a lower bound for edge-through-face crossings. A second
check_clearance pass at a larger shrink (`--deep`) is recorded too, but it is not reliable for thin parts (leaves,
fronds, petals): shrinking a few-LDU-thick shell turns it inside out. Writes
output/plants/Pxx_*/clearance.json and output/plants/clearance-summary.json.
"""

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
import bpy  # noqa: E402
from mathutils import Vector  # noqa: E402
from mathutils.bvhtree import BVHTree  # noqa: E402

from ldraw_mechanisms import blender as adapter, blender_tools as tools, plan as contract  # noqa: E402
import wind_clips as wc  # noqa: E402


RAYS = (Vector((1, 0.0013, 0.0007)), Vector((0.0011, 1, 0.0005)), Vector((0.0009, 0.0006, 1)))


def part_mesh(obj, deps):
    """World-space vertices and polygons of an occurrence's meshes."""
    verts, polys = [], []
    for o in [obj, *obj.children_recursive]:
        if o.type != "MESH":
            continue
        e = o.evaluated_get(deps)
        m = e.to_mesh()
        base = len(verts)
        verts += [e.matrix_world @ v.co for v in m.vertices]
        polys += [tuple(base + i for i in p.vertices) for p in m.polygons]
        e.to_mesh_clear()
    return verts, polys


def inside(bvh, p):
    votes = 0
    for d in RAYS:
        n, o = 0, p.copy()
        for _ in range(64):
            hit = bvh.ray_cast(o, d)
            if hit[0] is None:
                break
            n += 1
            o = hit[0] + d * 1e-7
        votes += n % 2
    return votes >= 2


def vertex_penetration(rig, a, b, controls, ldu):
    """Deepest vertex (LDU) of occurrence a inside b or b inside a at the given controls."""
    adapter.set_controls(rig, **controls)
    deps = bpy.context.evaluated_depsgraph_get()
    va, pa = part_mesh(rig["mapping"][a], deps)
    vb, pb = part_mesh(rig["mapping"][b], deps)
    worst = 0.0
    for verts, bvh in ((va, BVHTree.FromPolygons(vb, pb)), (vb, BVHTree.FromPolygons(va, pa))):
        for v in verts:
            if inside(bvh, v):
                hit = bvh.find_nearest(v)
                if hit[3] is not None:
                    worst = max(worst, hit[3] / ldu)
    return worst


def classify(depth):
    return "contact" if depth <= 0.5 else "shallow" if depth <= 2.0 else "deep"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cases", nargs="*")
    ap.add_argument("--every", type=int, default=4)
    ap.add_argument("--deep", type=float, default=1.5,
                    help="Second pass shrink (LDU): only crossings deeper than about twice this remain")
    a = ap.parse_args(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else [])
    library = wc.library()
    summary = {}
    for sc in wc.CASES:
        key = sc["key"]
        if a.cases and key not in a.cases:
            continue
        d = wc.OUT / key
        plan = contract.load(d / "plan.json")
        rig = tools.apply_plan(plan, glb=d / "study/model.glb", new_scene=True)["rig"]
        names = {r["id"]: r["role"] for r in json.loads((d / "source/parts.json").read_text())["parts"]}
        sweep = tools.check_clearance(plan, rig=rig, steps=17)
        clips = [c for c in library if c.case == key]
        poses = [dict(label=f"{c.id}@{f}", controls=c.values(f)) for c in clips
                 for f in range(1, c.frames + 1, a.every)]

        def by_clip(result):
            hits, frames = {}, {}
            for s in result["samples"]:
                clip, frame = s["pose"].split("@")
                for x, y in s["new_surface_crossings"]:
                    hits.setdefault(clip, set()).add(f"{names.get(x, x)}-{names.get(y, y)}")
                    frames.setdefault(clip, set()).add(int(frame))
            return ({k: sorted(v) for k, v in sorted(hits.items())}, {k: sorted(v) for k, v in sorted(frames.items())})

        posed = tools.check_clearance(plan, rig=rig, poses=poses)
        ldu = rig["root"].matrix_world.to_scale()[0]
        by_label = {p["label"]: p["controls"] for p in poses}
        depths = {}
        for smp in posed["samples"]:
            clip = smp["pose"].split("@")[0]
            for x, y in smp["new_surface_crossings"]:
                depth = vertex_penetration(rig, x, y, by_label[smp["pose"]], ldu)
                k = (clip, f"{names.get(x, x)}-{names.get(y, y)}")
                depths[k] = max(depths.get(k, 0.0), depth)
        adapter.set_controls(rig, **{k: c["default"] for k, c in plan["controls"].items()})
        penetration = {}
        for (clip, pair), depth in sorted(depths.items()):
            penetration.setdefault(clip, {})[pair] = dict(max_vertex_depth_ldu=round(depth, 3), kind=classify(depth))
        deep = tools.check_clearance(plan, rig=rig, poses=poses, shrink=a.deep)
        contact_pairs, contact_frames = by_clip(posed)
        deep_pairs, deep_frames = by_clip(deep)
        sweep_hits = sorted({(s["control"], round(s["value"], 3), f"{names.get(x, x)}-{names.get(y, y)}")
                             for s in sweep["samples"] for x, y in s["new_surface_crossings"]})
        report = dict(
            case=key,
            sweep=dict(no_new_surface_crossings=sweep["no_new_surface_crossings"], crossings=sweep_hits,
                       excluded_rest_pairs=[f"{names.get(x, x)}-{names.get(y, y)}"
                                            for x, y in sweep["excluded_rest_pairs"]]),
            clip_poses=dict(samples=len(posed["samples"]), every=a.every,
                            no_new_surface_crossings=posed["no_new_surface_crossings"],
                            crossings_by_clip=contact_pairs, frames_with_crossings=contact_frames,
                            vertex_penetration_by_clip=penetration,
                            deep_shrink_ldu=a.deep, no_deep_crossings=deep["no_new_surface_crossings"],
                            deep_crossings_by_clip=deep_pairs, frames_with_deep_crossings=deep_frames),
            roles=names,
            coverage=posed["coverage"])
        contract.save(d / "clearance.json", report)
        summary[key] = dict(sweep_clear=sweep["no_new_surface_crossings"], sweep_crossings=sweep_hits,
                            clip_poses_clear=posed["no_new_surface_crossings"],
                            clip_poses_without_deep_crossings=deep["no_new_surface_crossings"],
                            clips_with_crossings=contact_pairs, vertex_penetration=penetration,
                            worst_vertex_depth_ldu=round(max(depths.values(), default=0.0), 3),
                            worst_kind=classify(max(depths.values(), default=0.0)) if depths else "clear",
                            clips_with_deep_shrink_crossings=deep_pairs,
                            excluded_rest_pairs=report["sweep"]["excluded_rest_pairs"])
        print("MECHA_CLEARANCE", key, sweep["no_new_surface_crossings"], posed["no_new_surface_crossings"],
              summary[key]["worst_kind"], summary[key]["worst_vertex_depth_ldu"])
    path = wc.OUT / "clearance-summary.json"
    old = json.loads(path.read_text())["cases"] if path.exists() and a.cases else {}
    old.update(summary)
    contract.save(path, dict(cases=old, every=a.every, deep_shrink_ldu=a.deep))


if __name__ == "__main__":
    main()
