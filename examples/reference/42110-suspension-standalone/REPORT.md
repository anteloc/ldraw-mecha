# 42110 independent suspension as a standalone subsystem

The four-corner suspension of the Land Rover Defender, **on its own**, together with the frame it mounts on. Nothing else is in the model: no cab, bodywork, engine, gearboxes, differentials, steering rack or drivetrain shafts.

Only the suspension moves. The mounting frame is static context. The whole-vehicle animation (`output/42110-suspension`) is unchanged.

Open **`animated.blend`**: 612 frames at 24 fps.
- `SuspensionCamera` is the scene camera: a low front-left three-quarter view of the whole subsystem.
- `CornerCamera` is a close-up behind the rear-left corner. Select it and press Ctrl+Numpad0 to view through it.

## What is in the model (259 parts, `keep.json`)

| Role | Parts | What |
| --- | --- | --- |
| Moving | 117 | Wishbones, knuckles with hub, rim and tyre, inner couplers, toe links and tie rods, half-shafts (Cardan output side), and shocks as piston rod, cylinder and spring |
| Mounts | 38 | Static parts the moving ones join: wishbone pivot axles, inner pivot liftarms, toe-link ball pins, front tie-rod ball pins, shock-top axles, bushes and cross blocks, and the three static Cardan crosses |
| Frame | 104 | Connector parts holding the mounts (pins, cross blocks, axles, bushes, angle connectors), out to the first beams and liftarms holding them |

**Selection rule** (`scripts/build_suspension_standalone.py select`), measured on the full model:
- *Mounts* are found from pyldraw3 contacts, male connectors in hole lines, and coincident ball/clip/pin centres.
- *Frame* expands through connectors via contacts and hole lines, up to depth 4, keeping the first beams and liftarms but not going past them.
- Never added:
  - gears, differentials, the rack, and the gearbox, engine, camshaft and winch sections;
  - body parts and the Cardan input yokes;
  - anything another rig moves (`--moving-elsewhere output/42110/plan.json`). That removed three transfer-shaft parts and a winch bush that had reached the closure through frame cross blocks.

**Compromise:** the front tie rods keep their inner ball pins (`0/0/111/9`, `/10`) as mounts. The rack and the angle connectors that hold those pins are steering parts, so they are not included and the two pins have no visible holder.

## How it was built

1. **Extract.** `scripts/extract_subsystem.py` (generic) wrote `source/42110-suspension-standalone.mpd`.
   - Input: `output/42110-suspension/source/42110-1-shocks-split.mpd`, derived from `data/models-annotated/42110-1.mpd` by Philippe Hurbain, CCAL 2.0. The original is untouched (SHA-256 `b27fb069…0267dc`).
   - Each kept occurrence is one line with its composed world matrix and effective colour, preceded by `0 // from <original ID>`.
   - The embedded bearing, hub and rim DATs and their sub-files are copied verbatim.
   - `source/idmap.json` maps the original IDs to the new ones. Re-reading the file reproduces every reference, colour and world matrix (max error 6e-14 LDU).
2. **Prepare.** `prepare` ran on the standalone file. The model is small, so contacts ran in full: 419 contacts, all 36 axles with axle-hole evidence, all 259 parts bound in the GLB.
3. **Plan.** `scripts/build_suspension_standalone.py plan` reuses the verified suspension motion **verbatim**.
   - Same controls, signals, body origins and axes, anchors and the 48 checks; only instance IDs are remapped.
   - The extract keeps the original coordinate frame, so evaluated body transforms are identical to the full-model plan's (tested).
   - Views: four planned corners and one static `mounting_frame` view (142 parts).

## Motion (same as the whole-vehicle study)

- **Controls:**
  - `travel_fl` and `travel_fr`: 0–30.5 LDU of wheel rise from full droop (the source pose);
  - `travel_rl` and `travel_rr`: 0–40.5 LDU.
- **The mechanism:** each corner is a measured parallelogram of 100 LDU links.
  - Knuckles and wheels translate with no camber or toe change.
  - Half-shafts swing about their Cardan.
  - Shock cylinders pivot on the frame, rods slide, and springs (`stretch`) compress.
