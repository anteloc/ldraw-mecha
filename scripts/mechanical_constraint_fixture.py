"""Prepare the small, reproducible Blender mechanical-check integration fixture."""

import argparse
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ldraw_mechanisms import glb, plan
from ldraw_mechanisms.source import Document


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    out = Path(args.output).resolve()
    if out.exists():
        raise ValueError("Choose a new fixture output directory")
    out.mkdir(parents=True)
    fixtures = ROOT / "tests/fixtures"
    source = out / "fixture.mpd"
    shutil.copyfile(fixtures / "mechanical-constraint.mpd", source)
    p = json.loads((fixtures / "mechanical-constraint.plan.json").read_text())
    p["source"] = Document(source).manifest()
    plan.validate(p)
    assert plan.sweep(p, 33)["passed"]
    plan.save(out / "plan.json", p)
    glb.convert(p["source"], out / "model.glb")
    print(out)


if __name__ == "__main__":
    main()
