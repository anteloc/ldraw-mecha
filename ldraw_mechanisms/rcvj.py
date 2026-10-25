"""Reproducible RCVJ source study and animation counterexample checks.

This is a measured joint workbook, not a solved 127-part animation. Occurrence
IDs refer to the supplied annotated RCVJ.mpd. Reject another hierarchy instead
of quietly attaching constraints to different pieces.
"""

from __future__ import annotations

from copy import deepcopy
import math

from . import plan as contract
from .analysis import connectors
from .geometry import axis_residual, gear_meshes
from .math3d import direction, point, unit
from .source import Document, parts_library

# Exact physical instances, not annotated assembly names. The first two pairs
# are the opposed side gears of the central differential, NOT an external mesh.
SHAFTS = [
    ("left_side", "56", "3705.dat", "9/14", "3648a.dat"),
    ("right_side", "38", "32073.dat", "9/16", "3648a.dat"),
    ("front_side", "37", "6587.dat", "9/1", "3648a.dat"),
    ("rear_side", "27", "4519.dat", "9/2", "3648a.dat"),
    ("left_cam", "2", "4519.dat", "9/4", "6575.dat"),
    ("right_cam", "1", "4519.dat", "9/5", "6575.dat"),
    ("left_cam_connector", "2", "4519.dat", "32", "3651.dat"),
    ("right_cam_connector", "1", "4519.dat", "39", "3651.dat"),
    ("upper_input", "0/6", "4519.dat", "5/10", "6538a.dat"),
    ("lower_output", "0/0", "32073.dat", "0/5", "32039.dat"),
]
BEARINGS = [
    ("left_carrier_bearing", "56", "3705.dat", "32", "3651.dat"),
    ("right_carrier_bearing", "38", "32073.dat", "39", "3651.dat"),
]


def study(source, *, parts=None):
    manifest = Document(source).manifest()
    nodes = {n["id"]: n for n in manifest["nodes"] if n["kind"] == "part"}
    if len(nodes) != 127:
        raise ValueError(
            "RCVJ workbook expects the supplied 127-part annotated hierarchy"
        )
    parts = parts or parts_library()
    report = dict(
        source=manifest,
        designer="Thomas Reininghaus",
        designer_url="https://rcvj.reininghaus.org/",
        license="CC BY-NC-SA 4.0 (designer model and explanation)",
        scope="Measured shaft interfaces and rejection tests; whole-mechanism kinematics remain unresolved.",
        shafts=[],
        gears=gear_meshes(manifest),
    )
    plan = contract.draft(manifest, "RCVJ")
    plan["notes"] = [
        "Double-gimbal constant-velocity joint. Two differential angle bisectors operate in perpendicular planes.",
        "Assembly labels in the source are not rigid-body or kinematic definitions.",
        "Ten keyed interfaces and two carrier bearings are measured here. This is a constraint workbook, not a motion-ready rig.",
        "Source fit errors are retained and reported; their tolerances are not manufacturing allowances.",
        "Before ready: resolve both carriers, crown contacts, all link closures, keyed/bearing segments and output phase over articulated nonzero poses.",
    ]
    for pair in [*SHAFTS, *BEARINGS]:
        name, shaft, shaft_ref, mate, mate_ref = pair
        keyed = pair in SHAFTS
        if any(
            i not in nodes or nodes[i]["ref"].casefold() != ref
            for i, ref in ((shaft, shaft_ref), (mate, mate_ref))
        ):
            raise ValueError(f"RCVJ occurrence identity changed: {name}")
        a, b = (connectors(manifest, i, parts=parts) for i in (shaft, mate))
        options = []
        for ia, fa in enumerate(a["features"]):
            if fa["kind"] != "axle":
                continue
            for ib, fb in enumerate(b["features"]):
                if fb["kind"] != ("axle_hole" if keyed else "pin_hole"):
                    continue
                r = axis_residual(
                    fa["world_position"],
                    fa["world_axis"],
                    fb["world_position"],
                    fb["world_axis"],
                )
                options.append(
                    (
                        r["angle_degrees"] > 0.2,
                        r["radial_offset_ldu"],
                        r["axial_separation_ldu"],
                        ia,
                        ib,
                        r,
                    )
                )
        if not options:
            raise ValueError(f"No shaft/hole evidence for {name}")
        _, _, _, ia, ib, residual = min(options, key=lambda o: o[:5])
        fa, fb = a["features"][ia], b["features"][ib]
        # Bounded acceptance of the historical source fit. Never use a search
        # tolerance to silently fix an incorrectly selected connector.
        if residual["angle_degrees"] > 0.2 or residual["radial_offset_ldu"] > 2:
            raise ValueError(f"RCVJ interface changed: {name}: {residual}")

        def local(i, f):
            return dict(
                instance=i, point=f["position"], axis=[r[1] for r in f["frame"]]
            )

        if keyed:
            plan["checks"].append(
                dict(
                    kind="rigid",
                    name=name + "_keyed",
                    a=shaft,
                    b=mate,
                    tolerance_ldu=0.01,
                    tolerance_degrees=0.01,
                )
            )
        plan["checks"].append(
            dict(
                kind="coaxial",
                name=name + "_axis",
                a=local(shaft, fa),
                b=local(mate, fb),
                tolerance_ldu=residual["radial_offset_ldu"] + 0.02,
                tolerance_degrees=residual["angle_degrees"] + 0.02,
                axial_tolerance_ldu=0.02,
            )
        )
        report["shafts"].append(
            dict(
                name=name,
                kind="keyed" if keyed else "bearing",
                shaft=shaft,
                mate=mate,
                shaft_ref=shaft_ref,
                mate_ref=mate_ref,
                shaft_feature=ia,
                mate_feature=ib,
                shaft_frame=local(shaft, fa),
                mate_frame=local(mate, fb),
                axis=unit(fa["world_axis"]),
                origin=fa["world_position"],
                residual=residual,
                inference="Interface identified by source geometry; axial retention and complete surrounding assembly are separate checks. Bearings permit twist; keyed interfaces preserve relative pose.",
            )
        )
    opposed = [nodes[i] for i in ("9/14", "9/16")]
    report["opposed_gears"] = dict(
        ids=["9/14", "9/16"],
        **axis_residual(
            point(opposed[0]["world"], [0, 0, 0]),
            direction(opposed[0]["world"], [0, 0, 1]),
            point(opposed[1]["world"], [0, 0, 0]),
            direction(opposed[1]["world"], [0, 0, 1]),
        ),
        conclusion="Approximately coaxial, axially separated side gears; not a parallel external gear pair.",
    )
    contract.validate(plan)
    return plan, report


