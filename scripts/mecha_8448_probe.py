"""Design probe: list free connector holes of chosen car occurrences in the current robot layout.

    .venv/bin/python scripts/mecha_8448_probe.py UNIT [--near x,y,z] [--radius R] [--kinds pin_hole,axle_hole]
    .venv/bin/python scripts/mecha_8448_probe.py --car ROOT_ID [--T unit]   # car module in its car frame
"""
import argparse
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_mecha_8448 as bm  # noqa: E402
import mecha_connect as mc  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("unit", nargs="?")
    ap.add_argument("--car")
    ap.add_argument("--near")
    ap.add_argument("--radius", type=float, default=1e9)
    ap.add_argument("--kinds", default="pin_hole,axle_hole")
    ap.add_argument("--males", action="store_true", help="also list male ends (axles/pins) sticking out")
    a = ap.parse_args()
    car = bm.Car()
    if a.car:
        ids = car.under(a.car)
        parts = [(i, car.nodes[i]["ref"], car.world(i)) for i in ids if i not in car.flex]
        scope = set(ids)
    else:
        b = bm.build_all(car)
        parts = [(i, car.nodes[i]["ref"], b.matrix(i)) for i in b.placed if i not in car.flex]
        scope = set(b.units[a.unit]["items"])
    near = np.array([float(v) for v in a.near.split(",")]) if a.near else None
    free = mc.merge_lines(mc.free_females(parts, ids=scope, kinds=tuple(a.kinds.split(","))))
    rows = []
    for f in free:
        mid = f["mid"]
        d = 0 if near is None else float(np.linalg.norm(mid - near))
        if d <= a.radius:
            rows.append((d, f))
    rows.sort(key=lambda r: r[0])
    for d, f in rows[:80]:
        mid = f["mid"]
        print(f"{f['part']:>14} {car.nodes[f['part']]['ref']:>12} {f['kind']:>9} mid={np.round(mid, 1)} "
              f"axis={np.round(f['axis'], 3)} len={f['length']:.0f} d={d:.0f}")


main()
