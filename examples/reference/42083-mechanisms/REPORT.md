# 42083 Bugatti Chiron: five mechanisms, standalone, in one .blend

Source: `data/models-annotated/42083-1.mpd` (Philippe Hurbain [Philo], CCAL 2.0), section `42083 - chiron.ldr`.
The file is unmodified (SHA-256 `72df8a1a…69db`).

Deliverable: [`mechanisms.blend`](mechanisms.blend) contains five standalone extracts side by side, each with its own rig,
collection and controller. All of them animate at once over frames 1–480 at 24 fps.

| Slot (left → right) | Controller | Controls | What the demo does |
| --- | --- | --- | --- |
| Opening doors | `CTRL_chiron_42083_doors` | `door_left`, `door_right` (0 … 1.2 rad) | Right door opens at frames 40–130 and the left at 90–180. The left closes at 280–370 and the right at 330–420. |
| AWD drivetrain | `CTRL_chiron_42083_drivetrain` | `drive`, `diff_front`, `diff_rear` | Rolls forward, takes an S-bend (frames 150–340, differentials split both ways), then stops. |
| 8-speed gearbox + paddles | `CTRL_chiron_42083_gearbox` | `input`, `shift`, `paddle`, `phase_stage1/2` | Main shaft turning. Paddle upshifts 1→8 (frames 40–224), then downshifts 8→1 (262–446). |
| D/N/R selector | `CTRL_chiron_42083_dnr` | `input`, `selector`, `phase_ring_shaft` | N → D while rolling forward, then N → R while rolling backwards, then N. |
| Rear wing lift | `CTRL_chiron_42083_wing` | `wing` (0 … 0.4 rad) | Lifts (frames 60–170), holds, lowers (300–410). |

Frame: LDU, −Y up, front −Z, the car's left +X; angles in radians. Each extract keeps the chiron section's frame. Its
root is only translated into its slot, and verification is root-relative. `phase_*` controls are continuity carries,
keyed with constant interpolation at engagement changes; leave them keyed.

## What was found (inventory)

| Mechanism | Selected | Notes |
| --- | --- | --- |
| AWD drivetrain | yes | Main shaft locks front and rear (no centre diff); 28T/20T diffs; Cardans |
| 8-speed sequential gearbox + paddle shifters | yes | Two rotary catches, four driving rings, carry crank; **two gears reconstructed** (below) |
| D/N/R selector | yes | Console changeover catch and a fifth driving ring |
| Opening doors | yes | Vertical pillar hinges; the side mirrors ride on the doors |
| Rear wing | yes | Strut parallelogram; the real set switches it with the top-speed key (not installed) |
| W16 engine | no | Curated reference already exists: `output/42083-w16` |
| Steering | no | Wheel → bevels → 12:20 → idlers → pinion → rack → knuckles |
| Four-corner suspension | no | Two shocks per corner |
| Bonnet | not a mechanism | Two parallel Z-axis pins at x=±160 lock rotation: it lifts off |
| Engine cover, top-speed key, flex axles/hoses, seats, windscreen | static | Key is placed beside the car in `main.ldr` |

## The mechanisms as rigged

**AWD drivetrain** (`drivetrain/`; 337 parts, 82 moving)
- **Rear:** road wheels → hubs (CV spindle drivers, 1:1) → half shafts bent 20.3° (exact Cardan at the diff) →
  28T differential (12T side gears and planet) → 20T pinion on the main shaft.
- **Front:** straight half shafts and the same differential; its 20T pinion shaft meshes 16:16 with the main shaft.
- **Coupling:** main shaft = −1.4 × wheel roll. Front and rear were checked to agree for straight running, so the
  car has true locked AWD.
- **Interfaces:** the gearbox 24T input shaft and the D/N/R 16T reverse gear 1/57 turn as driven context only.
- **Static:** suspension and steering, front wheels straight.

**8-speed gearbox + paddles** (`gearbox/`; 397 parts incl. 2 reconstructed, 151 moving)
- **Stage 1 (catch 1, rings 0/90/54, 0/90/55):** four ratios.
- **Stage 2 (catch 2, rings 0/90/57, 0/90/56):** high/low, reached through an idler chain at z=−60.
- **Gear ratios**, output shaft / input shaft for gears 1–8: **1.667, 1.25, 1.0, 0.8, 0.6, 0.45, 0.36, 0.288**.
  That is eight distinct, decreasing values with the same sign, verified in all 16 catch states with exactly one ring
  engaged per catch.
