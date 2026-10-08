# Plant wind catalog: 20 plant cases, 60 wind clips, one scene

The deliverable is [`plants.blend`](plants.blend). Its single scene, **Wind**, holds twenty LEGO plants (palms,
bamboo, flowers, grass, reeds, vines, a hinged-branch tree, leaf vanes…). All of them are animated together by one
wind that blows from the viewer's left to the right (+X). Each plant has three wind clips: **A breeze**, **B gusty**
and **C storm**. Each plant moves in its own way: whips, flaps, sways, twirls, spins, nods, shivers, swings,
weathervanes…

Start with [`CATALOG.md`](CATALOG.md). It has:
- every case with its parts and motion;
- every control with its joint kind and response recipe;
- every clip, a style index, the clearance results and reuse snippets.

The same data is in machine form in [`catalog.json`](catalog.json). Each clip has its own file under
[`clips/`](clips/), plus `clips/WIND.json` for the shared wind. [`previews/overview.mp4`](previews/overview.mp4) shows
the whole field over the three regimes (rendered every second frame, played at 12 fps).

## How the .blend is organised

| What | Where |
| --- | --- |
| Scene | `Wind`, frames 1–752 at 24 fps. Markers `A breeze` (1), `B gusty` (257), `C storm` (513) and `end` (752). Active camera `CAM_Overview`. |
| One collection per case | `Plant wind catalog/P07_grass_meadow Grass meadow` … Each holds `SLOT_Pxx` (its fixed grid position) → the GLB root (the model), the rig collection `MECHA_plant_xx_*`, the controller, the floor labels and the case camera `CAM_Pxx`. |
| Controller | `CTRL_plant_xx_*`. One custom property per joint, in radians. The hover text gives the + meaning and the joint kind (`real` / `flex_approx`). Custom properties `pw_how`, `pw_element` and so on describe the case. |
| One Action per clip | `P01_palm_tree.breeze`, `.gusty`, `.storm`: 60 Actions. Each has one slot `plant_controller`, one LINEAR key per frame on every control, and a fake user. Metadata: `pw_case`, `pw_regime`, `pw_description`, `pw_styles`, `pw_loop_range`, `pw_channels` (meaning, joint kind, recipe per channel) and `pw_wind` (delay, direction). |
| One NLA track per clip | On each controller: `A breeze` (frames 1–240), `B gusty` (257–496) and `C storm` (513–752). Between windows the plant holds its rest pose. No active Action. |
| Wind | Collection `Wind`. Its `WIND` controller (custom properties `speed`, `u`, `v` at the field centre) has Actions `WIND.breeze`, `.gusty` and `.storm` on NLA tracks. Its `speed` drives the length of the blue arrow `WIND_arrow`. |
| Stage | Floor, three area lights, `CAM_Overview`. |

To see one case alone, make its `CAM_Pxx` the active camera, or hide the other collections.

## The wind model

This is a reusable approximation, not aerodynamics and not a multibody simulation. Everything is in
`scripts/wind_clips.py`.

**One shared field.** The wind is a speed U toward +X plus a cross-wind V toward +Z (LDraw), both normalised.
- Breeze: mean 0.42 with a periodic 4 s swell.
- Gusty: mean 0.45, three gusts up to about 0.85.
- Storm: mean 0.8, four gusts up to about 1.1, strong cross turbulence.

Gusts and turbulence are frozen into the air and travel along +X at 48 LDU per frame. The rightmost column (x =
+1040 LDU) feels each gust 43 frames after the leftmost column, so a gust visibly crosses the field.

**One recipe per joint.** The recipe turns the wind felt at that joint's x into an angle.

