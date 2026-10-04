"""Portable mechanism views of a motion plan (standard library only).

One JSON document owns source identities, candidate connections and executable
motion. Mermaid is derived output. A mechanism is a view, not a rigid body:
parts may appear in several views, but body ownership stays unique in plan.py.
"""

from collections import Counter
import json
from pathlib import Path
import re

NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,39}$")
KINDS = {
    "contact",
    "coaxial",
    "gear_mesh",
    "worm_mesh",
    "surface_contact",
    "fixed",
    "revolute",
    "prismatic",
    "ball",
    "unknown",
}
STATES = {"candidate", "reviewed", "rejected"}
DISPOSITIONS = {"unresolved", "planned", "deferred", "static"}


def members(plan, mechanism):
    """Expand view membership from its explicit parts and canonical rigid bodies."""
    m = plan["mechanisms"][mechanism]
    return set(m["parts"]) | {
        i for b in m["bodies"] for i in plan["bodies"][b]["instances"]
    }


def validate(plan):
    if "mechanisms" not in plan and "connections" not in plan:
        return  # Version-1 plans made before this workflow remain valid.
    parts = {n["id"] for n in plan["source"]["nodes"] if n["kind"] == "part"}
    mechanisms, connections = plan.get("mechanisms"), plan.get("connections")
    if not isinstance(mechanisms, dict) or not isinstance(connections, dict):
        raise ValueError("mechanisms and connections must both be dictionaries")
    for name, edge in connections.items():
        if not NAME.fullmatch(name):
            raise ValueError(f"Invalid connection ID: {name}")
        if (
            edge.get("a") not in parts
            or edge.get("b") not in parts
            or edge["a"] == edge["b"]
        ):
            raise ValueError(
                f"Connection endpoints must be distinct physical IDs: {name}"
            )
        if edge.get("kind") not in KINDS or edge.get("status") not in STATES:
            raise ValueError(f"Invalid connection kind/status: {name}")
        if not isinstance(edge.get("evidence"), str) or not edge["evidence"].strip():
            raise ValueError(f"Connection needs evidence: {name}")
        if edge["status"] in {"reviewed", "rejected"} and (
            not isinstance(edge.get("review"), str) or not edge["review"].strip()
        ):
            raise ValueError(
                f"Reviewed/rejected connection needs a review note: {name}"
            )
    covered = set()
    for name, m in mechanisms.items():
        if (
            not NAME.fullmatch(name)
            or not isinstance(m.get("label"), str)
            or not m["label"].strip()
        ):
            raise ValueError(f"Invalid mechanism ID/label: {name}")
        for field in ("parts", "bodies", "inputs", "outputs", "notes"):
            if not isinstance(m.get(field), list) or any(
                not isinstance(x, str) for x in m[field]
            ):
                raise ValueError(f"Mechanism {name}.{field} must be a list of strings")
            if len(m[field]) != len(set(m[field])):
                raise ValueError(f"Duplicate mechanism {field}: {name}")
        if set(m["parts"]) - parts or set(m["bodies"]) - set(plan["bodies"]):
            raise ValueError(f"Unknown mechanism part/body: {name}")
        if not m["parts"] and not m["bodies"]:
            raise ValueError(f"Empty mechanism: {name}")
        disposition = m.get("disposition", "unresolved")
        if disposition not in DISPOSITIONS:
            raise ValueError(f"Invalid mechanism disposition: {name}")
        if disposition != "unresolved" and (
            not isinstance(m.get("review"), str) or not m["review"].strip()
        ):
            raise ValueError(f"Mechanism disposition needs a review note: {name}")
        if disposition == "planned" and not m["bodies"]:
            raise ValueError(f"Planned mechanism needs motion bodies: {name}")
        covered.update(m["bodies"])
        own = members(plan, name)
        for ref in m["inputs"] + m["outputs"]:
            prefix, _, key = ref.partition(":")
            allowed = {
                "part": own,
                "body": set(m["bodies"]),
                "control": set(plan["controls"]),
            }
            if prefix not in allowed or key not in allowed[prefix]:
                raise ValueError(f"Invalid mechanism input/output {ref}: {name}")
    if set(plan["bodies"]) - covered:
        raise ValueError(
            "Every planned body must appear in at least one mechanism view"
        )
    json.dumps(dict(mechanisms=mechanisms, connections=connections), allow_nan=False)


