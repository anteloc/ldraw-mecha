"""Portable motion contract and safe, deterministic scalar dependency graph.

Signals use Blender's simple math subset. The same expressions run here for
analysis and as native Blender drivers; no eval of arbitrary Python is allowed.
"""

from __future__ import annotations

import ast
import hashlib
import json
import math
import re
from pathlib import Path

from .math3d import (
    cross,
    delta,
    frame,
    identity,
    inverse,
    length,
    matmul,
    point,
    sub,
    unit,
)

FUNCTIONS = {
    k: getattr(math, k)
    for k in (
        "sin",
        "cos",
        "tan",
        "asin",
        "acos",
        "atan",
        "atan2",
        "sqrt",
        "floor",
        "ceil",
    )
}
FUNCTIONS.update(
    min=min, max=max, abs=abs, pow=pow, clamp=lambda v, lo, hi: min(max(v, lo), hi)
)
NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,39}$")


def finite(value):
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
    )


def expression(expr, variables):
    if not isinstance(expr, str) or len(expr) > 255:
        raise ValueError("Driver expression must be a string of at most 255 characters")
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError as exc:
        raise ValueError(f"Invalid motion expression: {exc.msg}") from exc
    allowed = (
        ast.Expression,
        ast.BinOp,
        ast.UnaryOp,
        ast.Add,
        ast.Sub,
        ast.Mult,
        ast.Div,
        ast.Pow,
        ast.Mod,
        ast.USub,
        ast.UAdd,
        ast.Constant,
        ast.Name,
        ast.Load,
        ast.Call,
    )
    for n in ast.walk(tree):
        if not isinstance(n, allowed):
            raise ValueError(f"Unsupported expression syntax: {type(n).__name__}")
        if isinstance(n, ast.Constant) and not finite(n.value):
            raise ValueError("Only finite numeric constants are allowed")
        if (
            isinstance(n, ast.Name)
            and n.id not in variables
            and n.id not in FUNCTIONS
            and n.id != "pi"
        ):
            raise ValueError(f"Unknown expression variable {n.id}")
        if isinstance(n, ast.Call) and (
            not isinstance(n.func, ast.Name) or n.func.id not in FUNCTIONS or n.keywords
        ):
            raise ValueError("Only simple math function calls are allowed")
    return compile(tree, "<motion signal>", "eval")


def ordered(items, dependencies):
    """Topological order; fail on missing references and cycles before scene edits."""
    output, active, done = [], set(), set()

    def visit(name):
        if name in active:
            raise ValueError(f"Dependency cycle at {name}")
        if name in done:
            return
        if name not in items:
            raise ValueError(f"Unknown dependency {name}")
        active.add(name)
        for parent in dependencies(items[name]):
            visit(parent)
        active.remove(name)
        done.add(name)
        output.append(name)

    for name in items:
        visit(name)
    return output


def signal_order(plan):
    return ordered(
        plan["signals"],
        lambda s: [r[7:] for r in s["variables"].values() if r.startswith("signal:")],
    )


def body_order(plan):
    return ordered(plan["bodies"], lambda b: [b["parent"]] if b.get("parent") else [])


def load(path):
    plan = json.loads(Path(path).read_text())
    validate(plan)
    return plan


def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n"
    )


def digest(plan):
    return hashlib.sha256(
        json.dumps(plan, sort_keys=True, allow_nan=False).encode()
    ).hexdigest()


def draft(manifest, name="model"):
    return dict(
        version=1,
        name=name,
        status="draft",
        source=manifest,
        controls={},
        signals={},
        bodies={},
        anchors={},
        checks=[],
        notes=[
            "Assign rigid groups and measured joints before setting status to ready."
        ],
    )