| Recipe | What it does |
| --- | --- |
| `osc` | A damped second-order response (natural frequency, damping ratio, gain) driven by **drag projected on the joint's own swing**. The swing is the horizontal motion of the body's tip per radian, measured from the built geometry. One wind direction therefore makes upwind fronds fold over, downwind ones flatten, cross-wind ones only flutter, and every downwind lean go +X. Options: `lag` (chain delay), `lift` (flat leaves rise in strong wind), `threshold` (sheltered plants ignore weak wind), `flutter` (fast sines growing with \|W\|²), and an asymmetric-drag drive for twist joints. |
| `spin` | A rotor whose speed follows the wind (the pinwheel daisies). |
| `vane` | Turns a leaf toward the downwind heading and lets it hunt there. |

**How each regime is solved.**
- **Breeze (A)** is the exact periodic steady state (the forcing spectrum times the transfer function). Clip frames
  25–217 are two identical periods, so they loop seamlessly.
- **Gusty (B) and storm (C)** are integrated from rest with RK4 (8 substeps per frame). They end with a 20-frame fade
  to rest.
- **All clips** start and end at rest. Spins end on a multiple of 2π/petals, which looks identical to the rest pose.
  Outputs are soft-limited (tanh) to each control's range, which gives the storm its pinned, streaming look.

## The cases

The plants were picked from `data/categories/parts/plants.py` (plus mounts from `plates.py`, `bars.py`, `hinges.py`,
`bricks.py`, `cones.py` and others) by constant name. The rule was that a plant must have a connection that can move:
a ball socket, a clip on a bar, a bar or pin in a hole, or a stud. Joints are recorded as one of two kinds:
- **`real`**: the LEGO connection allows that rotation (87 of 112 joints).
- **`flex_approx`**: a tilt of at most 0.17 rad at a rigid part's seat, standing in for bending plastic (25 joints).
  Used for thin stems, grass blades, palm leaves held on two prongs, and the flexible vine.

| ID | Plant → mount | Placement source | Official cross-check |
| --- | --- | --- | --- |
| P01 Ball-chain palm | 2563a, six 2536a, 2566b, four 2518 | sub-parts of the LDraw shortcut 2518c01 (an S-curved trunk) | ball-to-socket gaps 0.0 LDU (pitch 35) |
| P02 Swordleaf palm | four 10884 on 60478 handles on a round-brick trunk | clip grip from the clip5 primitive | 10297 palm: grip 0.014 LDU from the handle-bar line |
| P03 Bamboo clump | four 10315 stalks on 22484 balls in 14418 friction sockets | stalk contents copied from 10315, splayed 20–30° | 10315 sections (copied) |
| P04 Flower bed | three 3741a with nine 3742 in 3941 pots | pin / hole connectors | 3185: 0.001 LDU |
| P05 Sunflower | 35473 on a 2540 handle in a 61252 clip on a stem | clip / bar connectors | — |
| P06 Pinwheel daisies | 32606 / 95831 / 4367 in 63868 clips on a post | clip / bar connectors | — |
| P07 Grass meadow | ten 15279 on a plate | stud | — |
| P08 Reeds | two 30093 in 3942c cones, 30239 on each top bar | cone hollow stud as 7161; clip on the vertical top bar | 7161: 0.0 LDU |
| P09 Hanging leafy vine | 16981 rebuilt from its subfiles as five links, end bar in a 60897 clip | the part's own subfile placements, stem split | — |
| P10 Rushes row | four stalks (as 10315 stalk-3, leaf bricks swapped for 32607) on balls | as P03 | — |
| P11 Oak with hinged branches | four 2540 + 2423 in 61252 clips on a round-brick trunk | clip / bar connectors | — |
| P12 Shivering aspen | five 2423 on 4733 side studs and the trunk top | stud connectors | — |
| P13 Fern bush | four 30239 on 60478 handles | clip / bar connectors | — |
| P14 Vase bouquet | the 10297 vase (24855 + 3× 32606), and a second vase with 19119 + 6× 3742 | vase copied from 10297; 19119 seated like the 24855 bar | 41075 (3742 on 19119): 0.001 LDU |
| P15 Tiered shrub | four 1566 threaded on a 63965a bar | bar | — |
| P16 Lianas | 73828 and 16981 strung between 61252 clips on posts | end bars measured from the k03 subfiles | grip spans 180 / 300 LDU exact |
| P17 Hanging tendrils | three 28870 hung in 61252 clips under an arch, a 1997 in a 60897 clip | clip / bar connectors | — |
| P18 Ground cover | 6255, 7264, 32607, 4728, 98262, 2682a on studs | stud connectors | — |
| P19 Leaf weathervanes | 2518 / 6148 on 2714a / 63965a / 87994 bars through one hole | bar top in the leaf hole | — |
| P20 Palm crowns on an axle | 30338 trunk, two 30339 on its axle | axle / round hole | — |

