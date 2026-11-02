"""Small source-only review report: planned motion is not complete discovery."""

from collections import Counter, defaultdict
import math

from . import mechanisms, plan as contract
from .math3d import dot, length, mul, sub, unit

COAXIAL_DEGREES, COAXIAL_LDU = 3.0, 2.0
STATIC = "static"


def _on_axis(position, axis, origin, joint_axis):
    a, j = unit(axis), unit(joint_axis)
    if abs(dot(a, j)) < math.cos(math.radians(COAXIAL_DEGREES)):
        return False
    d = sub(position, origin)
    return length(sub(d, mul(j, dot(d, j)))) <= COAXIAL_LDU


def boundary(bodies, connections, declared=()):
    """Pin/axle contacts that body membership would tear apart.

    Parts in different bodies may share a pin or axle only on the joint between
    them: coaxial with a revolute axis or along a slide. A keyed axle off that
    axis, or a static part bridging several joints, means a part sits in the
    wrong body. Contacts between moving bodies across several joints are
    linkages (info): declare their checks. `declared` holds instance sets of
    explicit checks; a pair inside one is resolved. Only connector contacts
    are seen: embedded parts, surface contacts and stops are not.
    """
    owner = {i: name for name, b in bodies.items() for i in b["instances"]}

    def chain(name):
        """Joints between a part and the static frame; fixed bodies add none."""
        out = []
        while name:
            if bodies[name]["kind"] != "fixed":
                out.append(name)
            name = bodies[name].get("parent")
        return out

    flagged, info, checked = defaultdict(set), defaultdict(set), 0
    for c in connections.values():
        m = c.get("measurements") or {}
        if c.get("kind") != "contact" or "axis" not in m:
            continue
        a, b = c["a"], c["b"]
        oa, ob = owner.get(a), owner.get(b)
        ca, cb = chain(oa), chain(ob)
        path = [x for x in ca if x not in cb] + [x for x in cb if x not in ca]
        if not path or any(a in s and b in s for s in declared):
            continue
        checked += 1
        kinds = tuple(sorted((m["first_kind"], m["second_kind"])))
        joint = bodies[path[0]] if len(path) == 1 else None
        if kinds not in (("pin", "pin_hole"), ("axle", "axle_hole")):
            reason, out = f"{kinds[0]}/{kinds[1]} contact across a body boundary", info
        elif len(path) > 1:
            reason = f"bridges {len(path)} joints"
            out = info if ca and cb else flagged
        elif joint["kind"] == "revolute":
            on = _on_axis(m["position"], m["axis"], joint["origin"], joint["axis"])
            keyed = kinds == ("axle", "axle_hole")
            if on and not keyed:
                continue
            reason = (
                ("keyed axle on the joint axis" if on else "keyed off the joint axis")
                if keyed
                else "pin off the joint axis"
            )
            out = info if on else flagged
        elif joint["kind"] == "prismatic":
            if abs(dot(unit(m["axis"]), unit(joint["axis"]))) >= math.cos(
                math.radians(COAXIAL_DEGREES)
            ):
                continue
            reason, out = "crosses the slide", flagged
        else:
            reason, out = f"{joint['kind']} body boundary", info
        out[(reason, *sorted((oa or STATIC, ob or STATIC)))].add(tuple(sorted((a, b))))

    def groups(found):
        return [
            dict(reason=reason, bodies=[x, y], pairs=[list(p) for p in sorted(pairs)])
            for (reason, x, y), pairs in sorted(found.items())
        ]

    return dict(checked_contacts=checked, flagged=groups(flagged), info=groups(info))


def audit(plan):
    contract.validate(plan)
    discovery = plan.get("discovery", {})
    warnings = list(discovery.get("warnings", []))
    if "contacts" not in discovery:
        warnings.append(
            dict(
                code="missing_contact_coverage",
                message="No contact discovery coverage recorded. Run prepare before treating this plan as a mechanism inventory.",
            )
        )
    elif (
        isinstance(discovery["contacts"], dict)
        and "summary" not in discovery["contacts"]
    ):
        warnings.append(
            dict(
                code="legacy_contact_coverage",
                message="This study predates axle coverage diagnostics. Re-run prepare in a new directory and compare findings.",
            )
        )
    deps = mechanisms.control_dependencies(plan)
    owner = {i: b for b, body in plan["bodies"].items() for i in body["instances"]}
    findings, covered = [], set()
    for name, view in sorted(plan.get("mechanisms", {}).items()):
        parts = mechanisms.members(plan, name)
        covered.update(parts)
        driven = {i for i in parts if i in owner and deps[owner[i]]}
        disposition = view.get("disposition", "unresolved")
        if disposition == "planned" and not any(deps[b] for b in view["bodies"]):
            warnings.append(
                dict(
                    code="planned_without_control",
                    mechanism=name,
                    message=f"{name} is marked planned but has no controlled body.",
                )
            )
        findings.append(
            dict(
                id=name,
                label=view["label"],
                disposition=disposition,
                review=view.get("review", ""),
                parts=len(parts),
                controlled_parts=sorted(driven),
                parts_without_control=sorted(parts - driven),
                controls=sorted({c for i in driven for c in deps[owner[i]]}),
            )
        )
    missing = sorted(set(discovery.get("mechanical_parts", [])) - covered)
    if missing:
        warnings.append(
            dict(
                code="unaccounted_mechanical_parts",
                message=f"{len(missing)} discovered mechanical parts no longer appear in any mechanism view.",
            )
        )
    pending = [f["id"] for f in findings if f["disposition"] == "unresolved"]
    deferred = [f["id"] for f in findings if f["disposition"] == "deferred"]
    from .constraints import coverage

    constrained = coverage(plan)
    if constrained["unchecked_bodies"]:
        warnings.append(
            dict(
                code="unchecked_motion",
                message="Controlled bodies lack cross-body mechanical checks: "
                + ", ".join(constrained["unchecked_bodies"]),
            )
        )
    from .constraints import KINDS, instances

    edges = boundary(
        plan["bodies"],
        plan.get("connections", {}),
        [instances(c) for c in plan["checks"] if c["kind"] in KINDS],
    )
    for group in edges["flagged"]:
        pairs = ", ".join("↔".join(p) for p in group["pairs"][:8])
        warnings.append(
            dict(
                code="body_boundary",
                bodies=group["bodies"],
                pairs=group["pairs"],
                message=f"{' / '.join(group['bodies'])}: {group['reason']} ({pairs}). "
                "A part is probably in the wrong body: fix membership, or declare a "
                "check covering both parts if this joint is real.",
            )
        )
    return dict(
        constraints=constrained,
        boundary=edges,
        summary=dict(Counter(f["disposition"] for f in findings)),
        review_complete=bool(findings)
        and not pending
        and not missing
        and not any(
            w["code"] in ("planned_without_control", "body_boundary") for w in warnings
        ),
        unresolved=pending,
        deferred=deferred,
        unaccounted_mechanical_parts=missing,
        mechanisms=findings,
        warnings=warnings,
        coverage="Bookkeeping of declared scope only. Supports may correctly lack controls. Planned, static and deferred dispositions require review notes; none certify discovery completeness, physical motion or clearance. Body boundaries are checked against connector contacts only; embedded parts, surface contacts and stops are not seen.",
    )
