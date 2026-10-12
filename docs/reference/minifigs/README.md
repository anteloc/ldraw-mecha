# Minifigs: articulated figures and reusable clips

This case documents [archived minifigs](../../../examples/reference/minifigs), introduced in
commit `a31034a` and reviewed on **2026-10-07**: ten constructed figures, seven
mechanical joints each, and thirty demonstration clips. It extends the vehicle
references with articulated characters, held-item placement and transferable
animation. It is not a human skeleton or a dynamics simulation.

| Reference | Reuse it for |
| --- | --- |
| [Joints and attachments](joints-and-attachments.md) | Connector-based placement, mirrored control meanings, hand/arm hierarchy and rigid accessories |
| [Reusable animation clips](animation-clips.md) | Shared channels, sparse easing keys, Actions, slots and NLA playback |
| [Whole-figure staging](whole-figure-staging.md) | Separate root motion, pivot conventions, walking and sitting approximations |
| [Pose and accessory clearance](pose-clearance.md) | Combined-pose sampling and qualifying clip transfer |
| [Scope and evidence](scope-and-evidence.md) | Exact inputs, fresh checks and known limitations |

Open [minifigs.blend](../../../examples/reference/minifigs/minifigs.blend). Each figure has
its own `CTRL_minifig_XX_name` controller, for example `CTRL_minifig_05_chef`,
with seven joint properties and six whole-figure properties. The three clips
per figure occupy frames **1–144**, **161–304**, **321–464** on a 1–480 timeline
at 24 fps. All ten figures play simultaneously. To pose manually, mute that
controller's NLA tracks and release any active Action; keep its rig drivers.

The [generated catalog](../../../examples/reference/minifigs/CATALOG.md) lists every figure,
clip and sampled compatibility result. It remains the roster; these pages
explain the shared techniques rather than repeating thirty clip descriptions.
See the [overview](../../../examples/reference/minifigs/previews/overview-f232.png).

Start from [build_minifigs.py](../../../scripts/build_minifigs.py) for assembly
and motion authoring, [minifig_clips.py](../../../scripts/minifig_clips.py) for
pure Python animation data, and
[animate_minifigs.py](../../../scripts/blender/animate_minifigs.py) for scene
construction. These are case builders, not a new `--recipe minifigs` option.
They use the ordinary source/GLB/plan adapter. The source builder is also a
worked example of [using the part taxonomy](../../part-information.md).

Reuse the channel meanings and parenting pattern after measuring the new
figure. Do not assume every minifigure-shaped DAT has separate joints or the
same limb geometry. Several attractive clips have known mesh crossings; read
the clearance page before selecting a motion as a mechanical precedent.
