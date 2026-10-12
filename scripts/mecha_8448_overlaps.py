"""Classify a glb_overlaps.py report for the mecha: inherited, engaged or suspicious pairs.

    .venv/bin/python scripts/mecha_8448_overlaps.py output/8448-mecha/overlaps.json [--connectivity C.json]

inherited  both occurrences were moved by the same rigid car-module transform: their geometry relation is the
           car's own (car calibration: the official model has 1757 such mesh contacts at 0.6 LDU shrink).
engaged    a connector engagement joins them (pin in hole, axle in hole, stud in tube...).
shaft_neighbours  both are engaged with the same pin/axle (flush neighbours on a shared shaft).
suspicious anything else: new geometric contact without a connector - review visually.
"""
import argparse
import json
from collections import Counter
from pathlib import Path


SHAFTS = {"2780.dat", "6558.dat", "3673.dat", "32002.dat", "32054.dat", "3749.dat", "4274.dat", "32062.dat",
          "4519.dat", "3705.dat", "3706.dat", "3707.dat", "3737.dat", "3708.dat", "32073.dat", "6587.dat", "32209.dat",
          "32138.dat"}


def classify(overlaps, idmap, edges):
    E = set(tuple(sorted(k.split("|"))) for k in edges)
    nbr = {}
    for a, b in E:
        nbr.setdefault(a, set()).add(b)
        nbr.setdefault(b, set()).add(a)
    out = {"inherited": [], "engaged": [], "shaft_neighbours": [], "suspicious": []}
    for p in overlaps["pairs"]:
        ga, gb = idmap[p["a"]].get("group"), idmap[p["b"]].get("group")
        common = nbr.get(p["a"], set()) & nbr.get(p["b"], set())
        if ga and ga == gb:
            out["inherited"].append(p)
        elif tuple(sorted((p["a"], p["b"]))) in E:
            out["engaged"].append(p)
        elif any(idmap[c]["ref"].lower() in SHAFTS for c in common):
            # Both sit on the same pin/axle: flush faces of neighbours on a shared shaft.
            out["shaft_neighbours"].append(p)
        else:
            out["suspicious"].append(p)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("overlaps")
    ap.add_argument("--idmap", default="output/8448-mecha/source/idmap.json")
    ap.add_argument("--connectivity", default="output/8448-mecha/connectivity.json")
    a = ap.parse_args()
    ov = json.loads(Path(a.overlaps).read_text())
    idmap = json.loads(Path(a.idmap).read_text())["idmap"]
    edges = json.loads(Path(a.connectivity).read_text())["edge_list"]
    c = classify(ov, idmap, edges)
    print({k: len(v) for k, v in c.items()})
    for p in c["suspicious"]:
        print(f"  {p['unit_a']}:{p['a']}({p['ref_a']}, car {p['car_a']})  x  {p['unit_b']}:{p['b']}({p['ref_b']}, car {p['car_b']})")
    Path(a.overlaps).with_name(Path(a.overlaps).stem + "-classified.json").write_text(json.dumps(
        {k: v for k, v in c.items()}, indent=1) + "\n")


if __name__ == "__main__":
    main()
