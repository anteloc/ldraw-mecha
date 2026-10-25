# RCVJ: a regression case for mechanical constraints

The [designer, Thomas Reininghaus](https://rcvj.reininghaus.org/), describes a
double-gimbal constant-velocity joint using two differential angle bisectors in
perpendicular planes. Gear spin alone cannot demonstrate it. The supplied
annotated `RCVJ.mpd` has 127 parts, 34 distinct references and five assemblies;
all physical occurrences match the designer's original LDR by reference, colour
and rest transform within 0.005 tolerance.

```sh
.venv/bin/python scripts/study_rcvj.py RCVJ.mpd --output output/rcvj
# To check an earlier flat-model animation as well:
.venv/bin/python scripts/study_rcvj.py RCVJ.mpd --output output/rcvj-comparison \
  --candidate-plan PATH/plan.json
```

The script preserves source bytes and creates a **draft constraint workbook**,
measured evidence and a deliberately wrong-motion rejection test. It refuses a
different hierarchy/part layout rather than silently reusing IDs. Candidate
plans are remapped by physical reference, colour and rest transform; ambiguous
matches fail. This is a diagnostic study, not a motion-ready reference rig.

## Concrete failure modes

| Parts in this source | Finding | Required treatment |
|---|---|---|
| Side gears `9/14`, `9/16`, both `3648a` | Local Z transforms to approximately world X; 62.250 LDU axial and only 1.752 LDU radial separation | Opposed approximately coaxial gears, not an external spur mesh |
| Shafts `56`, `38` and those gears | Cross-axle interfaces | Keep gear and keyed shaft relative pose fixed |
| Gears `9/1`, `9/2` and shafts `37`, `27` | Approximately world Z axes | Constrain their own shafts; do not use global Y spin |
| Cams `9/4`, `9/5` and axles `2`, `1` | Approximately world Y at x ≈ -51/+53; occupied cam holes offset 10 LDU | Use selected holes, not a common X axis or cam origins |
| Input `0/6`–`5/10`, output `0/0`–`0/5` | Keyed couplings, approximately Y | Rotate the rigid assembly about the same shaft line |
| `3749` axle-pins | Keyed +X and round -X sections | Shaft lock and bearing rotation can coexist on the same pin |
| `3650c` crowns | Tooth band lies at local Z=-6..0 | Review crown geometry, face and contact separately from spur discovery |
| `6575` cam alias | Wraps `6575a` with a 180° Y rotation | Compose alias transforms; preserve occupied-hole coordinates |

The prior animation had **zero closure checks**. Adding ten keyed interfaces
and two carrier bearings (22 checks) rejects it at 0.371, 1.13 and -2.27 radians:
fourteen checks fail at each phase. Four gears turn independently of their keyed
shafts, cam shafts separate from their keyed connectors, and the lower coupling
separates from its axle by 16.16, 46.90 and 79.42
LDU. All checks pass at rest. The regression [fixture](../tests/fixtures/rcvj-shafts.json)
retains the measured frames and source hash; [tests](../tests/test_rcvj.py)
need neither the user's working file nor an external checkout.

Source radial fit errors are 0.159–1.369 LDU across the measured interfaces. The
workbook reports them and allows only a small additional drift. These are
historical model residuals, not manufacturing allowances or physical-fit proof.
No snapping or semantic rewriting was applied. The source `bottom-axle` and
`upper-arm` names are misleading in LDraw's negative-Y-up coordinates, and the
`gear-train` assembly mixes moving groups.

## Rules for other machines

1. Inventory all parts, variants, aliases and shortcuts. Inspect complete
   occurrence transforms and engaged pin/axle sections before choosing axes.
2. Record each connection as keyed, bearing, mesh, pivot, slider, contact or
   unresolved. MPD hierarchy is not a rigid-body partition.
3. Choose independent input freedoms, then derive followers. Gear relations on
   moving carriers use `Na*(a-c)+Nb*(b-c)=0` for external parallel gears with
   consistent directed axes. A fixed-carrier formula is a special case.
4. An equal-side differential has `c=(a+b)/2`. Its planet spin is relative to
   that carrier and proportional to `a-b`. Equal side speeds stop relative
   planet spin, not carrier travel. `linkages.differential` implements this.
5. Add [mechanical checks](motion-plan.md#mechanical-checks-on-physical-occurrences)
   independently of driver expressions. Use nonzero/asymmetric and multi-turn
   cases. Intentionally break a coupling and confirm a failure.
6. Run `check --require-reviewed --require-constrained`, then
   `rig --require-constrained --animate --reopen` and inspect the actual motion.
   Bookkeeping, matrix agreement and visual plausibility are different evidence.

For the double-Cardan idealisation, each joint's output is nonuniform; correct
equal-bend phasing cancels it only at the final shaft. The intermediate direction
is `normalize(input_axis+output_axis)`, not averaged Euler angles. The new
`linkages.double_cardan` helper composes two individually solved joints and
retains intermediate shaft/cross signals. Tests cover 0°, positive/negative
bends, 45° total bend and signed multi-turn phases. This verifies the ideal
relation; the real mechanism must enforce its bisector and fork phase.

## Remaining RCVJ work

The full 127-part rig is not solved here. The workbook deliberately contains no
invented spinning bodies. Both carrier assignments, crown contacts, remaining
link closures, bearing/retention intervals and spatial articulation still need
to be resolved before marking it ready. The 22 interface checks are necessary
local constraints, not a complete mechanism solver. The ideal double-Cardan
helper cannot replace RCVJ's differential-centred linkage.

The companion `ldraw-nova` change supplies a preserved source study, parts
inventory and agent guidance. Its `technic catalog` reads all supplied Technic
assignments and installed mechanical names, with explicit availability,
alias-transform and connector-provenance reports. Neither project imports the
other at runtime. Use the designer's model or a supplied annotated copy as input
to the script above.

Designer source: [RCVJ.ldr](https://rcvj.reininghaus.org/model/RCVJ.ldr),
[CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/), accessed
2026-10-25. This licence also applies to the model-derived coordinate fixture;
the toolkit code licence does not relicense it.

## Reproduce adapter verification

The small integration fixture checks keyed shafts, round bearings and 8/24
gearing on a carrier that tilts about another axis. It is a coordinate/adapter
test, not the RCVJ animation or a collision-certified build.

```sh
.venv/bin/python scripts/mechanical_constraint_fixture.py --output output/constraint-fixture
blender --background --factory-startup --python-exit-code 1 \
  --python scripts/blender/check_mechanical_constraints.py -- \
  --plan output/constraint-fixture/plan.json --glb output/constraint-fixture/model.glb \
  --output output/constraint-fixture/verification
./ldraw-mecha rig output/constraint-fixture --require-constrained --reopen
```

The background script checks nonzero mixed poses, a moved/rotated model root,
intentional scene corruption, save/reopen, rebuild without leaks and source-pose
restoration. The final command verifies persistence in a separate Blender process.