def control_dependencies(plan):
    """Resolve the same signal/body dependencies used by the evaluator."""
    from .plan import signal_order, body_order

    signals, bodies = {}, {}
    for name in signal_order(plan):
        refs = plan["signals"][name]["variables"].values()
        signals[name] = set().union(
            *(signals[r[7:]] if r.startswith("signal:") else {r[8:]} for r in refs)
        )
    for name in body_order(plan):
        b = plan["bodies"][name]
        bodies[name] = set(signals.get(b.get("signal"), set())) | bodies.get(
            b.get("parent"), set()
        )
    # Rods cannot parent/anchor bodies, so endpoint dependencies can be added last.
    for name, b in plan["bodies"].items():
        if b["kind"] == "rod":
            bodies[name] = (
                bodies[plan["anchors"][b["start"]]["body"]]
                | bodies[plan["anchors"][b["end"]]["body"]]
            )
    return bodies


def motion_views(plan):
    """Default views by user control; shared bodies keep one global identity.

    Agents can split/combine these views without changing motion or source IDs.
    Existing candidate evidence remains intact when a motion plan is adopted.
    """
    deps = control_dependencies(plan)
    views = {}
    for name, control in plan["controls"].items():
        bodies = [b for b in plan["bodies"] if name in deps[b]]
        if bodies:
            views[name] = dict(
                label=control["description"],
                parts=[],
                bodies=bodies,
                inputs=["control:" + name],
                outputs=["body:" + b for b in bodies],
                notes=[
                    "View grouped by control dependencies; shared bodies are the same mechanism instances."
                ],
                disposition="planned",
                review="Grouped from declared control dependencies; this records planned motion, not physical verification.",
            )
    uncovered = set(plan["bodies"]) - {b for m in views.values() for b in m["bodies"]}
    if uncovered:
        key = "uncontrolled"
        while key in views:
            key += "_"
        views[key] = dict(
            label="Bodies without a control",
            parts=[],
            bodies=sorted(uncovered),
            inputs=[],
            outputs=[],
            notes=[],
        )
    return views


def _id(ref):
    # Exact encoding: safe Mermaid IDs, stable between files, no name collisions.
    return "N" + ref.encode().hex()


def _text(value):
    # Mermaid numeric entities quote source text without enabling HTML/directives.
    return "".join(
        c if c.isalnum() or c in " .,:/_+-()" else f"#{ord(c)};"
        for c in str(value).replace("\n", " ")
    )


