"""Measured candidates supplement connector contacts; they never prove coupling.

Reviewed parallel-axis gear profiles: LDraw part origins are tooth midplanes,
local Z is the shaft axis. Nominal pitch diameter is 2.5 LDU/tooth (module 1).
Do not apply this rule to bevel-only, crown, worm, rack or unreviewed gears.
"""

from itertools import combinations
import math
import re

from .analysis import connectors
from .math3d import cross, direction, dot, length, point, sub, unit
from .source import normalized, parts_library

# Confirmed using parts/{ref}.dat and its aliases/subparts. Small on purpose:
# extend only after reviewing origin, tooth plane, axis and nominal pitch.
GEARS = {
    "3647.dat": 8,
    "10928.dat": 8,
    "4019.dat": 16,
    "94925.dat": 16,
    "24505.dat": 24,
    "3648.dat": 24,
    "3648b.dat": 24,
    "32270.dat": 12,
    "18575.dat": 20,
    "32269.dat": 20,
    "32498.dat": 36,
    "3649.dat": 40,
}
ROTATIONAL = {"axle", "axle_hole", "pin", "pin_hole"}


def _tolerances(distance, angle):
    if (
        not math.isfinite(distance)
        or not math.isfinite(angle)
        or distance < 0
        or not 0 <= angle < 90
    ):
        raise ValueError(
            "Distance tolerance must be finite and >= 0 LDU; angle tolerance in [0,90) degrees"
        )


def axis_residual(a_position, a_axis, b_position, b_axis):
    """Symmetric infinite-line evidence; projected separation is NOT contact."""
    aa, ba = unit(a_axis), unit(b_axis)
    d = sub(b_position, a_position)
    return dict(
        angle_degrees=math.degrees(math.acos(min(1.0, abs(dot(aa, ba))))),
        radial_offset_ldu=max(length(cross(d, aa)), length(cross(d, ba))),
        axial_separation_ldu=max(abs(dot(d, aa)), abs(dot(d, ba))),
    )


def gear_meshes(manifest, *, distance_tolerance=0.5, angle_tolerance=1.0):
    """Detect coplanar external meshes among reviewed, unscaled gear parts."""
    _tolerances(distance_tolerance, angle_tolerance)
    gears, unsupported = [], []
    for n in manifest["nodes"]:
        if n["kind"] != "part":
            continue
        ref = normalized(n["ref"])
        if ref not in GEARS or n.get("embedded"):
            if re.search(r"gear|worm|rack", n.get("description", ""), re.I):
                unsupported.append(
                    dict(
                        id=n["id"],
                        ref=n["ref"],
                        reason="No reviewed parallel-axis profile",
                    )
                )
            continue
        axes = [direction(n["world"], v) for v in ([1, 0, 0], [0, 1, 0], [0, 0, 1])]
        if any(abs(length(a) - 1) > 0.003 for a in axes) or any(
            abs(dot(a, b)) > 0.003 for a, b in combinations(axes, 2)
        ):
            unsupported.append(
                dict(
                    id=n["id"], ref=n["ref"], reason="Scaled or sheared gear transform"
                )
            )
            continue
        gears.append(
            dict(
                id=n["id"],
                ref=n["ref"],
                teeth=GEARS[ref],
                pitch_radius_ldu=GEARS[ref] * 1.25,
                center=point(n["world"], [0, 0, 0]),
                axis=unit(axes[2]),
            )
        )
    if len(gears) > 1000:
        raise ValueError("Select a section with at most 1000 supported gears")
    meshes = []
    for a, b in combinations(gears, 2):
        residual = axis_residual(a["center"], a["axis"], b["center"], b["axis"])
        expected = a["pitch_radius_ldu"] + b["pitch_radius_ldu"]
        error = abs(residual["radial_offset_ldu"] - expected)
        if (
            residual["angle_degrees"] <= angle_tolerance
            and residual["axial_separation_ldu"] <= distance_tolerance
            and error <= distance_tolerance
        ):
            meshes.append(
                dict(
                    a=a["id"],
                    b=b["id"],
                    status="candidate",
                    center_distance_ldu=residual["radial_offset_ldu"],
                    expected_distance_ldu=expected,
                    distance_error_ldu=error,
                    plane_error_ldu=residual["axial_separation_ldu"],
                    angle_degrees=residual["angle_degrees"],
                    b_per_a=-math.copysign(
                        a["teeth"] / b["teeth"], dot(a["axis"], b["axis"])
                    ),
                )
            )
    return dict(
        section=manifest["section"],
        coordinate_space=manifest["coordinate_space"],
        gears=gears,
        meshes=meshes,
        unsupported=unsupported,
        tolerances=dict(distance_ldu=distance_tolerance, angle_degrees=angle_tolerance),
        coverage="Candidates for coplanar external meshes only; b_per_a uses reported axes. Tooth phase, engagement, backlash and collision untested. Unsupported gears are listed, not inferred.",
    )


def coaxial(
    manifest,
    instances,
    library=None,
    shadow=None,
    *,
    distance_tolerance=0.5,
    angle_tolerance=1.0,
):
    """Closest pair of rotational connector axes for each selected part pair.

    Report negative results too, with residuals. Axially separated pieces can
    share an infinite line without touching; do not turn candidates into bonds.
    """
    _tolerances(distance_tolerance, angle_tolerance)
    if not 2 <= len(instances) <= 100 or len(instances) != len(set(instances)):
        raise ValueError("Select 2..100 unique physical instance IDs")
    parts = parts_library(library, shadow)
    reports = {i: connectors(manifest, i, parts=parts) for i in instances}
    pairs = []
    for a, b in combinations(instances, 2):
        comparisons = []
        for ia, fa in enumerate(reports[a]["features"]):
            if fa["kind"] not in ROTATIONAL:
                continue
            for ib, fb in enumerate(reports[b]["features"]):
                if fb["kind"] not in ROTATIONAL:
                    continue
                residual = axis_residual(
                    fa["world_position"],
                    fa["world_axis"],
                    fb["world_position"],
                    fb["world_axis"],
                )
                aligned = (
                    residual["angle_degrees"] <= angle_tolerance
                    and residual["radial_offset_ldu"] <= distance_tolerance
                )
                comparisons.append(
                    dict(
                        first_feature=ia,
                        second_feature=ib,
                        first_kind=fa["kind"],
                        second_kind=fb["kind"],
                        first_position=fa["world_position"],
                        first_axis=unit(fa["world_axis"]),
                        second_position=fb["world_position"],
                        second_axis=unit(fb["world_axis"]),
                        coaxial=aligned,
                        **residual,
                    )
                )
        best = (
            min(
                comparisons,
                key=lambda r: (
                    not r["coaxial"],
                    r["angle_degrees"] > angle_tolerance,
                    r["radial_offset_ldu"],
                    r["angle_degrees"],
                    r["axial_separation_ldu"],
                ),
            )
            if comparisons
            else None
        )
        pairs.append(
            dict(
                a=a,
                b=b,
                status=("candidate" if best["coaxial"] else "not_coaxial")
                if best
                else "no_rotational_features",
                evidence=best,
            )
        )
    return dict(
        instances=instances,
        pairs=pairs,
        coordinate_space=manifest["coordinate_space"],
        tolerances=dict(distance_ldu=distance_tolerance, angle_degrees=angle_tolerance),
        coverage="Closest connector-axis pair per part pair, at arbitrary rotation. Infinite lines only; axial overlap, shape compatibility, retention and torque transfer untested. Feature indices refer to connectors.features.",
    )
