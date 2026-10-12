"""Turn the 8448 Super Street Sensation into a humanoid mecha built only from the car's own parts.

    .venv/bin/python scripts/build_mecha_8448.py inventory   # output/8448-mecha/inventory.json (car BOM + modules)
    .venv/bin/python scripts/build_mecha_8448.py mpd         # source/8448-mecha.mpd, idmap.json, bom.json
    .venv/bin/python scripts/build_mecha_8448.py connect     # connectivity.json (connector engagement graph)
    .venv/bin/python scripts/build_mecha_8448.py preview     # mpd + GLB + design renders (iteration loop)
    .venv/bin/python scripts/build_mecha_8448.py plan [--ready]

Golden rule, enforced by construction: every line of the robot/base MPD is one specific car occurrence
(physical part, or LDCad-generated flexible unit), used once, with its own reference and effective colour.
`Build` hands occurrences out of a pool keyed by (reference, colour); asking for a part the car no longer has
fails. Whole car sub-assemblies are reused as rigid units (robot world = T @ car world), so their internal pin
and axle joints are exactly the car's. The layout itself lives in `mecha_8448_design.py`.

Flexible LDCad units (ribbed hoses, flex axles, spring meshes) are geometry-only FILEs in the car. They are
written as embedded `.dat` blocks (content verbatim, inline physical parts removed and kept as their own
occurrences) so that the robot manifest sees them as physical leaves that can belong to rig bodies.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import json
import math
from pathlib import Path
import re
import subprocess
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
from ldraw_mechanisms import source  # noqa: E402

CAR = ROOT / "data/models-annotated/8448-1_Wing-Doors.mpd"
OUT = ROOT / "output/8448-mecha"
MPD = OUT / "source/8448-mecha.mpd"
MAIN = "8448-mecha.ldr"
FLEX_RE = re.compile(r"(ribbedhose|flexaxle|springmesh)", re.I)
BLENDER = "/Applications/Blender-5.app/Contents/MacOS/Blender"


# --------------------------------------------------------------------------- geometry
def rot(axis, degrees):
    a = math.radians(degrees)
    c, s = math.cos(a), math.sin(a)
    if abs(s) < 1e-12:
        s = 0.0
    if abs(c) < 1e-12:
        c = 0.0
    m = np.eye(4)
    if axis == "x":
        m[1:3, 1:3] = [[c, -s], [s, c]]
    elif axis == "y":
        m[0, 0], m[0, 2], m[2, 0], m[2, 2] = c, s, -s, c
    elif axis == "z":
        m[0:2, 0:2] = [[c, -s], [s, c]]
    else:
        raise ValueError(axis)
    return m


def rot_about(axis_dir, degrees):
    x, y, z = np.asarray(axis_dir, float) / np.linalg.norm(axis_dir)
    a = math.radians(degrees)
    c, s, t = math.cos(a), math.sin(a), 1 - math.cos(a)
    m = np.eye(4)
    m[:3, :3] = [[t * x * x + c, t * x * y - s * z, t * x * z + s * y],
                 [t * x * y + s * z, t * y * y + c, t * y * z - s * x],
                 [t * x * z - s * y, t * y * z + s * x, t * z * z + c]]
    return m


def trans(*t):
    m = np.eye(4)
    m[:3, 3] = t if len(t) == 3 else t[0]
    return m


def basis(x=None, y=None, z=None):
    """Rotation (4x4) whose columns are the given local axes expressed in world (two are enough)."""
    cols = {k: np.asarray(v, float) for k, v in (("x", x), ("y", y), ("z", z)) if v is not None}
    if len(cols) < 2:
        raise ValueError("need two axes")
    if "x" not in cols:
        cols["x"] = np.cross(cols["y"], cols["z"])
    if "y" not in cols:
        cols["y"] = np.cross(cols["z"], cols["x"])
    if "z" not in cols:
        cols["z"] = np.cross(cols["x"], cols["y"])
    m = np.eye(4)
    m[:3, :3] = np.column_stack([cols["x"], cols["y"], cols["z"]])
    if abs(np.linalg.det(m[:3, :3]) - 1) > 1e-6:
        raise ValueError("basis is not a rotation")
    return m


def point(m, p):
    return (np.asarray(m, float) @ np.append(np.asarray(p, float), 1.0))[:3]


def direction(m, d):
    return np.asarray(m, float)[:3, :3] @ np.asarray(d, float)


def unit(v):
    v = np.asarray(v, float)
    return v / np.linalg.norm(v)


_unit = unit


def frame(origin, axis, up):
    """4x4 frame: z = axis, y = component of `up` perpendicular to the axis."""
    z = unit(axis)
    y = np.asarray(up, float) - z * float(np.dot(up, z))
    if np.linalg.norm(y) < 1e-9:
        raise ValueError("up is parallel to the axis")
    y = unit(y)
    m = np.eye(4)
    m[:3, :3] = np.column_stack([np.cross(y, z), y, z])
    m[:3, 3] = origin
    return m


def align(local_frame, world_frame):
    """Transform T with T @ local_frame == world_frame (both 4x4 rigid frames)."""
    return np.asarray(world_frame, float) @ np.linalg.inv(np.asarray(local_frame, float))


def _dist_to_segment(p, a, b):
    ab = b - a
    t = 0.0 if float(ab @ ab) < 1e-9 else min(1.0, max(0.0, float((p - a) @ ab) / float(ab @ ab)))
    return float(np.linalg.norm(p - (a + ab * t)))


def number(v):
    s = f"{0.0 if abs(v) < 5e-10 else v:.10g}"
    return "0" if s in ("-0", "0") else s


# --------------------------------------------------------------------------- the car
class Car:
    """The source car: occurrences (physical parts + flexible LDCad units), modules and BOM."""

    def __init__(self, path=CAR):
        self.path = Path(path)
        self.manifest = source.Document(self.path).manifest()
        self.nodes = {n["id"]: n for n in self.manifest["nodes"]}
        self.kids = defaultdict(list)
        for n in self.manifest["nodes"]:
            self.kids[n["parent"]].append(n["id"])
        self.flex = sorted(i for i, n in self.nodes.items() if n["kind"] == "assembly" and FLEX_RE.search(n["ref"]))
        self.parts = [i for i, n in self.nodes.items() if n["kind"] == "part"]
        self.items = self.parts + self.flex

    def key(self, i):
        n = self.nodes[i]
        ref = source.normalized(n["ref"])
        return (("flex:" + ref) if i in self.flex else ref, n["effective_colour"])

    def under(self, root):
        """Occurrences (parts and flex units) at or below `root` (an assembly or item ID)."""
        if root in self.flex or (root in self.nodes and self.nodes[root]["kind"] == "part"):
            return [root]
        out = []
        for c in self.kids[root]:
            n = self.nodes[c]
            if n["kind"] == "part" or c in self.flex:
                out.append(c)
                if c in self.flex:
                    out.extend(self.under_flex(c))
            else:
                out.extend(self.under(c))
        return out

    def under_flex(self, fid):
        """Physical parts placed inside a flexible unit's FILE (e.g. a 6538b threaded on a flex axle)."""
        return [c for c in self.kids[fid] if self.nodes[c]["kind"] == "part"]

    def world(self, i):
        return np.array(self.nodes[i]["world"], float)

    def bom(self, ids=None):
        return Counter(self.key(i) for i in (self.items if ids is None else ids))

    def module_of(self, i):
        chain = []
        p = self.nodes[i]["parent"]
        while p in self.nodes:
            chain.append(self.nodes[p]["ref"])
            p = self.nodes[p]["parent"]
        return chain[::-1]