def wrong_motion(plan):
    """Minimal reproduction of the observed failure: rotate gear, leave axle."""
    wrong = deepcopy(plan)
    wrong["controls"] = {
        "input": dict(unit="radian", default=0, min=-2 * math.pi, max=2 * math.pi)
    }
    wrong["signals"] = {"input": dict(expression="x", variables={"x": "control:input"})}
    n = next(n for n in plan["source"]["nodes"] if n["id"] == "9/14")
    wrong["bodies"] = {
        "gear": dict(
            kind="revolute",
            instances=["9/14"],
            origin=point(n["world"], [0, 0, 0]),
            axis=[0, 0, 1],
            signal="input",
        )
    }
    return wrong


def remap_candidate(candidate, manifest, *, tolerance=0.005):
    """Match an older flat hierarchy by exact refs/colours and rest transforms.

    Source IDs cannot be copied across reannotation. Ambiguous matches are an
    error. This only imports body/control hypotheses into the measured workbook.
    """
    available = {n["id"]: n for n in manifest["nodes"] if n["kind"] == "part"}
    mapping = {}
    for n in candidate["source"]["nodes"]:
        if n["kind"] != "part":
            continue
        matches = [
            i
            for i, m in available.items()
            if m["ref"].casefold() == n["ref"].casefold()
            and m.get("effective_colour", m.get("colour"))
            == n.get("effective_colour", n.get("colour"))
            and max(
                abs(m["world"][r][c] - n["world"][r][c])
                for r in range(4)
                for c in range(4)
            )
            <= tolerance
        ]
        if len(matches) != 1:
            raise ValueError(
                f"Cannot uniquely map candidate occurrence {n['id']}: {matches}"
            )
        mapping[n["id"]] = matches[0]
        del available[matches[0]]
    return mapping


def evaluate_candidate(workbook, candidate):
    mapping = remap_candidate(candidate, workbook["source"])
    checked = deepcopy(workbook)
    for key in ("controls", "signals", "bodies", "anchors"):
        checked[key] = deepcopy(candidate[key])
    for b in checked["bodies"].values():
        b["instances"] = [mapping[i] for i in b["instances"]]
    contract.validate(checked)
    # Evaluate actual off-grid phases: uniform sweeps can alias gear periods.
    poses = [
        {name: factor for name in checked["controls"]}
        for factor in (0.371, 1.13, -2.27)
    ]
    results = [contract.evaluate(checked, p) for p in poses]
    return checked, dict(
        candidate_source_sha256=candidate["source"]["sha256"],
        mapping=mapping,
        passed=all(c["passed"] for r in results for c in r["checks"]),
        poses=[
            dict(
                controls=r["controls"],
                failures=[c for c in r["checks"] if not c["passed"]],
            )
            for r in results
        ],
    )
