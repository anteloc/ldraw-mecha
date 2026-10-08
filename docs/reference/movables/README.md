# Movable elements: doors, windows, lids and slides

Reviewed **2026-10-08**, from the twenty scenarios and sixty clips introduced in
commit `036c31e`. The preserved [example bundle](../../../examples/reference/movables)
contains the sources, plans, clips, checks, previews and
[movables.blend](../../../examples/reference/movables/movables.blend). The
[catalog](../../../examples/reference/movables/CATALOG.md) lists every scenario
and movement style. Working copies remain disposable under `output/`.

| Reference | Reusable technique |
| --- | --- |
| [Hinges and sliders](hinges-and-sliders.md) | Placement from connectors or an existing assembly, semantic signs, limits and missing metadata |
| [Dependent motion](dependent-motion.md) | Slewing crane with a plumb hook; forklift slide with a compressing spring |
| [Motion styles and scenes](motion-styles-and-scenes.md) | Eased opening, bounce, overshoot, paired leaves, clip transfer and independent scene evaluation |
| [Scope and evidence](scope-and-evidence.md) | Reproduction, measured claims and clearance qualifications |

The catalog includes a house door, casements, shutters, gate, cupboards, chest,
mailbox, trap door, car doors/roof, canopy, forklift, sliding shed door, radar,
crane, tipper, barrier, drawbridge and levers. The context walls, bases and
vehicles are mock constructions. Existing annotated models establish several
pair placements; they do not certify each new mock assembly or motion range.

Open the blend's `Catalog` scene for the grid, or its twenty individual scenario
scenes for close inspection. Each has its own controller `CTRL_movable_xx_*`.
Three NLA clips occupy 1–144, 161–304 and 321–464 at 24 fps on a 480-frame
timeline. Mute a controller's animation before using its properties manually.
Angles are radians and translations LDU. Positive meanings belong to each plan.

The sources are [build_movables.py](../../../scripts/build_movables.py) and
[movable_clips.py](../../../scripts/movable_clips.py); scene construction is in
[animate_movables.py](../../../scripts/blender/animate_movables.py).
These use the existing motion contract, not a separate rig format. For an
opening driven by a shared gust rather than an authored opening gesture, see
[wind response for other objects](../plants/wind-responses.md#apply-it-to-other-objects).