# --------------------------------------------------------------------------- the build
class Build:
    def __init__(self, car):
        self.car = car
        self.placed = {}  # car id -> dict(matrix, unit, role)
        self.units = {}  # unit name -> dict(T, region, items)
        self.order = []
        self.reserved = set()  # occurrences kept for whole-module reuse: never handed out as loose stock

    def reserve(self, roots):
        for r in roots:
            self.reserved.update(self.car.under(r))

    # --- allocation
    def _use(self, cid, matrix, unit_name, role, group=None):
        if cid in self.placed:
            raise ValueError(f"car occurrence {cid} used twice ({self.placed[cid]['unit']} and {unit_name})")
        if cid not in self.car.nodes or (cid not in self.car.flex and self.car.nodes[cid]["kind"] != "part"):
            raise ValueError(f"{cid} is not a car occurrence")
        self.placed[cid] = dict(matrix=np.asarray(matrix, float), unit=unit_name, role=role, group=group)
        self.order.append(cid)
        self.units[unit_name]["items"].append(cid)

    def unit(self, name, roots=(), T=None, *, region, exclude=(), role=None):
        # Using a reserved module whole is what the reservation is for.
        """Reuse car occurrences under `roots` rigidly: robot world = T @ car world."""
        T = np.eye(4) if T is None else np.asarray(T, float)
        u = self.units.setdefault(name, dict(T=T, region=region, items=[]))
        u["T"] = T
        skip = set()
        for e in exclude:
            skip.update(self.car.under(e))
        for r in roots:
            for cid in self.car.under(r):
                if cid not in skip:
                    self._use(cid, T @ self.car.world(cid), name, role or "module", group=name)
        return u

    def available(self, ref, colour, *, include_reserved=False):
        key = (source.normalized(ref if ref.endswith(".dat") else ref + ".dat"), str(colour))
        return [i for i in self.car.parts if i not in self.placed and self.car.key(i) == key
                and (include_reserved or i not in self.reserved)]

    def take(self, ref, colour, matrix, *, unit, role="part", prefer=(), cid=None):
        """Place one more car part of (ref, colour); fails when the car has none left."""
        if cid is None and isinstance(colour, (list, tuple)):
            for c in colour:
                if self.available(ref, c):
                    colour = c
                    break
            else:
                colour = colour[0]
        if cid is None:
            free = self.available(ref, colour)
            if not free:
                reserved = len(self.available(ref, colour, include_reserved=True))
                raise ValueError(f"the car has no unused {ref} in colour {colour} outside reserved modules "
                                 f"({reserved} reserved)")
            ranked = sorted(free, key=lambda i: (not any(i == p or i.startswith(p + "/") for p in prefer),
                                                  [int(x) for x in i.split("/")]))
            cid = ranked[0]
        self.units.setdefault(unit, dict(T=np.eye(4), region=unit, items=[]))
        self._use(cid, matrix, unit, role)
        return cid

    def matrix(self, cid):
        return self.placed[cid]["matrix"]

    def features(self, cid):
        import mecha_connect as mc
        return list(mc.world_features(cid, self.car.nodes[cid]["ref"], self.matrix(cid)))

    def leftovers(self):
        return [i for i in self.car.items if i not in self.placed]

    # --- connector lines and mating
    def line(self, cid, near, *, frame="robot", role=None, kinds=None, axis=None):
        """Merged connector line (hole or shaft) of one occurrence nearest to `near`.

        frame='car' reads the occurrence in the car; 'robot' where it has been placed. Returns dict with
        a, b (segment ends), mid, axis (unit), length, kind, role."""
        import mecha_connect as mc
        m = self.car.world(cid) if frame == "car" else self.matrix(cid)
        feats = [f for f in mc.world_features(cid, self.car.nodes[cid]["ref"], m)
                 if f["kind"] in ("pin", "axle", "pin_hole", "axle_hole", "bar")
                 and (role is None or f["role"] == role) and (kinds is None or f["kind"] in kinds)]
        lines = mc.merge_lines(feats)
        if axis is not None:
            lines = [ln for ln in lines if abs(float(np.dot(ln["axis"], unit(axis)))) > 0.99]
        if not lines:
            raise ValueError(f"{cid}: no connector line matching the request")
        near = np.asarray(near, float)
        return min(lines, key=lambda ln: _dist_to_segment(near, ln["a"], ln["b"]))

    def mate(self, child_cid, child_near, at, axis, *, up_child, up_world, child_frame="car"):
        """Unit transform T putting the child occurrence's connector line on the world line through `at` along
        `axis` (line midpoint at `at`), with the child's `up_child` direction turned towards `up_world`.

        The child line's own direction is aligned with `axis`; pass -axis to flip the child over."""
        ln = self.line(child_cid, child_near, frame=child_frame)
        local = frame(ln["mid"], ln["axis"], up_child)
        world = frame(at, axis, up_world)
        return align(local, world)

    def attach(self, name, roots, *, region, module_hole, body_hole, side=1, flip=False, up_child, up_world,
               pin="2780", pin_colour=0, exclude=(), prefer=(), role=None, slide=0.0):
        """Reuse a car module rigidly, pinned flush against a free hole of the already-built robot.

        module_hole = (car id, point near the hole in the car frame); body_hole = (car id, point in the robot).
        The module's hole is made coaxial with the body hole and placed against its end face on `side`
        (+1 along the body hole axis, -1 against it), `slide` LDU further; `flip` reverses the module's hole
        direction; up_child (car frame) turns towards up_world. A `pin` (if given) bridges the interface."""
        body = self.line(body_hole[0], body_hole[1])
        u = body["axis"]
        t0, t1 = 0.0, float((body["b"] - body["a"]) @ u)
        face = body["a"] + u * (max(t0, t1) if side > 0 else min(t0, t1))
        child = self.line(module_hole[0], module_hole[1], frame="car")
        centre = face + u * side * (child["length"] / 2 + slide)
        T = align(frame(child["mid"], child["axis"] * (-1 if flip else 1), up_child), frame(centre, u, up_world))
        self.unit(name, roots, T, region=region, exclude=exclude, role=role)
        if pin:
            self.connector(pin, pin_colour, face + u * side * slide / 2, u, unit=name, role="mount pin",
                           prefer=prefer)
        return T

    def joiner_between(self, ref, colour, a, b, *, unit, role="joiner", prefer=()):
        """Place a pin/axle across the meeting faces of two coaxial placed holes a=(cid, near), b=(cid, near)."""
        la, lb = self.line(*a), self.line(*b)
        u = la["axis"]
        if abs(float(u @ lb["axis"])) < 0.995:
            raise ValueError(f"holes {a[0]} and {b[0]} are not parallel")
        d = lb["mid"] - la["mid"]
        if np.linalg.norm(d - u * float(d @ u)) > 1.0:
            raise ValueError(f"holes {a[0]} and {b[0]} are not coaxial")
        ta = sorted(float((p - la["mid"]) @ u) for p in (la["a"], la["b"]))
        tb = sorted(float((p - la["mid"]) @ u) for p in (lb["a"], lb["b"]))
        face = (ta[1] + tb[0]) / 2 if tb[0] >= ta[0] else (ta[0] + tb[1]) / 2
        return self.connector(ref, colour, la["mid"] + u * face, u, unit=unit, role=role, prefer=prefer)

    def connector(self, ref, colour, center, axis, *, unit, role="connector", roll_hint=(0, -1, 0), prefer=(),
                  local_axis="x"):
        """Place a pin/axle/bush-like part on a world line: its `local_axis` along `axis`, origin at `center`."""
        a = _unit(axis)
        hint = np.asarray(roll_hint, float)
        if abs(float(np.dot(hint, a))) > 0.9:
            hint = np.array([0.0, 0.0, 1.0]) if abs(a[2]) < 0.9 else np.array([1.0, 0.0, 0.0])
        h = _unit(hint - a * float(np.dot(hint, a)))
        if local_axis == "x":
            m = basis(x=a, y=h)
        elif local_axis == "y":
            m = basis(y=a, z=h)
        else:
            m = basis(z=a, x=h)
        m[:3, 3] = center
        return self.take(ref, colour, m, unit=unit, role=role, prefer=prefer)

    def part(self, ref, colour, rotation, local_point, world_point, *, unit, role="part", prefer=()):
        """Place a part so that its local point lands on a world point with the given 4x4 rotation."""
        m = np.asarray(rotation, float).copy()
        m[:3, 3] = np.asarray(world_point, float) - m[:3, :3] @ np.asarray(local_point, float)
        return self.take(ref, colour, m, unit=unit, role=role, prefer=prefer)

    # --- outputs
    def entries(self):
        return [(cid, self.placed[cid]) for cid in self.order]


