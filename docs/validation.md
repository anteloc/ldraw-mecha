# Validation and evidence limits

Check the declared kinematics, the Blender implementation and the saved animation
separately. The [workflow](workflow.md) ends with visual review; selected results
can become [curated references](reference/README.md). Neither a plausible render
nor a passing transform comparison proves mechanical feasibility.

## Pure Python checks

```sh
.venv/bin/pytest -q
./ldraw-mecha validate output/study/plan.json
./ldraw-mecha sweep output/study/plan.json --output output/study/sweep.json
./ldraw-mecha audit output/study/plan.json --output output/study/audit.json
```

Tests cover source identities/attribution, parsing boundaries, numerical placement
correction, discovery coverage, search, evidence views, GLB binding, safe motion
expressions and case-specific mechanisms. Preparation tests verify that evidence
survives conversion failure and diagrams are created only by explicit export.

Test meaningful nonzero and asymmetric inputs, limits and relevant selector
states. Check mechanical invariants such as ratios and rod lengths, not just
that evaluation ran. A scope audit checks recorded findings and dispositions;
`--require-reviewed` can pass with explicit deferrals. It does not discover
missing mechanisms or validate their physics.

## Blender checks

Adapter changes require background builds, fresh-process reopening and lifecycle
checks. The original reference scripts remain unchanged. Set `BLENDER_BIN` to
an available Blender executable; generated reports belong under `output/`.

```sh
# Draft inspection -> measured roof joint -> rig on the same imported 106 model.
./ldraw-mecha prepare data/models-annotated/106-1.mpd --output output/check-106/study
"$BLENDER_BIN" -b --factory-startup --python-exit-code 1 \
  --python scripts/blender/check_prepared.py -- \
  --study output/check-106/study/plan.json --glb output/check-106/study/model.glb \
  --output output/check-106/rig

# Verify the saved result in a fresh process, without Python auto-run.
"$BLENDER_BIN" -b output/check-106/rig/rigged.blend --disable-autoexec \
  --python-exit-code 1 --python scripts/blender/apply_plan.py -- \
  --plan output/check-106/rig/plan.json --verify-existing \
  --report output/check-106/reopen-check.json

# Rebuilding, removal/restoration and duplicate-model isolation.
"$BLENDER_BIN" -b --factory-startup --python-exit-code 1 \
  --python scripts/blender/check_lifecycle.py -- \
  --plan output/check-106/rig/plan.json --glb output/check-106/study/model.glb \
  --report output/check-106/lifecycle.json
```

`check_prepared.py` checks draft selection by source ID, measured joint authoring,
import reuse, nonzero poses, animation restoration during clearance sampling,
embedded evidence freshness and reopening. It also checks that inspection creates
no diagram text blocks, cleans up the current root's obsolete generated cache
and preserves unrelated text and other model annotations.

`check_lifecycle.py` checks nonzero defaults, out-of-range controls, repeated
builds, rest-parent restoration and isolation of two imported copies.
It also verifies nonzero motion after translating and rotating the model root,
which catches rod-roll references that accidentally depend on world placement.
`check_workflows.py` exercises callable APIs, controller action/NLA/driver
restoration, exception cleanup, visibility, notes updates and duplicate imports:

```sh
"$BLENDER_BIN" -b --factory-startup --python-exit-code 1 \
  --python scripts/blender/check_workflows.py -- \
  --plan output/42083-w16/plan.json --glb output/42083-w16/model.glb \
  --output output/check-w16-workflows
```

Transform verification compares evaluated Blender results with the independent
plan evaluator. Default positional tolerance is 0.002 LDU; deeply nested models
may need an explicitly reported tolerance because Blender uses float32 placements.
Link checks use their declared tolerances. Reports must retain measured errors
and coverage. The saved rig uses ordinary drivers/constraints and requires no
persistent Python callback to operate.

For baseline example reproduction, use
`.venv/bin/python examples/build_examples.py --blender`. This writes generated
outputs; do not run it over user-selected evidence bundles without preserving
those bundles first.

## Clearance and visual review