def validate(plan, check_source=False):
    if plan.get("version") != 1:
        raise ValueError("Unsupported motion plan version")
    if not NAME.fullmatch(plan["name"]):
        raise ValueError("Invalid plan name")
    if plan.get("status") not in ("draft", "ready"):
        raise ValueError("Plan status must be draft or ready")
    source = plan["source"]
    nodes = {n["id"]: n for n in source["nodes"]}
    if len(nodes) != len(source["nodes"]):
        raise ValueError("Duplicate source instance ID")
    for group in ("controls", "signals", "bodies", "anchors"):
        for name in plan[group]:
            if not NAME.fullmatch(name):
                raise ValueError(f"Invalid {group} name {name!r}")
    for name, c in plan["controls"].items():
        if c.get("unit") not in ("radian", "ldu", "scalar"):
            raise ValueError(f"Invalid control unit: {name}")
        if (
            not all(finite(c[k]) for k in ("default", "min", "max"))
            or not c["min"] <= c["default"] <= c["max"]
        ):
            raise ValueError(f"Invalid control range: {name}")
    for name, s in plan["signals"].items():
        for var, ref in s["variables"].items():
            if not NAME.fullmatch(var) or var in FUNCTIONS or var == "pi":
                raise ValueError(f"Invalid variable: {var}")
            prefix, sep, target = ref.partition(":")
            if (
                not sep
                or prefix not in ("control", "signal")
                or target not in plan[prefix + "s"]
            ):
                raise ValueError(f"Unknown signal input {ref}")
        expression(s["expression"], s["variables"])
    signal_order(plan)
    owned = set()
    for name, b in plan["bodies"].items():
        if b["kind"] not in ("revolute", "prismatic", "fixed", "rod", "stretch"):
            raise ValueError(f"Unsupported joint kind: {name}")
        for key in ("origin", "axis"):
            if len(b[key]) != 3 or not all(finite(v) for v in b[key]):
                raise ValueError(f"Invalid {key}: {name}")
        frame(b["origin"], b["axis"], b.get("x_hint"))
        if (
            b["kind"] in ("revolute", "prismatic", "stretch")
            and b.get("signal") not in plan["signals"]
        ):
            raise ValueError(f"Missing motion signal: {name}")
        if not b["instances"]:
            raise ValueError(f"Empty rigid body: {name}")
        for instance in b["instances"]:
            if instance not in nodes or nodes[instance]["kind"] != "part":
                raise ValueError(f"Not a physical leaf: {instance}")
            if instance in owned:
                raise ValueError(f"Instance belongs to two rigid bodies: {instance}")
            owned.add(instance)
        if b["kind"] == "rod":
            if b.get("parent"):
                raise ValueError("Rods use endpoint anchors, not body parenting")
            for endpoint in ("start", "end"):
                if b.get(endpoint) not in plan["anchors"]:
                    raise ValueError(f"Unknown rod anchor: {name}")
            if not b.get("x_hint"):
                raise ValueError(f"Rod needs its source orientation x_hint: {name}")
            if not any(
                c.get("kind") == "distance"
                and {c.get("a"), c.get("b")} == {b["start"], b["end"]}
                for c in plan["checks"]
            ):
                raise ValueError(f"Rod needs a distance closure check: {name}")
    body_order(plan)
    for name, b in plan["bodies"].items():
        if b.get("parent") and plan["bodies"][b["parent"]]["kind"] == "rod":
            raise ValueError(f"A rod cannot parent another body: {name}")
        if b.get("parent") and plan["bodies"][b["parent"]]["kind"] == "stretch":
            raise ValueError(f"A stretched spring cannot parent another body: {name}")
    for name, a in plan["anchors"].items():
        if a.get("body") not in plan["bodies"]:
            raise ValueError(f"Unknown anchor body: {name}")
        if plan["bodies"][a["body"]]["kind"] == "rod":
            raise ValueError("Rod anchors cannot depend on rods")
        if plan["bodies"][a["body"]]["kind"] == "stretch":
            raise ValueError("Anchors cannot ride on a stretched spring")
        if len(a["point"]) != 3 or not all(finite(v) for v in a["point"]):
            raise ValueError(f"Invalid anchor: {name}")
    for check in plan["checks"]:
        if check["kind"] != "distance":
            from .constraints import validate as validate_constraint

            validate_constraint(check, nodes)
            from .constraints import instances as constraint_instances

            owners = {
                i: b for b, body in plan["bodies"].items() for i in body["instances"]
            }
            for instance in constraint_instances(check):
                if (
                    instance in owners
                    and plan["bodies"][owners[instance]]["kind"] == "stretch"
                ):
                    raise ValueError(
                        "Mechanical frame checks require rigid parts, not stretched springs"
                    )
            continue
        if any(check[k] not in plan["anchors"] for k in ("a", "b")):
            raise ValueError("Unknown check anchor")
        if (
            not finite(check["length"])
            or check["length"] <= 0
            or not finite(check["tolerance"])
            or check["tolerance"] <= 0
        ):
            raise ValueError("Invalid distance check")
    from .mechanisms import validate as validate_mechanisms

    validate_mechanisms(plan)
    if check_source:
        from .source import verify_source

        verify_source(source)
    result = evaluate(plan)
    failures = [c for c in result["checks"] if not c["passed"]]
    if failures:
        raise ValueError(f"Rest-pose closure failed: {failures}")
    return dict(
        valid=True,
        status=plan["status"],
        moving_parts=len(owned),
        bodies=len(plan["bodies"]),
        signals=len(plan["signals"]),
        checks=len(plan["checks"]),
    )


