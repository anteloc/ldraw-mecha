# Scope, evidence and provenance

Reviewed on **2026-10-07**, from the five-mechanism output selected by the user
and its implementation in commit `079b6c8`. The supplied W16 review directory
belongs to the [earlier engine case](../42083-w16/README.md); the new bundle is
[archived 42083-mechanisms](../../../examples/reference/42083-mechanisms).

Fresh curation evidence lives separately in
[archived 42083-mechanisms-reference-review](../../../examples/reference/42083-mechanisms-reference-review).
The selected models, plans and saved scene were not rewritten. New diagrams
were reconstructed from source geometry, executable motion and checks.

## What is reusable

| New reference | Supported result | Boundary |
| --- | --- | --- |
| [Wing lift](wing-lift.md) | Orientation-preserving parallelogram translation and closed rear rods | Fixed upper axis assumed; no key actuation or tilt |
| [Paddle stepper](paddle-stepper.md) | Moving-hinge pawl geometry on its driving branch and coordinated shift demonstration | Paddle does not drive ratchet automatically; detent completion and surface contact unsolved |
| [Gearbox cascade](cascaded-gearbox.md) | Four-state first stage, carry to a second stage, eight distinct ideal ratios | Two added gears; prescribed dwell/carry and engagement windows |
| [Independent rigs](independent-rigs.md) | Mapped standalone extracts, explicit interface assumptions and root-relative scene layout | Separate rigs are not a connected vehicle simulation |

The AWD, D/N/R and door extracts are checked variants of existing mechanism
types. Their differences are indexed in the [case overview](README.md), rather
than duplicating the earlier differential, Cardan, fork/ring and hinge recipes.

## Artifacts and fresh checks

The [source review script](../../../examples/reference/42083-mechanisms-reference-review/review.py)
reads the original source, plans, maps and contact evidence. Its
[report](../../../examples/reference/42083-mechanisms-reference-review/review.json) records
full artifact hashes, semantic plan digests and measured errors. It checks:

- All retained source leaves against extracted references, colours and matrices;
  reconstructed gears remain separately identified.
- Current builder motion against saved controls, signals, bodies, anchors and
  checks: all five match exactly.
- Sixty-five samples per control, plus the builder's 3 asymmetric drivetrain
  cases, all 16 gearbox detents and all 3 D/N/R states. Gearbox checks cover
  23 mesh relations and selected clutch locks; D/N/R has 10 mesh relations.
- All 480 timeline frames per rig for declared closures and signal-step limits.
  Those limits are diagnostics, not proof of subframe continuity.
- Wing translation/orientation at nonzero travel and limits; closure error stays
  below 0.000001 LDU. Pawl checks compare transformed body tips with the projected
  circle and signal endpoints on both driving branches.

| Extract | Physical parts | Moving parts | Bodies | Signals | Distance checks |
| --- | ---: | ---: | ---: | ---: | ---: |
| Drivetrain | 337 | 82 | 24 | 57 | 0 |
| Gearbox | 397 | 151 | 35 | 73 | 0 |
| D/N/R | 260 | 49 | 8 | 11 | 0 |
| Doors | 114 | 92 | 2 | 4 | 0 |
| Wing | 119 | 50 | 7 | 22 | 3 |

Zero distance checks means no closure evidence from a generic sweep for that
plan. Mesh/clutch claims use the separate mechanical verifier, not its sweep's
pass flag alone.

A fresh Blender **5.2.2 LTS** process reopened
[mechanisms.blend](../../../examples/reference/42083-mechanisms/mechanisms.blend) with Python
auto-run disabled. The [reopen report](../../../examples/reference/42083-mechanisms-reference-review/reopen-check.json)
checks all five roots, saved motion definitions, actions, keyed controls and
evaluated transforms at seven frames each (35 frame/rig samples). All pass at
0.002 LDU tolerance; the largest moving-matrix error is about 0.000464 LDU.
The case script now raises on a failed report so a check cannot silently exit
successfully after reporting failure.

The generic lifecycle check was extended to test translated and
translated/rotated model roots. Fresh [wing](../../../examples/reference/42083-mechanisms-reference-review/wing-lifecycle.json)
and [W16](../../../examples/reference/42083-mechanisms-reference-review/w16-lifecycle.json)
checks pass, including nonzero inputs, rebuild/removal, rest restoration,
clamping and two-copy isolation. This exercises the rod roll-reference fix from
the selected commit. The pure Python suite passed **141 tests**, including a
section-extraction regression independent of saved output bundles.
All six new Mermaid blocks rendered successfully; document links and 64
occurrence references resolved. A deliberately tighter reopening tolerance also
confirmed that a failed report produces a nonzero process exit.

## Clearance and assumptions

Existing clearance reports were reviewed rather than reclassified as physical
proof. The isolated doors, wing and drivetrain reported no new sampled surface
crossings. Gearbox and D/N/R reports contain crossings at rings, forks, catches,
pawls, knobs and detent context. The builder interprets several as intended
contact, but the kinematics do not resolve their surfaces or forces.

The separate context studies retain surrounding bodywork. Door samples through
1.65 rad were clear under the checker, with a crossing at 1.7; adopted travel is
1.2. Wing samples through 0.40 were clear, with two crossing pairs at 0.45;
adopted travel is 0.4. Context selection may omit obstacles. Rest-contact pairs
and within-body pairs are excluded, containment is untested, and discrete poses
cannot establish clearance between samples.

Other qualifications retained from the implementation:

- The D/N/R forward mesh is a 56.57 LDU diagonal versus 55 nominal; its use is
  a builder assumption. Forward holds the absent gearbox in third gear.
- Drivetrain wheel/hub transfer uses a CV assumption. Suspension and steering
  are static; the main shaft couples the two differentials without a centre diff.
- The gearbox reconstruction and official-inventory rationale are not
  independently established here. Its numerical ratios validate the adopted
  network, not the intended physical set.
- Pawl-to-roller contact, detent completion, rubber-band action, backlash and
  synchronizing teeth are not solved. The wing's upper-axis constraint is assumed.
- The opening animation and independent shaft timelines demonstrate motion;
  they do not model forces, whole-car dynamics or coupling between extracts.

## Identity and reproducibility

Original source SHA-256:
`72df8a1a852d6584eeba935320de411b9dc9dc23582177336341af68156469db`.
Selected FILE: `42083 - chiron.ldr`, Philippe Hurbain [Philo], CCAL 2.0.

| Plan | Semantic digest prefix |
| --- | --- |
| Drivetrain | `f1f7db818869103f` |
| Gearbox | `277c704e6f129eb4` |
| D/N/R | `1324acd396de9ceb` |
| Doors | `9be83ee11a426a01` |
| Wing | `d1f5e2ee85f84558` |

Full digests and file hashes are in the fresh review report. Reproduction uses
[build_42083_mechanisms.py](../../../scripts/build_42083_mechanisms.py),
[timeline_42083.py](../../../scripts/timeline_42083.py),
[the scene builder](../../../scripts/blender/animate_42083_mechanisms.py) and
[the reopening checker](../../../scripts/blender/check_42083_reopen.py).
The source builder needs the saved mechanical contact evidence; the scene builder
needs the five plans and GLBs. Include those artifacts when sharing this case.
Keep new runs in separate output directories; review affected documentation if
source, equations, state timing or assumptions change.
