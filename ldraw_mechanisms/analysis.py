"""Conservative discovery: evidence and candidates, never guessed connectivity."""

import re
from collections import Counter

from .source import Document, jsonable, parts_library
from .math3d import direction, point

ROLES = {
    "hinge": r"hinge|door|window.*(?:pane|glass)|hatch",
    "gear": r"gear|worm",
    "rack": r"rack",
    "axle": r"axle|shaft",
    "wheel": r"wheel|tyre",
    "piston": r"piston|cylinder|conrod|connecting rod|crank",
    "joint": r"joint|towball|ball socket|universal",
    "motor": r"motor",
    "turntable": r"turntable",
    "spring": r"spring|shock absorber",
}


def inspect(path, section=None, max_instances=100000):
    doc = Document(path)
    manifest = doc.manifest(section, max_instances)
    candidates = []
    for n in manifest["nodes"]:
        roles = [
            role
            for role, pattern in ROLES.items()
            if re.search(pattern, n["description"] or "", re.I)
        ]
        if roles:
            candidates.append(
                dict(
                    id=n["id"],
                    ref=n["ref"],
                    roles=roles,
                    description=n["description"],
                    evidence="source description / part catalog",
                    status="candidate",
                )
            )
    return dict(
        source=manifest,
        sections=[
            dict(name=m.name, description=m.description, placements=len(m.pieces))
            for m in doc.sections.values()
        ],
        counts=dict(Counter(n["kind"] for n in manifest["nodes"])),
        candidates=candidates,
        coverage=dict(
            parsing="pyldraw3",
            connectors="not requested",
            connectivity="not inferred",
            collision="not checked",
            rigid_groups="require a motion plan",
        ),
        next_steps=[
            "Inspect candidate connector frames and parent context.",
            "Assign rigid groups and measured joint frames in a plan.",
            "Validate, convert, rig and sweep controls.",
        ],
    )


def connectors(manifest, occurrence, library=None, shadow=None, *, parts=None):
    matches = [
        n for n in manifest["nodes"] if n["id"] == occurrence and n["kind"] == "part"
    ]
    if len(matches) != 1:
        raise ValueError(f"No physical occurrence {occurrence!r}")
    n = matches[0]
    if n.get("embedded"):
        raise ValueError(
            "Embedded DAT connector inspection is not supported; inspect its authored source instead of substituting a library part"
        )
    parts = parts or parts_library(library, shadow)
    report = parts.connection_metadata(n["ref"].removesuffix(".dat"))
    features = []
    for f in report.features:
        item = jsonable(f)
        item["world_position"] = point(n["world"], jsonable(f.position))
        # LDCad connector axes are local Y; keep the original complete frame too.
        item["world_axis"] = direction(n["world"], [row[1] for row in f.frame.rows])
        features.append(item)
    return dict(
        id=occurrence,
        ref=n["ref"],
        coordinate_space=manifest["coordinate_space"],
        features=features,
        metadata=jsonable(report),
        coverage="Connector evidence only; mating, mobility, retention and collision require review",
    )


def contacts(manifest, instances, library=None, shadow=None):
    """Ask pyldraw3 about a bounded selection, returning only useful evidence.

    A confirmed contact is geometric metadata agreement, not a rigid connection
    or proof of free motion. In particular axle/bearing roles require review.
    """
    from ldraw import Matrix, Model, Piece, Vector, inspect_model

    if len(instances) != len(set(instances)):
        raise ValueError("Duplicate contact selection")
    if not 2 <= len(instances) <= 100:
        raise ValueError("Select between 2 and 100 physical instance IDs")
    nodes = {n["id"]: n for n in manifest["nodes"] if n["kind"] == "part"}
    if set(instances) - set(nodes):
        raise ValueError("Contact selection contains a nonphysical or unknown instance")
    selected = [nodes[i] for i in instances]
    if any(n.get("embedded") for n in selected):
        raise ValueError(
            "Embedded DAT contacts are not supported; inspect authored source geometry separately"
        )
    parts = parts_library(library, shadow)
    model = Model(
        name="contact-selection.ldr",
        objects=[
            Piece.place(
                n["ref"],
                position=Vector(*[r[3] for r in n["world"][:3]]),
                matrix=Matrix([r[:3] for r in n["world"][:3]]),
            )
            for n in selected
        ],
    )
    inspection = inspect_model(model, parts)
    rows = []
    for c in inspection.connection_contacts():
        rows.append(
            dict(
                a=instances[c.first_occurrence.index],
                b=instances[c.second_occurrence.index],
                first=jsonable(c.first),
                second=jsonable(c.second),
                status=str(c.status),
                residual=jsonable(c.residual),
            )
        )
    return dict(
        instances=instances,
        complete=inspection.complete,
        contacts=rows,
        diagnostics=[d.to_dict() for d in inspection.diagnostics],
        coverage="pyldraw3 contacts for selected library parts only; no rigid grouping, collision proof or general mobility inference",
    )