def evaluate(plan, values=None):
    values = values or {}
    unknown = set(values) - set(plan["controls"])
    if unknown:
        raise ValueError(f"Unknown controls: {sorted(unknown)}")
    controls = {}
    for name, c in plan["controls"].items():
        value = values.get(name, c["default"])
        if not finite(value):
            raise ValueError(f"Nonfinite control: {name}")
        controls[name] = min(max(value, c["min"]), c["max"])
    signals = {}
    for name in signal_order(plan):
        s = plan["signals"][name]
        inputs = {
            k: (controls if r.startswith("control:") else signals)[r.split(":", 1)[1]]
            for k, r in s["variables"].items()
        }
        try:
            v = eval(
                expression(s["expression"], inputs),
                {"__builtins__": {}},
                {**FUNCTIONS, "pi": math.pi, **inputs},
            )
        except (ValueError, ZeroDivisionError, OverflowError) as exc:
            raise ValueError(f"Signal {name}: {exc}") from exc
        if not finite(v):
            raise ValueError(f"Nonfinite signal: {name}")
        signals[name] = v
    transforms, anchors = {}, {}
    for name in body_order(plan):
        b = plan["bodies"][name]
        if b["kind"] == "rod":
            continue
        if b["kind"] == "stretch" and not signals[b["signal"]] > 0:
            raise ValueError(f"Spring scale must stay positive: {name}")
        f = frame(b["origin"], b["axis"], b.get("x_hint"))
        transforms[name] = matmul(
            transforms[b["parent"]] if b.get("parent") else identity(),
            delta(f, b["kind"], signals.get(b.get("signal"), 0)),
        )
    for name, a in plan["anchors"].items():
        anchors[name] = point(transforms[a["body"]], a["point"])
    for name, b in plan["bodies"].items():
        if b["kind"] != "rod":
            continue
        start, end = anchors[b["start"]], anchors[b["end"]]
        # Local Y follows the connecting rod, Z remains its rotation plane normal.
        y = unit(sub(end, start))
        z = unit(b["axis"])
        x = unit(cross(y, z))
        from .math3d import pose

        current = pose(start, list(zip(x, y, unit(cross(x, y)))))
        transforms[name] = matmul(
            current, inverse(frame(b["origin"], b["axis"], b["x_hint"]))
        )
    checks = []
    if any(c["kind"] != "distance" for c in plan["checks"]):
        nodes = {n["id"]: n for n in plan["source"]["nodes"]}
        deltas = {
            i: transforms[name]
            for name, b in plan["bodies"].items()
            for i in b["instances"]
        }
    for c in plan["checks"]:
        if c["kind"] != "distance":
            from .constraints import evaluate as evaluate_constraint

            checks.append(evaluate_constraint(c, nodes, deltas))
            continue
        measured = length(sub(anchors[c["a"]], anchors[c["b"]]))
        error = abs(measured - c["length"])
        checks.append(
            dict(
                name=c.get("name", c["a"] + "-" + c["b"]),
                length=measured,
                error=error,
                passed=error <= c["tolerance"],
            )
        )
    return dict(
        controls=controls,
        signals=signals,
        transforms=transforms,
        anchors=anchors,
        checks=checks,
    )


def combined_sample(plan, fraction=0.4):
    """Move from each default toward alternating limits, within its range."""
    if not finite(fraction) or not 0 <= fraction <= 1:
        raise ValueError("Sample fraction must be between 0 and 1")
    sample = {}
    for i, (name, c) in enumerate(plan["controls"].items()):
        target = c["min"] if i % 2 and c["min"] < 0 else c["max"]
        if target == c["default"]:
            target = c["max"] if target == c["min"] else c["min"]
        sample[name] = c["default"] + fraction * (target - c["default"])
    return sample


def sweep(plan, steps=17):
    if steps < 2 or steps > 10000:
        raise ValueError("Sweep steps must be between 2 and 10000")
    samples = []
    for name, c in plan["controls"].items():
        for i in range(steps):
            value = c["min"] + (c["max"] - c["min"]) * i / (steps - 1)
            e = evaluate(plan, {name: value})
            samples.append(
                dict(
                    control=name,
                    value=value,
                    passed=all(c["passed"] for c in e["checks"]),
                    max_error=max((c["error"] for c in e["checks"]), default=0),
                )
            )
    return dict(
        passed=all(s["passed"] for s in samples),
        samples=samples,
        coverage="Each control swept independently; analytic closure only, not mesh collisions or dynamics",
    )
