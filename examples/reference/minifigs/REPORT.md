# Minifig movement catalog: 10 minifigs, 30 movement clips, one .blend

Deliverable: [`minifigs.blend`](minifigs.blend). It contains:
- ten minifigs, built from the part tables in `data/categories/parts/minifig`, each rigged with the same seven
  joints;
- three themed movement clips per figure (30 in total). Each clip is its own Blender Action on its own NLA track.

All ten figures play at the same time: clip A in frames 1–144, B in 161–304 and C in 321–464 (24 fps, 6 s per clip).

To reuse a clip, start from [`CATALOG.md`](CATALOG.md). It has the channel definitions, the clip table, a Blender
reuse snippet and a clip × figure clearance matrix. The same data is in machine form in
[`catalog.json`](catalog.json), with one file per clip under [`clips/`](clips/).

## How the .blend is organised

| What | Where |
| --- | --- |
| One collection per figure | `Minifig catalog/MF01_police Police officer` … `MF10_diver Diver`. Each holds the model, its rig collection `MECHA_minifig_xx_*`, and the `SLOT_` and `MOVE_` empties. |
| Controller per figure | `CTRL_minifig_01_police` … `CTRL_minifig_10_diver`, with the same 13 custom properties on each (below) |
| One Action per clip | `MF03_knight.sword_slash` and so on: 30 Actions. Each has a single slot `minifig_controller`, keys on all 13 controller properties, a fake user and its frame range set. Custom properties `mf_figure`, `mf_clip`, `mf_title`, `mf_description`, `mf_window`, `mf_timeline_start` and `mf_loop_range` describe the clip. |
| One NLA track per clip | On each controller: `A <clip>`, `B <clip>`, `C <clip>`, one strip each at the window start. Strips hold their last value forward, so the gaps between windows stay at the neutral pose. No active action is assigned. |
| Timeline markers | `A clips`, `B clips`, `C clips`, `end` |
| Stage | `Labels` (each figure's name and clip names on the floor), `Stage` (floor, `CatalogCamera`, three area lights) |

Layout: two rows of five, 240 LDU apart across and 400 LDU between rows. Each figure stands on the floor at its
`SLOT_`.

## The figures

All parts are picked by their constant name in the vendored tables. The builder checks that each part exists in the
LDraw library and is not an obsolete or moved stub.

| Figure | Torso | Head / headgear | Held / worn |
| --- | --- | --- | --- |
| MF01 Police officer | `973p1f` | `3626cp84` / police hat `3624` | radio `3962b` (left) |
| MF02 Classic spaceman | `973p90` | `3626cp01` / helmet `3842a` | airtanks `3838` |
| MF03 Knight | `973p41` | `3626cp07` / helmet `3844` | shield `3846p45` (left), sword `3847` (right) |
| MF04 Construction worker | `973p8i` | `3626cp72` / helmet `3833` | hammer `55295` (right) |
| MF05 Chef | `973p2a` | `3626cp7c` / cook's hat `3898` | frying pan `4528` (left), ladle `4337` (right) |
| MF06 Pirate | `973p3e` | `3626cp30` / bicorne `2528a` | cutlass `2530` (right) |
| MF07 Firefighter | `973p21` | `3626cp7i` / fire helmet `3834p01` | hose nozzle `4210a` (right) |
| MF08 Athlete | `973pg7` | `3626cp73` / hair `3901` | — |
| MF09 Wizard | `973pmc` | `3626cp88` / wizard's hat `6131` | staff `95049` (right) |
| MF10 Diver | `973p5f` | `3626cp8b` / — | airtanks `3838`, flippers `59275a` |

Every figure also has arms `3818`/`3819`, hands `3820`, hips `3815b` and legs `3816c`/`3817c`.

Two constraints shaped the part choice:
- **Torsos:** the patterned "torso with arms and hands" parts (`76382…`, `973c…`) are single meshes, so their arms
  cannot move. Only plain `973p…` torsos are used.
- **Misfiled entries:** some table entries are in unexpected files. The hips `3815b` sit in `accessories.py`, and
  many hats are in `accessories.py` too.

Sources:
- The MPDs are `MFxx_*/source/minifig.mpd`, one flat file per figure.
- `source/parts.json` maps each occurrence ID to its role, table constant, part ID and colour.
- LDraw parts are licensed CC BY 4.0. The connector frames come from the LDCad shadow library (CC BY-SA 4.0).

## Assembly and joints (measured)

**Placement.** Parts are placed by mating LDCad shadow connector frames, read through pyldraw3, in this order:
torso, then hips, legs, arms, hands, hand items, head, headgear and back items. Matrices are written at full
precision.

**Cross-check against the official 6682 minifig** (`data/models-annotated/6682-1.mpd`):
- All rotations match exactly, including the arm tilt (rows 0.985/0.17) and the hand's Rx(45°) on the arm.
- Hips and legs coincide.
- Arms differ by 1.0 LDU: the shadow torso sockets are at y = 9, while 6682 places the arms at y = 8. The hands
  differ by 0.9 LDU as a result.

**Frame:** LDU, with the torso origin at the neck, −Y up, the face looking along −Z, and the figure's left at +X. The
feet are at y = +72.

| Control | Body (parts) | Origin | Axis (sign set by meaning) | + means | Range |
| --- | --- | --- | --- | --- | --- |
| `neck` | head + headgear | (0, 0, 0) | (0, −1, 0) | face turns to the figure's left | ±π |
| `shoulder_l` | left arm | (15.552, 9, 0) | (−0.985, 0.170, 0) | arm forward and up | ±4π |
| `shoulder_r` | right arm | (−15.552, 9, 0) | (−0.985, −0.170, 0) | arm forward and up | ±4π |
| `wrist_l` | left hand + item (parent arm_l) | (23.691, 26.758, −9.884) | (−0.120, −0.697, 0.707) | item tip rolls outward (+X) | ±π |
| `wrist_r` | right hand + item (parent arm_r) | (−23.691, 26.758, −9.884) | (−0.120, 0.697, −0.707) | item tip rolls outward (−X) | ±π |
| `hip_l` | left leg (+ flipper) | (2, 44, 0) | (−1, 0, 0) | leg forward (+π/2 = seated) | ±π/2 |
| `hip_r` | right leg (+ flipper) | (−2, 44, 0) | (−1, 0, 0) | leg forward | ±π/2 |

Where each axis comes from:

| Joints | Connector pair |
| --- | --- |
| Shoulders | torso sockets in `s/973s01` and the arm pins |
| Wrists | arm sockets (45°) and the `3820` pin |
| Hips | `s/3815bs01` leg pins and the leg holes |
| Neck | the torso neck pin and the head socket |

**Signs.** The sign of each axis is set by a test with the portable evaluator (`kinematics.json`). Taking the
measured axes as they come, `shoulder_r`, `wrist_r` and `hip_l` had to be flipped, which is what the mirrored sides
predict.

**Independent connector check.** pyldraw3 contacts confirm all seven joints on all ten figures. These fixed
attachments are not detected, because their connector kinds do not pair:
- headgear on the head stud (placed at the head origin, the LDraw headgear convention);
- the knight's shield and the firefighter's nozzle in the hand clip;
- the diver's flippers.

**Ranges** are catalog choices, not measured stops: the real joints spin freely.

**Hand items:**
- **Grip:** each item's working end points along the hand clip's forward axis (forward and up at rest). Which end
  is the working end was read from the part geometry beyond the bar.
- **Ladle:** reversed so the bowl hangs down when stirring.
- **Frying pan:** rotated 285° about its bar, so that at `shoulder_l` = 0.45 and `wrist_l` = −1.31 it lies level
  across the belly. That pose was found with the evaluator.

**Plans:**
- One per figure, `MFxx_*/plan.json`, status `ready`.
- Seven `planned` mechanism views plus a `static` core (torso, hips, back items), with reviewed connector evidence
  in `connections`.
- Each passes `validate`, `sweep`, an asymmetric `evaluate` and `audit --require-reviewed`.

## Whole-figure channels (staging, not a mechanism)

Six more custom properties on each controller move the whole figure about its hip-axis centre, (0, 44, 0), which is
28 LDU above the ground:

| Channel | Unit | Meaning |
| --- | --- | --- |
| `move_forward` | LDU | home-frame offset forward |
| `move_left` | LDU | home-frame offset to the figure's left |
| `move_up` | LDU | home-frame offset up |
| `turn` | rad | yaw; + turns left |
| `pitch` | rad | about the hip axis; + leans forward |
| `roll` | rad | + leans toward the figure's left |

- **Order:** translate, then turn, then pitch, then roll.
- **Rig:** they drive `MOVE_MFxx`, which sits under `SLOT_MFxx` and is the parent of the GLB root. The driver
  expressions are in `minifig_clips.MOVE_DRIVERS`.
- **Not part of the plan:** these channels are not plan controls, so the joint verification, which is
  root-relative, is unaffected by them.

## Clips

| Figure | A | B | C |
| --- | --- | --- | --- |
| MF01 Police officer | walk_patrol | look_around | halt_signal |
| MF02 Spaceman | moon_hop | zero_g_tumble | wave |
| MF03 Knight | sword_slash | shield_block | courtly_bow |
| MF04 Construction worker | hammering | carry_load | head_shake_no |
| MF05 Chef | stirring | pan_flip | celebrate |
| MF06 Pirate | hornpipe_jig | lookout | cutlass_lunge |
| MF07 Firefighter | ladder_climb | run | hose_sweep |
| MF08 Athlete | sprint | high_jump (spin jump) | warmup_leg_swings |
| MF09 Wizard | spell_spin | levitate | cast_spell |
| MF10 Diver | swim_crawl | sit_down_stand_up | fall_and_get_up |

Descriptions and loop ranges (one stride, stroke or hop) are in `CATALOG.md`.

**Single source:** all clips are defined in `scripts/minifig_clips.py`. Their keys are sparse and use Blender's
own easing equations (SINE, QUAD or LINEAR per segment), so the Python values match Blender exactly. Sine waves start
and end on zero crossings, so they are exact; hops are exact parabolas (QUAD out, then in).

**Rules, all tested:**
- every channel starts at 0 and ends at 0, or on whole turns for shoulders, `turn`, `pitch` and `roll`;
- the figure returns to its home spot;
- values stay within range and change continuously.

**Gaits:**
- **Hip height:** as the straight legs split, the hips drop by 28 (1 − cos hip).
- **Travel:** eased so that velocity stays continuous.
- **Run:** the feet slide, because travel is shorter than the stride.

**Floor sit:** the legs lie flat at a hip angle of π/2 − 0.27 with the body leaned back 0.27 rad, which puts the
hip axis 11.1 LDU above the floor. With the legs at a full π/2, the resting hands sink into the thighs.

## Checks run

| Check | Result |
| --- | --- |
| `.venv/bin/pytest -q` (whole suite, including the new `tests/test_minifigs.py`) | 203 passed |
| Plan checks on all 10 plans (`validate`, `sweep`, asymmetric `evaluate`, `audit --require-reviewed`) | pass |
| Scene build (`animate_minifigs.py`), 23 timeline frames × 10 figures (inside every window and in the gaps) | passed: 230 samples. Worst errors: controller vs clips 3.3e-6, rig matrices 2.0e-4 LDU (tolerance 0.002), whole-figure transform 9.5e-5 LDU |
| Fresh-process reopen (`check_minifigs_reopen.py`) | passed: 10 figures × 11 frames, 30 Actions, worst matrix error 1.8e-4 LDU. `MF03_knight.sword_slash` on `CTRL_minifig_05_chef`: 14 frames, worst error 4.9e-7 |
| `check_lifecycle.py` per plan (`MFxx/lifecycle.json`) | 10/10 passed |
| Adapter regressions after the `check_clearance` change: `check_workflows.py` (42083 W16), `check_prepared.py`, reopen and lifecycle (106 roof), under `adapter-checks/` | all passed |

**Scene build check:** at every sampled frame, the build checks that:
- the controller values equal the clip library;
- every rig matches the portable evaluator, root-relative;
- every root equals rest @ `figure_transform`.

**Reopen check:** after reopening the saved file, it checks:
- each embedded plan equals its plan file;
- there are 30 Actions, with the right tracks, slots and metadata;
- the `MOVE_` drivers are valid;
- sampled frames re-verify;
- **clip reuse:** `MF03_knight.sword_slash` is played on the chef's controller and compared with its exported JSON.

## Clearance (mesh crossings, joints only)

`scripts/blender/check_minifigs_clearance.py` uses `blender_tools.check_clearance`. Rest-contact and same-body pairs
are excluded. For each figure it:
1. sweeps each joint on its own;
2. samples every clip every 6 frames as combined poses;
3. repeats the clip sampling with a 1.5 LDU shrink, which keeps only crossings deeper than about 3 LDU.

- **Own clips:**
  - **Clear (7 figures):** police, knight, builder, chef, pirate, firefighter and wizard play all three of their
    clips with no new crossing.
  - **Overhead arm passes (3 clips):** the spaceman's `wave` (as the arm rises), the athlete's `high_jump` (arms
    going up and down) and the diver's `swim_crawl` (each stroke) cross the head.
- **Why overhead arms cross:** the shoulder axis is tilted 9.79°, so a raised hand swings inward. Between about 2.1
  and 2.9 rad it passes inside the head's outline, whatever the wrist roll. Arms held at ≤ 2.0 rad (hands in front
  of the chin) or near π (straight up) are clear. Held poses in the clips were tuned to those values. Only motions
  that must pass overhead keep the crossing, and only while passing.