def flex_dat_name(car, fid):
    stem = re.sub(r"[^a-z0-9]+", "-", Path(car.nodes[fid]["ref"]).stem.lower()).strip("-")
    return f"8448-mecha-{stem}.dat"


def file_blocks(text):
    blocks, name, lines = {}, None, []
    for line in text.splitlines():
        m = re.match(r"^0\s+FILE\s+(.+?)\s*$", line)
        if m:
            if name is not None:
                blocks[source.normalized(name)] = (name, lines)
            name, lines = m.group(1), [line]
        elif name is not None:
            lines.append(line)
    if name is not None:
        blocks[source.normalized(name)] = (name, lines)
    return blocks


def flex_block(car, fid, blocks):
    """The car FILE of a flex unit, renamed to an embedded .dat; inline physical parts are removed."""
    ref = car.nodes[fid]["ref"]
    name, lines = blocks[source.normalized(ref)]
    new = flex_dat_name(car, fid)
    out = []
    for ln in lines:
        t = ln.split()
        if ln.startswith("0 FILE"):
            out.append(f"0 FILE {new}")
        elif ln.startswith("0 Name:"):
            out.append(f"0 Name: {new}")
        elif t and t[0] == "1" and len(t) >= 15 and not FLEX_RE.search(" ".join(t[14:])):
            out.append(f"0 // (inline part {' '.join(t[14:])} written as its own occurrence in {MAIN})")
        else:
            out.append(ln)
    while out and not out[-1].strip():
        out.pop()
    out.insert(2, f"0 // 8448-mecha: verbatim geometry of car FILE '{name}' (LDCad generated flexible element)")
    return out


