"""Small source-only reports: inventory first, coordinates when needed."""

from collections import Counter, defaultdict
import re

from .analysis import ROLES
from .math3d import direction, unit
from .source import Document, descriptions, normalized

# Counts of physical pieces, not inferred cylinders or independent shafts.
INVENTORY = {
    "pistons": r"engine piston",
    "rods": r"connecting rod|conrod",
    "crank_parts": r"crankshaft",
    "gears": r"\bgear\b|\bworm\b",
    "axles": r"\baxle\b",
}


def submodels(path, match=None, sort="pistons", limit=30):
    """Memoized recursive inventories retain repeated occurrences and parents.

    Embedded DATs are physical leaves, even when they contain type-1 geometry.
    Counts are per single occurrence of the section, including descendants.
    """
    if sort not in {"parts", *INVENTORY} or not 1 <= limit <= 1000:
        raise ValueError("Invalid inventory sort or limit (1..1000)")
    doc = Document(path)
    catalog = descriptions()
    memo, parents = {}, defaultdict(list)

    def inventory(model, ancestors=()):
        key = normalized(model.name)
        if key in ancestors:
            raise ValueError(f"Assembly cycle: {ancestors + (key,)}")
        if key not in memo:
            counts = Counter()
            for index, piece in enumerate(model.pieces):
                ref = normalized(piece.reference)
                child = doc.resolve(piece.reference)
                if child is not None and not ref.endswith(".dat"):
                    parents[normalized(child.name)].append(
                        dict(section=model.name, index=index)
                    )
                    counts.update(inventory(child, ancestors + (key,)))
                else:
                    counts[ref] += 1
            memo[key] = counts
        return memo[key]

    # Visit even unused FILE sections, but inventory each section only once.
    for model in list(doc.sections.values()):
        if not normalized(model.name).endswith(".dat"):
            inventory(model)
    rows = []
    seen = set()
    for model in doc.sections.values():
        key = normalized(model.name)
        if key not in memo or key in seen:
            continue
        seen.add(key)
        if (
            match
            and match.casefold()
            not in (model.name + " " + (model.description or "")).casefold()
        ):
            continue
        counts = memo[key]
        roles = {
            role: sum(
                n
                for ref, n in counts.items()
                if re.search(pattern, catalog.get(ref, ""), re.I)
            )
            for role, pattern in INVENTORY.items()
        }
        rows.append(
            dict(
                section=model.name,
                description=model.description,
                direct_placements=len(model.pieces),
                parts=sum(counts.values()),
                **roles,
                part_counts=dict(sorted(counts.items())),
                parents=parents[key],
            )
        )
    rows.sort(key=lambda r: (-r[sort], -r["parts"], r["section"]))
    return dict(
        path=str(doc.path),
        sort=sort,
        total=len(rows),
        truncated=len(rows) > limit,
        sections=rows[:limit],
        coverage="Physical piece counts per section occurrence, including descendants; description-based roles may overlap. Crank parts are not shaft counts.",
    )


def compact_inspect(
    manifest, *, refs=None, instances=None, mechanical_only=False, limit=100, offset=0
):
    if not 1 <= limit <= 10000 or offset < 0:
        raise ValueError("limit 1..10000; offset >= 0")
    refs = {normalized(r) for r in refs or []}
    instances = set(instances or [])
    if instances - {n["id"] for n in manifest["nodes"]}:
        raise ValueError("Unknown instance selection")
    rows = []
    for n in manifest["nodes"]:
        roles = [
            role
            for role, pattern in ROLES.items()
            if re.search(pattern, n["description"] or "", re.I)
        ]
        if (
            (refs and normalized(n["ref"]) not in refs)
            or (instances and n["id"] not in instances)
            or (mechanical_only and not roles)
        ):
            continue
        rows.append(
            dict(
                id=n["id"],
                parent=n["parent"],
                ref=n["ref"],
                kind=n["kind"],
                description=n["description"],
                roles=roles,
                position=[row[3] for row in n["world"][:3]],
                axes={
                    k: unit(direction(n["world"], axis))
                    for k, axis in zip("xyz", ([1, 0, 0], [0, 1, 0], [0, 0, 1]))
                },
            )
        )
    return dict(
        path=manifest["path"],
        section=manifest["section"],
        coordinate_space=manifest["coordinate_space"],
        total=len(rows),
        offset=offset,
        truncated=offset + limit < len(rows),
        instances=rows[offset : offset + limit],
        coverage="Axes are transformed part-local X/Y/Z, not inferred joint axes; use connectors for mechanical frames",
    )


def table(report):
    """TSV works in terminals and agent prompts without a rendering dependency."""

    def vector(v):
        return ",".join(f"{x:.4g}" for x in v)

    if "instances" in report:
        lines = [
            "id\tparent\tpart\tposition LDU\tlocal X\tlocal Y\tlocal Z\tdescription"
        ]
        lines += [
            "\t".join(
                [
                    r["id"],
                    r["parent"],
                    r["ref"],
                    vector(r["position"]),
                    *[vector(r["axes"][k]) for k in "xyz"],
                    r["description"] or "",
                ]
            )
            for r in report["instances"]
        ]
    else:
        keys = ["parts", *INVENTORY]
        lines = ["section\t" + "\t".join(keys) + "\tparents (placement index)"]
        lines += [
            "\t".join(
                [
                    r["section"],
                    *[str(r[k]) for k in keys],
                    "; ".join(f"{p['section']} [{p['index']}]" for p in r["parents"]),
                ]
            )
            for r in report["sections"]
        ]
    lines += [
        f"# total={report['total']}; truncated={report['truncated']}; {report['coverage']}"
    ]
    return "\n".join(lines)
