"""Explicit shaft/parallel-spur authoring, emitting the ordinary version-1 plan.

Interfaces are measured part-local dictionaries, not guessed from part names.
Helpers check source fit before mutating the plan. They do not solve contact,
infer keyed engagement, or establish tooth phase and physical clearance.
"""

from copy import deepcopy
import math

from . import constraints, plan as contract
from .geometry import GEARS, axis_residual, gear_meshes
from .math3d import direction, dot, point, unit
from .placements import analysis_placement
from .source import normalized

# Central cross holes, ordinary external spur contact. Deliberately exclude
# clutches, bevel/crown gears, shortcuts and embedded/unknown geometry.
SPUR_GEARS = {
    "3647.dat",
    "10928.dat",
    "4019.dat",
    "94925.dat",
    "3648.dat",
    "3648a.dat",
    "3648b.dat",
    "3649.dat",
}


def port(instance, point, axis, span):
    """Select one finite occupied section; directions and lengths are local LDU."""
    return dict(instance=instance, point=list(point), axis=list(axis), span=list(span))


def _nodes(plan):
    return {n["id"]: n for n in plan["source"]["nodes"] if n["kind"] == "part"}


def _review(evidence):
    if not isinstance(evidence, str) or not evidence.strip():
        raise ValueError("Record the physical evidence for keyed fit, bearings or mesh")


def _commit(plan, candidate):
    candidate["status"] = "draft"
    contract.validate(candidate)
    failures = [
        c["name"] for c in contract.evaluate(candidate)["checks"] if not c["passed"]
    ]
    if failures:
        raise ValueError("Source fit fails: " + ", ".join(failures))
    plan.clear()
    plan.update(candidate)


def shaft(
    plan,
    name,
    *,
    axle,
    keyed,
    bearings,
    evidence,
    signal=None,
    parent=None,
    mechanism=None,
):
    """Own axle + keyed mates as one body, with finite bearing/fit checks.

    Pass a driver signal, or leave signal unset for a follower that `mesh` drives.
    Every interface needs its real finite span. Retention and cross-hole phase
    must be described in evidence; axial checks preserve that reviewed rest fit.
    """
    _review(evidence)
    if name in plan["bodies"]:
        raise ValueError(f"Body already exists: {name}")
    if not keyed or not bearings:
        raise ValueError("A shaft needs keyed mates and at least one bearing")
    p = deepcopy(plan)
    if "mechanisms" in p and mechanism is None:
        raise ValueError("Pass mechanism= to associate the shaft with a prepared view")
    if mechanism is not None:
        if mechanism not in p.get("mechanisms", {}):
            raise ValueError(f"Unknown mechanism: {mechanism}")
        p["mechanisms"][mechanism]["bodies"].append(name)
    nodes = _nodes(p)
    for interface in [axle, *keyed, *bearings]:
        node = nodes.get(interface["instance"])
        if node is None:
            raise ValueError("Shaft interfaces require physical occurrence IDs")
        _, placement = analysis_placement(node, normalize=False)
        if placement["status"] == "unsupported" or placement["reflected"]:
            raise ValueError(
                "Shaft interfaces require unscaled, unsheared, proper rotations"
            )
    checks = []
    for i, mate in enumerate([*keyed, *bearings]):
        check = dict(
            name=f"{name}_fit_{i}",
            kind="coaxial",
            a=axle,
            b=mate,
            tolerance_ldu=0.02,
            tolerance_degrees=0.02,
            axial_tolerance_ldu=0.02,
            min_overlap_ldu=0.01,
        )
        constraints.validate(check, nodes)
        shorter = min(f["span"][1] - f["span"][0] for f in (axle, mate))
        check["min_overlap_ldu"] = max(shorter - 0.02, shorter * 0.99)
        checks.append(check)
    owned = [axle["instance"], *(f["instance"] for f in keyed)]
    if set(owned) & {f["instance"] for f in bearings}:
        raise ValueError("A bearing cannot also be keyed to the same shaft")
    body = dict(
        kind="revolute",
        instances=owned,
        origin=point(nodes[axle["instance"]]["world"], axle["point"]),
        axis=unit(direction(nodes[axle["instance"]]["world"], axle["axis"])),
    )
    if signal is None:
        signal = name + "_angle"
        if signal in p["signals"]:
            raise ValueError(f"Signal already exists: {signal}")
        p["signals"][signal] = dict(expression="0", variables={})
    body["signal"] = signal
    if parent is not None:
        body["parent"] = parent
    p["bodies"][name] = body
    for i, mate in enumerate(keyed):
        checks.append(
            dict(
                name=f"{name}_key_{i}",
                kind="rigid",
                a=axle["instance"],
                b=mate["instance"],
                tolerance_ldu=0.002,
                tolerance_degrees=0.002,
            )
        )
    p["checks"].extend(checks)
    p["notes"].append(f"{name}: {evidence}")
    _commit(plan, p)
    return name