def diagram(plan, mechanism, view="auto"):
    """Emit a graph: dashed candidates, solid reviewed evidence/declared motion."""
    validate(plan)
    if view not in {"auto", "connections", "motion"}:
        raise ValueError("Diagram view must be auto, connections or motion")
    m = plan["mechanisms"][mechanism]
    motion = view == "motion" or (view == "auto" and bool(m["bodies"]))
    parts = {n["id"]: n for n in plan["source"]["nodes"] if n["kind"] == "part"}
    own = members(plan, mechanism)
    owner = {i: b for b, body in plan["bodies"].items() for i in body["instances"]}
    nodes, edges = {}, []

    def node(ref, label, style="part"):
        nodes[ref] = (label, style)
        return ref

    def part(i):
        if motion and i in owner:
            return body(owner[i])
        n = parts[i]
        return node(
            "part:" + i,
            f"{i}: {n['ref']} - {n['description']}",
            "part" if i in own else "boundary",
        )

    def body(name):
        b = plan["bodies"][name]
        return node(
            "body:" + name,
            f"{name} ({len(b['instances'])} parts)",
            "body" if name in m["bodies"] else "boundary",
        )

    def link(a, b, label, candidate=False):
        if a != b:
            edges.append((a, b, label, candidate))

    if motion:
        for name in m["bodies"]:
            b = plan["bodies"][name]
            dst = body(name)
            if b["kind"] == "rod":
                for endpoint in ("start", "end"):
                    anchor = plan["anchors"][b[endpoint]]
                    link(body(anchor["body"]), dst, "anchor " + b[endpoint])
            else:
                support = (
                    body(b["parent"])
                    if b.get("parent")
                    else node("support", "Model frame / virtual support", "boundary")
                )
                axis = ",".join(f"{x:.4g}" for x in b["axis"])
                link(support, dst, f"{b['kind']} axis ({axis})")
        for i in m["parts"]:
            part(i)
    else:
        for i in sorted(own):
            part(i)
    for name, edge in sorted(plan["connections"].items()):
        if edge["status"] == "rejected" or not ({edge["a"], edge["b"]} & own):
            continue
        # The motion view collapses internal evidence and shows only couplings
        # between planned bodies. The connections view preserves every part edge.
        if (
            motion
            and edge["status"] != "reviewed"
            and (edge["a"] not in owner or edge["b"] not in owner)
        ):
            continue
        if (
            motion
            and edge["a"] in owner
            and edge["b"] in owner
            and owner[edge["a"]] == owner[edge["b"]]
        ):
            continue
        label = f"{edge['kind']} ({edge['status']})"
        if edge["kind"] == "gear_mesh" and not motion:
            ratio = edge.get("measurements", {}).get("b_per_a")
            if ratio is not None:
                label += f" b/a={ratio:.5g} (source gear axes)"
        if edge["kind"] == "worm_mesh" and not motion:
            ratio = edge.get("measurements", {}).get("wheel_per_worm_magnitude")
            if ratio is not None:
                label += f" abs(wheel/worm)={ratio:.5g}; direction unreviewed"
        link(part(edge["a"]), part(edge["b"]), label, edge["status"] == "candidate")
    for ref in m["inputs"]:
        prefix, _, key = ref.partition(":")
        if prefix == "control":
            c = plan["controls"][key]
            node(
                ref, f"INPUT {key}: {c['min']:.4g}..{c['max']:.4g} {c['unit']}", "input"
            )
            if motion:
                for b, deps in control_dependencies(plan).items():
                    if b in m["bodies"] and key in deps:
                        link(ref, body(b), "drives")
        else:
            target = part(key) if prefix == "part" else body(key)
            label, _ = nodes[target]
            nodes[target] = ("INPUT " + label, "input")
    for ref in m["outputs"]:
        prefix, _, key = ref.partition(":")
        if prefix == "control":
            continue
        target = part(key) if prefix == "part" else body(key)
        label, style = nodes[target]
        nodes[target] = ("OUTPUT " + label, style)
    if not m["inputs"]:
        node("unknown_input", "Input not yet identified", "unknown")
    if not m["outputs"]:
        node("unknown_output", "Output not yet identified", "unknown")
    lines = [
        "flowchart LR",
        "  %% Generated from plan.json; edit JSON, then regenerate.",
        "  %% Candidate edges are geometric evidence, not proven joints.",
    ]
    lines += [
        f'  {_id(ref)}["{_text(label)}"]:::{style}'
        for ref, (label, style) in sorted(nodes.items())
    ]
    for a, b, label, candidate in sorted(set(edges)):
        op = "-.->" if candidate else "-->" if a.startswith("control:") else "---"
        lines.append(f'  {_id(a)} {op}|"{_text(label)}"| {_id(b)}')
    lines += [
        "  classDef part fill:#eef2ff,stroke:#475569",
        "  classDef body fill:#dcfce7,stroke:#166534",
        "  classDef boundary fill:#f1f5f9,stroke:#64748b,stroke-dasharray:5 5",
        "  classDef input fill:#dbeafe,stroke:#1d4ed8",
        "  classDef unknown fill:#fef3c7,stroke:#92400e",
    ]
    return "\n".join(lines) + "\n"


