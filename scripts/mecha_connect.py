"""Geometric connector engagement for whole-model connectivity checks (8448 mecha builder).

pyldraw3 `connection_contacts` misses most pin/beam joints in 8448 (149 of 177 friction pins report no
contact on the official car), so the mecha builder uses its own, simpler test on the same connector metadata
(`parts_library().connection_metadata`, LDCad shadow + primitives):

- a male cylinder (pin, axle, bar) engages a female cylinder (pin hole, axle hole, clip) of another part when
  their axes are parallel, the lines are within RADIAL LDU of each other and the segments overlap axially;
- a stud engages a stud receptacle at the same point with a parallel axis;
- ball sockets (`generic`) and tyre bead / rim seat engage at the same point.

Axle features produced by `axlehol*` / `axl2ho*` hole primitives are reported by pyldraw3 as male; they are
holes and are reclassified as female here. Female-female or male-male coincidence never counts.

The result is evidence that parts *touch through a connector*, not proof of retention, strength or freedom.
It is calibrated on the official car (`calibrate` below) before being used as the robot's connectivity check.
Flexible LDCad units (hoses, flex axles, spring meshes) carry no connector metadata and are reported separately.
"""

from __future__ import annotations

from collections import defaultdict
from functools import lru_cache
import math

import numpy as np

from ldraw_mechanisms.placements import analysis_placement
from ldraw_mechanisms.source import jsonable, parts_library

RADIAL = 1.0  # LDU between coaxial lines
AXIAL_MIN = 2.0  # LDU of axial overlap required for a cylinder engagement
POINT = 1.5  # LDU for stud / ball / tyre point matches
PARALLEL = 0.995  # |cos| between axes

_HOLE_PRIMITIVES = ("axlehol", "axl2ho", "axl3ho", "axl4ho", "axl5ho", "axleho")


def _value(v):
    return getattr(v, "value", str(v))


@lru_cache(maxsize=None)
def part_features(ref):
    """Connector features of a library part in part-local coordinates (cached per reference)."""
    name = ref[:-4] if ref.lower().endswith(".dat") else ref
    out = []
    try:
        features = parts_library().connection_metadata(name).features
    except Exception:  # embedded/unknown geometry: no connectors
        return ()
    for f in features:
        j = jsonable(f)
        kind, role = _value(j["kind"]), _value(j["role"])
        frame = np.array(j["frame"], dtype=float)
        axis = frame[:, 1].copy()
        profile = j.get("profile") or {}
        length = float(sum(s["length"] for s in profile.get("sections", [])))
        fid = j["feature_id"]
        if kind == "axle" and role == "male" and any(p in fid for p in _HOLE_PRIMITIVES):
            kind, role = "axle_hole", "female"
        pos = np.array(j["position"], dtype=float)
        if profile.get("centered"):
            a, b = pos - axis * length / 2, pos + axis * length / 2
        else:
            a, b = pos, pos + axis * length
        out.append(dict(kind=kind, role=role, a=a, b=b, axis=axis, pos=pos, length=length, feature=fid))
    return tuple(out)


CYL_MALE = {"pin", "axle", "bar"}
CYL_FEMALE = {"pin_hole", "axle_hole", "clip"}
COMPATIBLE = {("pin", "pin_hole"), ("axle", "axle_hole"), ("axle", "pin_hole"), ("bar", "clip"),
              ("bar", "pin_hole"), ("pin", "clip")}


def world_features(pid, ref, world):
    m = np.asarray(world, float)
    r, t = m[:3, :3], m[:3, 3]
    for f in part_features(ref):
        yield dict(part=pid, kind=f["kind"], role=f["role"], a=r @ f["a"] + t, b=r @ f["b"] + t,
                   axis=r @ f["axis"], pos=r @ f["pos"] + t, length=f["length"], feature=f["feature"])


def _cyl_engaged(m, f):
    am = m["axis"] / (np.linalg.norm(m["axis"]) or 1)
    af = f["axis"] / (np.linalg.norm(f["axis"]) or 1)
    if abs(float(am @ af)) < PARALLEL:
        return None
    # Radial distance from the female segment's midpoint to the male line.
    fm = (f["a"] + f["b"]) / 2
    d = fm - m["a"]
    radial = np.linalg.norm(d - am * float(d @ am))
    if radial > RADIAL:
        return None
    # Axial intervals along the male axis.
    m0, m1 = sorted((0.0, float((m["b"] - m["a"]) @ am)))
    f0, f1 = sorted((float((f["a"] - m["a"]) @ am), float((f["b"] - m["a"]) @ am)))
    if f1 - f0 < 1e-6:  # point-like female (zero-length hole primitive)
        inside = m0 - 0.5 <= f0 <= m1 + 0.5
        return (radial, 0.0) if inside and m1 - m0 > 1e-6 else None
    overlap = min(m1, f1) - max(m0, f0)
    return (radial, overlap) if overlap >= AXIAL_MIN else None


def engagements(parts):
    """parts: iterable of (id, ref, 4x4 world). Returns {(a, b): evidence} with a < b (string order)."""
    feats = []
    for pid, ref, world in parts:
        feats.extend(world_features(pid, ref, world))
    cell = 40.0
    grid = defaultdict(list)
    for i, f in enumerate(feats):
        mid = (f["a"] + f["b"]) / 2
        span = np.linalg.norm(f["b"] - f["a"]) / 2 + 2
        lo = np.floor((mid - span) / cell).astype(int)
        hi = np.floor((mid + span) / cell).astype(int)
        for x in range(lo[0], hi[0] + 1):
            for y in range(lo[1], hi[1] + 1):
                for z in range(lo[2], hi[2] + 1):
                    grid[(x, y, z)].append(i)
    found = {}
    seen = set()
    for bucket in grid.values():
        for ii in range(len(bucket)):
            fi = feats[bucket[ii]]
            for jj in range(ii + 1, len(bucket)):
                fj = feats[bucket[jj]]
                if fi["part"] == fj["part"]:
                    continue
                key = (bucket[ii], bucket[jj]) if bucket[ii] < bucket[jj] else (bucket[jj], bucket[ii])
                if key in seen:
                    continue
                seen.add(key)
                ev = _match(fi, fj) or _match(fj, fi)
                if ev:
                    a, b = sorted((fi["part"], fj["part"]))
                    found.setdefault((a, b), ev)
    return found


