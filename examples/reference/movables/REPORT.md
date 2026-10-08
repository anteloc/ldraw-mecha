# Movable-element catalog: 20 mock scenarios, 60 movement clips, one .blend

The deliverable is [`movables.blend`](movables.blend). It holds 20 small scenarios of classic movable LEGO elements
(doors, windows, shutters, gates, lids, traps, car doors, a canopy, sliders, turntables and hinged booms). Each
scenario is animated three different ways. Minifigs and Technic mechanisms are out of scope.

Start with [`CATALOG.md`](CATALOG.md). It lists every scenario with its controls and joint frames, every clip with
its movement styles, a style index ("which clip shows a slam with a bounce?"), the clearance results and reuse
snippets. The same data is in machine form in [`catalog.json`](catalog.json), and each clip has its own file under
[`clips/`](clips/).

## How the .blend is organised

| What | Where |
| --- | --- |
| Overview | Scene `Catalog`: all 20 scenarios in a labelled 5 × 4 grid on one floor, with `CatalogCamera`. Timeline markers `A clips`, `B clips`, `C clips` and `end`. |
| One scene per scenario | Scenes `S01 House front door` … `S20 Control levers`. Each links that scenario's collection and the shared `Stage` (floor and lights). It has its own camera `CAM_<key>` framed on the whole motion, and markers named after its three clips (`A open_close`, `B slam`, `C creak`). |
| One collection per scenario | `Movable catalog/S01_house_door House front door` … It holds `SLOT_<key>` (stage position) → the GLB root (the model), the rig collection `MECHA_movable_xx_*`, the floor labels and the controller. |
| Controller | `CTRL_movable_xx_*`. It has one custom property per plan control, in radians for hinges and turntables and LDU for slides (1 LDU = 0.4 mm). Hover text gives the + meaning. |
| One Action per clip | `S07_treasure_chest.slow_reveal` and so on: 60 Actions. Each has one slot `movable_controller`, keys on all of the scenario's controls, a fake user and its frame range. Custom properties `mv_scenario`, `mv_clip`, `mv_title`, `mv_description`, `mv_styles`, `mv_window`, `mv_loop_range` and `mv_channels` describe it. |
| One NLA track per clip | On each controller: `A <clip>` (frames 1–144), `B <clip>` (161–304) and `C <clip>` (321–464). Between windows the element holds its rest pose. No active Action is assigned. |

All clips are 144 frames at 24 fps. Every clip starts and ends at rest; the radar spins end on whole turns.

## The scenarios

Movable elements were picked from the category tables (`doors.py`, `windows.py`, `hinges.py`, `containers.py`,
`turntables.py`, `vehicles.py`, `plates.py`, …) by constant name. Two checks decided whether a candidate was usable:
- **Connectors:** does it have LDCad shadow connectors that give a joint frame?
- **Official use:** does an official model in `data/models-annotated` hold the same pair, so the placement can be
  compared?

Each scenario's mock context (wall, floor, fence, chassis, castle gate) is built from basic bricks and plates on the
stud grid. The context is static.

| ID | Moving element → mount | How the joint was placed | Official cross-check |
| --- | --- | --- | --- |
| S01 House front door | door 60616b → frame 60596, in a brick wall | hinge connector pair | 10185 (60616a): 0 LDU |
| S02 Casement window | 2 panes 60608 → window 60594 | hinge pairs | 10224: 1 LDU |
| S03 Shuttered window | 2 shutters 3856 → classic window 3853 | hinge pairs | 6350 (closed): 3.0 / 3.2 LDU |
| S04 Garden gate | gate 3186 → gate base 3187, between fences | pin / pin hole | 6379: 0 LDU |
| S05 Kitchen cupboard | door 4533 and two drawers 4536 → two cupboards 4532 | hinge pair; generic slot, slide along −Z | 10197, 6416: 0 LDU |
| S06 Double-door cabinet | 2 doors 2043 → cupboard 2x6x7 2042 | 2042 has no hinge connector: placement from set 3636, axis from 2043's own hinge | 3636: 0 LDU |
| S07 Treasure chest | lid 4739a → chest 4738a | hinge pair | none (no annotated model holds the pair) |
| S08 Mailbox | slot door 4346 → box 4345a on a post | hinge pair | 1490: 0 LDU |
| S09 Floor trap door | trap door 30042 → frame 30041 on pillars | frame clips carry no hinge frame: placement from 6769/7657, axis from 30042's pins | 6769: 0 LDU |
| S10 Town car doors | doors 3822 / 3821 → mock car chassis | door hinge tube on a chassis stud, as set 106 | 106: 0 LDU |
| S11 Car roof hatch | roof 4213 → roof holder 4214 on a mock car | hinge pair | 106: 0 LDU |
| S12 Spaceship canopy | windscreen 2620 → hinge plate 4315 | hinge pair | 6351: 1 LDU |
| S13 Forklift mast | forks 3431 → rails 3430, spring u9529-f2 | positions from shortcuts 3430c00-f1/-f2 (raised/lowered) | shortcut DATs |
| S14 Sliding shed door | door 4511 → two door-rail plates 4510 end to end | no connectors: placement and slide direction from set 7735 | 7735: 0 LDU |
| S15 Rotating radar | turntable top 3679 + dish 3960 → base 3680 | pin / pin hole (shortcut 3680c01 split into its sub-parts) | shortcut DAT |
| S16 Mini crane | turntable 3404 (slew) → 3403; boom on hinge 3937 / 6134 (luff); hook 3136 | pin / pin hole; hinge pair; hook in a 1x2 brick with hole | — |
| S17 Dump truck tipper | bucket 4080 on hinge plates 4275b → hinge tiles 4531 | placement from set 6532; axis from 4531 (see findings) | 6532: 0 LDU |
| S18 Parking barrier | striped boom on hinge 1x2 top 3938 → base 3937 on a post | hinge pair | — |
| S19 Drawbridge | deck on two hinge 1x2 pairs 3937 / 3938 at a castle gate | hinge pairs (coaxial) | — |
| S20 Control levers | 2 sticks 4593 → bases 4592 on a desk | hinge pairs | — |

