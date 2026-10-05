"""Key the 42110 suspension rig through a ride-quality demonstration, bodywork hidden.

Run in a Blender session that already holds the rig (for example rigged.blend):

    blender --background output/42110-suspension/rigged.blend \
        --python scripts/blender/animate_defender_suspension.py -- \
        --plan output/42110-suspension/plan.json --hide output/42110-suspension/bodywork.json \
        --save output/42110-suspension/animated.blend \
        --report output/42110-suspension/animation-check.json

Only the four `travel_*` controls are keyed, one key per frame, so every frame
is an input the portable evaluator accepts. The sequence: rest at full droop,
settle to ride height, heave, roll, pitch, diagonal articulation, a bump under
each side, then back to full droop. `timeline` is plain Python (no bpy).
"""

import argparse
import json
import math
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from ldraw_mechanisms import plan as contract  # noqa: E402

FPS = 24
CORNERS = ("fl", "fr", "rl", "rr")
LEFT, RIGHT, FRONT, REAR = ("fl", "rl"), ("fr", "rr"), ("fl", "fr"), ("rl", "rr")
END = 612


def smooth(u):
    u = min(max(u, 0.0), 1.0)
    return u * u * (3 - 2 * u)


def ramp(frame, start, end, a, b):
    return a + (b - a) * smooth((frame - start) / (end - start))


def bump(frame, start, length, height):
    """Smooth single bump (raised cosine) from `start`, lasting `length` frames."""
    u = (frame - start) / length
    return height * 0.5 * (1 - math.cos(2 * math.pi * u)) if 0 <= u <= 1 else 0.0


def envelope(frame, start, end, fade=12):
    """1 inside [start, end], smoothly faded in/out over `fade` frames."""
    return smooth((frame - start) / fade) * smooth((end - frame) / fade)


def travel(frame, limits):
    """Wheel rise per corner (LDU) at a 1-based frame; `limits` maps corners to their maximum rise.

    Ride height, heave, roll and pitch use the smallest limit so the car stays level; articulation and
    bumps reach towards each corner's own limit.
    """
    ride = min(limits.values()) / 3
    swing = min(ride, min(limits.values()) - ride) * 0.95
    v = dict.fromkeys(CORNERS, 0.0)
    if frame <= 24:
        return v
    if frame <= 60:  # settle onto the springs
        return dict.fromkeys(CORNERS, ramp(frame, 24, 60, 0.0, ride))
    if frame <= 150:  # heave: two bounces
        h = ride + swing * math.sin(2 * math.pi * (frame - 60) / 45) * envelope(frame, 60, 150)
        return dict.fromkeys(CORNERS, h)
    if frame <= 222:  # roll: left side loaded, then right
        a = swing * math.sin(2 * math.pi * (frame - 150) / 72) * envelope(frame, 150, 222)
        return {c: ride + (a if c in LEFT else -a) for c in CORNERS}
    if frame <= 294:  # pitch: dive under braking, then squat
        a = swing * math.sin(2 * math.pi * (frame - 222) / 72) * envelope(frame, 222, 294)
        return {c: ride + (a if c in FRONT else -a) for c in CORNERS}
    if frame <= 426:  # diagonal articulation: FL+RR up, then FR+RL up
        if frame <= 330:
            a_up, b_up = smooth((frame - 294) / 36), -smooth((frame - 294) / 36)
        elif frame <= 354:
            a_up, b_up = 1.0, -1.0
        elif frame <= 396:
            u = smooth((frame - 354) / 42)
            a_up, b_up = 1.0 - 2 * u, -1.0 + 2 * u
        elif frame <= 408:
            a_up, b_up = -1.0, 1.0
        else:
            u = 1 - smooth((frame - 408) / 18)
            a_up, b_up = -u, u

        def lift(c, x):  # x in [-1, 1]: -1 full droop, 0 ride height, 1 near this corner's limit
            return ride + x * ((0.98 * limits[c] - ride) if x > 0 else ride)

        return {c: lift(c, a_up if c in ("fl", "rr") else b_up) for c in CORNERS}
    if frame <= 546:  # a bump under each side, front wheel first
        lag = 14  # frames between front and rear wheel on the same bump
        out = dict.fromkeys(CORNERS, ride)
        for c, start in (("fl", 432), ("rl", 432 + lag), ("fr", 492), ("rr", 492 + lag)):
            out[c] += bump(frame, start, 24, 0.85 * limits[c] - ride)
        return out
    if frame <= 588:  # lift the car: back to full droop
        return dict.fromkeys(CORNERS, ramp(frame, 552, 588, ride, 0.0))
    return v


def timeline(plan, frames=END):
    limits = {c: plan["controls"][f"travel_{c}"]["max"] for c in CORNERS}
    rows = []
    for frame in range(1, frames + 1):
        values = {f"travel_{c}": min(max(t, 0.0), limits[c]) for c, t in travel(frame, limits).items()}
        result = contract.evaluate(plan, values)
        rows.append(dict(frame=frame, controls=values, signals=result["signals"],
                         checks_passed=all(c["passed"] for c in result["checks"])))
    return rows


