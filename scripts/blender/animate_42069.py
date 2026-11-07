"""Key the 42069 Extreme Adventure rig through an in-place driving demonstration.

    blender --background output/42069/ai-rigged.blend \
        --python scripts/blender/animate_42069.py -- \
        --plan output/42069/plan.json --save output/42069/ai-animated.blend \
        --report output/42069/animation-check.json --tolerance 0.08

The vehicle never moves: the root is not keyed, so tracks circulate and wheels
turn in place. All nine controls are keyed on every frame (LINEAR), so every
frame is an input the portable evaluator accepts. Sequence (24 fps, 600 frames):

  1-24     rest
  25-120   pull away forward (track speed ramps up)
  121-260  steer left then right while driving; differential splits follow the turn
  261-430  pods pitch over a virtual terrain wave (front first, rear later) while the
           rear axle articulates
  431-520  slow down, stop and reverse
  521-600  stop and return pods, axle and steering to rest

`timeline` is plain Python (no bpy).
"""

import argparse
import math
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from ldraw_mechanisms import plan as contract  # noqa: E402

FPS = 24
END = 600
CRUISE = 0.22  # sprocket rad per frame (about 0.84 sprocket turns per second)
SPLIT_GAIN = 0.35  # half-difference of the sprockets per unit steering fraction, relative to the speed


def smooth(u):
    u = min(max(u, 0.0), 1.0)
    return u * u * (3 - 2 * u)


def ramp(frame, start, end, a, b):
    return a + (b - a) * smooth((frame - start) / (end - start))


def envelope(frame, start, end, fade=20):
    return smooth((frame - start) / fade) * smooth((end - frame) / fade)


def speed(frame):
    """Sprocket angular speed (rad/frame), signed."""
    if frame <= 24:
        return 0.0
    if frame <= 120:
        return ramp(frame, 25, 120, 0.0, CRUISE)
    if frame <= 430:
        return CRUISE if frame <= 260 else ramp(frame, 261, 300, CRUISE, 0.6 * CRUISE)
    if frame <= 520:
        return ramp(frame, 431, 470, 0.6 * CRUISE, 0.0) if frame <= 470 else ramp(frame, 471, 520, 0.0, -0.5 * CRUISE)
    return ramp(frame, 521, 570, -0.5 * CRUISE, 0.0)


def steer_fraction(frame):
    """Steering as a fraction of its limit: left (+) then right (-)."""
    if 121 <= frame <= 190:
        return 0.9 * envelope(frame, 121, 190, 22)
    if 191 <= frame <= 260:
        return -0.9 * envelope(frame, 191, 260, 22)
    return 0.0


def terrain(frame, phase):
    """Pod pitch from a travelling terrain wave; `phase` in frames delays the rear."""
    f = frame - phase
    return envelope(frame, 261 + phase, 430, 30) * math.sin(2 * math.pi * (f - 261) / 85)


def timeline(plan, frames=END):
    c = plan["controls"]
    lim = c["steering"]["max"]
    pod_amp = 0.8 * c["pod_fl"]["max"]
    roll_amp = 0.9 * c["rear_roll"]["max"]
    rows = []
    drive = split_f = split_r = 0.0
    for frame in range(1, frames + 1):
        v = speed(frame)
        s = steer_fraction(frame)
        drive += v
        # Turning: the inner (left for +) sprockets slow down, the outer ones speed up.
        split_f += -SPLIT_GAIN * s * v
        split_r += -0.8 * SPLIT_GAIN * s * v
        # Front pods meet the bump first; each pod tips its front up (negative) going on.
        values = dict(
            drive=drive,
            diff_front=split_f,
            diff_rear=split_r,
            steering=s * lim,
            pod_fl=-pod_amp * terrain(frame, 0),
            pod_fr=-pod_amp * terrain(frame, 12),
            pod_rl=-pod_amp * terrain(frame, 34),
            pod_rr=-pod_amp * terrain(frame, 46),
            rear_roll=roll_amp * envelope(frame, 290, 430, 30) * math.sin(2 * math.pi * (frame - 290) / 140),
        )
        if frame > 520:  # settle every non-drive control back to rest
            k = 1 - smooth((frame - 521) / 60)
            for name in ("diff_front", "diff_rear"):
                values[name] = values[name]  # splits stay where they are (sprockets keep their angles)
            for name in ("pod_fl", "pod_fr", "pod_rl", "pod_rr", "rear_roll", "steering"):
                values[name] *= k
        for name, value in values.items():
            if not c[name]["min"] <= value <= c[name]["max"]:
                raise ValueError(f"frame {frame}: {name}={value} outside its range")
        result = contract.evaluate(plan, values)
        rows.append(dict(frame=frame, controls=values, signals=result["signals"],
                         checks_passed=all(ch["passed"] for ch in result["checks"]),
                         worst_check=max((ch["error"] for ch in result["checks"]), default=0)))
    return rows


