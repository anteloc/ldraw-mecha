"""Conservative discovery: evidence and candidates, never guessed connectivity."""

import re
from collections import Counter

from .source import Document, jsonable, parts_library
from .math3d import direction, point
from .placements import analysis_placement, placement_report

ROLES = {
    "hinge": r"hinge|door|window.*(?:pane|glass)|hatch",
    "gear": r"gear|worm",
    "rack": r"\brack\b",
    "axle": r"axle|shaft",
    "wheel": r"wheel|tyre",
    "piston": r"piston|cylinder|conrod|connecting rod|crank",
    "joint": r"joint|towball|ball socket|universal",
    "motor": r"motor",
    "turntable": r"turntable",
    "spring": r"spring|shock absorber",
    "cam": r"\bcam\b|\beccentric\b",
    "clutch": r"clutch|driving ring|changeover|wave selector|ratchet|one way",
    "differential": r"differential",
    "flexible_drive": r"\bchain\b|\bsprocket\b|\bbelt\b|\bpulley\b|\btread\b|\bwinch\b",
    "pneumatic": r"pneumatic|\bvalve\b|air tank|\bpump\b",
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


def connectors(
    manifest, occurrence, library=None, shadow=None, *, parts=None, normalize=True
):
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
    world, placement = analysis_placement(n, normalize=normalize)
    features = []
    for f in report.features:
        item = jsonable(f)
        item["world_position"] = point(world, jsonable(f.position))
        # LDCad connector axes are local Y; keep the original complete frame too.
        item["world_axis"] = direction(world, [row[1] for row in f.frame.rows])
        features.append(item)
    return dict(
        id=occurrence,
        ref=n["ref"],
        coordinate_space=manifest["coordinate_space"],
        features=features,
        metadata=jsonable(report),
        placement=placement,
        coverage="Connector evidence only; mating, mobility, retention and collision require review",
    )


def contacts(
    manifest, instances, library=None, shadow=None, *, max_instances=100, normalize=True
):
    """Ask pyldraw3 about a bounded selection, returning only useful evidence.

    A confirmed contact is geometric metadata agreement, not a rigid connection
    or proof of free motion. In particular axle/bearing roles require review.
    """
    from ldraw import Matrix, Model, Piece, Vector, inspect_model

    if len(instances) != len(set(instances)):
        raise ValueError("Duplicate contact selection")
    if not 2 <= max_instances <= 2000 or not 2 <= len(instances) <= max_instances:
        raise ValueError(
            f"Select between 2 and {max_instances} physical instance IDs (maximum budget 2000)"
        )
    nodes = {n["id"]: n for n in manifest["nodes"] if n["kind"] == "part"}
    if set(instances) - set(nodes):
        raise ValueError("Contact selection contains a nonphysical or unknown instance")
    selected = [nodes[i] for i in instances]
    if any(n.get("embedded") for n in selected):
        raise ValueError(
            "Embedded DAT contacts are not supported; inspect authored source geometry separately"
        )
    parts = parts_library(library, shadow)
    placements = [analysis_placement(n, normalize=normalize) for n in selected]
    model = Model(
        name="contact-selection.ldr",
        objects=[
            Piece.place(
                n["ref"],
                position=Vector(*[r[3] for r in world[:3]]),
                matrix=Matrix([r[:3] for r in world[:3]]),
            )
            for n, (world, _) in zip(selected, placements)
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
    # Count actual axle pieces, not all descriptions containing "axle hole".
    axles = {
        n["id"]
        for n in selected
        if re.search(r"^=?Technic Axle\s+\d", n.get("description", ""), re.I)
    }
    axle_contacts = [
        c
        for c in rows
        if {c["first"]["kind"], c["second"]["kind"]} == {"axle", "axle_hole"}
    ]
    connected = {i for c in axle_contacts for i in (c["a"], c["b"])} & axles
    transforms = placement_report([r for _, r in placements])
    warnings = []
    for status, message in (
        (
            "normalized",
            "Rounded near-rigid placements normalized for analysis only; inspect placement diagnostics.",
        ),
        (
            "raw_near_rigid",
            "Raw rounded placements can silently suppress pyldraw3 axle contacts; compare with normalization enabled.",
        ),
        (
            "unsupported",
            "Substantial scale/shear left unchanged; connector results for these placements may be incomplete.",
        ),
    ):
        if transforms["counts"].get(status):
            warnings.append(dict(code="placement_" + status, message=message))
    if axles and not connected:
        warnings.append(
            dict(
                code="zero_axle_contacts",
                message=f"No axle-in-hole contacts for {len(axles)} selected axle parts. Investigate transforms, metadata and selection before planning motion.",
            )
        )
    elif len(axles) >= 4 and len(connected) / len(axles) < 0.5:
        warnings.append(
            dict(
                code="low_axle_coverage",
                message="Fewer than half of selected axles have axle-in-hole evidence. This is a review heuristic, not a failed physical test.",
            )
        )
    if not inspection.complete:
        warnings.append(
            dict(
                code="incomplete_inspection",
                message="pyldraw3 inspection is incomplete; inspect its diagnostics.",
            )
        )
    if not rows:
        warnings.append(
            dict(
                code="zero_contacts",
                message="No contacts in this selection. Absence of connector evidence does not establish disconnection or free motion.",
            )
        )
    return dict(
        instances=instances,
        complete=inspection.complete,
        contacts=rows,
        diagnostics=[d.to_dict() for d in inspection.diagnostics],
        placements=transforms,
        warnings=warnings,
        summary=dict(
            tested_parts=len(instances),
            contacts=len(rows),
            contacted_parts=len({i for c in rows for i in (c["a"], c["b"])}),
            by_kind=dict(
                Counter(
                    "/".join(sorted((c["first"]["kind"], c["second"]["kind"])))
                    for c in rows
                )
            ),
            axles=dict(
                selection="Catalog descriptions beginning Technic Axle followed by a numeric length; excludes axle pins, joiners and axle-hole supports",
                total=len(axles),
                with_axle_hole_contact=len(connected),
                without_axle_hole_contact=sorted(axles - connected),
            ),
        ),
        coverage="pyldraw3 contacts for selected library parts only; no rigid grouping, collision proof or general mobility inference",
    )
