"""Executable mechanical invariants measured from occurrence transforms.

Connections are discovery evidence. These checks are separate, explicit claims
about motion. They do not read the signal that drives a part to decide whether
that same part is correct. Source placements and unowned (fixed) parts matter.
"""

from __future__ import annotations

import math

from .math3d import (
    cross,
    direction,
    dot,
    frame,
    identity,
    inverse,
    length,
    matmul,
    point,
    sub,
    unit,
)

KINDS = {"rigid", "coaxial", "rotation"}


def _finite(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def _vector(v):
    return isinstance(v, (list, tuple)) and len(v) == 3 and all(_finite(x) for x in v)


def instances(check):
    if check["kind"] == "rigid":
        return {check["a"], check["b"]}
    if check["kind"] == "coaxial":
        return {check[k]["instance"] for k in ("a", "b")}
    if check["kind"] == "rotation":
        return {t["instance"] for t in check["terms"]} | (
            {check["carrier"]} if check.get("carrier") else set()
        )
    return set()


def validate(check, nodes):
    kind = check["kind"]
    if kind not in KINDS:
        raise ValueError(f"Unsupported check kind: {kind}")
    ids = instances(check)
    if any(i not in nodes or nodes[i]["kind"] != "part" for i in ids):
        raise ValueError("Mechanical checks require physical occurrence IDs")
    if len(ids) < 2:
        raise ValueError("Mechanical check needs distinct occurrences")
    keys = {
        "rigid": ("tolerance_ldu", "tolerance_degrees"),
        "coaxial": ("tolerance_ldu", "tolerance_degrees"),
        "rotation": ("tolerance_radians", "axis_tolerance_degrees"),
    }[kind]
    for key in keys:
        if not _finite(check.get(key)) or check[key] <= 0:
            raise ValueError(f"Mechanical check needs positive finite {key}")
    if kind == "coaxial":
        for key in ("a", "b"):
            f = check[key]
            if not _vector(f.get("point")) or not _vector(f.get("axis")):
                raise ValueError("Coaxial check needs part-local point and axis")
            unit(f["axis"])
            if "span" in f and (
                len(f["span"]) != 2
                or not all(_finite(x) for x in f["span"])
                or f["span"][0] >= f["span"][1]
            ):
                raise ValueError("Invalid finite shaft span")
        if check["a"]["instance"] == check["b"]["instance"]:
            raise ValueError("Coaxial check needs distinct occurrences")
        if "axial_tolerance_ldu" in check and (
            not _finite(check["axial_tolerance_ldu"])
            or check["axial_tolerance_ldu"] <= 0
        ):
            raise ValueError("Invalid axial displacement tolerance")
        if "min_overlap_ldu" in check and (
            not _finite(check["min_overlap_ldu"])
            or check["min_overlap_ldu"] <= 0
            or any("span" not in check[k] for k in ("a", "b"))
        ):
            raise ValueError(
                "Minimum overlap needs two finite spans and a positive length"
            )
    if kind == "rotation":
        terms = check["terms"]
        if len(terms) < 2 or len({t["instance"] for t in terms}) != len(terms):
            raise ValueError("Rotation relation needs distinct terms")
        for t in terms:
            if not _vector(t.get("axis")):
                raise ValueError("Rotation terms need global rest-frame directed axes")
            unit(t["axis"])
            if (
                not isinstance(t.get("coefficient"), int)
                or isinstance(t["coefficient"], bool)
                or t["coefficient"] == 0
            ):
                raise ValueError(
                    "Rotation coefficients must be nonzero integers (e.g. tooth counts)"
                )
            if t["instance"] == check.get("carrier"):
                raise ValueError(
                    "Use carrier-relative terms; carrier cannot also be a term"
                )


def _angle(a, b, *, unoriented=False):
    a, b = unit(a), unit(b)
    cosine = dot(a, b)
    return math.degrees(
        math.atan2(length(cross(a, b)), abs(cosine) if unoriented else cosine)
    )


def evaluate(check, nodes, deltas):
    """`deltas` maps physical IDs to global displacement from source pose."""
    kind = check["kind"]
    result = dict(name=check.get("name", kind), kind=kind)

    def delta(i):
        return deltas.get(i, identity())

    def world(i):
        return matmul(delta(i), nodes[i]["world"])

    if kind == "rigid":
        # Compare both motions at the same source frame. This preserves the
        # original imperfect fit instead of silently snapping the source.
        a, b = check["a"], check["b"]
        at = point(nodes[b]["world"], [0, 0, 0])
        translation = length(sub(point(delta(a), at), point(delta(b), at)))
        angles = [
            _angle(direction(delta(a), axis), direction(delta(b), axis))
            for axis in ([1, 0, 0], [0, 1, 0], [0, 0, 1])
        ]
        result.update(
            displacement_ldu=translation,
            rotation_degrees=max(angles),
            error=max(
                translation / check["tolerance_ldu"],
                max(angles) / check["tolerance_degrees"],
            ),
        )
    elif kind == "coaxial":
        a, b = check["a"], check["b"]

        def shaft(f, moved):
            w = world(f["instance"]) if moved else nodes[f["instance"]]["world"]
            return point(w, f["point"]), unit(direction(w, f["axis"]))

        ap, aa = shaft(a, True)
        bp, ba = shaft(b, True)
        d = sub(bp, ap)
        radial = max(length(cross(d, aa)), length(cross(d, ba)))
        angle = _angle(aa, ba, unoriented=True)
        ratios = [radial / check["tolerance_ldu"], angle / check["tolerance_degrees"]]
        result.update(radial_ldu=radial, angle_degrees=angle)
        if "axial_tolerance_ldu" in check:
            ar, ax = shaft(a, False)
            br, _ = shaft(b, False)
            drift = abs(dot(d, aa) - dot(sub(br, ar), ax))
            result["axial_drift_ldu"] = drift
            ratios.append(drift / check["axial_tolerance_ldu"])
        if "min_overlap_ldu" in check:
            ai = a["span"]
            bi = sorted(dot(d, aa) + x * dot(ba, aa) for x in b["span"])
            overlap = max(0.0, min(ai[1], bi[1]) - max(ai[0], bi[0]))
            result["overlap_ldu"] = overlap
            ratios.append(check["min_overlap_ldu"] / overlap if overlap else math.inf)
        result["error"] = max(ratios)
    elif kind == "rotation":
        carrier = (
            inverse(delta(check["carrier"])) if check.get("carrier") else identity()
        )
        angles, axis_errors = [], []
        for term in check["terms"]:
            relative = matmul(carrier, delta(term["instance"]))
            axis = unit(term["axis"])
            f = frame([0, 0, 0], axis)
            x = [row[0] for row in f[:3]]
            moved = direction(relative, x)
            angles.append(math.atan2(dot(axis, cross(x, moved)), dot(x, moved)))
            axis_errors.append(_angle(axis, direction(relative, axis)))
        phase = sum(t["coefficient"] * a for t, a in zip(check["terms"], angles))
        error = abs(math.atan2(math.sin(phase), math.cos(phase)))
        result.update(
            angles_radians=angles,
            phase_error_radians=error,
            axis_error_degrees=max(axis_errors),
            error=max(
                error / check["tolerance_radians"],
                max(axis_errors) / check["axis_tolerance_degrees"],
            ),
        )
    # Normalized errors combine different units without pretending degrees are
    # LDU. Keep reports valid JSON even for completely separated finite shafts.
    if not math.isfinite(result["error"]):
        result.update(error=1e300, failed_reason="No finite shaft overlap")
    result["passed"] = result["error"] <= 1
    return result


def coverage(plan):
    """Conservative body coverage; checks internal to one body prove nothing."""
    from .mechanisms import control_dependencies

    owner = {i: name for name, b in plan["bodies"].items() for i in b["instances"]}
    driven = {b for b, deps in control_dependencies(plan).items() if deps}
    covered = set()
    for c in plan["checks"]:
        if c["kind"] in KINDS:
            bodies = {owner.get(i) for i in instances(c)}
        elif c["kind"] == "distance":
            bodies = {plan["anchors"][c[k]]["body"] for k in ("a", "b")}
        else:
            continue
        if len(bodies) > 1:
            covered.update(bodies - {None})
            if c["kind"] == "distance":
                covered.update(
                    name
                    for name, body in plan["bodies"].items()
                    if body["kind"] == "rod"
                    and {body["start"], body["end"]} == {c["a"], c["b"]}
                )
    return dict(
        complete=bool(driven) and not (driven - covered),
        controlled_bodies=sorted(driven),
        checked_bodies=sorted(driven & covered),
        unchecked_bodies=sorted(driven - covered),
        note="Cross-body check participation only; does not establish sufficient constraints, engagement, collision clearance or dynamics.",
    )
