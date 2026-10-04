"""Headless entry point; the implementation lives in the shared Python package."""

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from ldraw_mechanisms.blender_tools import apply_plan


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", required=True)
    parser.add_argument("--glb")
    parser.add_argument("--save")
    parser.add_argument("--report")
    parser.add_argument("--verify-existing", action="store_true")
    parser.add_argument("--animate", action="store_true")
    parser.add_argument(
        "--new-scene",
        action="store_true",
        help="Explicitly start an empty scene before importing",
    )
    args = parser.parse_args(
        sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    )
    result = apply_plan(
        args.plan,
        glb=args.glb,
        save=args.save,
        report=args.report,
        verify_existing=args.verify_existing,
        animate=args.animate,
        new_scene=args.new_scene,
    )
    print("MECHA_RESULT", result["report"])


if __name__ == "__main__":
    main()