def _match(m, f):
    km, kf = m["kind"], f["kind"]
    if m["role"] != "male" or f["role"] != "female":
        return None
    if (km, kf) in COMPATIBLE:
        r = _cyl_engaged(m, f)
        if r:
            return dict(kind=f"{km}>{kf}", radial=round(r[0], 3), overlap=round(r[1], 2),
                        position=[round(float(v), 2) for v in (f["a"] + f["b"]) / 2])
        return None
    if (km, kf) in {("stud", "stud_receptacle"), ("generic", "generic"), ("rim_seat", "tyre_bead")}:
        if np.linalg.norm(m["pos"] - f["pos"]) <= POINT:
            if km == "generic" or abs(float(m["axis"] @ f["axis"])) >= PARALLEL:
                return dict(kind=f"{km}>{kf}", distance=round(float(np.linalg.norm(m["pos"] - f["pos"])), 3),
                            position=[round(float(v), 2) for v in f["pos"]])
    return None


def components(ids, edges):
    parent = {i: i for i in ids}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for a, b in edges:
        if a in parent and b in parent:
            parent[find(a)] = find(b)
    groups = defaultdict(list)
    for i in ids:
        groups[find(i)].append(i)
    return sorted(groups.values(), key=len, reverse=True)


def manifest_parts(manifest):
    """(id, ref, analysis world) for every physical part of a source manifest (rounded frames normalized)."""
    out = []
    for n in manifest["nodes"]:
        if n["kind"] != "part" or n.get("embedded"):
            continue
        world, _ = analysis_placement(n)
        out.append((n["id"], n["ref"], world))
    return out


def report(manifest):
    parts = manifest_parts(manifest)
    edges = engagements(parts)
    ids = [p[0] for p in parts]
    comps = components(ids, edges)
    degree = defaultdict(int)
    for a, b in edges:
        degree[a] += 1
        degree[b] += 1
    refs = {p[0]: p[1] for p in parts}
    isolated = [i for i in ids if degree[i] == 0]
    return dict(parts=len(ids), edges=len(edges), components=len(comps),
                component_sizes=[len(c) for c in comps[:12]],
                isolated=[dict(id=i, ref=refs[i]) for i in isolated],
                minor_components=[[dict(id=i, ref=refs[i]) for i in c] for c in comps[1:]],
                edge_list={f"{a}|{b}": e for (a, b), e in edges.items()},
                rule=dict(radial=RADIAL, axial_min=AXIAL_MIN, point=POINT, parallel=PARALLEL))


def free_females(manifest_or_parts, ids=None, kinds=("pin_hole", "axle_hole")):
    """Female cylinder features (world) of the given parts that no male of any part engages."""
    parts = manifest_or_parts if isinstance(manifest_or_parts, list) else manifest_parts(manifest_or_parts)
    feats = [f for pid, ref, w in parts for f in world_features(pid, ref, w)]
    males = [f for f in feats if f["role"] == "male" and f["kind"] in CYL_MALE]
    out = []
    for f in feats:
        if f["role"] != "female" or f["kind"] not in kinds or (ids is not None and f["part"] not in ids):
            continue
        if any(m["part"] != f["part"] and (m["kind"], f["kind"]) in COMPATIBLE and _cyl_engaged(m, f) for m in males
               if np.linalg.norm((m["a"] + m["b"]) / 2 - (f["a"] + f["b"]) / 2) < 60):
            continue
        out.append(f)
    return out


def angle_between(a, b):
    a, b = np.asarray(a, float), np.asarray(b, float)
    return math.degrees(math.acos(max(-1.0, min(1.0, float(a @ b) / (np.linalg.norm(a) * np.linalg.norm(b))))))


def is_fragment(feature_id):
    """Partial hole surfaces (npeghol*/npeghole) between real holes of bent liftarms and triangles."""
    last = feature_id.split("/")[-1]
    return last.startswith("npeghol")


def merge_lines(features):
    """Collapse coaxial, overlapping cylinder features of the same part and kind into single holes/shafts.

    Fragment primitives (`is_fragment`) are ignored: they are surfaces between holes, not connectors."""
    groups = defaultdict(list)
    for f in features:
        if is_fragment(f.get("feature", "")):
            continue
        ax = f["axis"] / (np.linalg.norm(f["axis"]) or 1)
        if ax[np.argmax(np.abs(ax))] < 0:
            ax = -ax
        p = f["a"] - ax * float(f["a"] @ ax)  # foot of the line nearest the origin
        key = (f["part"], f["kind"], tuple(np.round(ax, 2)), tuple(np.round(p / 2)))
        groups[key].append((f, ax))
    out = []
    for (pid, kind, _, _), fs in groups.items():
        ax = fs[0][1]
        base = fs[0][0]["a"]
        ts = [float((x - base) @ ax) for f, _ in fs for x in (f["a"], f["b"])]
        t0, t1 = min(ts), max(ts)
        out.append(dict(part=pid, kind=kind, role=fs[0][0]["role"], axis=ax, a=base + ax * t0, b=base + ax * t1,
                        mid=base + ax * (t0 + t1) / 2, length=t1 - t0))
    return out
