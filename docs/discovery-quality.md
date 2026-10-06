# Discovery quality and missing mechanisms

Start with evidence, check its coverage, then plan motion. Neither a successful
command nor a dense connection graph establishes that every mechanism was found.

## Prepare and check the report

```sh
./ldraw-mecha prepare data/models-annotated/10265-1_B-Model.mpd \
  --contact-limit 2000 --no-glb --output output/new-10265-study
./ldraw-mecha audit output/new-10265-study/plan.json \
  --output output/new-10265-study/audit.json
```

Preparation prints a compact summary; full evidence is in `preparation.json`
and `plan.json`. Read these before choosing rigid bodies:

- Contact counts by kind, tested parts and contacted parts.
- Straight axle count, how many have axle-in-hole evidence, and the missing IDs.
  The axle denominator uses catalog descriptions beginning “Technic Axle” followed
  by a numeric length; axle pins, joiners and axle-hole supports are excluded.
  This is a useful sanity check, not an inventory of every shaft-like feature.
- Placement normalization, unsupported transforms and pyldraw3 diagnostics.
- Skipped searches, isolated mechanical candidates, unclassified parts and
  unsupported gears. The 300-part default is a budget, not sufficient full-model
  coverage for a large car; raise it up to 2000 or inspect bounded sections.

Zero axle coverage in an assembled drivetrain calls for investigation. A warning
also appears below 50% coverage for selections of at least four straight axles;
that threshold is a heuristic. A selection can intentionally omit its bearings.
Compare connector frames, transforms and surrounding parts before drawing a
mechanical conclusion. Missing connectors can hide real mechanisms; contacts
alone cannot distinguish a rigid axle coupling from a freely rotating bearing.

## Embedded copies of library parts

