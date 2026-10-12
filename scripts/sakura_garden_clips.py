"""Bespoke minifig clips for the sakura-garden diorama (pure Python, Blender-safe).

None of the 10 existing minifig-catalog archetypes (police/spaceman/.../diver) fit a
monk/gardener/visitor, so these three clips are authored fresh from
scripts/minifig_clips.py's shared primitives (gait/wave/turn_steps/hold), not
transferred unchanged from the library. Heading/distance for the monk's walk are
derived from this model's own measured placements (see notes below), not guessed.
"""
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import minifig_clips as mc  # noqa: E402

# Monk: starts at world (80,-24,-130) facing world +Z (home-forward = +Z, home-left = -X, since the
# model's local +X convention ["the figure's left is +X"] maps through the monk's 180deg yaw to world -X).
# Target: temple-steps approach near (220,-24,-50); stop short of the steps themselves. In the
# gait()/heading_offsets() home frame: forward_component = target_dz = 80, left_component = -(target_dx) = -140,
# giving heading = atan2(-140, 80) = -1.051 rad, full distance 161 LDU; walking only 125 LDU stops the monk
# roughly 36 LDU short of the steps, clear of the stair geometry.
MONK_HEADING = math.atan2(-140.0, 80.0)
MONK_DISTANCE = 125.0


def monk_walk_to_pagoda():
    c = mc.Clip("GF_monk", "walk_to_pagoda", "Walk to the pagoda",
                "Settles, turns to face the pagoda's approach, walks there at an unhurried, contemplative "
                "pace, and stops short of the steps.", 144)
    mc.hold(c, "neck", 1, 10, 0.0)
    mc.turn_steps(c, 10, 26, 0.0, MONK_HEADING, hip=0.12)
    f1, end = mc.gait(c, 26, steps=5, period=28, hip=0.32, arm=0.28, heading=MONK_HEADING,
                       distance=MONK_DISTANCE)
    mc.hold(c, "neck", f1, f1 + 10, 0.0)
    return c, end


def gardener_idle():
    c = mc.Clip("GF_gardener", "garden_idle", "Quiet idle near the torii gate",
                "Stands at ease: a slow weight shift, occasional unhurried glances around the garden. No "
                "held tool (this figure has no accessory parts).", 144, loop=(1, 144))
    mc.wave(c, "hip_l", 1, 192, 1, 0.05)
    mc.wave(c, "hip_r", 1, 192, 1, 0.05, sign=-1.0)
    mc.wave(c, "neck", 20, 96, 2, 0.3)
    return c


def visitor_watch_koi():
    """Only the neck moves (watching the koi); shoulder/wrist/hip all stay at rest. Her rest pose already
    clears the bridge's west rail by only 1 LDU, so any added shoulder/arm swing would move her hands toward
    it -- and a clearance check (output/sakura-garden/clearance-visitor-strict.json) showed that even a tiny
    hip sway nudges her feet into the bridge deck she stands on at a strict 0.1 LDU shrink, so that was
    dropped too. No existing library clip fits (e.g. the pirate lookout both moves the shoulder and assumes
    a held item she doesn't have)."""
    c = mc.Clip("GF_visitor", "watch_koi", "Watching the koi at the rail",
                "Leans at the bridge rail, glances down and side to side at the koi pond; shoulders/wrists/hips "
                "stay at rest to preserve the documented 1 LDU hand-to-rail clearance and her footing on the "
                "bridge deck.", 144, loop=(1, 144))
    mc.wave(c, "neck", 20, 96, 2, 0.4)
    return c


def all_clips():
    monk, monk_end = monk_walk_to_pagoda()
    return dict(monk=monk, gardener=gardener_idle(), visitor=visitor_watch_koi()), monk_end


if __name__ == "__main__":
    clips, monk_end = all_clips()
    for fig, c in clips.items():
        errs = mc.check(c)
        print(fig, c.name, "frames=", c.frames, "errors=", errs)
    print("monk end (forward,left) home-frame offset:", monk_end)
