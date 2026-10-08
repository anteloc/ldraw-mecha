# 42110 Land Rover Defender: inner mechanisms rigged and animated, bodywork hidden

Source: `data/models-annotated/42110-1.mpd` (Philippe Hurbain), unmodified.

**How the plan was built:** `plan.json` is written by `scripts/build_defender_rig.py`. Its inputs are:
- `study/plan.json`, the `prepare --contact-limit 2000` draft;
- `evidence/contacts-mechanical.json`, a bounded pyldraw3 contact run.

**Frame:** LDU, −Y up, front −Z, car's left +X. Longitudinal shafts use the measured 0.003 rad chassis tilt. Angles are radians; values are offsets from the source pose.

## What moves

| Mechanism | Path |
| --- | --- |
| Drivetrain | Wheels → CV hub drivers → exact cardan half shafts → front/rear differentials (28T ring, 20T pinion, 12T spiders) → 8T/24T steps → centre differential → transfer shaft → middle gearbox |
| Middle gearbox | Forward/reverse ring `0/0/128/61` and its extension, high/low ring `0/0/128/62` and its extension, both changeover catches with their cab levers |
| Rear sequential 4-speed | Internal double-cardan propshafts A and B; two constant-mesh trains; two driving rings; rotary catch; the cab dial through two knob wheels |
| Engine | Camshaft (1:1 with the gearbox input through an idler) and six cam-driven axle pistons |
| Steering | Wheel → two exact cardans → 16/20, 12/20 gears → 12T pinion → rack → two closed 100 LDU ball links → kingpin knuckles; the front wheels ride the knuckles. The roof knob (`0/358`) is geared to the same input shaft. |
| Winch | Knob `0/69` under the bonnet → three 12T bevels → drum |

That is 91 bodies, 301 moving parts and 194 signals, with 37 gear meshes and 48 connections reviewed with their measurements.

Gear ratios, engine turns per wheel turn:

| Range | 1st | 2nd | 3rd | 4th |
| --- | --- | --- | --- | --- |
| Low | 2.333 | 1.400 | 0.778 | 0.467 |
| High | 1.493 | 0.896 | 0.498 | 0.299 |
| Reverse (any gear) | 0.299 (engine turns the opposite way) | | | |

The 4-speed itself gives c76/c77 = 0.2, 1/3, 0.6, 1.0. The source pose is 1st gear, with both middle rings in neutral.

## Controls

| Control | Range | Meaning |
| --- | --- | --- |
| `drive` | ±2000 rad | Road-wheel roll (axle side-gear angle); positive drives forward |
| `diff_front`, `diff_rear`, `diff_center` | ±200 rad | Half-difference splits (left/right, front/rear); the animation sets them from Ackermann wheel speeds |
| `steering` | ±2.583 rad | Steering wheel; positive turns right. It gives ±18 LDU of rack and about 27–28° at the knuckles. |
| `gear_select` | −0.5 … 2π | Rotary-catch angle: 0, π/2, π and 3π/2 select 1st–4th (cyclic); the dial turns the other way |
| `range_select` | −1 … 1 | −1 is low and +1 is high; the high/low ring and its lever travel 10 LDU |
| `direction_select` | −1 … 1 | +1 is forward through the 4-speed; −1 is reverse |
| `phase_engine`, `phase_mid`, `phase_c26` | ±4000 rad | Carry offsets, keyed at ratio changes so every shaft stays continuous |
| `winch` | ±400 rad | Winch knob angle |

## Bodywork removal

`bodywork.json` lists 1512 hidden occurrences:
- 50 body sections: doors, roof, roof rack, bonnet, panels, seats, dashboard, lights, back door with spare wheel, running boards, wheel arches;
- chassis-level panels, slopes, tiles and plates;
- chassis-level parts above y = −400 (roof and cab posts).

