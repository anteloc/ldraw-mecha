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

## Alternative process branch

The diagram workflow adds source preparation, optional connection evidence and
mechanism views to the existing motion contract. **58 Python tests pass**.
Mermaid CLI 12.0.0 rendered all seven provisional 106 diagrams, all 47 provisional
W16 diagrams, the adopted W16 motion diagram, and a hostile-label escaping
fixture. The 47 W16 views reflect incomplete initial grouping, not 47 confidently
identified mechanisms.

Evidence is under `output/alt-process/`. `106/rig/workflow-check.json` verifies
loading a draft without rigging, selecting diagram identities in Blender,
authoring a measured roof joint, applying it to the same imported GLB, refreshing
embedded diagrams, nonzero motion, animation preservation, sampled clearance
and reopening. Fresh-process reopening and lifecycle reports pass as well.
The initial positive connector axis closed the roof into the car; choosing the
opposite axis for outward opening removed the sampled new crossings. This
illustrates why connector alignment alone cannot choose a safe control direction.

`w16/motion.json` adopts the existing W16 recipe while preserving discovered
connections and source identities. Its 33-step sweep, background Blender build
and fresh-process reopening pass. `hatch/preparation.json` records a full
prepare/diagram/convert pass for the standalone 928 hatch using its existing
motion plan. These cases validate the alternative workflow and existing
kinematics, not general automatic mechanism inference or collision-free motion.

## 10265 Ford Mustang B-model

`output/10265-v2/` holds a full prepare/review/adopt/rig pass for
`10265-1_B-Model.mpd` (1497 parts) using recipe `10265`. It replaces an earlier
study whose discovery never ran: that run used the default `--contact-limit 300`
against 1441 library parts, so `preparation.json` recorded
`contacts: "not run"`, every connection stayed a candidate, and 232 of 245
mechanism views were single parts. Raising the limit to 2000 lets contacts run
over all 1441 parts and yields 29 contact edges plus the 16T/40T mesh.

The steering is a pitman crank rather than a rack. The steering wheel turns a
raked column, a universal joint passes the rotation to the longitudinal 16T
shaft, the 16T/40T mesh (centres 70 LDU apart, exactly 20 + 50 pitch radii)
turns the crank by -0.4 of the input, and the crank's two towballs push 100 LDU
steering links against knuckles on vertical kingpins. Both knuckle angles are
solved from that closure, so the links carry the motion and both tie-rod
distances are checked numerically; the earlier study left the links static, had
no `anchors` and no `checks`, and so passed its sweep while nothing moved.
Closure holds to 5.5e-4 LDU, limited by the source's own rounded rotation
matrix, and evaluated Blender transforms match the independent evaluator to
2.7e-4 LDU. The linkage is Ackermann: the inner knuckle turns further than the
outer, and near a 36 degree crank angle the outer one reverses at a dead point.

**The rod construction in the Blender adapter was wrong for this linkage.** A
single `LOCKED_TRACK` only rotates a rod about one fixed axis, which reproduces
the contract exactly for a rod that stays in a plane, such as the 42000 rack tie
rods, but not for a spatial link. Here the crank towball rises about 6 LDU as it
swings while the knuckle ball stays level, so the rod must tilt out of plane;
the adapter disagreed with the contract by up to 8.5 LDU. Rods now aim with
`DAMPED_TRACK` and take their roll from a `LOCKED_TRACK` against a reference
that follows the start anchor at a constant axis offset, which is exactly the
contract's "local Y follows the rod, local Z is the declared axis projected
perpendicular to it". Rod error dropped to 2.3e-5 LDU. The 42000 (two tie rods,
eight conrods), 42083 W16 (sixteen conrods) and 106 rigs were rebuilt and still
pass, so the change is a fix, not a regression.

### Clearance

All four wheel controls are **clean** through a full turn. The other two are
not, and their ranges were set by these sweeps rather than by connector
alignment:

- `steering` (+-0.18 rad at the wheel, 4.1 degrees of crank) reports six pairs.
  One, `0/307`-`0/308`, is inherent: a universal joint cross swings on two
  perpendicular pins and no single revolute can express it, so the cross is
  carried by the column and still meets the other joint end. One,
  `0/90/16`-`0/90/19`, is a checker artefact: the knuckle and its own stub axle
  are rigidly linked by parenting and were measured at 1.9e-6 relative motion
  over the full sweep, so they cannot newly cross. The remaining four are
  measured contact. The crank's towballs rest flush against the open-centre
  chassis brick `0/0/21` and clear the suspension arms above them by about
  3 LDU, so the crank has only a few degrees in either direction. That is a
  property of the source model, not of the rig, and is why the declared travel
  is small.
- `valve_covers` (0 to 0.15 rad) reports two pairs, both against `0/284/2`, the
  embedded flexible hose. Flexible parts are outside this contract's scope. The
  opening sign was chosen by sweeping both directions: the opposite sense drives
  both covers straight into the block and the hoses within one step.

Sampled crossings do not prove continuous clearance, and a clean sweep does not
prove a mechanism is physically free.

### Not rigged

The doors have a verified vertical hinge line: two `2429`/`2430` plate pairs per
side share x = +-160, z = -160, which fixes the axis without guessing. They are
still not rigged. The `Sill Panel Door` submodels interleave the static sill panel
with the door leaf; the original study lacked contact evidence to split them.
That discovery result was affected by rounded placements, as described below;
it must not be attributed to missing System hinge metadata. The bonnet and trunk lid
contain no hinge parts at all. The rear axle worm and 8T gear, the gearshift and
the supercharger were not resolved to a measured output. These are findings, not
implemented mechanisms.

### Discovery correction after the second attempt

The root and nested rounded rotations suppressed pyldraw3 contacts. Analysis now
projects near-rigid occurrence frames onto orthogonal matrices while preserving
source transforms, IDs and translations. Full-model comparison gives 29 raw
contact records versus 921 corrected records; all 25 catalogued straight axles
gain axle-in-hole evidence. That denominator excludes axle pins and joiners.
The corrected records include 18 hinge contacts and 211 stud contacts. The
earlier absence of those contacts was not evidence that these mechanisms lack
connector metadata.

A finite worm/spur profile finds `0/104/37` to `0/104/41`; its provisional view
also contains the knob, both shafts and both liftarm cranks. The crank-to-rear-frame
surface coupling remains unverified. Six `32198` bevel gears remain unsupported,
and three library-internal connector diagnostics keep inspection incomplete.
No new rig or clearance claim follows from this discovery repair.

Evidence: `output/10265-discovery-audit/` contains raw/corrected contact reports,
the new source-only study, a rendered adjuster candidate diagram, an audit of the
old study, and recipe adoption/sweep/asymmetric-evaluation reports. Adoption keeps
90 unresolved provisional views alongside six planned control views. The pure
suite passes 82 tests, including new matrix, worm near-miss and omission regressions.
The new worm diagram parses and renders with Mermaid CLI. Blender adapters and
the existing saved scenes were not changed during this correction; source-only
checks do not validate new Blender motion. See [discovery quality](discovery-quality.md).
