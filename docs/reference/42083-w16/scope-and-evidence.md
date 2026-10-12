# Scope, evidence and provenance

This is a worked reference for the selected W16 engine rig, reviewed on
**2026-10-06**. It covers one input shaft, three gear meshes, three crankshafts
and sixteen piston/rod linkages. The surrounding car, gearbox, valves,
combustion, lubrication and engine dynamics are outside this example.

## What was checked during curation

| Check | Result | Meaning |
| --- | --- | --- |
| Source/plan validation | Pass | The saved plan still matches its source hash and has valid identities and motion definitions |
| Current recipe rebuilt from parsed source | Exact match for controls, signals, bodies, anchors and checks | These documents describe the same motion as the selected saved plan |
| Standalone extraction compared with selected original section | Identity, type, parent, transform and colour fields match | The supplied extraction represents the selected engine without changing its placement |
| Geometric gear discovery | Exactly three candidates | Parallel axes, planes and centre distances support the recorded gear pairs |
| Signed mesh equations | Pass at nonzero positive/negative inputs, limits and a clamped input | The plan's shaft angles match the three ratios after normalizing axis conventions |
| Rod closure sweep | 97 positions across -4*pi..+4*pi; all 16 checks pass | Maximum error about 3.6e-14 LDU in the ideal linkage equations |
| Exact stroke extrema | All 16 pass | Central strokes about 19.999402 LDU; lower strokes 20 LDU |
| Geometric cycle checks | Pass | Linkages return after 6*pi/5 input radians; all shaft frames return after 6*pi |
| Targeted Python tests | 11 passed | W16 motion, inventory, mesh geometry, near misses and rotated-crank evidence |
| Saved Blender file reopened in a background process | Blender 5.2.2 LTS; embedded motion matches | Confirms the selected file contains the documented rig |
| Fresh Blender transform checks | Five cases pass at 0.002 LDU tolerance | Rest, drive 0.37, -2.9, 7.3 and out-of-range 20 agree with the portable evaluator |

The fresh Blender check's largest moving/static matrix discrepancy was
approximately 9.16e-5; maximum rod-length error was approximately 2.06e-5 LDU.
The action was inspected and control animation restored after diagnostic
sampling. The source blend was not saved or rebuilt during this review.

The saved controller is `CTRL_w16_42083`. Its action has linear keys at frames
1/120/360/480 with values 0/+4*pi/-4*pi/0, within float32 storage precision.
The scene spans frames 1–480 at 24 fps. The review checks selected control poses;
it does not claim every animation frame or subframe was independently verified.

## Evidence locations

| Evidence | Artifact |
| --- | --- |
| Fresh measured dimensions, phases, strokes, ratios and reproduction | [review.json](../../../examples/reference/42083-w16-reference-review/review.json) |
| Source-only reproduction script | [review.py](../../../examples/reference/42083-w16-reference-review/review.py) |
| Fresh mesh candidates | [gear-meshes.json](../../../examples/reference/42083-w16-reference-review/gear-meshes.json) |
| Fresh rotated-crank connector lines | [coaxial.json](../../../examples/reference/42083-w16-reference-review/coaxial.json) |
| Fresh saved-scene inspection and transform checks | [blender-check.json](../../../examples/reference/42083-w16-reference-review/blender-check.json) |
| Read-only Blender inspection script | [inspect_blend.py](../../../examples/reference/42083-w16-reference-review/inspect_blend.py) |
| Original plan sweep | [sweep.json](../../../examples/reference/42083-w16/sweep.json) |
| Original Blender / reopen checks | [blender-check.json](../../../examples/reference/42083-w16/blender-check.json), [reopen-check.json](../../../examples/reference/42083-w16/reopen-check.json) |
| Original clearance samples | [clearance.json](../../../examples/reference/42083-w16/clearance.json) |
| Source and converted identity binding | [inspection.json](../../../examples/reference/42083-w16/inspection.json), [conversion.json](../../../examples/reference/42083-w16/conversion.json) |
| Exposed mechanism previews | [rest](../../../examples/reference/42083-w16/pose-rest.png), [quarter-crank pose](../../../examples/reference/42083-w16/pose-crank-quarter.png), [half-crank pose](../../../examples/reference/42083-w16/pose-crank-half.png) |

