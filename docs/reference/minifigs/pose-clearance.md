# A transferable clip still needs pose clearance

The important result here is the distinction between three checks: an Action
can address the target's channels, the rig can reproduce their transforms, and
the target meshes can avoid unwanted crossings. Passing the first two does not
establish the third.

The saved [own-clip report](../../../output/minifigs/clearance-summary.json)
contains new surface crossings for three clips:

| Clip | Reported area |
| --- | --- |
| `MF02_spaceman.wave` | Raised arm/hand against head and helmet |
| `MF08_athlete.high_jump` | Raised hands/arms against head and hair |
| `MF10_diver.swim_crawl` | Windmilling arms/hands against head |

Seven other figures have no new crossings in the sampled poses of their own
three clips. This is a statement about those samples and exclusions, not a
collision-free certificate. Full-range joint sweeps also find crossings for
many held items. The athlete and diver pass the saved **17-step single-joint
sweep** yet fail combined animation sampling: a coarse sweep across a large
angle range can miss the intervening poses.

## Check the actual animation and the actual accessories

[check_minifigs_clearance.py](../../../scripts/blender/check_minifigs_clearance.py)
imports each figure into a background scene and performs:

1. Seventeen samples per joint, with other controls at defaults.
2. Combined joint poses from the clips, sampled every six frames.
3. A second pass with 1.5 LDU surface shrink instead of the default 0.4.

The second shrink setting is a sensitivity diagnostic, not a penetration-depth
measurement. Both passes exclude same-body and rest-contact pairs, do not test
containment, and leave whole-figure staging unapplied. Ground, props and other
figures are outside this report.

The reusable API already accepts combined poses:

```python
# Inside Blender, with an explicit rig context and its plan:
from ldraw_mechanisms import blender_tools
poses = [dict(label=f"{clip.id}@{f}",
              controls={j: clip.value(j, f) for j in mc.JOINTS})
         for f in range(1, clip.frames + 1, 6)]
result = blender_tools.check_clearance(plan, rig=rig, poses=poses)
```

Here `mc` and `clip` come from the [clip library](animation-clips.md). Include
endpoints, key transitions and denser/subframe samples where motion passes an
obstacle; the example's six-frame step alone is not enough to prove clearance.
The API temporarily releases animation and restores its state; an explicit root
or rig prevents sampling the wrong copy. See the [API guide](../../discovery-and-blender.md).

With `--all-clips`, the case script samples all thirty clips on every figure.
The [compatibility matrix](../../../output/minifigs/CATALOG.md) is therefore
more informative than a simple “same rig” flag. Long weapons, tools and wide
headgear change which gestures are usable. The three bare-handed figures have
27 of 30 clips without new sampled crossings; do not generalize that count to
figures with equipment.

## Choose a path, not just clear endpoints

In this implementation, the tilted shoulder swings a raised hand inward. The
original review identifies roughly 2.1–2.9 rad as the problematic overhead band;
held poses around ≤2.0 rad or near π were used for some gestures. Those are
case observations, not universal safe limits. A clear raised pose can still
have a crossing on the way up. The three clips above retain such crossings.

Accessory sequencing matters as well. `wizard().cast_spell` raises the staff
before rolling it outward; rolling it while low would swing its lower end into
the leg. Adapt timing and travel to the target, rerun pose checks, and record
remaining crossings before describing a result as a reference. If a visually
useful motion intentionally keeps an impossible pass-through, label it as an
animation approximation rather than expanding the claimed physical joint range.
