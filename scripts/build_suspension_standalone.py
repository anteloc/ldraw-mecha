#!/usr/bin/env python3
"""Standalone 42110 suspension: choose the subsystem, then reuse its verified motion.

    # 1. Suspension parts + the static frame they mount on (keep.json)
    scripts/build_suspension_standalone.py select \
        --plan output/42110-suspension/plan.json \
        --evidence output/42110-suspension/evidence/contacts-suspension.json \
        --output output/42110-suspension-standalone/keep.json
    # 2. scripts/extract_subsystem.py writes the standalone MPD + idmap.json
    # 3. ./ldraw-mecha prepare <standalone.mpd> --output output/42110-suspension-standalone/study
    # 4. The full-model plan's motion with instance IDs remapped
    scripts/build_suspension_standalone.py plan \
        --plan output/42110-suspension/plan.json \
        --study output/42110-suspension-standalone/study/plan.json \
        --idmap output/42110-suspension-standalone/source/idmap.json \
        --keep output/42110-suspension-standalone/keep.json \
        --output output/42110-suspension-standalone/plan.json --ready

Selection, all measured on the full model:
- moving: every instance of the suspension plan;
- mounts: static parts joined to a moving part (pyldraw3 contacts, a male
  connector in a hole line, or coincident ball/clip/pin connector centres);
  Cardan input yokes belong to the drivetrain and are left out;
- frame: from the mounts, expand (contacts and hole lines) through connector
  parts (pins, axles, bushes, cross blocks, angle connectors, joiners) up to
  the first beams/liftarms,
  which are kept but not expanded; depth <= 4. Gears, differentials, rack,
  gearbox/engine sections, body parts and anything another rig moves
  (`--moving-elsewhere`, e.g. the transfer shaft) are never added.
The extracted model keeps the source frame, so controls, signals, bodies'
origins/axes, anchors and checks are copied unchanged; only IDs are remapped.
"""

import argparse
from collections import defaultdict
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
from build_defender_rig import Geometry, sections  # noqa: E402
from build_defender_suspension import CORNERS, seated  # noqa: E402
from ldraw_mechanisms import plan as contract  # noqa: E402
from ldraw_mechanisms.math3d import length, sub  # noqa: E402

CONNECTOR = re.compile(r"Pin|Axle|Bush|Cross Block|Angle Connector|Joiner|Connector", re.I)
MEMBER = re.compile(r"Beam|Liftarm", re.I)
NEVER = re.compile(r"Gear|Differential|Rack|Driving Ring|Changeover|Panel|Fairing|Tile|Plate|Slope|Brick|"
                   r"Wheel|Tyre|Hose|Rope|String|Rubber|Hook|Steering Wheel ", re.I)
NEVER_SECTIONS = ("frontgearbox", "frontgearbox2", "frontgearbox4", "shiftplate", "engine", "camshaft",
                  "reargearbox", "reargearbox2", "reargearbox4", "reargearboxlever", "rearbox3", "steerrack",
                  "frontaxle2", "winchgears")
MAX_DEPTH = 4


def key(s):
    return [int(x) for x in s.split("/")]


def select(plan, evidence, include=(), exclude=(), elsewhere=()):
    """`elsewhere`: parts another rig moves (shafts, knobs); never treated as frame."""
    elsewhere = set(elsewhere)
    g = Geometry(plan["source"], evidence)
    nodes = g.nodes
    moving = {i for b in plan["bodies"].values() for i in b["instances"]}
    parts = [n["id"] for n in plan["source"]["nodes"]
             if n["kind"] == "part" and not n["ref"].lower().startswith("p/")]
    adj = defaultdict(set)
    for c in evidence["contacts"]:
        adj[c["a"]].add(c["b"])
        adj[c["b"]].add(c["a"])

    def drivetrain(q):
        return "Universal Joint 3L End" in g.desc(q)

    def coincident(a, b):
        pairs = {("generic", "generic"), ("clip", "pin"), ("pin", "clip")}
        return any((f["kind"], h["kind"]) in pairs and length(sub(f["pos"], h["pos"])) < 0.6
                   for f in g.conn(a) for h in g.conn(b))

    reasons = {}
    for m in sorted(moving, key=key):
        local = [q for q in parts if q not in moving and length(sub(g.at(q), g.at(m))) < 140]
        joined = (adj[m] - moving) | seated(g, m, ("pin_hole", "axle_hole"), local)
        joined |= {q for q in local if m in seated(g, q, ("pin_hole", "axle_hole"), [m]) or coincident(m, q)}
        for q in joined:
            if q not in moving and not drivetrain(q):
                reasons.setdefault(q, ("mount", f"joined to moving {m} ({g.desc(m)})"))
    neighbours = {}

    def joined_to(r):
        """Contacts plus hole lines both ways: pyldraw3 reports no axle-in-round-hole contact."""
        if r not in neighbours:
            local = [q for q in parts if q != r and length(sub(g.at(q), g.at(r))) < 120]
            neighbours[r] = (adj[r] | seated(g, r, ("pin_hole", "axle_hole"), local, reach=60)
                             | {q for q in local if r in seated(g, q, ("pin_hole", "axle_hole"), [r], reach=60)})
        return neighbours[r]

    mounts = [q for q, (role, _) in reasons.items() if role == "mount"]
    frontier = list(mounts)
    for depth in range(1, MAX_DEPTH + 1):
        nxt = []
        for r in frontier:
            if r in reasons and reasons[r][0] == "frame" and MEMBER.search(g.desc(r)):
                continue  # beams/liftarms end the frame closure
            for q in sorted(joined_to(r) - moving - set(reasons), key=key):
                desc = g.desc(q)
                if (NEVER.search(desc) or drivetrain(q) or q in elsewhere
                        or any(s in NEVER_SECTIONS for s in sections(plan, q))):
                    continue
                if MEMBER.search(desc) or CONNECTOR.search(desc):
                    reasons[q] = ("frame", f"depth {depth} from {r} ({g.desc(r)})")
                    nxt.append(q)
        frontier = nxt
    for q in include:
        reasons[q] = ("frame", "included after visual review")
    for q in exclude:
        reasons.pop(q, None)
    rows = [dict(id=i, role="moving", reason=next(b for b, v in plan["bodies"].items() if i in v["instances"]),
                 description=g.desc(i)) for i in sorted(moving, key=key)]
    rows += [dict(id=i, role=role, reason=why, description=g.desc(i))
             for i, (role, why) in sorted(reasons.items(), key=lambda kv: key(kv[0]))]
    return rows


