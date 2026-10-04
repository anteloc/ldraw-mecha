"""Small source-only review report: planned motion is not complete discovery."""

from collections import Counter

from . import mechanisms, plan as contract


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
    return dict(
        summary=dict(Counter(f["disposition"] for f in findings)),
        review_complete=bool(findings)
        and not pending
        and not missing
        and not any(w["code"] == "planned_without_control" for w in warnings),
        unresolved=pending,
        deferred=deferred,
        unaccounted_mechanical_parts=missing,
        mechanisms=findings,
        warnings=warnings,
        coverage="Bookkeeping of declared scope only. Supports may correctly lack controls. Planned, static and deferred dispositions require review notes; none certify discovery completeness, physical motion or clearance.",
    )
