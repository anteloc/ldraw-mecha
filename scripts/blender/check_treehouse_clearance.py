"""Sample surface crossings of the treehouse wind animation at its strongest frames (fresh process).

    bin/Blender.app/Contents/MacOS/Blender --background output/21318-autumn-wind/ai-animated.blend \
        --python-exit-code 1 --python scripts/blender/check_treehouse_clearance.py -- \
        --study output/21318-autumn-wind [--shrink 0.4] [--poses 14]

Poses are clip frames (all controls together, as played): per regime the frames with the largest summed
|angle| and, per control, the frame of its own extreme. Uses blender_tools.check_clearance (crossings new
relative to the rest pose; rigid-body and rest-contact pairs excluded). Not a proof of collision-free motion.
"""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
import bpy  # noqa: E402

from ldraw_mechanisms import blender as adapter, blender_tools as tools, plan as contract  # noqa: E402
import wind_clips as wc  # noqa: E402


def main():
    a = argparse.ArgumentParser()
    a.add_argument("--study", required=True)
    a.add_argument("--shrink", type=float, default=0.4)
    a.add_argument("--poses", type=int, default=14)
    a.add_argument("--controls", nargs="*")
    a.add_argument("--report", default="clearance.json")
    args = a.parse_args(sys.argv[sys.argv.index("--") + 1:])
    study = Path(args.study).resolve()
    plan = contract.load(study / "plan.json")
    clips = json.loads((study / "clips.json").read_text())["controls"]
    names = args.controls or list(plan["controls"])
    frames = set()
    for w in "ABC":
        total = [sum(abs(clips[n][w][i]) for n in names) for i in range(wc.CLIP_FRAMES)]
        best = sorted(range(wc.CLIP_FRAMES), key=total.__getitem__, reverse=True)
        picked = []
        for i in best:  # spread the picks at least 12 frames apart
            if all(abs(i - j) >= 12 for j in picked):
                picked.append(i)
            if len(picked) == max(2, args.poses // 3):
                break
        frames |= {(w, i) for i in picked}
    for n in names:
        for w in "BC":
            series = clips[n][w]
            frames.add((w, max(range(wc.CLIP_FRAMES), key=lambda i: series[i])))
            frames.add((w, min(range(wc.CLIP_FRAMES), key=lambda i: series[i])))
    poses = [dict(label=f"{w}{i + 1}@{wc.WINDOWS[w][0] + i}", controls={n: clips[n][w][i] for n in plan["controls"]})
             for w, i in sorted(frames)]
    root = next(o for o in bpy.data.objects if o.get("mecha_id") == "root")
    rig = adapter.context_from_scene(plan, root)
    out = study / args.report
    result = tools.check_clearance(plan, rig=rig, controls=names, poses=poses, shrink=args.shrink, report=out)
    print("MECHA_RESULT", json.dumps(dict(poses=len(poses), keys=[k for k in result if k != "samples"],
                                          passed=result.get("passed"))))


if __name__ == "__main__":
    main()