def mesh(plan, driver, follower, *, gear_a, gear_b, evidence):
    """Drive a free follower shaft through reviewed parallel external spur gears.

    Both bodies must have the same parent. Their signals are parent-relative;
    the parent transform supplies carrier motion once. A driven follower is
    rejected instead of silently replacing an independent input or a loop.
    """
    _review(evidence)
    p = deepcopy(plan)
    if driver == follower:
        raise ValueError("A mesh needs two distinct shafts")
    a, b = (p["bodies"][k] for k in (driver, follower))
    if a.get("parent") != b.get("parent"):
        raise ValueError("Spur shafts must share a carrier (or both be unparented)")
    follower_signal = b.get("signal")
    if p["signals"].get(follower_signal) != dict(expression="0", variables={}):
        raise ValueError(
            "Follower already driven; close the constraint graph explicitly"
        )
    if any(
        k != follower and v.get("signal") == follower_signal
        for k, v in p["bodies"].items()
    ):
        raise ValueError("Follower signal is shared with another body")
    nodes = _nodes(p)
    for body, gear in ((a, gear_a), (b, gear_b)):
        if body["kind"] != "revolute" or gear not in body["instances"]:
            raise ValueError("Each selected gear must belong to its revolute shaft")
        node = nodes[gear]
        if normalized(node["ref"]) not in SPUR_GEARS or node.get("embedded"):
            raise ValueError(f"No supported external spur profile: {node['ref']}")
        residual = axis_residual(
            body["origin"],
            body["axis"],
            point(node["world"], [0, 0, 0]),
            direction(node["world"], [0, 0, 1]),
        )
        if residual["radial_offset_ldu"] > 0.02 or residual["angle_degrees"] > 0.02:
            raise ValueError("Gear centre axis must coincide with its shaft")
    selected = {**p["source"], "nodes": [nodes[gear_a], nodes[gear_b]]}
    candidates = gear_meshes(
        selected, distance_tolerance=0.02, angle_tolerance=0.02, normalize=False
    )["meshes"]
    if not candidates:
        raise ValueError(
            "Selected spur gears do not meet pitch spacing and tooth-plane checks"
        )
    na, nb = (GEARS[normalized(nodes[i]["ref"])] for i in (gear_a, gear_b))
    sign = int(math.copysign(1, dot(unit(a["axis"]), unit(b["axis"]))))
    p["signals"][follower_signal] = dict(
        expression=f"{-sign * na}/{nb}*a",
        variables={"a": "signal:" + a["signal"]},
    )
    check = dict(
        name=f"{driver}_{follower}_mesh",
        kind="rotation",
        terms=[
            dict(instance=gear_a, axis=a["axis"], coefficient=na),
            dict(instance=gear_b, axis=b["axis"], coefficient=sign * nb),
        ],
        tolerance_radians=0.0001,
        axis_tolerance_degrees=0.002,
    )
    if a.get("parent"):
        check["carrier"] = p["bodies"][a["parent"]]["instances"][0]
    p["checks"].append(check)
    p["notes"].append(f"{driver} → {follower}: {evidence}")
    _commit(plan, p)
    return follower_signal