def write_mpd(build, path=MPD, title="8448 mecha"):
    car = build.car
    text = car.path.read_text(encoding="utf-8-sig")
    blocks = file_blocks(text)
    first = next(iter(blocks.values()))[1]
    author = next((ln for ln in first if ln.startswith("0 Author:")), None)
    licence = next((ln for ln in first if ln.startswith("0 !LICENSE")), None)
    out = [
        f"0 FILE {MAIN}",
        f"0 {title}: humanoid mecha rebuilt only from the parts of 8448 Super Street Sensation "
        f"({len(build.placed)} occurrences)",
        f"0 Name: {MAIN}",
        *(v for v in (author, "0 !LDRAW_ORG Unofficial_Model", licence) if v),
        f"0 // Derived by ldraw-mecha scripts/build_mecha_8448.py from {car.path.name} (original model by "
        "Orion Pobursky). Every type-1 line below is one car occurrence (ID in the preceding comment), "
        "with its own part and colour; see idmap.json and bom.json.",
        "",
    ]
    idmap, flex_used = {}, []
    by_unit = defaultdict(list)
    for cid, p in build.entries():
        by_unit[p["unit"]].append(cid)
    index = 0
    for uname, cids in by_unit.items():
        u = build.units[uname]
        out.append(f"0 // ===== unit {uname} (region {u['region']}, {len(cids)} occurrences)")
        for cid in cids:
            m = build.placed[cid]["matrix"]
            n = car.nodes[cid]
            ref = n["ref"]
            if cid in car.flex:
                ref = flex_dat_name(car, cid)
                flex_used.append(cid)
            values = [m[0, 3], m[1, 3], m[2, 3], *m[0, :3], *m[1, :3], *m[2, :3]]
            out.append(f"0 // from car {cid} | unit {uname} | role {build.placed[cid]['role']}")
            out.append(f"1 {n['effective_colour']} " + " ".join(number(v) for v in values) + f" {ref}")
            idmap[str(index)] = dict(car=cid, unit=uname, region=u["region"], role=build.placed[cid]["role"],
                                     ref=n["ref"], colour=n["effective_colour"], group=build.placed[cid]["group"])
            index += 1
        out.append("0 STEP")
    seen = set()
    for fid in flex_used:
        name = flex_dat_name(car, fid)
        if name in seen:
            continue
        seen.add(name)
        out += ["", *flex_block(car, fid, blocks)]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(out) + "\n")
    return idmap


