"""Render stills (and optionally a preview video) of output/21318-autumn-wind/ai-animated.blend.

    bin/Blender.app/Contents/MacOS/Blender --background output/21318-autumn-wind/ai-animated.blend \
        --python scripts/blender/render_treehouse_wind.py -- --out output/21318-autumn-wind/stills \
        [--samples 24] [--video --step 2]
"""
import argparse
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "scripts/blender"))
import bpy  # noqa: E402
import animate_plants as ap_  # noqa: E402

STILLS = dict(rest=1, breeze=121, gusty_peak=361, storm_push=553, storm_gust=601)


def main():
    a = argparse.ArgumentParser()
    a.add_argument("--out", required=True)
    a.add_argument("--samples", type=int, default=24)
    a.add_argument("--cameras", nargs="*", default=["CAM_Overview", "CAM_Crown", "CAM_Swing_Rope"])
    a.add_argument("--video", action="store_true")
    a.add_argument("--step", type=int, default=2)
    args = a.parse_args(sys.argv[sys.argv.index("--") + 1:])
    out = Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    scene = bpy.context.scene
    ap_.setup_render(scene, 1280, 900, args.samples)
    for cam in args.cameras:
        scene.camera = bpy.data.objects[cam]
        for label, frame in STILLS.items():
            scene.frame_set(frame)
            scene.render.filepath = str(out / f"{cam[4:].lower()}-{label}-f{frame:03d}.png")
            bpy.ops.render.render(write_still=True)
    if args.video:
        frames = out / "video_frames"
        frames.mkdir(exist_ok=True)
        ap_.setup_render(scene, 960, 540, max(4, args.samples // 3))
        scene.camera = bpy.data.objects["CAM_Overview"]
        for f in range(scene.frame_start, scene.frame_end + 1, args.step):
            scene.frame_set(f)
            scene.render.filepath = str(frames / f"f{f:04d}.png")
            bpy.ops.render.render(write_still=True)
        ffmpeg = shutil.which("ffmpeg")
        if ffmpeg:
            subprocess.run([ffmpeg, "-y", "-framerate", str(24 // args.step), "-pattern_type", "glob", "-i",
                            str(frames / "f*.png"), "-c:v", "libx264", "-pix_fmt", "yuv420p",
                            str(out / "overview.mp4")], check=False, capture_output=True)
    scene.frame_set(1)


if __name__ == "__main__":
    main()
