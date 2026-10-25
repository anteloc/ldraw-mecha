"""Background checks for physical invariants, including actual scene tampering."""

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import bpy
from mathutils import Matrix
from ldraw_mechanisms import blender as adapter, blender_tools, plan as contract


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", required=True)
    parser.add_argument("--glb", required=True)
    parser.add_argument("--output", required=True)
    a = parser.parse_args(sys.argv[sys.argv.index("--") + 1 :])
    out = Path(a.output).resolve()
    out.mkdir(parents=True, exist_ok=True)
    plan = contract.load(a.plan)
    result = blender_tools.apply_plan(plan, glb=a.glb, new_scene=True)
    rig = result["rig"]
    samples = [dict(drive=0.731, orbit=-0.38), dict(drive=-2.27, orbit=0.61)]
    checked = adapter.verify(rig, plan, samples)
    assert checked["passed"], checked
    # A wrong scene can still contain the correct driver expressions. Measure
    # actual part matrices, including a rotated/translated model root.
    root = rig["root"]
    root.matrix_world = (
        Matrix.Translation((0.7, -0.4, 0.2))
        @ Matrix.Rotation(0.37, 4, "Y")
        @ root.matrix_world
    )
    assert adapter.verify(rig, plan, samples)["passed"]
    gear = rig["mapping"]["0"]
    old = gear.matrix_basis.copy()
    gear.matrix_basis = old @ Matrix.Rotation(0.23, 4, "Z")
    bad = adapter.verify(rig, plan, samples)
    assert not bad["passed"]
    assert any(not c["passed"] for s in bad["samples"] for c in s["mechanical_checks"])
    gear.matrix_basis = old
    bpy.context.view_layer.update()
    adapter.set_controls(rig, **samples[0])
    bpy.ops.wm.save_as_mainfile(filepath=str(out / "checked.blend"))
    bpy.ops.wm.open_mainfile(filepath=str(out / "checked.blend"))
    rig = adapter.context_from_scene(plan)
    reopened = adapter.verify(rig, plan, samples)
    assert reopened["passed"], reopened
    count = len(bpy.data.objects)
    rig = adapter.build(plan, rig["root"])
    assert len(bpy.data.objects) == count
    assert adapter.verify(rig, plan, samples)["passed"]
    adapter.remove(rig["root"])
    adapter.bind(plan, rig["root"])
    contract.save(
        out / "checks.json",
        dict(
            passed=True,
            verified=checked,
            reopened=reopened,
            changed_scene_rejected=True,
            rebuild_no_leaks=True,
            rest_restored=True,
        ),
    )


if __name__ == "__main__":
    main()