- **Every clip on every figure** (`--all-clips`): the matrix is in `CATALOG.md`.
  - **Bare-handed figures** (spaceman, athlete, diver) take 27 of the 30 clips without crossings.
  - **Long items and wide headgear** (knight, chef, wizard and others) cross on many clips borrowed from other
    figures.
- **Single-joint sweeps:** full-range sweeps report crossings for large items. For example, the shield against the
  legs, the staff and sword against the hat, and the cutlass against the right leg.

## Limitations and assumptions

- **No physical proof:** transform and equation checks plus visual review do not establish collision-free or
  physically feasible motion. Clearance is sampled and does not test containment.
- **Whole-figure motion is staging, not simulation.** Ground contact is approximate (heights from the leg and hip
  geometry), feet slide in the walk and run, and jumps and the tumble are kinematic. Nothing touches anything:
  there is no ladder, pot, hose, water, pancake or seat. Whole-figure channels are not clearance-checked against the
  floor or the neighbouring slots.
- **Seated and lying heights are approximations:** 11.1 LDU (leaned-back sit) and 24 LDU (the diver on its tanks).
  The diver stands on its flippers, 2 LDU higher than bare feet.
- **Attachments not confirmed by pyldraw3:** headgear, the shield, the nozzle and the flippers are placed from
  connector frames or the LDraw headgear convention.