`Pxx_*/source/parts.json` records every part's role, table constant, reference and colour, the joints with their
kind and evidence, the official comparisons and the geometry checks.

**Not used:**

| Plant | Why |
| --- | --- |
| Trees 3470, 3471, 2435, 3778, 52211; bushes 6064b / 6065; Fabuland trees; pumpkin 51270; root vegetable 37681; Duplo plants | One rigid piece on studs, so nothing moves except a spin of the whole plant |
| 49577 seaweed, 1747 stem, 88964 bar with leaf | No connector data and no official use to place them from |
| 2536b / 6135a short-connector palm segments | Planned for P20. Their R10 palm connector only mates other palm segments, so P20 uses the 30338 trunk with an axle instead. |
| 30176 bamboo leaf bricks on the rushes | Their lobes (49 LDU) reached the neighbouring rushes; 32607 leaf plates replace them in P10 |

## Findings worth reusing

- **Blender 5.2 driver F-curves snap small values to zero.** `driver_add` creates an identity F-curve with keys at
  (0, 0) and (1, 1). Evaluating it snaps any driver value within about 1e-4 of a key onto the key, so 5e-5 rad became
  0. That error reached 0.018 LDU at the top of a 250 LDU cane.
  - **Fixed in the shared adapter:** `ldraw_mechanisms/blender.py` `_driver` now deletes the keys, so the F-curve
    passes values through exactly.
  - **Regression checks run:** the 296 existing tests, lifecycle on P01/P03/P09 and on movables S16,
    `check_workflows.py` on P03, and a reopen check that every driver F-curve is key-free.
  - **Older blends:** rigs saved before the fix still carry the identity keys.
- **10884 swordleaf clip:** the shadow-derived clip point is 3 LDU off. 10884 places the clip5 primitive mirrored;
  use the primitive origin (0, 4, 30), whose grip axis is local Y. Against the five official fronds of 10297 the
  grip lies 0.014 LDU from the handle-bar line.
- **Swordleaf fans (10884 / 30239) grip a bar along the fan's normal.**
  - On a horizontal bar they flap in their own vertical plane.
  - On a vertical bar they swing horizontally like flags.
  - The fans are 113 LDU wide, so mounts and cones below them must leave room.
- **Clip on a bar coaxial with the part = twist only.** This applies to the 1997 curl, the vine end bars and the
  stems with a bar at their base. A pendulum needs the bar across the part, as 28870 has.
- **Flexible vines 16981 / 73828 are a unit cylinder (k04) scaled along x, plus end bars and leaves.**
  - Splitting the scaled cylinder gives rigid links. Scaled placements bind into the GLB and rig correctly.
  - pyldraw3 marks them unsupported for contact analysis only.
  - The end bars are coaxial, so a vine strung between two clips can only rock about that line.
- **Palm ball chain:** 2536a's ball (y = +3) sits in the socket (y = −32) of the part below, giving a pitch of 35
  LDU. The older 2536 stacks every 32 LDU.
