"""Key the 42110 Defender rig into a drive cycle with the bodywork hidden.

Run in a Blender session that already holds the rig (for example rigged.blend):

    blender --background output/42110/rigged.blend --python scripts/blender/animate_defender.py -- \
        --plan output/42110/plan.json --hide output/42110/bodywork.json \
        --save output/42110/animated.blend --report output/42110/animation-check.json

Only plan controls are keyed (one key per frame), so every frame is an input
the portable evaluator accepts. The timeline is computed in plain Python
(`timeline`), including Ackermann wheel speeds for the differentials and the
phase carries that keep every shaft continuous when a gear ratio changes.
"""

import argparse
import json
import math
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from ldraw_mechanisms import plan as contract  # noqa: E402

FPS = 24
CARRIES = (("engine", "phase_engine"), ("mid", "phase_mid"), ("c26", "phase_c26"))
STATE = ("fwd", "rev", "lo", "hi", "g_on", "g_i")


def smooth(u):
    u = min(max(u, 0.0), 1.0)
    return u * u * (3 - 2 * u)


def ramp(frame, start, end, a, b):
    """Smoothstep from a (at start) to b (at end); constant outside."""
    return a + (b - a) * smooth((frame - start) / (end - start))


# Speed profile (wheel radians per frame) and selector moves. Frames are 1-based.
SEGMENTS = dict(
    engage=(1, 24),  # direction lever to forward, range lever to low
    shifts=[(96, 108, 0.0, 0.5), (168, 180, 0.5, 1.0), (240, 252, 1.0, 1.5)],  # gear_select / pi
    range_high=(330, 354),
    steer_high=(360, 432),
    stop=(432, 468),
    reverse=(468, 492),  # direction lever to reverse
    reverse_drive=(492, 564),
    neutral=(564, 588),
    winch=(588, 672),
    end=696,
)
SPEEDS = [(1, 0.0), (24, 0.0), (90, 0.10), (108, 0.10), (160, 0.14), (180, 0.14), (232, 0.19), (252, 0.19),
          (320, 0.24), (432, 0.24), (468, 0.0), (492, 0.0), (520, -0.10), (548, -0.10), (564, 0.0)]


def speed(frame):
    for (f0, v0), (f1, v1) in zip(SPEEDS, SPEEDS[1:]):
        if f0 <= frame <= f1:
            return v0 + (v1 - v0) * smooth((frame - f0) / (f1 - f0))
    return 0.0


def selectors(frame, steer_max):
    s = SEGMENTS
    direction = ramp(frame, *s["engage"], 0.0, 1.0)
    direction = ramp(frame, *s["reverse"], direction, -1.0) if frame >= s["reverse"][0] else direction
    direction = ramp(frame, *s["neutral"], direction, 0.0) if frame >= s["neutral"][0] else direction
    rng = ramp(frame, *s["engage"], 0.0, -1.0)
    rng = ramp(frame, *s["range_high"], -1.0, 1.0) if frame >= s["range_high"][0] else rng
    rng = ramp(frame, *s["neutral"], 1.0, 0.0) if frame >= s["neutral"][0] else rng
    gear = 0.0
    for f0, f1, a, b in s["shifts"]:
        if frame >= f0:
            gear = ramp(frame, f0, f1, a * math.pi, b * math.pi)
    # Back down to 1st while stopped (sequential: 4 -> 3 -> 2 -> 1) before reversing.
    if frame >= s["stop"][0]:
        gear = ramp(frame, s["stop"][0] + 6, s["stop"][1], 1.5 * math.pi, 0.0)
    steer = 0.0
    a, b = s["steer_high"]
    if a <= frame <= b:
        steer = steer_max * math.sin(2 * math.pi * (frame - a) / (b - a)) * smooth((frame - a) / 8) * smooth((b - frame) / 8)
    a, b = s["reverse_drive"]
    if a <= frame <= b:
        steer = -0.6 * steer_max * math.sin(math.pi * (frame - a) / (b - a))
    winch = 0.0
    a, b = s["winch"]
    if frame >= a:
        winch = ramp(frame, a, b, 0.0, 4 * math.pi)
    return dict(direction_select=direction, range_select=rng, gear_select=gear, steering=steer, winch=winch)


def wheel_rates(plan, knuckle_l, knuckle_r, v):
    """Ackermann wheel speeds about the instantaneous centre on the rear axle line."""
    b = plan["bodies"]
    fl, fr, rl, rr = (b[f"wheel_{w}"]["origin"] for w in ("fl", "fr", "rl", "rr"))
    base = (rl[2] - fl[2] + rr[2] - fr[2]) / 2  # wheelbase along +Z (front is -Z)
    delta = (knuckle_l + knuckle_r) / 2  # positive turns left (+X)
    if abs(math.tan(delta)) < 1e-9:
        return dict(fl=v, fr=v, rl=v, rr=v)
    xc = base / math.tan(delta)  # ICR x on the rear axle line (+X for a left turn)
    zr = (rl[2] + rr[2]) / 2
    centre = abs(xc)
    rates = {}
    for name, p in (("fl", fl), ("fr", fr), ("rl", rl), ("rr", rr)):
        rates[name] = v * math.hypot(p[0] - xc, p[2] - zr) / centre
    return rates