`Sxx_*/source/parts.json` records every part's role, table constant, reference, colour and the official
comparison. One context part, the wheel holder 4600, is referenced directly because the tables list only the later
4870 mould.

**Candidates not used:**

| Candidate | Reason |
| --- | --- |
| Garage door 821/822, revolving door 30101/30102, castle gate 33227 with portcullis 89513, two-way door 3861a, trailer ramp 727 | No connector pair and no annotated model to place them from |
| Roller door 4218b, lift door 6155 | Segmented flexible shutters that roll into their frames, so they can't be one rigid body. 6155 was planned for S13; the forklift mast replaced it as the vertical-slide example. |
| Click hinges 44301a / 44302a | Planned for the drawbridge, but the straight pair crossed at once in the sweep and no flattened official model holds it. Hinge 1x2 pairs are used instead. |

## Findings worth reusing

- **The 4275b / 4276b shadow hinge frames lie along the plate, not along the finger axis.** Set 6532 shows the
  bucket turning about the finger line, which is also what the 4531 hinge tile's connector gives. S17 uses the
  4531 frame. Check these plates' connector axis before rigging with them.
- **Opening side is geometry, not choice.**
  - The casement panes clear frame 60594 only on its back side, so S02 is turned 180° to face the viewer.
  - The canopy 2620 hangs from its top-rear hinge, so opening swings its lower edge **forward** and up. The deck
    ahead of it must stay flat, which is why S12 has a tiled nose instead of a slope.
- **Hinge tops overhang their axis.** The back stud row of hinge 2x2 top 6134 sits over the axis, and parts on it
  dip into the hinge base as the boom rises. The S16 boom therefore sits on a 1x2 riser on the front row.
- **Dependent motion:**
  - The crane hook is a child of the boom with signal `hook_angle = -luff`, so it stays plumb (checked at three
    poses, including slewed ones).
  - The forklift spring is a `stretch` body. Its signal `spring_scale = (136 - lift) / 136` is a scale about its
    fixed top seat, and its lower seat follows the forks to within 1e-6 LDU.
- **Sign convention by meaning.** The sign of each axis was set by an evaluator test ("+ door opens toward the
  viewer", "+ lifts the front edge") and recorded in `kinematics.json`. Mirrored leaves therefore carry mirrored
  axes.
- **Blender, background mode:** a scene other than the context scene re-evaluates its animation for rendering only
  inside `bpy.context.temp_override(scene=…, view_layer=…)`. Without it, renders show the last-evaluated pose. In
  the UI the active scene evaluates normally.

## Controls and clips

The control names, units, ranges and + meanings are in `CATALOG.md`. Ranges are catalog choices, narrowed by the
clearance sweeps against each mock context; they are not measured mechanical stops.

The 60 clips cover 19 movement styles:
- `ease_cycle`, `slam_bounce`, `hesitant`, `mirrored_pair`, `staggered_pair`
- `damped_swing`, `flutter`, `peek`, `gravity_drop`, `winch_linear`
- `overshoot_settle`, `stepped`, `continuous_spin`, `spin_up_down`, `sweep`
- `slide_bounce`, `sequence`, `shake`, `toggle`

They use Blender's own interpolation and easing per key: SINE, QUAD, CUBIC, LINEAR, CONSTANT, `BOUNCE_OUT` (hitting
a stop) and `BACK_OUT` (overshoot with back = 1.70158). The Python evaluator `movable_clips.value_at` implements the
same equations, so the JSON values equal what Blender plays. The build checks this to 1e-5.

## Verification (final run)