def verify_mpd(build, idmap, path=MPD):
    """Re-read the written MPD: same occurrences, references, colours and matrices as the builder."""
    man = source.Document(path).manifest()
    nodes = {n["id"]: n for n in man["nodes"]}
    if set(nodes) != set(idmap):
        extra = sorted(set(nodes) ^ set(idmap))[:5]
        raise ValueError(f"written MPD occurrences differ from the ID map: {extra}")
    worst = 0.0
    for rid, e in idmap.items():
        n = nodes[rid]
        cid = e["car"]
        want_ref = flex_dat_name(build.car, cid) if cid in build.car.flex else build.car.nodes[cid]["ref"]
        if source.normalized(n["ref"]) != source.normalized(want_ref) or n["effective_colour"] != e["colour"]:
            raise ValueError(f"{rid} (car {cid}): reference or colour changed")
        if n["kind"] != "part":
            raise ValueError(f"{rid} (car {cid}) is not a physical leaf in the robot MPD")
        worst = max(worst, float(np.max(np.abs(np.array(n["world"]) - build.placed[cid]["matrix"]))))
    if worst > 1e-6:
        raise ValueError(f"written matrices differ from the builder by {worst}")
    return dict(occurrences=len(nodes), max_matrix_error=worst, sha256=source.sha256(path))