def write_diagrams(plan, directory, *, view="auto", mechanism=None):
    """Write reproducible .mmd files and an index with shared-part interfaces.

    Only files listed in our previous index are replaced/removed. A plan digest
    lets agents detect diagrams made from an older edit without timestamps.
    """
    from .plan import digest, validate as validate_plan

    validate_plan(plan)
    if "mechanisms" not in plan:
        raise ValueError(
            "Plan has no mechanism views; use prepare --plan to attach them"
        )
    names = [mechanism] if mechanism else sorted(plan.get("mechanisms", {}))
    if mechanism and mechanism not in plan["mechanisms"]:
        raise ValueError(f"Unknown mechanism {mechanism}")
    rendered = {name + ".mmd": diagram(plan, name, view) for name in names}
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    index_path = directory / "index.json"
    old = json.loads(index_path.read_text()) if index_path.exists() else {}
    for filename in old.get("files", []):
        if (
            re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,39}\.mmd", filename)
            and filename not in rendered
        ):
            (directory / filename).unlink(missing_ok=True)
    for filename, text in rendered.items():
        (directory / filename).write_text(text)
    membership = {name: members(plan, name) for name in names}
    shared = {
        i: [name for name in names if i in membership[name]]
        for i, count in Counter(
            i for group in membership.values() for i in group
        ).items()
        if count > 1
    }
    result = dict(
        plan_digest=digest(plan),
        view=view,
        files=sorted(rendered),
        shared_parts=shared,
        mechanisms=len(names),
        coverage=plan.get("discovery", {}),
    )
    from .audit import audit

    result["audit"] = audit(plan)
    index_path.write_text(json.dumps(result, indent=2) + "\n")
    lines = [
        "# Mechanisms",
        "",
        f"Plan digest: `{result['plan_digest']}`",
        "",
        "Dashed edges show candidates. Solid edges show reviewed evidence or declared motion; neither establishes physical feasibility.",
        "",
        "Grey nodes are external parts/bodies or the model frame. Shared identities refer to the same part across diagrams.",
        "",
    ]
    coverage = plan.get("discovery", {})
    lines += [
        "Discovery coverage (details in index.json):",
        "",
        f"- Unclassified parts: {len(coverage.get('unclassified_parts', []))}.",
        f"- Mechanism dispositions: `{result['audit']['summary']}`.",
        "- Source contacts and normalization details: see index.json; successful execution is not complete discovery.",
        "- Surface-bearing levers/cams and friction are not discovered from connector metadata.",
        "",
    ]
    contact_summary = coverage.get("contacts", {})
    if isinstance(contact_summary, dict) and "summary" in contact_summary:
        summary = contact_summary["summary"]
        axles = summary["axles"]
        lines += [
            f"Contacts: {summary['contacts']} across {summary['tested_parts']} parts; axles with axle-hole evidence: {axles['with_axle_hole_contact']}/{axles['total']}.",
            "",
        ]
    lines += ["- " + _text(w["message"]) for w in result["audit"]["warnings"]] + [""]
    for name in names:
        m = plan["mechanisms"][name]
        lines += [
            f"## {name}",
            "",
            _text(m["label"]),
            "",
            "Disposition: "
            + m.get("disposition", "unresolved")
            + ". "
            + _text(m.get("review", "Review input, output and missing couplings.")),
            "",
            "```mermaid",
            rendered[name + ".mmd"].rstrip(),
            "```",
            "",
            "Parts: " + ", ".join(f"`{i}`" for i in sorted(membership[name])),
            "",
        ]
        for b in m["bodies"]:
            spec = plan["bodies"][b]
            lines += [
                f"- Body `{b}`: parts {', '.join(spec['instances'])}; origin `{spec['origin']}`; axis `{spec['axis']}`; signal `{spec.get('signal', 'anchors/fixed')}`."
            ]
        if m["bodies"]:
            lines.append("")
        lines += ["- " + _text(note) for note in m["notes"]] + [""]
    (directory / "README.md").write_text("\n".join(lines))
    return dict(directory=str(directory.resolve()), **result)


def add_joint(
    plan,
    *,
    mechanism,
    name,
    instances,
    origin,
    axis,
    minimum,
    maximum,
    kind="revolute",
    default=0.0,
    description=None,
    parent=None,
):
    """Return a plan with one independently controlled measured joint.

    This small authoring helper writes the existing executable contract directly.
    It does not promote contact candidates, choose moving parts or mark a draft
    ready. Adding coupled gears/rods still uses signals/anchors in that contract.
    """
    from copy import deepcopy
    from .plan import validate as validate_plan

    validate_plan(plan)
    if kind not in {"revolute", "prismatic"}:
        raise ValueError("add_joint supports revolute and prismatic joints")
    if mechanism not in plan.get("mechanisms", {}):
        raise ValueError(f"Unknown mechanism {mechanism}")
    if any(name in plan[group] for group in ("controls", "signals", "bodies")):
        raise ValueError(f"Joint name already in use: {name}")
    result = deepcopy(plan)
    result["status"] = "draft"
    result["controls"][name] = dict(
        min=minimum,
        max=maximum,
        default=default,
        unit="radian" if kind == "revolute" else "ldu",
        description=description or name,
    )
    result["signals"][name] = dict(expression="v", variables={"v": "control:" + name})
    result["bodies"][name] = dict(
        instances=list(instances),
        kind=kind,
        origin=list(origin),
        axis=list(axis),
        signal=name,
    )
    if parent:
        result["bodies"][name]["parent"] = parent
    m = result["mechanisms"][mechanism]
    m["bodies"].append(name)
    m["inputs"].append("control:" + name)
    m["outputs"].append("body:" + name)
    validate_plan(result)
    return result
