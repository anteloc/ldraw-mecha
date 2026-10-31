"""Sampled joint clearance over the 3625 clip's actual joint values (every 6th frame, plus head/arm extremes).

    blender --background output/3625/animated.blend --python scripts/blender/check_plane_3625_clearance.py -- \
        --plan output/3625/plan.json --report output/3625/clearance.json

Staging (climb/bank/lift) moves the whole airframe rigidly, so only the five joint channels are sampled. Rest-contact
and same-body pairs are excluded; this detects new surface crossings, not containment.
"""

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
from ldraw_mechanisms import blender as adapter, blender_tools as tools, plan as contract  # noqa: E402
import plane_clips_3625 as pc  # noqa: E402


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", required=True)
    parser.add_argument("--report", required=True)
    parser.add_argument("--shrink", type=float, default=0.4)
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1:])
    plan = contract.load(args.plan)
    rig = adapter.context_from_scene(plan)
    rows = pc.timeline()
    chosen = sorted(set(range(1, pc.END + 1, 6)) | {pc.END, max(range(1, pc.END), key=lambda f: rows[f - 1]["head"]),
                                                    min(range(1, pc.END), key=lambda f: rows[f - 1]["head"]),
                                                    max(range(1, pc.END), key=lambda f: rows[f - 1]["arm_l"]),
                                                    max(range(1, pc.END), key=lambda f: rows[f - 1]["arm_r"])})
    poses = [dict(label=f"f{f}", controls={c: rows[f - 1][c] for c in plan["controls"]}) for f in chosen]
    result = tools.check_clearance(plan, rig=rig, poses=poses, report=args.report, shrink=args.shrink)
    print("MECHA_CLEARANCE", result["no_new_surface_crossings"])


if __name__ == "__main__":
    main()