def bom_report(build, idmap):
    car = build.car
    robot_ids = [e["car"] for e in idmap.values() if e["region"] != "base"]
    base_ids = [e["car"] for e in idmap.values() if e["region"] == "base"]
    used = robot_ids + base_ids
    if len(set(used)) != len(used):
        raise ValueError("a car occurrence appears twice")
    car_bom, robot_bom, base_bom = car.bom(), car.bom(robot_ids), car.bom(base_ids)
    over = {k: (robot_bom[k] + base_bom[k], car_bom[k]) for k in robot_bom + base_bom
            if robot_bom[k] + base_bom[k] > car_bom[k]}
    if over:
        raise ValueError(f"uses more than the car has: {list(over.items())[:5]}")
    missing = car_bom - (robot_bom + base_bom)
    car_parts = sum(v for k, v in car_bom.items() if not k[0].startswith("flex:"))
    robot_parts = sum(v for k, v in robot_bom.items() if not k[0].startswith("flex:"))

    def rows(c):
        return [dict(ref=k[0], colour=k[1], count=v) for k, v in sorted(c.items())]

    return dict(
        golden_rule="Every robot/base occurrence is a distinct car occurrence with the car's reference and "
                    "effective colour (injective ID map, multiset inclusion checked).",
        car_occurrences=sum(car_bom.values()), car_parts=car_parts, car_flex_units=len(car.flex),
        robot_occurrences=len(robot_ids), robot_parts=robot_parts, base_occurrences=len(base_ids),
        unused_occurrences=sum(missing.values()),
        robot_share_of_parts=round(robot_parts / car_parts, 4),
        complete=(robot_bom + base_bom) == car_bom,
        unused=rows(missing), robot=rows(robot_bom), base=rows(base_bom), car=rows(car_bom),
    )


# --------------------------------------------------------------------------- commands
def cmd_inventory(car):
    mods = []
    for i, n in car.nodes.items():
        if n["kind"] == "assembly" and i not in car.flex:
            items = car.under(i)
            mods.append(dict(id=i, ref=n["ref"], description=n.get("description"), items=len(items)))
    data = dict(source=str(car.path), sha256=car.manifest["sha256"], parts=len(car.parts), flex_units=car.flex,
                bom=[dict(ref=k[0], colour=k[1], count=v) for k, v in sorted(car.bom().items())], modules=mods)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "inventory.json").write_text(json.dumps(data, indent=1) + "\n")
    print(json.dumps(dict(parts=len(car.parts), flex_units=len(car.flex), types=len(car.bom()))))


def build_all(car):
    import mecha_8448_design as design
    b = Build(car)
    design.build(b)
    return b