def remap(full, study, idmap, keep):
    m = lambda i: idmap[i]  # noqa: E731
    out = dict(study)
    bodies = {}
    for name, b in full["bodies"].items():
        b = dict(b)
        b["instances"] = sorted((m(i) for i in b["instances"]), key=key)
        bodies[name] = b
    out.update(name="defender_42110_suspension_standalone", controls=full["controls"], signals=full["signals"],
               bodies=bodies, anchors=full["anchors"], checks=full["checks"], status="draft")
    connections = dict(study.get("connections", {}))
    for cid, c in full["connections"].items():
        if cid.startswith("susp_") and c["a"] in idmap and c["b"] in idmap:
            connections[cid] = dict(c, a=m(c["a"]), b=m(c["b"]))
    out["connections"] = connections
    owned = {i for b in bodies.values() for i in b["instances"]}
    views = {}
    for name, v in full["mechanisms"].items():
        if name.startswith("suspension_"):
            views[name] = dict(v, parts=sorted((m(i) for i in v["parts"] if i in idmap), key=key))
    static = [m(r["id"]) for r in keep if r["role"] != "moving"]
    leftover = sorted((set(study["discovery"]["mechanical_parts"]) | set(static)) - owned, key=key)
    views["mounting_frame"] = dict(
        label="Mounting frame (static context)", parts=leftover, bodies=[], inputs=[], outputs=[],
        notes=[f"Parts: {len(leftover)}.",
               "Pivot axles, inner liftarms, link ball pins, shock-top axles and the beams/cross blocks holding them."],
        disposition="static",
        review="Kept only as the frame the suspension pivots on; static by decision (the coupled elements are "
               "context, not moving). Differentials, steering rack and the rest of the vehicle are not in this model.")
    out["mechanisms"] = views
    out["notes"] = [
        "Standalone subsystem extracted from output/42110-suspension/source/42110-1-shocks-split.mpd (derived "
        "from data/models-annotated/42110-1.mpd by Philippe Hurbain) with scripts/extract_subsystem.py: the "
        "suspension and the static frame it mounts on, written with world matrices in the original frame.",
        "Selection (keep.json): every suspension-plan instance, the static parts joined to them, and connector "
        "parts out to the first beams/liftarms. Cardan input yokes, differentials, steering rack, gearboxes, "
        "engine, cab and bodywork are left out.",
        "Front tie rods keep their inner ball pins as mounts; the rack that holds them is not in this model.",
        *full["notes"][1:],
    ]
    return out


def main():
    ap = argparse.ArgumentParser()
    sub_ = ap.add_subparsers(dest="command", required=True)
    s = sub_.add_parser("select")
    s.add_argument("--plan", required=True)
    s.add_argument("--evidence", required=True)
    s.add_argument("--output", required=True)
    s.add_argument("--include", nargs="*", default=[])
    s.add_argument("--exclude", nargs="*", default=[])
    s.add_argument("--moving-elsewhere", help="Another plan (e.g. the drivetrain rig): its moving parts are not frame")
    p = sub_.add_parser("plan")
    p.add_argument("--plan", required=True, help="Full-model suspension plan")
    p.add_argument("--study", required=True, help="Prepared study of the standalone MPD")
    p.add_argument("--idmap", required=True)
    p.add_argument("--keep", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--ready", action="store_true")
    a = ap.parse_args()
    if a.command == "select":
        full = contract.load(a.plan)
        elsewhere = ()
        if a.moving_elsewhere:
            other = contract.load(a.moving_elsewhere)
            elsewhere = {i for b in other["bodies"].values() for i in b["instances"]}
        rows = select(full, json.loads(Path(a.evidence).read_text()), a.include, a.exclude, elsewhere)
        counts = {r: sum(1 for x in rows if x["role"] == r) for r in ("moving", "mount", "frame")}
        Path(a.output).parent.mkdir(parents=True, exist_ok=True)
        Path(a.output).write_text(json.dumps(dict(parts=rows, counts=counts, include=a.include, exclude=a.exclude,
                                                  moving_elsewhere=a.moving_elsewhere,
                                                  source_plan=a.plan, source_digest=contract.digest(full)),
                                             indent=1) + "\n")
        print(json.dumps(dict(output=a.output, **counts)))
        return
    full = contract.load(a.plan)
    idmap = json.loads(Path(a.idmap).read_text())["idmap"]
    keep = json.loads(Path(a.keep).read_text())["parts"]
    out = remap(full, contract.load(a.study), idmap, keep)
    if a.ready:
        out["status"] = "ready"
    contract.validate(out)
    contract.save(a.output, out)
    print(json.dumps(dict(plan=a.output, status=out["status"], bodies=len(out["bodies"]),
                          moving=sum(len(b["instances"]) for b in out["bodies"].values()),
                          parts=sum(1 for n in out["source"]["nodes"] if n["kind"] == "part"),
                          views={k: v["disposition"] for k, v in out["mechanisms"].items()})))


if __name__ == "__main__":
    main()
