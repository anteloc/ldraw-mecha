"""Reproduce studied plans and optionally their GLBs/Blender rigs.

Run with .venv/bin/python examples/build_examples.py [--blender].
Generated files go to output/, never the reference catalog.
"""

import argparse
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ldraw_mechanisms.recipes import create
from ldraw_mechanisms.plan import save, sweep, validate


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--blender", action="store_true")
    args = parser.parse_args()
    cases = [
        ("106", "106", None),
        ("928", "928", None),
        ("42000", "42000", None),
        ("hatch", "928", "928 - Space Ship - Cargo Hatchway.ldr"),
    ]
    for label, recipe, section in cases:
        source = ROOT / "data/models-annotated" / f"{recipe}-1.mpd"
        out = ROOT / "output" / label
        plan = create(source, recipe, section)
        validate(plan, check_source=True)
        save(out / "plan.json", plan)
        report = sweep(plan)
        save(out / "sweep.json", report)
        if not report["passed"]:
            raise RuntimeError(f"{label}: closure failed")
        if args.blender:
            from ldraw_mechanisms.glb import convert

            save(out / "conversion.json", convert(plan["source"], out / "model.glb"))
            subprocess.run(
                [
                    str(ROOT / "ldraw-mecha"),
                    "rig",
                    str(out / "plan.json"),
                    "--glb",
                    str(out / "model.glb"),
                    "--save",
                    str(out / "rigged.blend"),
                    "--report",
                    str(out / "blender-check.json"),
                ],
                check=True,
            )
        print(label, "passed", len(plan["bodies"]), "rigid bodies")


if __name__ == "__main__":
    main()