- **Limits:**
  - Front: where the tile cluster on each front lower arm reaches the inner pivot liftarm (both kept here).
  - Rear: 16 of the 20 LDU shock stroke.
- **Timeline:** settle to ride height, heave, roll, pitch, diagonal articulation, a bump under each side, then back to full droop.

## Checks

- **pytest:** 122 passed. `tests/test_suspension_standalone.py` covers:
  - extraction fidelity and a one-to-one ID map;
  - identical transforms against the full plan at four poses;
  - all closures;
  - every animation frame closed and continuous;
  - re-extraction reproducing the saved MPD byte for byte.
- **CLI:** `validate`, `sweep`, asymmetric `evaluate` (FL 9.15, FR 30.5, RL 0, RR 28.35) and `audit --require-reviewed` pass. The audit counts 4 planned and 1 static view.
- **Blender 5.2.2**, all at a 0.01 LDU tolerance:
  - **Rig** (`blender-check.json`, 14 samples): moving error 0.0021, static 3e-5, closure 0.0039, no invalid drivers.
  - **Reopen** and **animated reopen**: pass.
  - **Lifecycle:** passes (no leaks, isolated copies, restore error 5e-7).
  - **Animation** (`animation-check.json`): 17 sampled frames verified, closure on every frame, continuity passes.
- **Clearance** (`clearance.json`, 9 steps × 4 controls): no new surface crossings.
  - It tests against the **kept frame only**, since the rest of the car is absent.
  - The whole-vehicle study's clearance, against the complete car, also found none within these limits.

## Limits

Kinematic only: no spring rates, damping or weight. Steering, drive and wheel spin are not animated. Clearance is sampled, not continuous. Pin retention and ball seating are not proven.

## Files

| Group | Files |
| --- | --- |
| Model | `source/42110-suspension-standalone.mpd`, `source/idmap.json`, `keep.json` |
| Study | `study/` (prepare output, GLB) |
| Plan | `plan.json`, `diagrams/` |
| Scenes | `rigged.blend`, `animated.blend` |
| Reports | `validate.json`, `sweep.json`, `evaluate-asymmetric.json`, `audit.json`, `blender-check.json`, `reopen-check.json`, `lifecycle.json`, `clearance.json`, `animation-check.json`, `animated-reopen-check.json` |
| Previews | `preview-rest.png`, `preview-full-bump.png`, `preview-articulation.png`, `preview-articulation-side.png`, `preview-corner-rest.png`, `preview-corner-articulation.png` |

The two corner previews are Eevee renders of `animated.blend` frames 1 and 402 through `CornerCamera`. The other previews come from `scripts/blender/preview_plan.py`.

## Reproduce

```sh
S=output/42110-suspension-standalone
.venv/bin/python scripts/build_suspension_standalone.py select --plan output/42110-suspension/plan.json \
  --evidence output/42110-suspension/evidence/contacts-suspension.json \
  --moving-elsewhere output/42110/plan.json --output $S/keep.json
.venv/bin/python scripts/extract_subsystem.py output/42110-suspension/source/42110-1-shocks-split.mpd \
  --keep $S/keep.json --output $S/source/42110-suspension-standalone.mpd \
  --title "42110 Land Rover Defender - independent suspension with its mounting frame"
./ldraw-mecha prepare $S/source/42110-suspension-standalone.mpd --contact-limit 2000 --output $S/study
.venv/bin/python scripts/build_suspension_standalone.py plan --plan output/42110-suspension/plan.json \
  --study $S/study/plan.json --idmap $S/source/idmap.json --keep $S/keep.json --output $S/plan.json --ready
./ldraw-mecha rig $S/plan.json --glb $S/study/model.glb --save $S/rigged.blend \
  --report $S/blender-check.json --tolerance 0.01
"$BLENDER_BIN" --background $S/rigged.blend --python scripts/blender/animate_defender_suspension.py -- \
  --plan $S/plan.json --save $S/animated.blend --report $S/animation-check.json --corner-camera rl
```
