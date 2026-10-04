"""Mark the discovered edges the 10265 recipe relies on as reviewed.

Discovery leaves every connection a candidate. The recipe turns a few of them
into motion, so those edges get an explicit review note before the motion is
adopted. A reviewed edge records that an agent looked at it; it certifies
nothing by itself.

    .venv/bin/python scripts/review_10265.py output/10265-v2/plan.json
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ldraw_mechanisms import plan as contract

REVIEWS = {
    ("0/91/7", "0/103"): (
        "16T and 40T centres are 70 LDU apart on parallel longitudinal axes, "
        "which is exactly the sum of the 20 and 50 LDU pitch radii. Used as the "
        "-0.4 steering reduction. Tooth phase and backlash are untested."
    ),
    ("0/453", "0/454"): "Rim and tyre turn together as one wheel.",
    ("0/455", "0/456"): "Rim and tyre turn together as one wheel.",
    ("0/457", "0/458"): "Rim and tyre turn together as one wheel.",
    ("0/459", "0/460"): "Rim and tyre turn together as one wheel.",
    ("0/90/0", "0/90/1"): (
        "Cross block and suspension arm carry the left kingpin; the arm holds "
        "the upper 15460 ball at y=-14. Treated as static support."
    ),
    ("0/90/3", "0/90/4"): (
        "Cross block and suspension arm carry the right kingpin; the arm holds "
        "the upper 15460 ball at y=-14. Treated as static support."
    ),
    ("0/90/0", "0/91/0"): "Lower left suspension arm holds the 15460 ball at y=-54.",
    ("0/90/3", "0/91/1"): "Lower right suspension arm holds the 15460 ball at y=-54.",
}


def main(path):
    plan = contract.load(path)
    marked = 0
    for edge in plan.get("connections", {}).values():
        note = REVIEWS.get((edge["a"], edge["b"])) or REVIEWS.get((edge["b"], edge["a"]))
        if note and edge["status"] == "candidate":
            edge["status"] = "reviewed"
            edge["review"] = note
            marked += 1
    contract.validate(plan)
    contract.save(path, plan)
    print(f"reviewed {marked} connections in {path}")


main(sys.argv[1])
