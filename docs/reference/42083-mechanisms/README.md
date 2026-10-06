# 42083 Chiron: independent mechanism studies

These references document the five animated extracts in
[output/42083-mechanisms](../../../output/42083-mechanisms), introduced in commit
`079b6c8`. Curation date: **2026-10-07**. The earlier
[W16 reference](../42083-w16/README.md) remains the engine example; the directory
`output/42083-w16-reference-review` contains its earlier review evidence.

The new material focuses on mechanisms and techniques beyond that engine and
the existing Defender references. Diagrams describe the implemented motion and
its assumptions; they are not executable plans or contact simulations.

## New examples to reuse

| Reference | Reusable idea | Qualification |
| --- | --- | --- |
| [Wing parallelogram lift](wing-lift.md) | Counter-rotating child body preserves orientation; rear links close by circle intersection | Upper axis is assumed fixed; manual lift only, no key actuation or wing tilt |
| [Paddle, pawls and ratchet](paddle-stepper.md) | A rocking input carries two hinged pawls; choose the reachable driving branch and separate return motion | Paddle and ratchet are independently keyed; detent completion and contact dynamics are not solved |
| [Cascaded gearbox and carry](cascaded-gearbox.md) | Four selector positions drive a second stage once per revolution, producing eight ratios | Two gears are reconstructed in this extract; carry timing and ring dwell are prescribed |
| [Independent rigs and context](independent-rigs.md) | Section-relative extraction, explicit interfaces, separate timelines and movable model roots | The five examples do not transmit motion between their separate controllers |
| [Scope and evidence](scope-and-evidence.md) | Exact plans, checks, provenance and limits | Separates implementation agreement from physical proof |

## Familiar mechanisms in this bundle

| Extract | What differs here | Existing reference to adapt |
| --- | --- | --- |
| `drivetrain` | Locked AWD without a centre differential; 28T carriers drive 20T pinions. Rear Cardans bend about 20.3 degrees; hub coupling is assumed CV | [Differentials](../42110/rear-axle.md), [Cardan joints](../42110/internal-propshafts.md) |
| `dnr` | One ring selects D/N/R. Forward assumes the neighbouring gearbox is in third; signed engine/main increments are D -1.2, N 0, R +3 | [Fork, sliding ring and direction states](../42110/range-direction-gearbox.md), [phase carries](../42110/shift-animation.md) |
| `doors` | Opposite signs about two vertical pillar hinges; side mirrors belong to the door groups. Both controls range 0..1.2 rad | [Measured hinge authoring](../../workflow.md#author-and-test-motion), [context and outward-sign checks](independent-rigs.md#keep-context-when-setting-travel) |

Those mechanisms do not need another full explanation here. Their exact
implementations remain in the [builder](../../../scripts/build_42083_mechanisms.py)
and individual [saved plans](../../../output/42083-mechanisms).

## Identity and controls

Source: [42083-1.mpd](../../../data/models-annotated/42083-1.mpd), Philippe Hurbain
[Philo], CCAL 2.0; selected FILE `42083 - chiron.ldr`. It is unchanged. Coordinates
are LDU, -Y up, front -Z, car's left +X. Angles use radians and directed axes.
Each extraction retains this frame but assigns new leaf IDs. Tables distinguish
**source IDs in that selected FILE** from **extract IDs**; do not use either with
another root selection. Each extract has its own `source/idmap.json`.

Open [mechanisms.blend](../../../output/42083-mechanisms/mechanisms.blend):

| Controller suffix after `CTRL_chiron_42083_` | Main controls |
| --- | --- |
| `doors` | `door_left`, `door_right` |
| `drivetrain` | `drive`, `diff_front`, `diff_rear` |
| `gearbox` | `input`, `shift`, `paddle`, `phase_stage1`, `phase_stage2` |
| `dnr` | `input`, `selector`, `phase_ring_shaft` |
| `wing` | `wing` |

The 480-frame demonstration runs at 24 fps. Phase controls are keyed offsets
for continuity; preserve them when playing the demo. For interactive experiments,
pause or release the controller action before adjusting properties. Updating a
selector alone does not perform the demonstration's phase-carry calculation.

The engine, steering, suspension and wing key/tilt are outside these five rigs.
See the [overview preview](../../../output/42083-mechanisms/previews/overview-f140.png)
and [evidence page](scope-and-evidence.md) before extending any claim.
