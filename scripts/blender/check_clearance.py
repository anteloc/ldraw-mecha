"""Optional sampled mesh diagnostic, reusing the supplied rig's BVH helpers.

Rest-contact pairs and pairs within a rigid body are excluded. This detects new
surface crossings, not containment or worsening of an existing contact. It is
not a substitute for joint fit and physical clearance review.
"""

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from ldraw_mechanisms.blender_tools import check_clearance


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--plan", required=True)
    p.add_argument("--report", required=True)
    p.add_argument("--controls", nargs="+", required=True)
    p.add_argument("--steps", type=int, default=9)
    p.add_argument(
        "--rebuild",
        action="store_true",
        help="Study a revised plan in this background process",
    )
    args = p.parse_args(sys.argv[sys.argv.index("--") + 1 :])
    result = check_clearance(
        args.plan,
        controls=args.controls,
        steps=args.steps,
        report=args.report,
        rebuild=args.rebuild,
    )
    print("MECHA_CLEARANCE", result["no_new_surface_crossings"])


if __name__ == "__main__":
    main()
