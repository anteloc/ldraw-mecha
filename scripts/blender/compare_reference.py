"""Read-only numeric comparison against the supplied 42000 implementation."""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts/blender"))
import rig_42000 as reference
from ldraw_mechanisms import plan as contract


def compare():
    plan = contract.load(ROOT / "output/42000/plan.json")
    parts = reference.lm.parse_mpd(reference.MPD, reference.SUBMODEL)
    steering, drive = reference.Steering(parts), reference.Drive(parts)
    errors = []
    for value in (-1.0, -0.5, 0.0, 0.5, 1.0):
        actual = contract.evaluate(
            plan, dict(steering=value, spin_rl=value, spin_rr=-value / 3)
        )["signals"]
        expected = dict(
            column=steering.k_column * value,
            steer_shaft=steering.k_shaft * value,
            rack=steering.rack(value),
            knuckle_l=steering.knuckle("l", value),
            knuckle_r=steering.knuckle("r", value),
            propshaft=drive.k_prop * value / 3,
            crank=drive.k_crank * value / 3,
        )
        for i, cylinder in enumerate(drive.cylinders):
            expected[f"piston{i}"] = eval(
                drive.piston_expr(cylinder),
                {"__builtins__": {}},
                {**contract.FUNCTIONS, "rl": value, "rr": -value / 3},
            )
        errors.extend(abs(actual[k] - v) for k, v in expected.items())
    return dict(
        passed=max(errors) < 1e-5,
        max_error=max(errors),
        comparisons=len(errors),
        reference="scripts/blender/rig_42000.py; read-only Steering and Drive calculations",
    )


if __name__ == "__main__":
    result = compare()
    contract.save(ROOT / "output/42000/reference-comparison.json", result)
    if not result["passed"]:
        raise RuntimeError(result)
    print(result)