- **Shift sequence:** catch 1 turns π/2 per shift (gear = 1 + shift/(π/2)). After the 4th→5th shift the crank on
  knob shaft 0/90/92 advances catch 2 by π/2. The 16-state cycle repeats every 8 gears, so 8th wraps to 1st.
- **Paddles:** one rocker carries both paddles and pivots about a vertical pin. Each pawl tip rides the ratchet
  rollers (radius 24.65 LDU) only on its driving stroke and lifts off on the other.
  - The ratchet drives catch 1 through three 4-knob right angles.
  - Measured result: **pulling the paddle on the driver's left (x=180, `paddle` = −0.6) upshifts**, and the right
    paddle downshifts.
  - That is the reverse of the usual car convention; it follows from the knob signs and from assuming the driver
    pulls the paddles towards the wheel.

**D/N/R selector** (`dnr/`; 260 parts, 49 moving)
- **Mechanism:** the console lever and changeover catch 1/150/39 (fork 40 LDU below its pivot) slide ring 1/62 by
  ±10 LDU.
- **D:** clutch 1/63 (20T) is driven from the gearbox output 24T 1/64/31.
- **R:** clutch 1/57 (16T) is driven directly from the main shaft.
- **Engine input per main-shaft radian:** D −1.2 (gearbox held in 3rd, 1:1 inside), R +3.0, N 0. Opposite signs mean
  true reverse: rolling backwards in R turns the engine forwards. The demo shows exactly that.

