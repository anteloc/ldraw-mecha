"""Reopen the saved 42083 mechanisms blend and re-verify every rig against its plan file.

    Blender --background output/42083-mechanisms/mechanisms.blend --python scripts/blender/check_42083_reopen.py -- \
        --report output/42083-mechanisms/reopen-check.json [--tolerance 0.002]
"""

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
import bpy  # noqa: E402

from ldraw_mechanisms import blender as adapter, plan as contract  # noqa: E402
import timeline_42083 as t  # noqa: E402

NAMES = ("doors", "drivetrain", "gearbox", "dnr", "wing")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", required=True)
    ap.add_argument("--tolerance", type=float, default=0.002)
    a = ap.parse_args(sys.argv[sys.argv.index("--") + 1:])
    scene = bpy.context.scene
    out, ok = {}, True
    for name in NAMES:
        plan = contract.load(t.OUT / name / "plan.json")
        root = next(o for o in bpy.data.objects if o.get("mecha_42083") == name)
        stored = json.loads(root["mecha_plan"])
        same = {k: v for k, v in stored.items() if k != "notes"} == {k: v for k, v in plan.items() if k != "notes"}
        rig = adapter.context_from_scene(plan, root)
        ctrl = rig["controller"]
        kin = json.loads((t.OUT / name / "kinematics.json").read_text())
        rows = t.timeline(name, plan, paddle_up_stroke=(kin.get("paddle") or {}).get("up_stroke", -0.6))
        samples = []
        for frame in (1, 60, 130, 210, 300, 390, 480):
            scene.frame_set(frame)
            values = {k: float(ctrl[k]) for k in plan["controls"]}
            key_error = max(abs(values[k] - rows[frame - 1]["controls"][k]) for k in values)
            check = adapter.verify(rig, plan, [values], tolerance=a.tolerance)
            s = check["samples"][0]
            samples.append(dict(frame=frame, key_error=key_error, max_matrix_error=s["max_matrix_error"],
                                max_static_error=s["max_static_error"], max_closure_error=s["max_closure_error"],
                                passed=check["passed"] and key_error < 1e-3))
        action = ctrl.animation_data.action if ctrl.animation_data else None
        out[name] = dict(embedded_plan_matches=same, controller=ctrl.name, action=action.name if action else None,
                         root_location=[round(v, 4) for v in root.location], samples=samples,
                         passed=same and action is not None and all(s["passed"] for s in samples))
        ok = ok and out[name]["passed"]
    scene.frame_set(1)
    report = dict(passed=ok, blender=bpy.app.version_string, file=bpy.data.filepath, frames=[scene.frame_start, scene.frame_end],
                  fps=scene.render.fps, tolerance=a.tolerance, mechanisms=out,
                  coverage="Saved file reopened in a fresh process; embedded plans compared with the plan files; "
                           "keyed controls and evaluated transforms checked at sampled frames (root-relative)")
    contract.save(a.report, report)
    print("MECHA_REOPEN", ok)
    if not ok:
        raise RuntimeError(f"Saved mechanism verification failed; see {a.report}")


if __name__ == "__main__":
    main()