def cmd_mpd(car, quiet=False):
    b = build_all(car)
    idmap = write_mpd(b)
    check = verify_mpd(b, idmap)
    bom = bom_report(b, idmap)
    (OUT / "source/idmap.json").write_text(json.dumps(dict(idmap=idmap, verification=check), indent=1) + "\n")
    (OUT / "bom.json").write_text(json.dumps(bom, indent=1) + "\n")
    summary = {k: bom[k] for k in ("car_occurrences", "robot_occurrences", "base_occurrences",
                                   "unused_occurrences", "robot_share_of_parts", "complete")}
    summary["units"] = {k: len(v["items"]) for k, v in b.units.items()}
    if not quiet:
        print(json.dumps(summary, indent=1))
    return b, idmap


def cmd_connect(car):
    import mecha_connect as mc
    man = source.Document(MPD).manifest()
    r = mc.report(man)
    idmap = json.loads((OUT / "source/idmap.json").read_text())["idmap"]
    for x in r["isolated"]:
        x["unit"] = idmap[x["id"]]["unit"]
    for comp in r["minor_components"]:
        for x in comp:
            x["unit"] = idmap[x["id"]]["unit"]
    (OUT / "connectivity.json").write_text(json.dumps(r, indent=1) + "\n")
    print(json.dumps(dict(parts=r["parts"], edges=r["edges"], components=r["components"],
                          sizes=r["component_sizes"], isolated=len(r["isolated"])), indent=1))
    return r


def cmd_preview(car, views, tag):
    cmd_mpd(car)
    glb = OUT / "design/robot.glb"
    glb.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([str(ROOT / "ldraw-mecha"), "convert", str(MPD), "--output", str(glb)], check=True,
                   stdout=subprocess.DEVNULL)
    subprocess.run([BLENDER, "-b", "--factory-startup", "--python", str(ROOT / "scripts/blender/render_glb_views.py"),
                    "--", "--glb", str(glb), "--output", str(OUT / "design" / tag), "--views", views,
                    "--size", "900x1000"], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print("renders:", OUT / "design" / tag)


def cmd_check(car, views, tag, render=True):
    """Iteration loop: MPD + GLB, connector engagement graph, rest-pose overlaps (classified), renders."""
    cmd_mpd(car)
    glb = OUT / "design/robot.glb"
    glb.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([str(ROOT / "ldraw-mecha"), "convert", str(MPD), "--output", str(glb)], check=True,
                   stdout=subprocess.DEVNULL)
    cmd_connect(car)
    ov = OUT / "overlaps.json"
    subprocess.run([BLENDER, "-b", "--factory-startup", "--python", str(ROOT / "scripts/blender/glb_overlaps.py"),
                    "--", "--glb", str(glb), "--idmap", str(OUT / "source/idmap.json"), "--output", str(ov)],
                   check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run([sys.executable, str(ROOT / "scripts/mecha_8448_overlaps.py"), str(ov)], check=True)
    if render:
        subprocess.run([BLENDER, "-b", "--factory-startup", "--python",
                        str(ROOT / "scripts/blender/render_glb_views.py"), "--", "--glb", str(glb),
                        "--output", str(OUT / "design" / tag), "--views", views, "--size", "900x1000"],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        print("renders:", OUT / "design" / tag)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("inventory")
    sub.add_parser("mpd")
    sub.add_parser("connect")
    p = sub.add_parser("preview")
    p.add_argument("--views", default="front,side,threequarter,back")
    p.add_argument("--tag", default="latest")
    p = sub.add_parser("check")
    p.add_argument("--views", default="front,side,threequarter,back")
    p.add_argument("--tag", default="latest")
    p.add_argument("--no-render", action="store_true")
    p = sub.add_parser("plan")
    p.add_argument("--ready", action="store_true")
    a = ap.parse_args()
    car = Car()
    if a.cmd == "inventory":
        cmd_inventory(car)
    elif a.cmd == "mpd":
        cmd_mpd(car)
    elif a.cmd == "connect":
        cmd_connect(car)
    elif a.cmd == "preview":
        cmd_preview(car, a.views, a.tag)
    elif a.cmd == "check":
        cmd_check(car, a.views, a.tag, render=not a.no_render)
    elif a.cmd == "plan":
        import mecha_8448_plan as mp
        mp.author(car, ready=a.ready)


if __name__ == "__main__":
    main()