How it is applied:
- **Blender only:** hiding uses the new `blender.set_hidden` (reversible; its snapshot persists in the `.blend`).
- **Rigged parts are never hidden:** `set_hidden` refuses them.
- **Source untouched:** nothing in the MPD changes.

The frame, wheels, suspension, rope and every rigged part stay visible.

## Checks run

**Pure checks:**
- `.venv/bin/pytest -q`: 99 passed. New: `tests/test_defender_rig.py`, plus embedded-alias, duplicate-placement and merged-primitive tests.
- `validate`, `sweep` (204 samples), asymmetric `evaluate` (`evaluate-asymmetric.json`, tie rods closed to within 4e-7 LDU) and `audit --require-reviewed` all pass. The audit counts 8 planned, 6 deferred and 1 static view, and review is complete.
- The build script's own assertions pass:
  - every mesh distance against its pitch radii;
  - bevel apexes;
  - piston rest heights against the cam law;
  - in-phase propshaft forks;
  - steering sign.
- `kinematics.json`: in all 16 direction × range × gear states, all 37 meshes and every engaged clutch hold to within 3e-16 rad.

**Blender:**
- **Rig** (`blender-check.json`, 38 samples): passes, max matrix error 0.0036 LDU moving / 0.0040 static, closure 5e-5, no invalid drivers.
- **Reopen** (`reopen-check.json`): passes.
- **Lifecycle** (`lifecycle.json`): passes — rebuild without leaks, two isolated copies, restore error 1e-6, nonzero defaults and clamping.
- **Tolerance:** these runs use a matrix tolerance of 0.01 LDU instead of 0.002. The measured residual is float32 rounding. It comes in exact multiples of 2⁻¹³ LDU on parts about 0.4 m from the origin (this model spans more than 1000 LDU). Rotation errors are 4e-6.

**Toolkit regressions:** `check_workflows.py` (on 106, with the new hide → save → reopen → restore case) and `check_prepared.py` (106) both pass.

**Animation:**
- `animated.blend`: 696 frames at 24 fps, with 24 ratio/state changes.
- Sequence: engage forward and low; accelerate through 1st→4th; low→high on the move; steering lock to lock with differential splits; stop; downshift; reverse with steering; levers to neutral; winch.
- `animation-check.json`: 15 sampled frames match the evaluator. Continuity holds on every body signal: at most 0.37 rad per frame for revolute bodies and 5.1 LDU per frame for the rings during the quick stopped downshift.
- `animated-reopen-check.json`: passes, and the hidden bodywork, action and camera persist.

**Previews:**

| File | Pose |
| --- | --- |
| `preview-rest.png` | Rest |
| `preview-drive-4th-high.png` | 4th gear, high range |
| `preview-full-lock.png` | Full steering lock |
| `preview-gearbox-2nd-low.png` | Middle gearbox in 2nd, low range |
| `preview-sequential-3rd.png` | Sequential box in 3rd |
| `preview-engine.png` | Engine and cams |
| `preview-moving.png` | Moving parts only |

## Sampled clearance (`clearance.json`, 9 steps × 6 controls; `clearance-steering.json`, 21 steps)

This is a sampled test, not proof. New surface crossings remain, and none were hidden by narrowing ranges:

| Control | Crossing | Assessment |
| --- | --- | --- |
| Clutches | Engaged ring or extension teeth into their clutch gears (`0/0/128/65`↔66, 61↔50, 62↔63, `0/1/133/20`↔47) | This is the engagement itself. |
| Catches | Changeover forks against their rings | The fork tip swings on a 40 LDU arc while the ring slides straight: about 1.3 LDU of groove play at full travel. |
| Steering | Steering links `0/0/111/11`/`12` against lower wishbones `0/0/17`/`18` | Intermittent graze between about 0.9 and 1.65 rad (not a contiguous band). |
| Steering | Steering cardan cross `0/0/125` against the column axle tip `0/27` | The axle reaches within about 5 LDU of the joint centre in the source. |
| Sequential selector | Rotary catch against ring `0/1/133/40`; knob wheels against each other; the selector's angle connector `0/1/146` against bracket beam `0/1/147/0` | Cam and knob contacts are real, but their profiles are approximated. |
| Winch | 16T ratchet `0/111` against the static pawl `0/113` | The pawl is not animated. |
| Drive | CV spindle drivers `0/0/59`/`64` turning inside the steering bearings | Real contact. |