- **30339 quadruple leaves reach their diagonals** (radius 245 LDU), so the grid pitch had to grow to 520 × 500 LDU.
- **pyldraw3 does not report some joints.** Bars threaded through holes (leaf bricks, 1566 tiers, vane leaves), the
  mirrored 10884 clip, 28870 in a clip and 30339 on an axle are missing; it confirms that the two parts touch for 73 of
  the 112 joint pairs. The other placements come from connector mating or the official sources named above.
- **A flex tilt about a stud centre dips the part's edge into its seat** by at most radius × angle (0.7–1.4 LDU
  here). This is inherent to the approximation and is reported by the clearance check.
- **Clip reuse across controllers:** Blender clamps keyed custom-property values to the target controller's range.
  `P02_swordleaf_palm.storm` played on the fern is cut at the fern's −0.28 rad.
- **Wind sign by geometry:** projecting drag on each tip's measured swing is enough for one wind direction to give
  plausible fold-over, flatten and flutter on identical leaves. Flat horizontal leaves also need the `lift` term,
  otherwise drag and geometry cancel (the downwind oak branch hardly moved).

## Verification

| Check | Result |
| --- | --- |
| `validate`, `sweep`, asymmetric `evaluate --set` and `audit --require-reviewed` on all 20 plans | all exit 0 (`cli-checks.txt`) |
| Sign semantics: + = downwind, tip rises, or right-hand twist | tested with the evaluator for every leaning or hinged body (`kinematics.json`) |
| Roster geometry: each recipe's joint x and swing equal the built geometry | 112 / 112 (`build_plants.py plan` refuses a mismatch) |
| Clip rules, 60 clips: rest at both ends, ranges, ≤ 0.35 rad per frame, exact breeze loop | passed (`tests/test_plants.py`) |
| The periodic breeze solution equals a long RK4 run | within 1e-5 |
| Build (`apply_plan` sweep per plan) | passed, worst 6.0e-4 LDU |
| 26 timeline frames × 20 rigs: NLA values equal the clip library; rigs equal the portable evaluator (root-relative) | worst key error 9.6e-7, worst matrix error 5.6e-4 LDU; every case inside its grid slot; WIND controller error 2.7e-8 (`animation-check.json`) |
| Reopen in a fresh process | passed (`reopen-check.json`) |
| What the reopen covers | embedded plans, hierarchy, valid key-free driver F-curves, 3 NLA tracks and 60 Actions with metadata, one scene, markers, WIND tracks and arrow driver, 14 sampled frames per case |
| Reopen clip transfer: `P02_swordleaf_palm.storm` played on the fern's controller | passed (5 of 22 samples clamped to the fern's range) |
| Lifecycle: rebuild, two copies, restoring the rest pose | passed for P01 (6-deep chain), P03 (canes with spinning children) and P09 (scaled vine links) (`adapter-checks/`) |
| `check_workflows.py` on P03 | passed |
| Pure tests: `tests/test_plants.py` (102) and the full suite | 398 passed (`pytest.log`) |
| Visual review | `previews/`: overview stills at rest, breeze, gusty peak and storm; 3 frames per regime per case (sheets `previews/Pxx_*.png`); `overview.mp4` |

**Clearance** (`check_plants_clearance.py`: every control swept alone, then every 4th frame of every clip; vertex
depth in LDU):

| Result | Cases |
| --- | --- |
| No new mesh crossing | P02, P03, P04, P06, P08, P10, P11, P12, P13, P15, P16, P18, P19, P20 |
| Contact (≤ 0.5) | P17: the 1997 curl turning in its clip touches the clip plate (0.28) |
| Shallow (≤ 1.4), all from flex tilts or parts that touch at rest | P01: leaves stacked on the crown prongs graze each other and the crown (≤ 1.06), segments meet at the ball joints (≤ 0.73). P05: stalk edge into the base (0.92). P07: blade bases into the plate (1.32). P09: vine stem pieces at the bends (0.67). P14: the leaning stem into its vase stud (1.40). |

