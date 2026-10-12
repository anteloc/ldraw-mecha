"""Design search: where can a car module be pinned onto the current robot with the fewest collisions?

    .venv/bin/python scripts/mecha_8448_attach.py --roots 0/30 --rot "y:180,x:-90" --near 0,-900,-120 \
        [--radius 80] [--units torso,pelvis] [--exclude ...] [--top 8]

The module keeps its car geometry and is turned by `--rot` (successive axis:degrees, applied left to right to
the car frame). Candidates put one free module hole coaxial and flush against one free robot hole whose axis is
parallel, with the module's centre within `--radius` of `--near`. Each candidate is scored by approximate
collisions (part-local bounding boxes, shrunk 2 LDU, separating-axis test) and by how many further module/robot
hole pairs line up (each could take another pin). The best rows print the arguments for `Build.attach` (module
hole near-point in the car frame, robot hole near-point, side, flip=False with the given rotation baked in).
This is a ranking aid; the chosen placement is re-checked by the connector graph and mesh overlap report.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
import build_mecha_8448 as bm  # noqa: E402
import mecha_connect as mc  # noqa: E402

BOUNDS = json.loads((ROOT / "output/8448-mecha/part-bounds.json").read_text())
from mecha_8448_overlaps import SHAFTS  # noqa: E402  pins/axles: their hollow is not a mounting hole
SHRINK = 2.0


def parse_rot(spec):
    m = np.eye(4)
    if not spec:
        return m
    for item in spec.split(","):
        ax, deg = item.split(":")
        m = bm.rot(ax.strip(), float(deg)) @ m
    return m


def obbs(items):
    """(centres Nx3, rotations Nx3x3, half extents Nx3) for (ref, matrix) pairs with known bounds."""
    cs, rs, hs = [], [], []
    for ref, m in items:
        bnd = BOUNDS.get(ref.lower())
        if not bnd:
            continue
        lo, hi = np.array(bnd[0]), np.array(bnd[1])
        h = np.maximum((hi - lo) / 2 - SHRINK, 0.5)
        c = (lo + hi) / 2
        r = m[:3, :3]
        cs.append(r @ c + m[:3, 3])
        rs.append(r)
        hs.append(h)
    return np.array(cs).reshape(-1, 3), np.array(rs).reshape(-1, 3, 3), np.array(hs).reshape(-1, 3)


def sat(ca, ra, ha, cb, rb, hb):
    t = cb - ca
    axes = [ra[:, i] for i in range(3)] + [rb[:, i] for i in range(3)]
    for i in range(3):
        for j in range(3):
            v = np.cross(ra[:, i], rb[:, j])
            n = np.linalg.norm(v)
            if n > 1e-6:
                axes.append(v / n)
    for ax in axes:
        pa = sum(ha[k] * abs(ax @ ra[:, k]) for k in range(3))
        pb = sum(hb[k] * abs(ax @ rb[:, k]) for k in range(3))
        if abs(t @ ax) > pa + pb:
            return False
    return True


def collisions(mod, body):
    mc_, mr, mh = mod
    bc, br, bh = body
    if not len(mc_) or not len(bc):
        return 0
    mrad = np.linalg.norm(mh, axis=1)
    brad = np.linalg.norm(bh, axis=1)
    d = np.linalg.norm(mc_[:, None, :] - bc[None, :, :], axis=2)
    cand = np.argwhere(d < mrad[:, None] + brad[None, :])
    return sum(1 for i, j in cand if sat(mc_[i], mr[i], mh[i], bc[j], br[j], bh[j]))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--roots", required=True)
    ap.add_argument("--exclude", default="")
    ap.add_argument("--rot", default="")
    ap.add_argument("--near", required=True)
    ap.add_argument("--radius", type=float, default=80)
    ap.add_argument("--units", default="")
    ap.add_argument("--top", type=int, default=8)
    ap.add_argument("--min-length", type=float, default=8)
    a = ap.parse_args()
    car = bm.Car()
    b = bm.build_all(car)
    roots = a.roots.split(",")
    excl = set()
    for e in filter(None, a.exclude.split(",")):
        excl.update(car.under(e))
    ids = [i for r in roots for i in car.under(r) if i not in excl]
    taken = [i for i in ids if i in b.placed]
    if taken:
        raise SystemExit(f"already placed: {taken[:5]}")
    phys = [i for i in ids if i not in car.flex]
    R = parse_rot(a.rot)
    near = np.array([float(v) for v in a.near.split(",")])
    # module centre (car frame) and free holes (car frame, free within the module)
    centre_car = np.mean([car.world(i)[:3, 3] for i in phys], axis=0)
    mparts = [(i, car.nodes[i]["ref"], car.world(i)) for i in phys]
    mholes = [h for h in mc.merge_lines(mc.free_females(mparts, ids=set(phys))) if h["length"] >= a.min_length
              and car.nodes[h["part"]]["ref"].lower() not in SHAFTS]
    # robot free holes near the target
    units = set(filter(None, a.units.split(",")))
    bparts = [(i, car.nodes[i]["ref"], b.matrix(i)) for i in b.placed if i not in car.flex]
    span = max(np.linalg.norm(car.world(i)[:3, 3] - centre_car) for i in phys) + a.radius + 40
    scope = {i for i, _, m in bparts if np.linalg.norm(m[:3, 3] - near) < span
             and (not units or b.placed[i]["unit"] in units)}
    bholes = [h for h in mc.merge_lines(mc.free_females(bparts, ids=scope)) if h["length"] >= a.min_length
              and car.nodes[h["part"]]["ref"].lower() not in SHAFTS]
    body = obbs([(ref, m) for i, ref, m in bparts if np.linalg.norm(m[:3, 3] - near) < span + 200])
    rows = []
    for mh in mholes:
        ax_m = R[:3, :3] @ mh["axis"]
        for bh in bholes:
            u = bh["axis"]
            if abs(float(ax_m @ u)) < 0.995:
                continue
            for side in (1, -1):
                t0, t1 = 0.0, float((bh["b"] - bh["a"]) @ u)
                face = bh["a"] + u * (max(t0, t1) if side > 0 else min(t0, t1))
                target_mid = face + u * side * mh["length"] / 2
                t = target_mid - R[:3, :3] @ mh["mid"]
                if np.linalg.norm(R[:3, :3] @ centre_car + t - near) > a.radius:
                    continue
                T = R.copy()
                T[:3, 3] = t
                mod = obbs([(car.nodes[i]["ref"], T @ car.world(i)) for i in phys])
                col = collisions(mod, body)
                # extra coaxial pairs
                extra = 0
                for mh2 in mholes:
                    if mh2 is mh:
                        continue
                    p2 = R[:3, :3] @ mh2["mid"] + t
                    a2 = R[:3, :3] @ mh2["axis"]
                    for bh2 in bholes:
                        if bh2 is bh or abs(float(a2 @ bh2["axis"])) < 0.995:
                            continue
                        dvec = bh2["mid"] - p2
                        radial = np.linalg.norm(dvec - bh2["axis"] * float(dvec @ bh2["axis"]))
                        if radial < 0.8 and abs(float(dvec @ bh2["axis"])) < (mh2["length"] + bh2["length"]) / 2 + 2:
                            extra += 1
                rows.append((col, -extra, float(np.linalg.norm(R[:3, :3] @ centre_car + t - near)), mh, bh, side,
                             T))
    rows.sort(key=lambda r: (r[0], r[1], r[2]))
    print(f"module parts {len(phys)}, module holes {len(mholes)}, robot holes {len(bholes)}, candidates {len(rows)}")
    for col, nextra, dist, mh, bh, side, T in rows[: a.top]:
        joiner = "2780 pin" if mh["kind"] == bh["kind"] == "pin_hole" else "32062 axle 2"
        print(f"collisions={col} extra_pins={-nextra} dist={dist:.0f} side={side} joiner={joiner} "
              f"module_hole=({mh['part']}, {np.round(mh['mid'], 1).tolist()}) "
              f"robot_hole=({bh['part']} {b.placed[bh['part']]['unit']}, {np.round(bh['mid'], 1).tolist()}) "
              f"axis={np.round(bh['axis'], 2).tolist()} t={np.round(T[:3, 3], 1).tolist()}")


if __name__ == "__main__":
    main()
