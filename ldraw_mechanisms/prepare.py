"""Prepare once: source identities, bounded evidence and optional GLB.

No Blender dependency. Discovery has explicit budgets and never invents rigid
bodies from scene parenting. Agent corrections live in the plan JSON; rerunning
prepare refuses to replace it. Diagnostic diagram export is an explicit command;
curated references are written separately after reviewing a working rig.
"""

from copy import deepcopy
import hashlib
from pathlib import Path
import re

from . import plan as contract, mechanisms
from .analysis import ROLES, contacts
from .geometry import coaxial, gear_meshes
from .source import Document, library_path


def connection(kind, a, b, evidence, measurements, key=""):
    token = f"{kind}:{a}:{b}:{key}"
    name = "c_" + hashlib.sha256(token.encode()).hexdigest()[:16]
    return name, dict(
        a=a,
        b=b,
        kind=kind,
        status="candidate",
        evidence=evidence,
        measurements=measurements,
    )


def discover(manifest, library=None, shadow=None, *, contact_limit=300):
    """Conservative evidence, then provisional groups of mechanical candidates.

    Union only mechanical seeds. Shared ordinary support parts stay visible in
    separate mechanisms instead of joining an entire model through its frame.
    This is a grouping hypothesis, never a rigid-body partition.
    """
    if not 2 <= contact_limit <= 2000:
        raise ValueError("contact_limit must be 2..2000")
    nodes = {n["id"]: n for n in manifest["nodes"] if n["kind"] == "part"}
    seeds = {
        i
        for i, n in nodes.items()
        if any(re.search(p, n["description"] or "", re.I) for p in ROLES.values())
    }
    connections = {}
    coverage = dict(
        grouping="Provisional connected mechanical candidates; agent may split/merge views",
        unclassified_parts=[],
        embedded_parts=[i for i, n in nodes.items() if n.get("embedded")],
        contact_limit=contact_limit,
        rigid_groups="not inferred",
        inputs_outputs="not inferred",
        mechanical_parts=sorted(seeds),
        warnings=[],
        surface_contacts="Not detected: cams, levers bearing on beams, friction and stops need geometric/visual review even when connector contacts are absent",
    )
    gears = gear_meshes(manifest)
    coverage["unsupported_gears"] = gears["unsupported"]
    coverage["gear_placements"] = gears["placements"]
    if gears["unsupported"]:
        coverage["warnings"].append(
            dict(
                code="unsupported_gears",
                message=f"{len(gears['unsupported'])} gear/rack/worm parts have no supported geometry profile; inspect them explicitly.",
            )
        )
    for mesh in gears["meshes"]:
        name, edge = connection(
            mesh["kind"], mesh["a"], mesh["b"], gears["coverage"], mesh
        )
        connections[name] = edge
        seeds.update((mesh["a"], mesh["b"]))
    ids = [i for i, n in nodes.items() if not n.get("embedded")]
    try:
        library_path(library)
    except ValueError:
        if library:
            raise
        coverage["contacts"] = "not run: no LDraw library configured"
        coverage["coaxial"] = coverage["contacts"]
    else:
        if 2 <= len(ids) <= contact_limit:
            report = contacts(
                manifest, ids, library, shadow, max_instances=contact_limit
            )
            coverage["contacts"] = dict(
                complete=report["complete"],
                tested_parts=len(ids),
                diagnostics=report["diagnostics"],
                summary=report["summary"],
                placements=report["placements"],
            )
            coverage["warnings"].extend(report["warnings"])
            for c in report["contacts"]:
                if not {c["a"], c["b"]} & seeds:
                    continue
                first, second = c["first"], c["second"]
                kind = (
                    "revolute"
                    if first["kind"] == second["kind"] == "hinge"
                    else "contact"
                )
                measured = dict(
                    first_kind=first["kind"],
                    second_kind=second["kind"],
                    first_feature=first["feature_id"],
                    second_feature=second["feature_id"],
                    position=first["position"],
                    axis=[r[1] for r in first["frame"]],
                    contact_status=c["status"],
                    residual=c["residual"],
                )
                name, edge = connection(
                    kind,
                    c["a"],
                    c["b"],
                    "pyldraw3 connector contact; mating metadata does not determine rigidity or free motion",
                    measured,
                    str((first["feature_id"], second["feature_id"])),
                )
                connections[name] = edge
        else:
            coverage["contacts"] = (
                f"not run: {len(ids)} library parts outside 2..{contact_limit}; select a section or adjust --contact-limit"
            )
        # Bounded shaft/gear line evidence supplements contacts at arbitrary roll.
        axial = [
            i
            for i in ids
            if re.search(
                r"(?:^=?Technic (?:Axle|Gear|Worm))|Engine Crankshaft",
                nodes[i]["description"],
                re.I,
            )
        ]
        coverage["coaxial_selection"] = (
            "Catalog axle, gear, worm and engine crankshaft parts; positive line evidence within 80 LDU axial separation"
        )
        if 2 <= len(axial) <= 100:
            report = coaxial(manifest, axial, library, shadow)
            coverage["coaxial"] = dict(
                tested_parts=len(axial),
                max_axial_separation_ldu=80,
                placements=report["placements"],
            )
            contact_pairs = {frozenset((e["a"], e["b"])) for e in connections.values()}
            for pair in report["pairs"]:
                if (
                    pair["status"] != "candidate"
                    or pair["evidence"]["axial_separation_ldu"] > 80
                ):
                    continue
                if frozenset((pair["a"], pair["b"])) in contact_pairs:
                    continue
                name, edge = connection(
                    "coaxial",
                    pair["a"],
                    pair["b"],
                    report["coverage"],
                    pair["evidence"],
                )
                connections[name] = edge
        else:
            coverage["coaxial"] = (
                f"not run: {len(axial)} shaft/gear candidates outside 2..100; select a section"
            )
    for name in ("contacts", "coaxial"):
        if isinstance(coverage[name], str):
            coverage["warnings"].append(
                dict(code=name + "_not_run", message=coverage[name])
            )
    # Stable components; isolated candidates remain visible as unanswered cases.
    parent = {i: i for i in seeds}

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for e in connections.values():
        if e["a"] in seeds and e["b"] in seeds:
            a, b = find(e["a"]), find(e["b"])
            parent[max(a, b)] = min(a, b)
    groups = {}
    for i in sorted(seeds):
        groups.setdefault(find(i), set()).add(i)
    views = {}
    for first, group in sorted(groups.items()):
        neighbours = {
            i
            for e in connections.values()
            if {e["a"], e["b"]} & group
            for i in (e["a"], e["b"])
        }
        key = "m_" + hashlib.sha256(first.encode()).hexdigest()[:12]
        views[key] = dict(
            label=nodes[first]["description"],
            parts=sorted(group | neighbours),
            bodies=[],
            inputs=[],
            outputs=[],
            notes=[
                "Provisional mechanism boundary. Review connections, identify input/output and assign moving groups."
            ],
        )
    assigned = {i for m in views.values() for i in m["parts"]}
    coverage["unclassified_parts"] = sorted(set(nodes) - assigned)
    coverage["isolated_mechanical_parts"] = sorted(
        seeds - {i for e in connections.values() for i in (e["a"], e["b"])}
    )
    # A model with no recognized candidates still gets a useful unresolved view.
    if not views and nodes:
        views["unresolved"] = dict(
            label="No mechanism identified",
            parts=sorted(nodes),
            bodies=[],
            inputs=[],
            outputs=[],
            notes=[
                "No supported mechanical evidence found. Absence of evidence does not imply a static model."
            ],
        )
    return dict(
        mechanisms=views,
        connections=dict(sorted(connections.items())),
        discovery=coverage,
    )


