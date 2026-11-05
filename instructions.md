# Agent workflow

Use **prepare → edit the plan → check → rig → visual review**.
The [workflow guide](docs/workflow.md) is the command reference;
[how it works](docs/how-it-works.md) explains the model behind it.

## Before preparation

1. Read the [reference catalog](docs/reference/README.md) for matching mechanisms.
   Reuse reasoning and checks; remeasure the target's parts, frames and limits.
2. Choose scope. A request for one mechanism defaults to a standalone subsystem
   with the agreed coupled elements and mounts. Resolve unclear boundaries early,
   reusing prior user decisions. Explicit whole-model/in-place requests win.
   Study with `--section`, then use `scripts/extract_subsystem.py` and remap IDs;
   the delivered MPD, GLB and blend must contain only the selected subsystem.
3. For an **unannotated original**, offer to [annotate](docs/annotation.md) it
   with `bin/ldraw-annotator`. Run `prep` first (no tokens), then give the user
   the model's size and a token estimate, with a plain warning for large models.
   If they decline, stop. If they accept, follow `ldraw-annotator prompt` on the
   prepped copy until `ldraw-annotator check` says `"ok": true`, then use that
   copy for everything that follows, as if it were the model supplied.
   **Do not rewrite or regroup already annotated models unless requested.**

## Prepare, author, check and rig

```sh
./ldraw-mecha prepare MODEL.mpd --output output/study
# Inspect evidence/geometry; edit output/study/plan.json with measured motion.
./ldraw-mecha check output/study
# Reconcile every finding, then check recorded scope before delivery.
./ldraw-mecha check output/study --require-reviewed
./ldraw-mecha rig output/study --animate --reopen
```

- `prepare` saves identities, candidate evidence, a draft plan and a bound GLB.
  `--no-glb` is source-only; `--recipe NAME` adopts studied motion for an exact
  matching source while retaining unresolved evidence. Never reprepare over an
  edited study. Read `preparation.json`: skipped searches, contact kinds, axle
  coverage, placement corrections and unsupported geometry. Default contact
  budget: 300 parts, adjustable to 2000. Investigate zero axle coverage in a
  drivetrain; use focused queries for larger assemblies.
- Inspect early with `blender_tools.inspect_prepared` and `select_mechanism`.
  Record visual findings immediately, including input, output and missing links.
  Candidate views are provisional and may overlap; they are not rigid bodies.
  Retain findings until planned, explicitly deferred or reviewed as static.
