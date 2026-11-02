# Build and animate a mechanism

Start with a supported, reproducible assembly, then add one checked coupling at
a time. The [23-part gear drive](../examples/gear-drive/README.md) is the small
working example: four round bearings support two retained keyed shafts; one
input turns an 8-tooth gear and drives a 24-tooth output at `-input/3`.

```sh
export LDRAW_DIR=/path/to/ldraw
.venv/bin/python scripts/gear_drive.py --output output/gear-drive
./ldraw-mecha check output/gear-drive --require-reviewed --require-constrained --set drive=0.731
./ldraw-mecha rig output/gear-drive --require-constrained --animate --reopen
```

Set `BLENDER_BIN` or pass `--blender /path/to/blender` when needed. Choose a new
output directory for a rebuild; preserve the reviewed revision. Inspect the
saved animation and several nonzero poses before delivery.

## Author the physical connections first

Measure **occurrences**, not just part numbers. A selected interface needs a
part-local point, directed axis, finite engaged span and evidence of its type.
Compose every parent/alias transform. Part axes vary: standard axles run along
local X; many gears and bushes run along local Z. LDCad connector frames use
local Y. Do not confuse any of these with world-up.

Partition parts by actual rigidity. Cross axles, matching cross holes, gears
and retaining bushes normally share a body. Round bearing holes allow the axle
to spin. On a mixed pin/axle, classify the occupied section at each end.
Assembly names, touching bounds and coincident lines do not establish torque
transfer. An off-centre keyed hole makes an eccentric, not a centred gear.
Build order and height cut-offs are not rigidity either.

`check` audits body boundaries against the study's connector contacts. Parts in
different bodies may share a pin or axle only on the joint between them:
coaxial with a revolute axis or along a slide. Each `body_boundary` warning names
the bodies and part pairs of a pin off a revolute axis, a keyed axle off it, a
pin across a slide, or a static part touching a part beyond its first joint.
That usually means a part sits in the wrong body: a frame half riding a turret,
a gear leaving its axle. Fix membership; if the joint is real, declare a check
covering both parts. `--require-reviewed` fails until each is resolved.
Linkages between moving bodies and keyed shafts on the joint axis are listed as
info. Embedded parts, surface contacts and stops are not seen; look at them.

Use a construction tool such as LDraw Nova for parts, supports and editable
geometry. Keep the official parts library unchanged. Inspect fit, tooth phase,
insertion, axial stops and the space swept by the mechanism. A centred shaft
still needs bearings and retention. Complete joint/shock shortcuts must be
split into their actual components before internal articulation is possible.

## Use the small authoring helpers

`transmission.port`, `shaft` and `mesh` write ordinary version-1 plan fields.
They complement `recipes.Builder`; there is no second runtime or plan format.
The complete example is [scripts/gear_drive.py](../scripts/gear_drive.py).
For a plan from `prepare`, pass `mechanism="VIEW_ID"` to `shaft` to attach its
body to that existing mechanism view. Helpers mark edited plans as draft;
finish the connections and scope review before setting `status: ready`.

```python
from ldraw_mechanisms.transmission import port, shaft, mesh

# IDs and interfaces must come from the selected source revision.
shaft(plan, "input",
      axle=port("1/0", [0, 0, 0], [1, 0, 0], [-79.5, 79.5]),
      keyed=[port("1/1", [0, 0, 0], [0, 0, 1], [-9.5, 9.5])],
      bearings=[port("0/5", [0, 10, 0], [0, 0, 1], [-10, 10])],
      signal="drive", evidence="Describe keyed fit, bearing and retention.")
# Add the output shaft with all its keyed mates and bearings; omit signal.
mesh(plan, "input", "output", gear_a="1/1", gear_b="2/1",
     evidence="Reviewed external spur contact, tooth phase and clearances.")
```

