"""Measure RCVJ and optionally test a prior animation against its shaft contracts."""

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ldraw_mechanisms import plan
from ldraw_mechanisms.rcvj import evaluate_candidate, study, wrong_motion


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("model")
    p.add_argument("--output", required=True)
    p.add_argument("--candidate-plan")
    a = p.parse_args()
    out = Path(a.output)
    if out.exists():
        raise ValueError("Study output exists; choose a new directory")
    workbook, evidence = study(a.model)
    wrong = wrong_motion(workbook)
    rejected = plan.evaluate(wrong, {"input": 0.731})
    assert not all(c["passed"] for c in rejected["checks"])
    evidence["counterexample"] = dict(
        input=0.731, failures=[c for c in rejected["checks"] if not c["passed"]]
    )
    if a.candidate_plan:
        candidate = json.loads(Path(a.candidate_plan).read_text())
        checked, result = evaluate_candidate(workbook, candidate)
        plan.save(out / "candidate-with-checks.json", checked)
        plan.save(out / "candidate-check.json", result)
    plan.save(out / "plan.json", workbook)
    plan.save(out / "evidence.json", evidence)
    print(
        json.dumps(
            dict(
                output=str(out),
                parts=127,
                checks=len(workbook["checks"]),
                status="draft",
                false_animation_rejected=True,
                whole_mechanism_solved=False,
            )
        )
    )


if __name__ == "__main__":
    main()