def timeline(plan, frames=None):
    """Per-frame control values, with differential splits and continuity carries."""
    end = frames or SEGMENTS["end"]
    steer_max = 0.92 * plan["controls"]["steering"]["max"]
    wheels = dict(fl=0.0, fr=0.0, rl=0.0, rr=0.0)
    carry = {c: 0.0 for _, c in CARRIES}
    rows, previous = [], None
    for frame in range(1, end + 1):
        values = selectors(frame, steer_max)
        probe = contract.evaluate(plan, dict(values, **carry))
        rates = wheel_rates(plan, probe["signals"]["knuckle_l_angle"], probe["signals"]["knuckle_r_angle"], speed(frame))
        if frame > 1:
            for w in wheels:
                wheels[w] += rates[w]
        values.update(
            drive=sum(wheels.values()) / 4,
            diff_center=((wheels["fl"] + wheels["fr"]) - (wheels["rl"] + wheels["rr"])) / 4,
            diff_front=(wheels["fl"] - wheels["fr"]) / 2,
            diff_rear=(wheels["rl"] - wheels["rr"]) / 2,
        )
        values.update(carry)
        result = contract.evaluate(plan, values)
        state = tuple(result["signals"][k] for k in STATE)
        if previous and state != previous["state"]:
            # Ratio change: keep each group where it was and let it follow the new ratio.
            fresh = contract.evaluate(plan, dict(values, **{c: 0.0 for _, c in CARRIES}))
            for group, name in CARRIES:
                ratio = fresh["signals"]["ratio_" + ("e" if group == "engine" else "m" if group == "mid" else "c26")]
                carry[name] = previous["signals"][group] - ratio * previous["signals"]["out"]
            values.update(carry)
            result = contract.evaluate(plan, values)
        rows.append(dict(frame=frame, controls=values, state=state, signals=result["signals"]))
        previous = rows[-1]
    return rows


def continuity(plan, rows, radians=0.8, ldu=6.0):
    """Largest per-frame change of every body signal: rad for revolute, LDU for prismatic."""
    kinds = {b["signal"]: b["kind"] for b in plan["bodies"].values() if b.get("signal")}
    worst = {}
    for a, b in zip(rows, rows[1:]):
        for n in kinds:
            d = abs(b["signals"][n] - a["signals"][n])
            if d > worst.get(n, (0, 0))[0]:
                worst[n] = (d, b["frame"])
    limit = {n: radians if k == "revolute" else ldu for n, k in kinds.items()}
    bad = {n: v for n, v in worst.items() if v[0] > limit[n]}
    top = sorted(((v[0], n, kinds[n], v[1]) for n, v in worst.items()), reverse=True)
    return dict(limit_radians_per_frame=radians, limit_ldu_per_frame=ldu,
                worst_revolute=[t for t in top if t[2] == "revolute"][:8],
                worst_prismatic=[t for t in top if t[2] == "prismatic"][:8],
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
        name = fc.data_path.split('"')[1]
        mode = "CONSTANT" if name.startswith("phase_") else "LINEAR"
        for kp in fc.keyframe_points:
            kp.interpolation = mode
    if args.hide:
        adapter.set_hidden(rig, json.loads(Path(args.hide).read_text())["hidden"])
    # A camera and lights for playback / rendering; the model itself is untouched.
    meshes = [o for o in rig["root"].children_recursive if o.type == "MESH" and not o.hide_render]
    pts = [o.matrix_world @ Vector(c) for o in meshes for c in o.bound_box]
    lo = Vector([min(p[i] for p in pts) for i in range(3)])
    hi = Vector([max(p[i] for p in pts) for i in range(3)])
    centre, size = (lo + hi) / 2, max(hi - lo)
    cam = bpy.data.objects.new("DefenderCamera", bpy.data.cameras.new("DefenderCamera"))
    scene.collection.objects.link(cam)
    cam.location = centre + Vector((-1.25, -1.3, 0.95)) * size
    cam.rotation_euler = (centre - cam.location).to_track_quat("-Z", "Y").to_euler()
    cam.data.lens = 50
    cam.data.clip_start = 0.001
    scene.camera = cam
    for name, offset, energy in (("Key", (1, -1, 2), 80), ("Fill", (-1, 0.5, 1), 35)):
        light = bpy.data.objects.new(name, bpy.data.lights.new(name, "AREA"))
        scene.collection.objects.link(light)
        light.location = centre + Vector(offset) * size
        light.data.energy = energy * size * size
        light.data.size = size
        light.rotation_euler = (centre - light.location).to_track_quat("-Z", "Y").to_euler()
    samples = []
    checks = sorted({1, 24, 60, 102, 140, 174, 246, 300, 342, 380, 400, 480, 520, 600, rows[-1]["frame"]})
    for frame in checks:
        scene.frame_set(frame)
        values = {k: float(ctrl[k]) for k in plan["controls"]}
        expected = rows[frame - 1]["controls"]
        key_error = max(abs(values[k] - expected[k]) for k in values)
        check = adapter.verify(rig, plan, [values], tolerance=args.tolerance)
        samples.append(dict(frame=frame, key_error=key_error, passed=check["passed"] and key_error < 1e-4,
                            detail=check["samples"][0]))
    scene.frame_set(1)
    shifts = [r["frame"] for a, r in zip(rows, rows[1:]) if r["state"] != a["state"]]
    report = dict(
        passed=all(s["passed"] for s in samples) and report_continuity["passed"],
        frames=rows[-1]["frame"],
        fps=FPS,
        hidden_bodywork=len(json.loads(Path(args.hide).read_text())["hidden"]) if args.hide else 0,
        state_changes=shifts,
        continuity=report_continuity,
        samples=samples,
        tolerance=args.tolerance,
        coverage="Keys are plan controls only (one per frame); sampled frames re-evaluated against the portable "
        "evaluator; continuity checked on every body signal; no collision test of the whole sequence",
    )
    contract.save(args.report, report)
    Path(args.save).resolve().parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(Path(args.save).resolve()))
    print("MECHA_ANIMATION", report["passed"], report["frames"], len(shifts))


if __name__ == "__main__":
    main()