Converted models often embed pre-release parts as DATs titled only by their
number (`0 18575`). The manifest now labels such an occurrence with the library
title and `library_alias`, so role and gear discovery see it; its embedded
geometry is still never replaced and `gear-meshes` lists it as unsupported with
reason `Embedded copy of …`. In 42110 this exposed ten 20T gears, a clutch gear
and the rotary catch that previously appeared nowhere in the report. Measure
such meshes explicitly (library connector frames on the occurrence's own matrix).

## Rounded source matrices

pyldraw3 1.7.0 rejects connector metadata under invalid scale/shear. A rotation
rounded to three decimal places can trigger this without an occurrence-level
diagnostic. In 10265, the root's `0.999/0.052` coefficients introduce a scale
of about 1.000352, hiding axle contacts throughout the car. The rear-wheel
subassembly has another rounded rotation.

The toolkit uses the nearest orthogonal 3×3 matrix for **analysis only** when
every singular value differs from one by at most 0.002. This is a dimensionless
rounding bound; positional mating tolerances remain those of pyldraw3. The
projection uses NumPy's SVD, preserves reflections and translations, and applies
to each composed physical occurrence, including nested rotations. Connector,
contact, coaxial and gear analysis share this policy.

The manifest, source files, identities, hashes, GLB transforms and rig rest poses
remain untouched. Larger scale/shear is left unchanged and reported as
unsupported by the correction policy; gear inference excludes those placements.
Reflections retain their handedness and may still be disallowed by some connector
metadata. No attempt is made to repair library-internal geometry or connectors.
Small intentional scaling cannot be distinguished from rounding by this test;
affected IDs and correction magnitudes are reported for review.

Use `--raw-transforms` on the four focused commands to compare source behavior:

```sh
./ldraw-mecha contacts data/models-annotated/10265-1_B-Model.mpd \
  --instances 0/104/34 0/104/41 --raw-transforms
./ldraw-mecha contacts data/models-annotated/10265-1_B-Model.mpd \
  --instances 0/104/34 0/104/41
```

These return zero and three contact records respectively. Several records can
describe the same part pair; contact counts are not independent joint counts.
Changing `--section` changes coordinates and occurrence IDs. Use raw comparison
on the same manifest rather than transplanting section IDs into an existing plan.

## Worm drives and surface contacts

`gear-meshes` now has a separate `4716.dat` worm profile: local Z shaft,
single start, nominal pitch radius 10 LDU. Geometry is reviewed against the
[LDraw part](https://library.ldraw.org/parts/9398) and its `s/4716s01.dat` /
`s/4716s02.dat` thread surfaces. The thread extends to ±20 LDU; discovery
conservatively accepts closest-axis stations within ±16 LDU to avoid partial
end threads. Supported mating wheels are the straight spur profiles in
`geometry.WORM_WHEELS`, not every bevel/double-bevel profile in `GEARS`.

A candidate needs perpendicular axes, the expected shortest axis distance, a
contact station inside that finite thread span and agreement with the wheel's
tooth midplane. Results report each residual. The single-start reduction gives
`wheel_per_worm_magnitude = 1 / wheel_teeth`, consistent with
[LEGO Education's worm-gear example](https://assets.education.lego.com/_/downloads/MachinesAndMechanisms_Advancing-With-Simple-And-Powered-Machines_1.0_en-US.pdf).
The signed direction requires review before authoring a driver. Engagement,
tooth phase, friction, backdriving and clearance are not established by this
candidate. Unreviewed worms such as the two-start 32905 remain unsupported.

In 10265 this finds `0/104/37 → 0/104/41`, about 20.007 LDU apart,
with a nominal ratio magnitude of 1/8. Connector evidence joins the input
axle/knob and the output axle/liftarm cranks into one provisional view.

The next link—cranks bearing on beams in the rear axle frame—is still unresolved.
There need not be a mating connector for that contact. Inspect the relevant
surfaces and motion before choosing a linkage, contact constraint or approximation.
If a particular physical part pair is identified visually, record a
`surface_contact` candidate with the observed evidence and the unverified claim.
Do not invent an edge just because connectors are absent. A mechanism view can
span both groups while its coupling remains unknown.

## Keep known mechanisms visible

Record a manually found mechanism immediately as a named view, using physical
IDs, input/output parts and notes describing the missing link. This applies even
when it is outside the supported detector families. For the rear adjuster, a
`ride_height` view should contain the measured drive chain and rear-frame parts;
state that the crank-to-frame coupling is unverified.

Views default to `disposition: unresolved`. After review choose:

- `planned`: reference the controlled bodies and explain the declared motion.
- `deferred`: keep the mechanism and explain exactly what remains undone.
- `static`: explain why this candidate is nonmoving or a false positive.

Each of these needs a nonempty `review` string. For example:

```python
p['mechanisms']['ride_height'].update(
    disposition='deferred',
    review='Drive chain measured; crank-to-beam coupling and travel unverified.',
)
```

Adopting a recipe preserves existing views and adds its control views. It does
not resolve the retained views automatically. Reconcile overlaps using the audit's
controlled/uncontrolled part lists; supports may legitimately remain static.
When replacing previously planned motion, recheck its body/control references.
Regrouping is allowed, but keep all known candidates accounted for.

```sh
./ldraw-mecha audit output/new-10265-study/plan.json --require-reviewed
```

The strict audit exits 1 for unresolved views, unaccounted discovered mechanical
parts, or planned views without a control. An explicitly deferred view remains
visible and may pass that **scope review**. This is not a completeness,
clearance or feasibility test; delivery must list unresolved/deferred mechanisms
and outstanding discovery warnings alongside the implemented controls.

## Regression evidence

Source-only outputs are under `output/10265-discovery-audit/`; the old
`output/10265-v2/` artifacts are not rewritten. With this library and source:

| Evidence | Raw placements | Analysis correction |
| --- | ---: | ---: |
| Contact records, 1441 parts | 29 | 921 |
| Straight axles with axle-hole evidence | 0 / 25 | 25 / 25 |
| Axle 9 ↔ 8T | 0 | 3 |
| Axle 9 ↔ liftarm crank | 0 | 1 |
| Axle 5.5 ↔ worm | 0 | 3 |
| Steering 40T ↔ axle | 0 | 1 |

The corrected study retains six unsupported `32198.dat` bevel gears and three
library connector warnings; it does not claim complete discovery. Tests cover
nested frames, arbitrary nonzero rotations, reflections, genuine scale/shear,
finite worm near misses, retained manual/deferred findings, and nonzero motion
after adopting a recipe. Existing F1/W16 kinematic tests remain applicable.