def continuity(plan, rows, radians=0.2, ldu=3.0, scale=0.1):
    """Largest per-frame change of every body signal, by body kind."""
    kinds = {b["signal"]: b["kind"] for b in plan["bodies"].values() if b.get("signal")}
    limits = dict(revolute=radians, prismatic=ldu, stretch=scale)
    worst = {}
    for a, b in zip(rows, rows[1:]):
        for n in kinds:
            d = abs(b["signals"][n] - a["signals"][n])
            if d > worst.get(n, (0, 0))[0]:
                worst[n] = (d, b["frame"])
    bad = {n: v for n, v in worst.items() if v[0] > limits[kinds[n]]}
    top = sorted(((v[0], n, kinds[n], v[1]) for n, v in worst.items()), reverse=True)
    return dict(limits_per_frame=limits, worst={k: [t for t in top if t[2] == k][:4] for k in limits},
                violations=bad, passed=not bad)


def main():
    import bpy
    from mathutils import Vector

    from ldraw_mechanisms import blender as adapter

    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", required=True)
    parser.add_argument("--hide", help="bodywork.json with the hidden occurrence list")
    parser.add_argument("--save", required=True)
    parser.add_argument("--report", required=True)
    parser.add_argument("--tolerance", type=float, default=0.01)
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1 :])
    plan = contract.load(args.plan)
    rig = adapter.context_from_scene(plan)
    ctrl = rig["controller"]
    if ctrl.animation_data:
        ctrl.animation_data_clear()
    rows = timeline(plan)
    report_continuity = continuity(plan, rows)
    scene = bpy.context.scene
    scene.render.fps = FPS
    scene.frame_start, scene.frame_end = 1, rows[-1]["frame"]
    for row in rows:
        for name, value in row["controls"].items():
            ctrl[name] = float(value)
            ctrl.keyframe_insert(data_path=f'["{name}"]', frame=row["frame"])
    action = ctrl.animation_data.action
    fcurves = []
    if hasattr(action, "layers"):
        for layer in action.layers:
            for strip in layer.strips:
                for slot in action.slots:
                    channelbag = strip.channelbag(slot)
                    if channelbag:
                        fcurves += list(channelbag.fcurves)
    else:
        fcurves = list(action.fcurves)
    for fc in fcurves:
        for kp in fc.keyframe_points:
            kp.interpolation = "LINEAR"
    hidden = json.loads(Path(args.hide).read_text())["hidden"] if args.hide else []
    if hidden:
        adapter.set_hidden(rig, hidden)
    # Camera on the visible chassis: low front three-quarter view, wheels and shocks in frame.
    meshes = [o for o in rig["root"].children_recursive
              if o.type == "MESH" and o.visible_get() and not o.hide_render]
    pts = [o.matrix_world @ Vector(c) for o in meshes for c in o.bound_box]
    lo = Vector([min(p[i] for p in pts) for i in range(3)])
    hi = Vector([max(p[i] for p in pts) for i in range(3)])
    centre, size = (lo + hi) / 2, max(hi - lo)
    cam = bpy.data.objects.new("SuspensionCamera", bpy.data.cameras.new("SuspensionCamera"))
    scene.collection.objects.link(cam)
    cam.location = centre + Vector(CAMERA_OFFSET) * size
    cam.rotation_euler = (centre - cam.location).to_track_quat("-Z", "Y").to_euler()
    cam.data.lens = 45
    cam.data.clip_start = 0.001
    scene.camera = cam
    for name, offset, energy in (("Key", (1, -1, 2), 80), ("Fill", (-1, 0.5, 1), 35), ("Rim", (0, 1.5, 0.6), 25)):
        light = bpy.data.objects.new(name, bpy.data.lights.new(name, "AREA"))
        scene.collection.objects.link(light)
        light.location = centre + Vector(offset) * size
        light.data.energy = energy * size * size
        light.data.size = size
        light.rotation_euler = (centre - light.location).to_track_quat("-Z", "Y").to_euler()
    samples = []
    checks = sorted({1, 42, 71, 120, 168, 204, 240, 276, 342, 380, 402, 444, 456, 504, 518, 570, rows[-1]["frame"]})
    for frame in checks:
        scene.frame_set(frame)
        values = {k: float(ctrl[k]) for k in plan["controls"]}
        expected = rows[frame - 1]["controls"]
        key_error = max(abs(values[k] - expected[k]) for k in values)
        check = adapter.verify(rig, plan, [values], tolerance=args.tolerance)
        samples.append(dict(frame=frame, key_error=key_error, passed=check["passed"] and key_error < 1e-4,
                            detail=check["samples"][0]))
    scene.frame_set(1)
    report = dict(
        passed=all(s["passed"] for s in samples) and report_continuity["passed"]
        and all(r["checks_passed"] for r in rows),
        frames=rows[-1]["frame"],
        fps=FPS,
        hidden_bodywork=len(hidden),
        closures_every_frame=all(r["checks_passed"] for r in rows),
        max_travel=max(max(r["controls"].values()) for r in rows),
        continuity=report_continuity,
        samples=samples,
        tolerance=args.tolerance,
        coverage="Keys are the four travel controls (one per frame); every frame evaluated for closure; sampled "
        "frames re-verified in Blender against the portable evaluator; no collision test of the whole sequence",
    )
    contract.save(args.report, report)
    Path(args.save).resolve().parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(Path(args.save).resolve()))
    print("MECHA_ANIMATION", report["passed"], report["frames"])


CAMERA_OFFSET = (1.2, -1.15, 0.5)

if __name__ == "__main__":
    main()