def continuity(plan, rows, radians=1.2, ldu=6.0, scale=0.1):
    """Largest per-frame change of every body signal by kind (path tables wrap and are skipped)."""
    kinds = {b["signal"]: b["kind"] for b in plan["bodies"].values() if b.get("signal") and b["kind"] != "path"}
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
    parser.add_argument("--save", required=True)
    parser.add_argument("--report", required=True)
    parser.add_argument("--tolerance", type=float, default=0.002)
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1:])
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
    root = rig["root"]
    root_rest = [list(r) for r in root.matrix_world]
    # Cameras: a front three-quarter view of the whole vehicle and a low side view of the tracks.
    meshes = [o for o in root.children_recursive if o.type == "MESH" and o.visible_get() and not o.hide_render]
    pts = [o.matrix_world @ Vector(cn) for o in meshes for cn in o.bound_box]
    lo = Vector([min(p[i] for p in pts) for i in range(3)])
    hi = Vector([max(p[i] for p in pts) for i in range(3)])
    centre, size = (lo + hi) / 2, max(hi - lo)
    cams = {}
    for name, offset, lens in (("MainCamera", (1.35, -1.6, 0.75), 45), ("TrackCamera", (1.35, 0.05, 0.08), 40)):
        cam = bpy.data.objects.new(name, bpy.data.cameras.new(name))
        scene.collection.objects.link(cam)
        cam.location = centre + Vector(offset) * size
        cam.rotation_euler = (centre - cam.location).to_track_quat("-Z", "Y").to_euler()
        cam.data.lens = lens
        cam.data.clip_start = 0.001
        cams[name] = cam
    scene.camera = cams["MainCamera"]
    for name, offset, energy in (("Key", (1, -1, 2), 80), ("Fill", (-1, 0.5, 1), 35), ("Rim", (0, 1.5, 0.6), 25)):
        light = bpy.data.objects.new(name, bpy.data.lights.new(name, "AREA"))
        scene.collection.objects.link(light)
        light.location = centre + Vector(offset) * size
        light.data.energy = energy * size * size
        light.data.size = size
        light.rotation_euler = (centre - light.location).to_track_quat("-Z", "Y").to_euler()
    samples = []
    frames = sorted({1, 60, 120, 155, 190, 225, 260, 300, 330, 360, 395, 430, 470, 500, 540, END})
    for frame in frames:
        scene.frame_set(frame)
        values = {k: float(ctrl[k]) for k in plan["controls"]}
        expected = rows[frame - 1]["controls"]
        key_error = max(abs(values[k] - expected[k]) for k in values)
        check = adapter.verify(rig, plan, [values], tolerance=args.tolerance)
        root_error = max(abs(root.matrix_world[i][j] - root_rest[i][j]) for i in range(4) for j in range(4))
        samples.append(dict(frame=frame, key_error=key_error, root_error=root_error,
                            passed=check["passed"] and key_error < 1e-4 and root_error == 0.0,
                            detail=check["samples"][0]))
    playback = adapter.verify_animation(rig, plan, tolerance=args.tolerance)
    scene.frame_set(1)
    report = dict(
        passed=all(s["passed"] for s in samples) and report_continuity["passed"]
        and all(r["checks_passed"] for r in rows) and playback["passed"],
        frames=rows[-1]["frame"],
        fps=FPS,
        in_place="Root not keyed; its world matrix is identical on every sampled frame",
        closures_every_frame=all(r["checks_passed"] for r in rows),
        worst_check_ratio=max(r["worst_check"] for r in rows),
        drive_range=[min(r["controls"]["drive"] for r in rows), max(r["controls"]["drive"] for r in rows)],
        continuity=report_continuity,
        samples=samples,
        playback={k: v for k, v in playback.items() if k != "samples"},
        tolerance=args.tolerance,
        coverage="All nine controls keyed every frame; every frame evaluated for closure in Python; sampled frames "
        "and 33 playback positions re-verified in Blender; no collision test of the whole sequence",
    )
    contract.save(args.report, report)
    bpy.ops.wm.save_as_mainfile(filepath=str(Path(args.save).resolve()))
    print("MECHA_ANIMATION", report["passed"], report["frames"])


if __name__ == "__main__":
    main()