No tyre or wheel crossed the hidden mudguards anywhere in the steering range.

## Assumptions and limits

**Assumptions:**
- **Rotary catch cam:** its profile is not measured. Each 4-speed ring follows 10·sat(cos/sin) of the catch angle, with an 18° dwell, so the rings never overlap. The cab dial direction for an upshift is a convention.
- **Driving-ring travel:** 10 LDU, taken from the source 1st-gear ring offset. Extensions move only when pushed towards their gear.
- **Pistons:** the cam follower is an agent hypothesis (`surface_contact` connections). The model is a flat follower on a 1×2 liftarm stadium cam (eccentricity 20, radius 10) with a stop at 20 LDU. That gives up to 10 LDU of lift, and it matches the source pose of all six pistons.
- **CV at the hubs:** the wheel angle equals the half-shaft angle. The cardan at the diff makes the wheels differ from `drive` by less than 0.7°.
- **Propshafts A and B:** their intermediate forks are measured in phase within 0.01° and snapped exactly in phase, so they are constant velocity.

**Not modelled:** friction, backlash, gravity and compliance.

**Deferred (listed in `audit.json`):**
- suspension at static ride height, by decision; the shocks are single rigid parts;
- doors, bonnet, tailgate, roof trunk, side case and ladder hinges (hidden);
- rope, hose and bands, which are static (the rope does not unwind);
- the winch ratchet pawl;
- 318 frame supports that were not traced to motion.

The camshaft, dial and gearbox brackets were reviewed as static.

## Toolkit changes made for this model

**Discovery:**
- `source.py`: an embedded DAT whose own title is only a library part number (e.g. `18575`) now gets that part's title and `library_alias`. Previously ten 20T gears, a clutch gear and the rotary catch were invisible to discovery.
- `geometry.py`: embedded gears are listed as unsupported, and no profile is substituted.

**GLB binding:**
- `glb.py`: exact duplicate placements (`0/1/133/39`/`43`) bind in source order.
- `glb.py`: library primitives placed as leaves (the 395 rope cylinders) bind to their parent's merged mesh, which is tagged `mecha_merged`.
- `blender.py`: `bind`, `verify` and `build` handle merged geometry. It must move as one body.

**Blender helpers:**
- `blender.set_hidden(rig, ids)`, which shares the persisted snapshot with `set_moving_only`.
- `ldraw_mechanisms/linkages.py`:
  - a general cardan joint with any fork phase, unwrapped over many turns;
  - a ball-link closure solver.

**CLI and scripts:**
- `--tolerance` on `rig`, `apply_plan.py` and `check_lifecycle.py`; it is reported in the outputs.
- `preview_plan.py --hide/--view/--size/--samples`.
- `check_clearance` handles merged objects.

## Files

| Group | Files |
| --- | --- |
| Plan and supporting data | `plan.json`, `bodywork.json`, `kinematics.json`, `diagrams/`, `evidence/contacts-mechanical.json` |
| Study | `study/` (`prepare` wrote the study before its GLB step failed on the duplicate axle; the GLB was then made with `convert`, see `conversion.json`) |
| Scene files | `model.glb`, `rigged.blend`, `animated.blend` |
| Reports | `blender-check.json`, `reopen-check.json`, `lifecycle.json`, `animation-check.json`, `animated-reopen-check.json`, `clearance*.json`, `sweep.json`, `audit.json`, `evaluate-asymmetric.json` |
| Previews | `preview-*.png` |

Scripts: `scripts/build_defender_rig.py`, `scripts/blender/animate_defender.py`.