The snippet shows the API, not the starter's complete parts list. Include every
keyed bush, wheel and coupling in the actual call. `shaft` derives the global
joint frame from the selected axle section and creates rigidity, coaxiality,
finite overlap and axial displacement checks. Source-fit failure or duplicate
ownership leaves the plan unchanged. The unconnected follower starts at zero;
connect it before declaring the mechanism ready and check its expected output.

`mesh` accepts the ordinary central-hole spur variants listed in
`transmission.SPUR_GEARS`. It requires pitch spacing, coincident tooth planes,
parallel axes, shaft-centred gears and a common parent. It derives the sign
from the directed body axes and adds an occurrence-based tooth-count relation.
It refuses a second drive, a crown/bevel/worm/unknown profile or an embedded
namesake. Tooth phase, cross-hole phase, retention and clearance still require
geometric review; the helper never snaps or repairs the source.

For a moving common carrier, both shaft angles are **relative to that parent**.
The parent transform applies its motion once; the ratio check removes the
carrier's full transform. For absolute angles about a fixed directed axis use
`linkages.gear_pair`: `b = c - Na/Nb*(a-c)`. Mixing these two conventions applies
the carrier twice.

## Extend only the part of the machine you can check

| Mechanism | Available authoring | Required independent evidence |
|---|---|---|
| Supported spur shafts | `transmission.shaft`, `mesh` | Occupied sections, phase, supports, retention, mesh clearance |
| General rigid/hinged/sliding groups | `Builder`, `mechanisms.add_joint` | Real mates, limits, bearing/slider geometry |
| Differential | `linkages.differential` | Side mean and relative planet spin; planet parent, contacts and second boundary condition |
| Cardan / phased equal-bend pair | `universal_joint`, `double_cardan` | Fork phase, cross axes, pivot closure; fixed bend and real centring geometry |
| Rod/crank/steering linkage | Rod bodies, distance checks, studied recipes | Measured pivots, constant lengths, assembly branch and travel limits |
| Worm, crown/bevel mesh, cam, selector | Measured geometry and explicit plan | Reviewed sign/contact/travel; discovery candidates do not execute motion |
| Hose, chain, belt or spring | Nova flex generation; explicit motion model | Static LSynth geometry is not a moving belt/chain solver; only springs may use `stretch` |

The catalog is a discovery inventory, not a universal motion-profile database.
Unknown geometry or an unresolved loop stays explicit. Do not assign independent
spin to its parts to make a plausible animation. Resolve the physical relation,
narrow the demonstrated scope, or report it as unsupported.

## Verify the geometry that actually moves

Use the [mechanical checks](motion-plan.md#mechanical-checks-on-physical-occurrences)
for rigidity, bearing alignment/engagement, rotation relations and link lengths.
Include fixed supports. Sweeps must include nonzero, off-grid, negative,
multi-turn and asymmetric inputs; equal differential inputs conceal planet and
carrier errors. Preserve source phase instead of resetting each part's rotation.

`--require-constrained` rejects controlled bodies without cross-body checks, but participation in
a check is not proof of a fully constrained machine. `--require-reviewed`
accounts for declared scope and still permits explicit deferrals. Inspect both
reports. Intentionally break a known coupling and require failure: this catches
a check that merely repeats the driver expression.

Blender verification measures actual scene matrices, including fixed parts and
root placement, then applies the same mechanical invariants. `--reopen` checks
the saved file in a fresh process. Both build and reopen sample off-grid inputs
and, when the controller has animation, 33 evaluated timeline positions with
the action, NLA and controller drivers active. `blender.verify(current=True)`
checks the current scene without overriding inputs; `verify_animation` checks
playback and restores the original time. For adapter changes also run
`scripts/blender/check_lifecycle.py` to test rebuild, two copies and restoration.

Clearance checks are separate. `check_clearance.py` excludes existing contacts
and same-body pairs, so inspect gear contact explicitly with `sweep_contact.py`
and inspect keyed fit in the source. A sampled surface-crossing result cannot
prove containment, load capacity, friction, backlash or manufacturing tolerance.
Record the inspected views, sampled range, exclusions and unresolved contacts
beside the exact source, plan and saved blend.
