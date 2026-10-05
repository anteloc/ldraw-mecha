"""Measured candidates supplement connector contacts; they never prove coupling.

Reviewed parallel-axis gear profiles: LDraw part origins are tooth midplanes,
local Z is the shaft axis. Nominal pitch diameter is 2.5 LDU/tooth (module 1).
Worms have separate finite profiles; never apply the parallel-axis rule to them.
"""

from itertools import combinations
import math
import re

from .analysis import connectors
from .math3d import cross, direction, dot, length, point, sub, unit
from .source import normalized, parts_library
from .placements import analysis_placement, placement_report

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
# 4716.dat / s/4716s02.dat: local Z shaft, thread from -20 to +20,
# nominal pitch radius 10 LDU, single start. Keep end stations conservative:
# partial end threads do not establish a useful mesh. See docs/discovery-quality.md.
WORMS = {"4716.dat": dict(starts=1, pitch_radius_ldu=10.0, thread_half_length_ldu=16.0)}
WORM_WHEELS = {
    "3647.dat",
    "10928.dat",
    "4019.dat",
    "94925.dat",
    "24505.dat",
    "3648.dat",
    "3648b.dat",
    "3649.dat",
}


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


def gear_meshes(
    manifest, *, distance_tolerance=0.5, angle_tolerance=1.0, normalize=True
):
    """Coplanar external gears and finite perpendicular worm candidates."""
    _tolerances(distance_tolerance, angle_tolerance)
    gears, worms, unsupported, placements = [], [], [], []
    for n in manifest["nodes"]:
        if n["kind"] != "part":
            continue
        ref = normalized(n["ref"])
        if ref not in GEARS and ref not in WORMS or n.get("embedded"):
            if re.search(r"\b(?:gears?|worm|rack)\b", n.get("description", ""), re.I):
                alias = n.get("library_alias") if n.get("embedded") else None
                unsupported.append(
                    dict(
                        id=n["id"],
                        ref=n["ref"],
                        reason=f"Embedded copy of {alias}; profile not applied"
                        if alias
                        else "No reviewed gear/worm profile",
                    )
                )
            continue
        world, placement = analysis_placement(n, normalize=normalize)
        placements.append(placement)
        if placement["status"] == "unsupported":
            unsupported.append(
                dict(
                    id=n["id"], ref=n["ref"], reason="Scaled or sheared gear transform"
                )
            )
            continue
        if ref in WORMS:
            worms.append(
                dict(
                    id=n["id"],
                    ref=ref,
                    center=point(world, [0, 0, 0]),
                    axis=unit(direction(world, [0, 0, 1])),
                    **WORMS[ref],
                )
            )
            continue
        gears.append(
            dict(
                id=n["id"],
                ref=n["ref"],
                teeth=GEARS[ref],
                pitch_radius_ldu=GEARS[ref] * 1.25,
                center=point(world, [0, 0, 0]),
                axis=unit(direction(world, [0, 0, 1])),
            )
        )
    if len(gears) + len(worms) > 1000:
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
                    kind="gear_mesh",
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
    for worm in worms:
        for wheel in gears:
            if normalized(wheel["ref"]) not in WORM_WHEELS:
                continue
            aa, ba = worm["axis"], wheel["axis"]
            cosine = dot(aa, ba)
            angle_error = math.degrees(math.asin(min(1.0, abs(cosine))))
            if angle_error > angle_tolerance:
                continue
            d = sub(wheel["center"], worm["center"])
            # Closest points on the two directed lines, at a + s*aa and b + t*ba.
            denominator = 1 - cosine * cosine
            s = (dot(d, aa) - cosine * dot(d, ba)) / denominator
            t = (cosine * dot(d, aa) - dot(d, ba)) / denominator
            distance = abs(dot(d, unit(cross(aa, ba))))
            expected = worm["pitch_radius_ldu"] + wheel["pitch_radius_ldu"]
            if (
                abs(distance - expected) <= distance_tolerance
                and abs(t) <= distance_tolerance
                and abs(s) <= worm["thread_half_length_ldu"]
            ):
                meshes.append(
                    dict(
                        a=worm["id"],
                        b=wheel["id"],
                        kind="worm_mesh",
                        status="candidate",
                        center_distance_ldu=distance,
                        expected_distance_ldu=expected,
                        distance_error_ldu=abs(distance - expected),
                        perpendicular_error_degrees=angle_error,
                        worm_station_ldu=s,
                        wheel_plane_error_ldu=abs(t),
                        thread_half_length_ldu=worm["thread_half_length_ldu"],
                        wheel_per_worm_magnitude=worm["starts"] / wheel["teeth"],
                        direction_requires_review=True,
                    )
                )
    return dict(
        section=manifest["section"],
        coordinate_space=manifest["coordinate_space"],
        gears=gears,
        worms=worms,
        meshes=meshes,
        unsupported=unsupported,
        placements=placement_report(placements),
        tolerances=dict(distance_ldu=distance_tolerance, angle_degrees=angle_tolerance),
        coverage="Candidates for coplanar external gears and reviewed finite perpendicular worm/spur pairs. b_per_a uses reported axes for parallel meshes only; worm ratios are magnitudes, direction requires review. Tooth phase, engagement, backlash, backdriving and collision untested. Unsupported gears are listed, not inferred.",
    )


def coaxial(
    manifest,
    instances,
    library=None,
    shadow=None,
    *,
    distance_tolerance=0.5,
    angle_tolerance=1.0,
    normalize=True,
):
    """Closest pair of rotational connector axes for each selected part pair.

    Report negative results too, with residuals. Axially separated pieces can
    share an infinite line without touching; do not turn candidates into bonds.
    """
    _tolerances(distance_tolerance, angle_tolerance)
    if not 2 <= len(instances) <= 100 or len(instances) != len(set(instances)):
        raise ValueError("Select 2..100 unique physical instance IDs")
    parts = parts_library(library, shadow)
    reports = {
        i: connectors(manifest, i, parts=parts, normalize=normalize) for i in instances
    }
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
        placements=placement_report([r["placement"] for r in reports.values()]),
        pairs=pairs,
        coordinate_space=manifest["coordinate_space"],
        tolerances=dict(distance_ldu=distance_tolerance, angle_degrees=angle_tolerance),
        coverage="Closest connector-axis pair per part pair, at arbitrary rotation. Infinite lines only; axial overlap, shape compatibility, retention and torque transfer untested. Feature indices refer to connectors.features.",
    )