| Check | Result |
| --- | --- |
| `validate`, `sweep`, asymmetric `evaluate --set`, `audit --require-reviewed` on all 20 plans | all exit 0 (`cli-checks.txt`) |
| Build: `apply_plan` sweep per plan; 28 timeline frames × 20 rigs (controller = clip library, rig = portable evaluator, root-relative) | passed. Worst key error 1.0e-5, worst matrix error 4.0e-4 LDU (`animation-check.json`) |
| Scenario scenes reproduce the catalog's poses while the catalog is parked at rest | 20/20, difference 0 (`animation-check.json` → `scene_checks`) |
| Reopen in a fresh process: embedded plans, hierarchy, drivers, NLA tracks, 60 Actions, 21 scenes and markers, sampled frames; a clip transfer (`S10_car_doors.both_doors` on the cabinet's controller) | passed (`reopen-check.json`) |
| Lifecycle (rebuild, two copies, rest restoration) for S16 (parented and dependent), S13 (stretch) and S19 | passed (`adapter-checks/`) |
| Pure tests `tests/test_movables.py` (93) and the full suite | 296 passed (`pytest.log`) |
| Visual review of the previews | `previews/` (catalog stills; 3 frames per clip per scenario, sheets `previews/Sxx_*.png`) |

**Clearance** (`check_movables_clearance.py`; every control swept, then every 4th frame of every clip):

| Result | Scenarios |
| --- | --- |
| No new mesh crossing | 16 |
| Contact level (deepest vertex at most 0.12 LDU), only within a few degrees of closed: square edges sweeping past each other | S02 pane against pane; S04 gate end against the right fence post; S12 canopy rear rim against the hull |
| Shallow (deepest vertex 1.6 LDU) | S13: the rescaled spring coils against the forks and rails |

Rest-contact pairs (a hinge leaf and its frame) are excluded by design. The larger-shrink pass is recorded but is not
meaningful for thin parts such as lattices, window frames and canopy shells.

## Limitations and approximations

- Transform, equation and sampled clearance checks do **not** prove collision-free or physically feasible motion.
  The bounces, overshoots, pendulum swings and gravity drops are easing curves, not simulation.
- The mock contexts are generated, not official builds. Official models were used only to place and cross-check
  the moving pairs.
- **S13 spring.** The spring is the extended spring DAT scaled along its axis. Its end caps compress with it, and
  its coils touch the forks and rails by up to 1.6 LDU.
- **S16 hook.** The hook's pins sit in the hole of a Technic brick 1x2 with hole (3700), used as a plain structural
  carrier. The real hook is meant to hang from a string.
- **Trap door, car doors.** pyldraw3 does not report the trap door's pins in the frame's clips, nor the car doors'
  hinge tubes on the chassis studs. Both placements are taken from official models (0 LDU difference).
- **S07 chest.** The chest and lid are checked against their connectors only.
- **S03 shutters.** The shutters are 3 LDU from 6350's closed placement. Their connector-mated hinge line agrees
  within 2 LDU with 6365, which shows them opened 60°.
- **Lever range.** The control-stick range ±0.7 rad is a catalog choice; the clearance sweep found no stop before
  ±1.6 rad.
- **Not curated.** No curated reference pages were written (`docs/reference`). That happens only if you select
  results.

## Files and regeneration

Scripts:
- `scripts/movable_clips.py`: roster, controls and the 60 clips (the single source of keys).
- `scripts/build_movables.py`: `mpd`, `plan [--ready]` and `catalog`.
- Blender: `scripts/blender/animate_movables.py`, `check_movables_clearance.py` and `check_movables_reopen.py`.
- Tests: `tests/test_movables.py`.

Per scenario, `Sxx_*/` holds:
- `source/scenario.mpd` and `source/parts.json`;
- `study/` (bound GLB and preparation report);
- `plan.json` and `kinematics.json`;
- `clearance.json`;
- the CLI reports.

```sh
.venv/bin/python scripts/build_movables.py mpd
for d in output/movables/S*_*/; do rm -rf $d/study; ./ldraw-mecha prepare $d/source/scenario.mpd --output $d/study; done
.venv/bin/python scripts/build_movables.py plan --ready
# per plan: ./ldraw-mecha validate|sweep|evaluate --set ...|audit --require-reviewed  (values: build_movables.asymmetric)
export BLENDER_BIN=/Applications/Blender-5.app/Contents/MacOS/Blender
$BLENDER_BIN --background --factory-startup --python-exit-code 1 --python scripts/blender/animate_movables.py -- \
    --save output/movables/movables.blend --report output/movables/animation-check.json --render output/movables/previews
$BLENDER_BIN --background --factory-startup --python-exit-code 1 --python scripts/blender/check_movables_clearance.py --
.venv/bin/python scripts/build_movables.py catalog
$BLENDER_BIN --background output/movables/movables.blend --python-exit-code 1 \
    --python scripts/blender/check_movables_reopen.py -- --report output/movables/reopen-check.json
.venv/bin/pytest -q
```

LDraw parts are licensed CC BY 4.0. The connector frames come from the LDCad shadow library (CC BY-SA 4.0).
Official models are cited by set number and are not redistributed here.