Run `.venv/bin/python examples/reference/42083-w16-reference-review/review.py` from the
repository root to reproduce the source review. Connector expansion requires
the configured LDraw library and supplied shadow data.

The later toolkit workflow tests also used this engine:
[workflow-check.json](../../../examples/reference/toolkit-improvements/w16/workflow-check.json).
That report covers animation/action restoration, NLA/driver preservation,
exception cleanup, reversible visibility, notes-only updates and duplicate import
isolation. It belongs to a separate generated copy and is not a fresh lifecycle
test of this selected blend.

## What the clearance result actually says

The retained original report sampled 97 input positions with a 0.4 LDU surface
shrink and 0.05 LDU touching tolerance. It excluded eight rest pairs and 24 touching
pairs, in addition to same-rigid-body comparisons, and reported
`no_new_surface_crossings=true`.

This is useful sampled evidence. It does not establish containment inside bores,
continuous collision freedom between samples, correct gear tooth phase,
bearing retention or physically valid contact forces. No new clearance run was
needed to create these references, and none was performed.

## Important distinctions for reuse

- **Inventory beats the annotation here.** The section says “V8/two crankshafts”
  but contains 223 physical parts, 16 pistons and three rotating crank groups.
  The plan has 36 bodies, 66 moving occurrences, 20 signals and 16 rod checks.
- **A double-bevel part need not form a perpendicular drive.** This input pair
  is parallel and coplanar.
- **A mesh sign is meaningless without its axes and ordering.** The discovery
  report and plan use different axis conventions for the 24T pairs.
- **The original contact gap is not a disconnected crank.** Fresh coaxial evidence
  supports the central connector lines, while the original reports retain their
  historical missing contacts. Coaxial evidence alone still cannot establish a lock.
- **The cylinder solution is centred and planar.** Source rounding is accepted
  within a stated distance tolerance; intentionally offset bores need another model.
- **Working linkage geometry is not a combustion model.** The phases describe
  the LEGO assembly, not a real Bugatti firing order or four-stroke timing.

## Stable provenance

All six Mermaid diagrams rendered successfully. Documentation checks resolved
47 local links and 79 occurrence references; the gear-train render was also
inspected for readability.

Source attribution: Philippe Hurbain [Philo], CCAL 2.0, retained in both the
original MPD and the standalone extraction. These hashes identify this review.

| Item | SHA-256 or semantic digest |
| --- | --- |
| Source MPD SHA-256 | `72df8a1a852d6584eeba935320de411b9dc9dc23582177336341af68156469db` |
| Plan semantic digest | `0375ef52c91109b6fe0425a9c7fbbddd38f4b03cf63aa897abb4c7fe423469ff` |
| Plan file SHA-256 | `0dec73f2257f550e4bdbdb8a47adc004c017cacef7da09c321493f28f04b5669` |
| Extracted MPD SHA-256 | `fd899ff744d5935063b8d37257aef4eb987862ea67094ca2fb78f25b0e204341` |
| Recipe module SHA-256 | `282dc8ba97c1e76161b3c6363ad1228da14a48b4f7fde86e8e4e8a40402e8f7c` |
| Selected blend SHA-256 | `1a39cc0777372b09efee75f25082dc046f84eef77c8a0ebd4d20234f9779d287` |

The references are hand-curated. A changed source, recipe or saved plan needs
a review of the affected claims and diagrams. Selected evidence and playback
assets are retained in the [example archive](../../../examples/README.md),
including the source files needed to reproduce the review without `output/`.

[Back to engine index](README.md)