def adopt_motion(study, motion):
    """Attach studied motion to prepared identities without losing source evidence.

    This is explicit replacement of the motion fields, not automatic inference.
    Keep every study view, including manually named/deferred mechanisms. Add
    views for the new controls; a recipe must not silently discard unsolved work.
    """
    contract.validate(study)
    contract.validate(motion)
    if study["source"] != motion["source"]:
        raise ValueError(
            "Motion plan and prepared study must have the exact same source manifest"
        )
    result = deepcopy(motion)
    result["connections"] = deepcopy(study.get("connections", {}))
    result["discovery"] = deepcopy(study.get("discovery", {}))
    result["mechanisms"] = {}
    for name, view in study.get("mechanisms", {}).items():
        retained = deepcopy(view)
        retained["parts"] = sorted(mechanisms.members(study, name))
        # Old body/control names may no longer exist in the replacement motion.
        retained["bodies"] = []
        for field in ("inputs", "outputs"):
            retained[field] = [r for r in retained[field] if r.startswith("part:")]
        if retained.get("disposition") == "planned":
            retained["disposition"] = "unresolved"
            retained["notes"].append(
                "Motion replaced; recheck this view against the new control/body definitions."
            )
        result["mechanisms"][name] = retained
    for name, view in mechanisms.motion_views(result).items():
        if name in result["mechanisms"]:
            name = "motion_" + hashlib.sha256(name.encode()).hexdigest()[:16]
        while name in result["mechanisms"]:
            name = "motion_" + hashlib.sha256(name.encode()).hexdigest()[:16]
        result["mechanisms"][name] = view
    result["notes"] = list(dict.fromkeys([*study["notes"], *result["notes"]]))
    contract.validate(result)
    return result


def prepare(
    path,
    output,
    *,
    section=None,
    library=None,
    shadow=None,
    contact_limit=300,
    convert_glb=True,
    motion=None,
):
    out = Path(output).resolve()
    if out.exists() and any(out.iterdir()):
        raise ValueError(
            "Study directory is not empty; edit and validate its plan, or choose a new output directory"
        )
    manifest = Document(path).manifest(section)
    study = contract.draft(manifest)
    study.update(discover(manifest, library, shadow, contact_limit=contact_limit))
    if motion is not None:
        study = adopt_motion(study, motion)
    contract.validate(study, check_source=True)
    # Persist inspectable work BEFORE conversion, even if the converter fails.
    contract.save(out / "plan.json", study)
    report = dict(
        plan=str(out / "plan.json"),
        status=study["status"],
        glb=None,
        discovery=study["discovery"],
    )
    from .audit import audit

    report["audit"] = audit(study)
    contract.save(out / "preparation.json", report)
    if convert_glb:
        from .glb import convert

        report["glb"] = convert(study["source"], out / "model.glb", library)
        contract.save(out / "preparation.json", report)
    return report
