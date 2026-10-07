"""Sampled mesh-crossing diagnostic for every catalog minifig: single joints swept, then clip poses.

    Blender --background --factory-startup --python-exit-code 1 \
        --python scripts/blender/check_minifigs_clearance.py -- [--figures MF03_knight ...] [--every 6] [--all-clips]

For each figure a fresh scene imports its GLB and builds its plan. The seven joint controls are swept one at a
time (17 steps), then the joint values of clip frames (every `--every` frames) are sampled as combined poses,
once at the default 0.4 LDU shrink (contacts) and once at `--deep` (crossings deeper than about 2x that);
with --all-clips every catalog clip is sampled on every figure (clip reuse), otherwise only the figure's own
clips. Rest-contact and same-body pairs are excluded (blender_tools.check_clearance). Whole-figure channels are
not applied: ground, prop and neighbour contact are not tested. Writes output/minifigs/MFxx_*/clearance.json and
output/minifigs/clearance-summary.json (with --all-clips: clearance-all-clips.json, clearance-summary-all-clips.json).
"""

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
import bpy  # noqa: E402,F401

from ldraw_mechanisms import blender_tools as tools, plan as contract  # noqa: E402
import minifig_clips as mc  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--figures", nargs="*")
    ap.add_argument("--every", type=int, default=6)
    ap.add_argument("--all-clips", action="store_true")
    ap.add_argument("--deep", type=float, default=1.5,
                    help="Second pass shrink (LDU): only crossings deeper than about twice this remain")
    a = ap.parse_args(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else [])
    cat = json.loads((mc.OUT / "catalog.json").read_text())
    library = mc.library()
    summary = {}
    for entry in cat["figures"]:
        figure = entry["figure"]
        if a.figures and figure not in a.figures:
            continue
        d = mc.OUT / figure
        plan = contract.load(d / "plan.json")
        rig = tools.apply_plan(plan, glb=d / "study/model.glb", new_scene=True)["rig"]
        sweep = tools.check_clearance(plan, rig=rig, steps=17)
        clips = library if a.all_clips else [c for c in library if c.figure == figure]
        poses = [dict(label=f"{c.id}@{f}", controls={j: c.value(j, f) for j in mc.JOINTS})
                 for c in clips for f in range(1, c.frames + 1, a.every)]
        names = {r["id"]: r["role"] for r in json.loads((d / "source/parts.json").read_text())["parts"]}

        def by_clip(result):
            hits, frames = {}, {}
            for s in result["samples"]:
                clip, frame = s["pose"].split("@")
                for x, y in s["new_surface_crossings"]:
                    hits.setdefault(clip, set()).add(f"{names.get(x, x)}-{names.get(y, y)}")
                    frames.setdefault(clip, set()).add(int(frame))
            return ({k: sorted(v) for k, v in sorted(hits.items())}, {k: sorted(v) for k, v in sorted(frames.items())})

        posed = tools.check_clearance(plan, rig=rig, poses=poses)
        deep = tools.check_clearance(plan, rig=rig, poses=poses, shrink=a.deep)
        contact_pairs, contact_frames = by_clip(posed)
        deep_pairs, deep_frames = by_clip(deep)
        report = dict(
            figure=figure,
            sweep=dict(no_new_surface_crossings=sweep["no_new_surface_crossings"],
                       crossings=sorted({(s["control"], round(s["value"], 3), tuple(p))
                                         for s in sweep["samples"] for p in s["new_surface_crossings"]}),
                       excluded_rest_pairs=sweep["excluded_rest_pairs"]),
            clip_poses=dict(samples=len(posed["samples"]), every=a.every,
                            no_new_surface_crossings=posed["no_new_surface_crossings"],
                            crossings_by_clip=contact_pairs, frames_with_crossings=contact_frames,
                            deep_shrink_ldu=a.deep,
                            no_deep_crossings=deep["no_new_surface_crossings"],
                            deep_crossings_by_clip=deep_pairs, frames_with_deep_crossings=deep_frames),
            roles=names,
            coverage=posed["coverage"] + "; joint channels only (whole-figure staging not applied)")
        contract.save(d / ("clearance-all-clips.json" if a.all_clips else "clearance.json"), report)
        summary[figure] = dict(sweep_clear=sweep["no_new_surface_crossings"],
                               clip_poses_clear=posed["no_new_surface_crossings"],
                               clip_poses_without_deep_crossings=deep["no_new_surface_crossings"],
                               clips_with_crossings=contact_pairs, clips_with_deep_crossings=deep_pairs)
        print("MECHA_CLEARANCE", figure, sweep["no_new_surface_crossings"], posed["no_new_surface_crossings"],
              deep["no_new_surface_crossings"])
    name = "clearance-summary-all-clips.json" if a.all_clips else "clearance-summary.json"
    contract.save(mc.OUT / name, dict(figures=summary, every=a.every, all_clips=a.all_clips))


if __name__ == "__main__":
    main()