**Opening doors** (`doors/`; 114 parts, 92 moving)
- **Hinges:** each door turns about its front-pillar pin (438 / 400, vertical) and opens outwards.
- **Mirrors:** each side mirror (liftarm, axle pin and fairing on the door's long pin: 548/549/547, 536/537/538)
  turns with its door. It was first mistaken for a latch.
- **Limit:** 1.2 rad (69°).

**Rear wing** (`wing/`; 119 parts, 50 moving)
- **Model:** lower cranks on cross-axle 107/11 and the upper axle 107/14 form a measured 40×40 LDU parallelogram with
  the struts. With the upper axle held, the struts and wing translate straight up.
- **Rear links:** beam 3 on the lower axle plus the beam-7 rod (120 LDU) close by circle intersection. The closure
  checks pass over the whole range.
- **Limit:** 0.4 rad (≈16 LDU of lift).

## Gearbox reconstruction (important)

The source file lacks two **12T double-bevel gears (32270)**. The official inventory lists 8; the file has 6. Without
them:
- the 20T clutch gear 0/90/84 and shaft 0/90/30 have no partner;
- the "8-speed" collapses to 3 ratios plus neutral states.

The gearbox extract **alone** adds them in the empty 20-LDU slots where they mesh:

| Position | On shaft | Meshes |
| --- | --- | --- |
| (80, 0, 40) | 0/90/53 | 20T 0/90/84 |
| (−80, −40, 160) | 0/90/30 | 20T 0/90/13 |

With them, the measured trains give the eight decreasing ratios above, matching published descriptions (4-speed ×
high/low, 16 configurations, 8 + R). The added lines are commented in
`gearbox/source/42083-gearbox.mpd`, and their IDs are recorded in `gearbox/source/idmap.json`.

## Assumptions and approximations

- **Rotary-catch ring travel** uses a dwell profile: 10 LDU × sat(cos/sin of the catch angle).
  - The lobe direction is measured: the source ring 0/90/57 sits at −10, where the lobe holds it.
  - The source leaves ring 0/90/54 centred although catch 1 holds it at −10 in 1st, so **the rig shows the cam
    position**, 10 LDU from the source pose.
- **Carry timing** comes from the crank geometry (it faces catch 2 at 7π/4). It is modelled as a linear transfer over
  the 4th→5th shift; the detent rocker 0/90/149 stays static.
- **Paddle detent:** the full 0.6 rad stroke sweeps 69° of the ratchet. The stepper detent completing each 90° step
  is assumed.
- **Rubber bands** stay static context.
- **Wing:** "upper axle held" is an assumption (links 107/13/16 static). It gives a pure parallel lift without tilt.
  - A rigid tilt about the lower axle was tested and rejected: it crosses the rear fascia within 0.05–0.1 rad.
  - The real top-speed-key mechanism cannot be checked without the key installed.
- **D/N/R mesh:** 1/63 (20T) to 1/64/31 (24T) is a loose 2×2 diagonal mesh (56.57 vs 55 LDU). It is accepted as
  designed because 1/63 has no other partner.
- **D/N/R gearbox ratio:** the D/N/R extract holds the gearbox in 3rd. The interface gears in each extract are driven
  context, not a coupled simulation of the other extracts.

## Verification

| Check | Result |
| --- | --- |
| `pytest -q` (whole suite, incl. 18 new `tests/test_42083_mechanisms.py`) | 140 passed |
| `validate`, `sweep`, `audit --require-reviewed` (all five plans, status `ready`) | pass |
| `evaluate --set` nonzero/asymmetric cases (`*/evaluate-*.json`) | 14 cases written |
| Builder kinematics (`*/kinematics.json`) | Mesh residuals ≤1e-15 in every state; clutch locks hold. Covers 3 drivetrain cases, all 16 gearbox states and 3 selector states. |
| Blender build + verification (`animation-check.json`) | All five rigs pass at the **default 0.002 LDU** tolerance (max 0.0006); 65 sampled frame×rig checks pass; per-frame continuity passes |
| Reopen in a fresh process (`reopen-check.json`, Blender 5.2.2 LTS) | Embedded plans match the files, actions present, sampled frames pass (max 0.0005 LDU) |
| Lifecycle (`*/lifecycle.json`) | Two copies isolated, rebuild without leaks, restore: pass for all five |

### Sampled clearance (`*/clearance.json`)

| Extract | Result |
| --- | --- |
| Doors, wing, drivetrain | No new surface crossings |
| Gearbox, D/N/R | Crossings only where parts ride on each other by design (list below) |

The gearbox and D/N/R crossings, none of which the kinematic model resolves:
- driving rings in the rotary-catch rims;
- the changeover fork in ring 1/62;
- pawl tips on the ratchet rollers when `shift` is swept alone;
- 4-knob phase at right angles;
- ratchet pins grazing the floor beams under the stepper by about 2 LDU;
- rollers passing the stepper's static detent axle.

**Clearance-context studies** (`doors/clearance-context`, `wing/clearance-context`) add the surrounding bodywork:
- **Doors:** clear up to 1.65 rad.
- **Wing lift:** clear up to 0.40 rad; at 0.45 the rear rods touch the engine-cover fairing pins.

These are sampled checks. They do not prove collision-free or physically feasible motion, tooth phase, retention or
bore containment.

## Toolkit changes made for this work

- **`scripts/extract_subsystem.py --section`:** extracts in a selected section's frame and IDs.
- **`ldraw_mechanisms/blender.py` (rod roll reference):** the offset is now added in the model root's space.
  - Before, a rod's reference included the root translation, so every rod mis-rolled once a root was moved off the
    origin. The 42110 rigs never moved a root, so it never showed.
  - Regression: the W16 (16 rods) and the wing verify at the origin, translated, and translated plus rotated.
  - Pytest, lifecycle and reopen checks pass.
- **New scripts:**
  - `scripts/build_42083_mechanisms.py`: selection, extraction, plans, kinematic checks.
  - `scripts/timeline_42083.py`: Blender-safe timelines and the opening limits.
  - `scripts/blender/study_42083.py`: rig, clearance and renders.
  - `scripts/blender/animate_42083_mechanisms.py`: the combined blend.
  - `scripts/blender/check_42083_reopen.py`: reopen check.

## Reproduce

```sh
for n in drivetrain gearbox dnr doors wing; do
  .venv/bin/python scripts/build_42083_mechanisms.py select $n
  .venv/bin/python scripts/build_42083_mechanisms.py extract $n
  ./ldraw-mecha prepare output/42083-mechanisms/$n/source/42083-$n.mpd \
      --output output/42083-mechanisms/$n/study --contact-limit 2000   # into a new/empty study folder
  .venv/bin/python scripts/build_42083_mechanisms.py plan $n --ready
done
Blender --background --factory-startup --python scripts/blender/animate_42083_mechanisms.py -- \
    --save output/42083-mechanisms/mechanisms.blend --report output/42083-mechanisms/animation-check.json \
    --render output/42083-mechanisms/previews
Blender --background output/42083-mechanisms/mechanisms.blend --python scripts/blender/check_42083_reopen.py -- \
    --report output/42083-mechanisms/reopen-check.json
```

Previews: `previews/overview-f*.png` (all five), and per extract `*/previews/*.png` (gears 1/3/5, paddle stroke,
D/N/R states, doors open, wing lifted).

## Not done / open

- Engine, steering and suspension (not selected).
- Wing tilt and the top-speed key.
- Paddle-to-ratchet contact dynamics.
- Coupling between the extracts: each one drives its neighbours' interface gears from a fixed assumption.
