# Validation and limits

Validation date: 2026-10-04. Generated evidence is under `output/`; reproduce the
plans and end-to-end builds with:

```sh
.venv/bin/pytest -q
.venv/bin/python examples/build_examples.py --blender
```

The initial 20 Python tests passed. The committed [result summary](validation-results.json)
records counts, source hashes, measured Blender errors and report paths for the
four completed cases. Generated motion, reopening and lifecycle checks passed.

The toolkit improvement pass now has **38 passing Python tests**. Evidence is
under `output/toolkit-improvements/`: `gear-meshes.json` recovers exactly the
three W16 meshes, `coaxial.json` records the rotated central crank's axis
evidence, and `jev-status.json` records a single-request HTTP 402 failure.
The inventory reports 223 physical pieces, 16 pistons, 16 rods and 15 crank
pieces in the engine section. New tests cover FTS identities/syntax/read-only
access, stopping before reranking on 402, nested counts, compact output, and
gear/coaxial near misses including rotated, translated and scaled inputs.

`w16/workflow-check.json` records background Blender 4.5.6 checks of callable
import/verification/clearance, animated control and action-slot restoration,
NLA/driver preservation, injected-exception cleanup, reversible visibility after
reopening, notes-only updates and duplicate imports. Its nine clearance samples
reported no new surface crossings under the exclusions below.
`w16/reopen-check.json` verifies the saved rig in a fresh process;
`w16/moving-only.png` shows its exposed mechanism. `f1-reopen.json` includes
asymmetric wheel/steering inputs; `f1-lifecycle.json` passes rebuild/removal,
two-copy isolation, nonzero defaults and clamping. The original W16 artifacts
and the user's live Blender scene were not changed by this pass.

The study progressed from the 65-part 106 car to the nested 928 spaceship hatch
and then the 1,377-part 42000 Technic car. A two-part standalone 928 hatch checks
that the same contract works without its surrounding model. Existing catalog
files and original Blender scripts were preserved.

| Study | Implemented motion | Evidence |
| --- | --- | --- |
| 106 | Two doors, roof, five rim/tyre groups (including spare) | GLB identity binding, evaluated motion/static transforms, sampled clearance, removal/rebuild and two-copy isolation |
| 928 | Cargo ramp rigid group within the complete model | Nested source transforms, sampled clearance and source-pose offsets |
| Standalone hatch | Same two-part assembly on a virtual support | Section extraction with attribution, GLB conversion and independent control |
| 42000 | Steering gear train, rack, knuckles, wheels, differential, prop shaft and V8 | 32 bodies; two tie-rod and eight conrod closures; asymmetric wheel input; comparison with supplied reference; save/reopen and lifecycle |

Python tests cover repeated occurrences, inherited colour, embedded DAT physical
boundaries, external LDR assemblies, cycle/missing-reference failures, attributed
section extraction, unsafe expression rejection, ownership conflicts, input
limits, gear direction, differential ratios, piston motion and GLB binding
failures. Missing/wrong GLB metadata fails before writing a bound result.

The read-only Blender MCP reference comparison checks 75 scalar results from
the supplied `Steering` and `Drive` implementations. Maximum discrepancy was
about `1.81e-6`; original controller properties and scene contents were left in
place. Analytic link-closure errors in the portable 42000 sweep were below
`6e-14` LDU. Evaluated Blender transforms are checked to `0.002` LDU; declared
link lengths to `0.02` LDU. Reports retain measured errors, not just pass flags.

The live reference scene reports Blender 5.2.2 LTS. The local executable used
for generated rig integration, rendering and reopening reports **4.5.6 LTS**.
The generic adapter has been tested in that executable; inspection of the live
reference does not constitute testing the adapter in 5.2.

## Clearance review

`scripts/blender/check_clearance.py` reuses the supplied BVH helpers. It samples
control poses, excludes parts within one rigid body and pairs already touching
at declared control defaults, and reports new surface crossings. Sampling restores
the controller's animation and pose on success or failure. A projection check in both
part frames filters touching faces within 0.05 LDU; this was necessary because
triangle overlaps flickered at the ramp/wing boundary after GLB compression.
The report lists excluded touching pairs and uses a 0.4 LDU normal shrink.

The initial 106 90-degree limits crossed the rear roof plate and neighbouring
door bricks. The final roof and door limits are 75 degrees and were swept in
5-degree steps. The 928 ramp's source pose already opens toward the ground:
further opening crosses the landing pad. Closing past approximately -1.3 radians
meets the side hatches in their source poses. Its final independent range is
[-1.25, 0] radians. Full closing would require coordinating the side hatches;
the example does not pretend that the ramp can pass through them. The standalone
hatch retains [-114 degrees, 0] because those surrounding obstructions are absent.

These sampled diagnostics cannot prove continuous clearance, solid containment,
or worsening penetration of pairs already in contact. F1 steering preserves the
reference's collision-swept limits; the new adapter verifies its kinematics but
does not repeat a complete mesh collision sweep of all Technic parts.

## Reopening, lifecycle and visual inspection

Typical additional checks (replace the example paths as needed):

```sh
blender -b output/42000/rigged.blend --disable-autoexec --python-exit-code 1 \
  --python scripts/blender/apply_plan.py -- --plan output/42000/plan.json \
  --verify-existing --report output/42000/reopen-check.json
blender -b --factory-startup --python-exit-code 1 \
  --python scripts/blender/check_lifecycle.py -- --plan output/106/plan.json \
  --glb output/106/model.glb --report output/106/lifecycle.json
blender -b output/106/rigged.blend --python-exit-code 1 \
  --python scripts/blender/check_clearance.py -- --plan output/106/plan.json \
  --controls roof door_left door_right --steps 16 --report output/106/clearance.json
```

The lifecycle check exercises nonzero defaults, values outside control ranges,
repeat building, rest-parent restoration and two imported copies. The generated
blend contains ordinary simple-expression drivers and constraints. No driver
namespace registration, frame handler, service or persistent Python callback is
needed. Animation remains editable through the controller custom properties.

Evidence renders use `scripts/blender/preview_plan.py`, which changes only the
background process. Whole-model previews and opened/steered poses were inspected.
The initial background startup cube was visible around the F1 preview; the CLI
now starts an explicitly empty scene. Final previews are `106/open.png`,
`928/open.png`, and `42000/steered.png` under `output/`.

## Scope

Generic analysis returns descriptions, occurrence transforms, connector frames
and bounded contact queries. It does not automatically infer rigid bodies or
solve arbitrary mechanisms. Embedded DATs are preserved as physical parts;
connector/contact inspection of their custom geometry fails explicitly rather
than substituting a library part. Contact status reports pyldraw3's metadata
agreement, not a mobility classification. Offline FTS5/BM25 is the default search;
keyword substring ranking remains available, and semantic discovery uses Jev
when requested. Geometric gear/coaxial reports add candidates, not automatic
coupling or mobility decisions. See the [workflow guide](discovery-and-blender.md)
for supported profiles and evidence limits.

Rigid revolute/prismatic groups, dependency equations and planar connecting rods
are supported. Backlash, friction, forces, suspension compliance, flexible hoses,
shape-key deformation, general closed-loop solvers and whole-car path generation
are outside the generic adapter. The supplied 42000 path integrator remains
available for its original model. Linux/container paths are configurable, but a
Docker image has not been built or tested.

Primary implementation references: [pyldraw3](https://github.com/hbmartin/pyldraw3/),
[LDCad connector metadata](https://www.melkert.net/LDCad/tech/meta), and
[Blender driver documentation](https://docs.blender.org/manual/en/latest/animation/drivers/index.html).
