"""Routine study checks and background rigging; no Blender imports.

The plan remains the only motion document. A study directory is simply a
convenience for locating plan.json and its neighbouring artifacts.
"""

import os
from pathlib import Path
import subprocess
import sys

from . import plan as contract
from .audit import audit
from .source import find_tool


def plan_path(value):
    path = Path(value).resolve()
    return path / "plan.json" if path.is_dir() else path


def protect_inputs(inputs, outputs):
    """Reject output aliases of inputs or each other before writing artifacts."""
    used = {Path(p).resolve() for p in inputs}
    for value in outputs:
        path = Path(value).resolve()
        if path in used:
            raise ValueError(
                f"Output would overwrite an input or another output: {path}"
            )
        used.add(path)


def control_values(assignments):
    """Parse CLI assignments once for both evaluate and check."""
    values = {}
    for assignment in assignments:
        name, separator, value = assignment.partition("=")
        if not separator or not name:
            raise ValueError("--set needs CONTROL=VALUE")
        values[name] = float(value)
    return values


def check(
    plan, *, steps=17, values=None, require_reviewed=False, require_constrained=False
):
    """Validate current source, sweep controls and report scope in one place.

    Mixed poses supplement independent sweeps, not mechanism-specific tests.
    Nothing here changes the plan or certifies physical motion.
    """
    validated = contract.validate(plan, check_source=True)
    if not 2 <= steps <= 10000:
        raise ValueError("Sweep steps must be between 2 and 10000")
    if values is not None:
        unknown = set(values) - set(plan["controls"])
        if unknown:
            raise ValueError(f"Unknown controls: {sorted(unknown)}")
        if any(not contract.finite(v) for v in values.values()):
            raise ValueError("Nonfinite control input")
    scope = audit(plan)
    try:
        swept = contract.sweep(plan, steps)
    except ValueError as exc:
        swept = dict(passed=False, error=str(exc))
    poses = {"defaults": {}}
    if plan["controls"]:
        # Distinct fractions expose coupling that equal inputs can conceal.
        low = contract.combined_sample(plan, 0.37)
        high = contract.combined_sample(plan, 0.61)
        poses["mixed"] = {
            name: (low if i % 2 == 0 else high)[name]
            for i, name in enumerate(plan["controls"])
        }
    if values is not None:
        poses["requested"] = values
    evaluated = {}
    for label, controls in poses.items():
        try:
            result = contract.evaluate(plan, controls)
            result["passed"] = all(c["passed"] for c in result["checks"])
        except ValueError as exc:
            result = dict(passed=False, error=str(exc))
        evaluated[label] = dict(requested=controls, **result)
    return dict(
        passed=swept["passed"]
        and all(p["passed"] for p in evaluated.values())
        and (not require_constrained or scope["constraints"]["complete"])
        and (not require_reviewed or scope["review_complete"]),
        plan_digest=contract.digest(plan),
        validation=validated,
        sweep=swept,
        poses=evaluated,
        audit=scope,
        require_reviewed=require_reviewed,
        require_constrained=require_constrained,
        summary=dict(
            status=plan["status"],
            moving_parts=validated["moving_parts"],
            sweep_passed=swept["passed"],
            poses_passed=all(p["passed"] for p in evaluated.values()),
            review_complete=scope["review_complete"],
            unresolved=len(scope["unresolved"]),
            deferred=len(scope["deferred"]),
            unaccounted_parts=len(scope["unaccounted_mechanical_parts"]),
        ),
        warnings=scope["warnings"],
        coverage="Source freshness, declared equations, sampled closure and recorded scope only; no collision or physical-feasibility proof. Add mechanism-specific poses and invariants.",
    )


def blender_executable(value=None):
    return find_tool(
        "blender",
        value or os.environ.get("BLENDER_BIN"),
        "Blender.app/Contents/MacOS/Blender",
    )


def rig(
    value,
    *,
    glb=None,
    save=None,
    report=None,
    blender=None,
    animate=False,
    tolerance=0.002,
    reopen=False,
    require_constrained=False,
):
    """Build using conventional paths or explicit overrides; optionally reopen.

    Keep subprocess output on stderr so CLI stdout remains JSON. Existing rig
    invocations keep the same adapter checks and exit status.
    """
    path = plan_path(value)
    plan = contract.load(path)
    contract.validate(plan, check_source=True)
    if require_constrained:
        preflight = check(plan, require_constrained=True)
        if not preflight["passed"]:
            return dict(
                passed=False,
                verified=False,
                reason="Mechanical preflight failed",
                preflight=preflight,
            )
    if not contract.finite(tolerance) or tolerance <= 0:
        raise ValueError("Tolerance must be a positive finite number in LDU")
    model = Path(glb).resolve() if glb else path.with_name("model.glb")
    if not model.is_file():
        raise ValueError(f"Bound GLB not found: {model}; run convert or pass --glb")
    saved = Path(save).resolve() if save else path.with_name("rigged.blend")
    report = Path(report).resolve() if report else saved.with_name("blender-check.json")
    reopened = report.with_name(report.stem + "-reopen.json")
    protect_inputs(
        [path, model, plan["source"]["path"], *plan["source"]["dependencies"]],
        [saved, report, *([reopened] if reopen else [])],
    )
    executable = blender_executable(blender)
    script = Path(__file__).resolve().parents[1] / "scripts/blender/apply_plan.py"
    common = [
        "--python-exit-code",
        "1",
        "--python",
        str(script),
        "--",
        "--plan",
        str(path),
        "--tolerance",
        repr(tolerance),
    ]
    command = [
        executable,
        "--background",
        "--factory-startup",
        *common,
        "--new-scene",
        "--glb",
        str(model),
        "--save",
        str(saved),
        "--report",
        str(report),
    ]
    if animate:
        command.append("--animate")
    run = subprocess.run(command, stdout=sys.stderr, stderr=sys.stderr)
    result = dict(
        saved=str(saved),
        verified=run.returncode == 0,
        passed=run.returncode == 0,
        report=str(report),
    )
    if reopen and result["passed"]:
        command = [
            executable,
            "--background",
            "--disable-autoexec",
            str(saved),
            *common,
            "--verify-existing",
            "--report",
            str(reopened),
        ]
        run = subprocess.run(command, stdout=sys.stderr, stderr=sys.stderr)
        result.update(
            passed=run.returncode == 0,
            reopened=run.returncode == 0,
            reopen_report=str(reopened),
        )
    return result
