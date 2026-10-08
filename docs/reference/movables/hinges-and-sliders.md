# Locate the joint, then choose its travel

Part of the [movables reference](README.md); [evidence and limits](scope-and-evidence.md).
The useful pattern is a fixed mount, an explicit moving group and a measured
revolute or prismatic joint. A category name supplies a candidate, not the pivot.

```mermaid
flowchart LR
    candidate["Category or model search"] --> placement["Connector frames or relative placement in a source model"]
    placement --> joint["Measured pivot / guide axis"]
    joint --> meaning["Nonzero test: positive input opens or lifts"]
    meaning --> context["Sweep with frame, neighbours and attached parts"]
    context --> plan["Body, signal and qualified travel in plan"]
```

## Use the strongest available placement evidence

`Build.attach()` in [the builder](../../../scripts/build_movables.py) aligns a
selected child connector with a parent connector, checking parallel axes and
composing full source transforms. For missing or suspect metadata,
`Build.reference()` compares the relative placement `inverse(parent) * child`
with occurrences in an annotated model. Compare both translation and rotation;
a small translation residual alone does not establish the same opening pose.

| Case and moving occurrence | Joint in the saved source frame | Evidence and qualification |
| --- | --- | --- |
| S01 house door `2`, `60616b` | origin (-32, -74, 5), axis (0, 1, 0); `door` 0..1.75 rad | Frame `60596` hinge; 10185 uses variant `60616a` with matching relative placement |
| S06 cabinet leaves `2`, `3`, both `2043` | origins (-52, -33, -16), (52, -33, -16); axes +Y, -Y; each 0..1.9 rad | Mount `2042` has no usable hinge feature; placement from 3636, axes from the doors |
| S09 trap `6`, `30042` | origin (-50, -128, 26), axis +Z; `trap` 0..1.95 rad | Placement from 6769/7657, axis from trap pins; frame clips are not confirmed as mates |
| S14 sliding door `3`, `4511` | origin (-18, -67, -13), direction +X; `slide` 0..150 LDU | No door connectors; placement and guide direction from 7735 and its `4510` rails |

Coordinates use LDU, -Y up and front -Z. IDs are local to each scenario's
`source/scenario.mpd`. Exact roles and frames are in its `source/parts.json`
and `plan.json`, for example the
[cabinet plan](../../../examples/reference/movables/S06_double_cabinet/plan.json)
and [slider identity map](../../../examples/reference/movables/S14_sliding_door/source/parts.json).
The mirrored cabinet axes make positive values open both leaves. An evaluator
test chooses each sign; copying one axis sign to both sides would reverse one.

A connector used to locate a drawer need not point along its travel. S05's
generic slot locates the drawer; the builder explicitly assigns the slide
direction along -Z. Slider directions come from the guide geometry.

## Connector metadata and context can mislead

The studied `4275b`/`4276b` shadow hinge frames run along the plates rather than
their finger line. S17's bucket uses the mating `4531` tile's axis and set 6532
placement instead. Its saved group is occurrences `15`, `17`, `18` (two hinge
plates plus bucket), about (-10, -20, 170) along -X with `tip` 0..1 rad. This is
a measured workaround in this snapshot, not a global edit to the library.

Opening direction must clear the frame. S02's casement panes open on the back
side of their frame; the scenario faces them toward the viewer by rotating the
assembly. S12's top-rear canopy hinge sends its lower edge forward and up, so
the mock nose is tiled flat. Hinge tops also overhang their pivots: S16 places
the boom on a riser on the front row of `6134` to avoid its rear overhang dipping
into the base.

Limits were chosen and narrowed against these particular mock contexts. They
are not measured mechanical stops. Include trim, panes, handles and supports
in the relevant moving/static groups and inspect intermediate poses, not only
open/closed endpoints. A roller shutter that bends into a guide cannot be one
rigid sliding body: candidates `4218b` and `6155` were explicitly excluded.

Missing mate evidence can be resolved with geometry and an existing assembly,
but must remain qualified. S07's chest relies on connector placement without
an annotated-model precedent; S03's shutters differ by roughly 3 LDU from the
closed placement in 6350. Preserve those observations when adapting the examples.