Clearance shaped the layout and ranges:
- P02 and P13 frond ranges were narrowed because the fronds reached the trunk and the base.
- P03 canes were splayed further and their range narrowed.
- P10 rushes were spaced 80 LDU apart with smaller leaf plates.
- P08 leaves moved to the reeds' top bars.
- P17 tendrils moved away from the posts.
- P19 poles were ordered tallest upwind.

## Limitations and approximations

- **Not physics.** Transform, equation and sampled clearance checks do not prove collision-free or physically
  feasible motion. The wind response is an artistic, decoupled oscillator model:
  - no aerodynamics, gravity or contact;
  - chains are lagged oscillators, not coupled dynamics.
- **Ball joints use one of their two tilts** (about Z, so they bend with the wind); cross-wind wobble of the balls
  is not modelled.
- **flex_approx joints** (25) are not LEGO freedoms. They stand in for bending plastic and are marked in the plans,
  the controller tooltips, the Actions' `pw_channels` and the catalog.
- **Pinwheel spin** of a symmetric flower is artistic: a real flower has no blade pitch.
- **Clips are baked for their grid slot.** The wind delay depends on x, so moving a case elsewhere in a field needs
  its clips regenerated: `wind_clips.respond(spec, regime, slot_x)`.
- **Ranges are catalog choices** narrowed by clearance. They are not measured stops.
- **The mock bases, trunks and posts are generated.** Official models were used only for the placements listed
  above.
- **Overview camera:** the front row's floor labels are cut by the frame. The case cameras show them.
- **Not curated.** No reference pages were written in `docs/reference`; that happens only for results you select.

## Files and regeneration

Scripts:
- `scripts/wind_clips.py`: the wind field, response recipes, roster (cases, controls, measured geometry) and the 60
  clips. It is the single source.
- `scripts/build_plants.py`: subcommands `mpd`, `plan [--ready]`, `geometry` and `catalog` (the catalog uses
  `scripts/plant_catalog.py`).
- Blender: `scripts/blender/animate_plants.py`, `check_plants_clearance.py` and `check_plants_reopen.py`.
- Tests: `tests/test_plants.py`.
- Shared fix: `ldraw_mechanisms/blender.py` (`_driver`, see the first finding).

Per case, `Pxx_*/` holds:
- `source/scenario.mpd` and `source/parts.json`;
- `study/` (the bound GLB and the preparation report);
- `plan.json` and `kinematics.json`, which records the semantics, the measured `wind_geometry`, the joint kinds and
  contacts;
- `clearance.json`;
- the CLI reports.

```sh
.venv/bin/python scripts/build_plants.py mpd
for d in output/plants/P*_*/; do rm -rf $d/study; ./ldraw-mecha prepare $d/source/scenario.mpd --output $d/study; done
.venv/bin/python scripts/build_plants.py geometry      # measured joint x / swing (wind_clips.GEOMETRY must match)
.venv/bin/python scripts/build_plants.py plan --ready
# per plan: ./ldraw-mecha validate | sweep | evaluate --set <asymmetric> | audit --require-reviewed
B=/Applications/Blender-5.app/Contents/MacOS/Blender
$B --background --factory-startup --python-exit-code 1 --python scripts/blender/animate_plants.py -- \
   --save output/plants/plants.blend --report output/plants/animation-check.json --render output/plants/previews --video
$B --background --factory-startup --python-exit-code 1 --python scripts/blender/check_plants_clearance.py --
.venv/bin/python scripts/build_plants.py catalog
$B --background output/plants/plants.blend --python-exit-code 1 --python scripts/blender/check_plants_reopen.py -- \
   --report output/plants/reopen-check.json
.venv/bin/pytest -q
```

LDraw parts are licensed CC BY 4.0. The connector frames come from the LDCad shadow library (CC BY-SA 4.0). Official
models are cited by set number and are not redistributed here.