- **Hand-item roll was chosen visually:** the `spin` values in `ITEMS` (`scripts/build_minifigs.py`), apart from
  the solved frying pan.
- **Joint ranges** (±π, ±4π, ±π/2) are catalog choices.

## Files and how to reproduce

Code:
- `scripts/build_minifigs.py`: roster, connector placement, MPD writer, plan author, catalog export.
- `scripts/minifig_clips.py`: joint and channel conventions and the 30 clips.
- `scripts/blender/animate_minifigs.py`: builds the scene.
- `scripts/blender/check_minifigs_reopen.py`: reopen and clip-reuse check.
- `scripts/blender/check_minifigs_clearance.py`: clearance.
- `tests/test_minifigs.py`: pure tests.
- `ldraw_mechanisms/blender_tools.check_clearance` gained optional `poses` (combined states) and `shrink`. The
  defaults are unchanged; the new options are documented in `docs/discovery-and-blender.md`.

```sh
export BLENDER_BIN=/Applications/Blender-5.app/Contents/MacOS/Blender
.venv/bin/python scripts/build_minifigs.py mpd
for d in output/minifigs/MF*; do ./ldraw-mecha prepare $d/source/minifig.mpd --output $d/study; done
.venv/bin/python scripts/build_minifigs.py plan --ready
"$BLENDER_BIN" -b --factory-startup --python-exit-code 1 --python scripts/blender/check_minifigs_clearance.py
"$BLENDER_BIN" -b --factory-startup --python-exit-code 1 --python scripts/blender/check_minifigs_clearance.py -- --all-clips
.venv/bin/python scripts/build_minifigs.py catalog
"$BLENDER_BIN" -b --factory-startup --python-exit-code 1 --python scripts/blender/animate_minifigs.py -- \
  --save output/minifigs/minifigs.blend --report output/minifigs/animation-check.json --render output/minifigs/previews
"$BLENDER_BIN" -b output/minifigs/minifigs.blend --python-exit-code 1 \
  --python scripts/blender/check_minifigs_reopen.py -- --report output/minifigs/reopen-check.json
for d in output/minifigs/MF*; do "$BLENDER_BIN" -b --factory-startup --python-exit-code 1 \
  --python scripts/blender/check_lifecycle.py -- --plan $d/plan.json --glb $d/study/model.glb --report $d/lifecycle.json; done
```

Previews (Cycles): `previews/overview-f*.png` shows the whole stage at the middle of each window, and
`previews/figures/MFxx-<window><phase>-f*.png` shows three phases of every clip.