```sh
"$BLENDER_BIN" -b output/study/rigged.blend --python-exit-code 1 \
  --python scripts/blender/check_clearance.py -- --plan output/study/plan.json \
  --controls roof --steps 16 --report output/study/clearance.json
```

Choose controls present in the plan. Clearance samples evaluated surfaces,
excludes within-body pairs and pairs already touching at declared control
defaults, and reports new surface crossings. The helper uses a 0.4 LDU normal
shrink and a 0.05 LDU touching-face tolerance. Controller animation and pose are
restored on success or failure.

This test cannot establish continuous clearance, containment or worsening
penetration of already-excluded rest contacts. Inspect reported contacts and
exclusions. Run it before finalizing limitation notes; `update_plan_notes` can
update embedded prose without rebuilding, but the revised JSON/blend must be
saved explicitly.

Use `preview_plan.py` to inspect representative poses and limits. Moving-only
or selective bodywork hiding exposes internal mechanisms without deleting parts.
Check the actual demonstration's frames and transitions: independent control
sweeps do not establish continuity through a gearbox shift. User visual selection
identifies a useful case for curation; cite numerical and geometric evidence
separately for each mechanical claim.

## Studied cases and qualifications

| Example | Declared motion and important limits |
| --- | --- |
| CLI `106` | Doors, roof and rim/tyre groups. Roof/door limits are 75 degrees; the original 90-degree trials crossed surrounding bricks. |
| CLI `928` | Cargo ramp in the complete model uses [-1.25, 0] radians. Further closing meets side hatches; full closing needs coordinated motion outside this example. |
| Standalone `928` hatch | Two parts on a virtual support; [-114 degrees, 0] travel assumes the surrounding obstructions are absent. |
| CLI `42000` | Studied steering, differential and V8, including asymmetric rear wheels and link closures. The supplied speed/path integrator remains specific to the original rig; generic motion operates in place. |
| CLI `42083` | Three geared cranks and 16 pistons/rods in the selected engine. See the [W16 evidence](reference/42083-w16/scope-and-evidence.md) for exact geometry, checked closures and clearance coverage. |
| CLI `10265` | The `output/10265-v2` recipe has four wheel controls, steering and hinged valve covers. It does not implement every mechanism in that model; see below. |
| Defender and standalone suspension | Case-specific builders and animation. See the [Defender evidence](reference/42110/scope-and-evidence.md) and [suspension evidence](reference/42110-suspension-standalone/scope-and-evidence.md) for state/frame checks, geometric approximations and unsupported effects. |
| Chiron independent mechanisms | Wing linkage, paddle geometry, reconstructed eight-speed cascade and familiar drivetrain/selector/hinge variants. See [case evidence](reference/42083-mechanisms/scope-and-evidence.md) for separate controls, imposed contacts and reconstructed parts. |

The `10265` v2 steering range is ±0.18 radians at the wheel; valve covers use
[0, 0.15] radians. Historical clearance checks reported steering contacts,
a rigidly parented knuckle/stub-axle checker artefact, and cover contacts with
an embedded hose. Its universal-joint cross follows an approximation; the later
Mustang builder is a separate implementation. These limitations belong to that
specific recipe and should not be copied onto another implementation unexamined.

The v2 doors, rear ride-height adjuster, gearshift and supercharger remain
unimplemented. Its low contact count was caused by rounded placement matrices,
not proof of missing System hinge connectors. Analysis now corrects near-rigid
frames: the recorded 10265 regression rose from 29 raw contacts to 921 corrected
contacts, including the axle and hinge evidence. A worm/spur candidate was also
found; crank-to-frame surface coupling remains unverified. See
[discovery quality](discovery-quality.md) for measured coverage and source-only
regression paths. A discovery correction does not retroactively validate a rig.

## Evidence storage and scope

Keep current test reports, source/plan hashes, Blender version and previews in
the relevant output bundle. Case reference pages retain provenance and scope;
there is no repository-wide static test-count snapshot to keep synchronized.

The adapter implements declared rigid-body kinematics, equations, rods and
specified deformation approximations. Connector evidence does not classify
mobility; embedded geometry may lack metadata. Forces, friction, backlash,
general closed-loop/contact solving and flexible-material physics remain outside
its guarantees. Container deployment is configurable but untested.