- **Look** with [`./ldraw-mecha xray`](docs/xray.md) (`bin/ldraw-xray doctor` once).
  When a candidate's parts or axis are uncertain: `xray STUDY --instances IDS
  --point X Y Z --direction X Y Z` with the axis from `connectors`. Before `rig`
  and after each correction: `xray STUDY` (or `--body NAME`). Answer each board's
  check list and cite `xray/<board>/mosaic.png`. xray angles are degrees, plan
  values radians. Renders are not clearance proof.
- Author in the same [version-1 plan](docs/motion-plan.md). Keep `source` intact.
  Declare moving parts (including rim and tyre), measured origins/axes, limits,
  dependencies, anchors and checks. `mechanisms.add_joint` handles simple hinges
  and sliders. Record coupling meaning, signs, conditions and approximations in
  notes/evidence, not only in scripts or renders. Set `status: ready` when the
  declared motion is decided; this does not assert complete discovery.
- For drivetrains and machines, follow the [mechanism authoring guide](docs/mechanisms.md).
  Resolve keyed shafts, round bearings, mixed pin sections and carriers before
  assigning spin. Add occurrence-based rigidity, axis, ratio and closure checks;
  use `check --require-constrained` and `rig --require-constrained`. Empty checks
  or agreeing driver expressions do not validate a transmission.
  Start new spur drives from `scripts/gear_drive.py`; its `transmission.shaft`
  and `mesh` helpers create checked keyed groups and a coupled follower.
- `check` combines source validation, independent sweeps, default/mixed poses
  and a scope audit. Add meaningful nonzero/asymmetric `--set NAME=VALUE` cases
  and mechanism-specific assertions for ratios, links and selector states.
  Review `check.json`; `--require-reviewed` permits explicit deferrals, which
  still belong in the delivery's omitted-work list, but fails on every
  `body_boundary` warning: a pin or axle shared off the joint between two bodies
  usually means a part sits in the wrong body. Fix membership or declare a check.
- Apply to the inspected root or use background `rig`. Reuse the bound GLB while
  source/selection stays unchanged. `--reopen` checks persistence in a fresh
  process. Verify the actual demonstration, inspect/render several poses and
  limits, and run relevant [clearance checks](docs/validation.md#clearance-and-visual-review).
  Deliver the exact source, plan, blend, animation, reports and previews reviewed,
  with deferred mechanisms and untested assumptions.
- **Hand over** as in [the workflow](docs/workflow.md#hand-over-the-result): clickable
  workspace-relative links to the `.blend` (plus its absolute path), every
  `xray/<board>/mosaic.png`, stills and reports; then offer to open the `.blend` in
  Blender's user interface, and launch it detached only if the user agrees.

## Invariants and focused tools

- Use pyldraw3 for parsing/connector expansion and `scripts/mpd2glb.sh` for
  conversion. Binding must succeed; never substitute an unbound GLB or infer
  identity from Blender names. Source edits invalidate hashes and may change
  occurrence IDs; regenerate/rebind. Preserve originals and the supplied Blender
  reference scripts. Generated artifacts belong under `output/`.
- Analysis stays independent of Blender. Motion angles are radians, geometry and
  slide lengths LDU; discovery's explicitly named angle tolerances use degrees.
  Motion is a source-pose offset. Body parenting composes motion, so wheel spin
  follows its steering/suspension carrier.
- Use [part information](docs/part-information.md) for selection and
  [analysis tools](docs/discovery-and-blender.md) for measurement. Connector
  `position`/`frame` are part-local; `world_position`/`world_axis` are in the
  selected model. LDCad's local Y is the connector axis. Rounded near-rigid frames
  are corrected only for analysis; compare `--raw-transforms` when needed.
  Review scale/shear, aliases, library availability and unsupported geometry.
  Coaxial lines do not prove coupling; worm direction needs measurement. Surface
  contacts, friction and stops may have no connector evidence.
- Offline `search ... --engine fts` is the default. Explicit `--engine jev`
  enables billable semantic reranking; `jev-status` runs its availability probe.
  Stop a batch on HTTP 402 and never print credentials.
- Prefer background Blender for builds/previews. Live inspection is additive;
  use explicit roots when copies exist. `remove(root)` restores source pose;
  `set_moving_only`/`set_hidden` are reversible. `update_plan_notes` changes
  embedded prose; save JSON/blend explicitly. Mechanical edits require rebuilds.
- Run relevant pure tests (`.venv/bin/pytest -q`). Adapter changes also require
  background builds, fresh-process reopening and lifecycle checks. Neither
  equation/transform agreement nor plausible renders prove collision-free or
  physically feasible motion. Report actual evidence and limits.
- Exit codes: 0 success, 1 failed checks, 2 input/execution errors. Large reports
  use `--output`; successful discovery is informational, not proof of mobility.

## Curating selected results

Only when requested, document user-selected results using
[the curation guide](docs/reference/curation.md). Reconstruct each subsystem from
source, plan, builder, checks and saved Blender output. Write fresh explanatory
diagrams, identities, equations, evidence and limitations; update the catalog.
Normal rigging does not require diagrams. Optional `diagrams` exports describe
recorded plan fields and cannot replace reference reasoning.

Before publishing links, **copy, never move**, selected source, evidence, scripts
and playback assets into `examples/reference/`. Follow [the archive guide](examples/README.md)
and run `scripts/reference_assets.py check`. References must work after `output/`
is deleted. User selection establishes usefulness, not mechanical proof.
