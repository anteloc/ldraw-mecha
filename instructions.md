# Agent entry point

Build controllable mechanisms, check their propagation, and report exactly what
was implemented and tested. The workflow is **reference → study → rig and animate
→ verify → visual review**. Selected successful results can then become new
references. See [the workflow](docs/workflow.md) for commands and Python examples.

## Prerequisite: annotate the source

Before analyzing a model's structure/mechanics, inspecting its assemblies or
running `prepare`, check its source across MPD sections for descriptive type-0
comments starting with `0 // ` immediately above the corresponding type-1 part
lines, for example `0 // Plate  2 x  2 (black)`. A descriptive header, a folder
named `models-annotated` or a few unrelated comments do not establish coverage.

If those annotations are missing or partial, create a separate annotated copy:

```sh
./ldraw-mecha annotate ORIGINAL.mpd --output output/annotated/MODEL.mpd
./ldraw-mecha prepare output/annotated/MODEL.mpd --output output/STUDY
```

Use the annotated path consistently for study, extraction, plans and conversion;
retain the original source and attribution. Existing adequately annotated files
can be used directly. Review reported unknown references against the source or
library before relying on the annotated inventory. Use directory mode for models
with external subfiles to retain relative paths. Annotation uses the bundled
description database and the configured library's `LDConfig.ldr`; see
[annotation options and limits](docs/workflow.md#annotate-before-analysis).
Do this before creating a plan: adding comments changes source hashes and line
numbers, so existing plans must be regenerated/rebound after changing source.

## Rigging and animation

1. Read the [curated reference catalog](docs/reference/README.md) for matching
   mechanisms. Reuse its reasoning, equations and checks, but remeasure the target
   model. Reference part IDs, axis signs and motion ranges belong to that example.
   Normal rigging tasks do not require creating diagrams.
2. For a request to animate one mechanism, default to a **standalone subsystem**:
   the mechanism plus the agreed coupled elements, such as its mounting frame.
   Everything else must be absent from the delivered MPD, GLB and blend. Clarify
   early which coupled elements to retain and whether they should move, using
   any selection already agreed with the user. Follow explicit whole-model or
   in-place requests. Study with `--section`, then use
   `scripts/extract_subsystem.py` for selected occurrences and remap the plan's
   IDs. See [subsystem scope](docs/workflow.md#choose-the-deliverable).
   Inventory mechanisms using source evidence and visual inspection. Use
   `submodels MODEL --match engine --format table` to compare assemblies and
   `inspect MODEL --format table --mechanical-only` for positions and transformed
   part-local axes. Keep the surrounding supports and interfaces in view.
3. Run `./ldraw-mecha prepare MODEL --output output/STUDY`, adding `--section`
   as needed. It saves source identities, candidate evidence, a draft plan and
   a bound GLB. `--no-glb` keeps preparation source-only. Read `preparation.json`:
   contact kinds, axle coverage, placement corrections, unsupported geometry and
   skipped searches. The default contact budget is 300 parts; raise it up to 2000
   or inspect bounded groups/sections for larger models. Zero axle coverage in a
   drivetrain requires investigation. See [discovery quality](docs/discovery-quality.md).
4. Inspect the GLB early with `blender_tools.inspect_prepared`; use
   `select_mechanism` to select a named view's parts. Keep stable occurrence IDs
   from the plan; Blender display names and scene parenting do not define joints.
   Provisional views may need merging or splitting and are not rigid bodies.
   Record visually discovered mechanisms immediately with their input, output
   and unresolved link. Retain findings until planned, explicitly deferred or
   reviewed as static. Preserve evidence when adopting an existing recipe with
   `plan MODEL --recipe NAME --study PLAN --output PLAN`.
5. Author motion in that plan using the [motion contract](docs/motion-plan.md):
   rigid groups, axes, origins, limits, dependency equations, anchors and checks.
   `mechanisms.add_joint` helps with a measured hinge or slider. Record coupling
   meaning, sign conventions, conditions and approximations in the plan's notes
   and evidence; keep reusable equations/checks in the plan where supported.
   A script or render alone must not be the only record of a mechanical decision.
   Keep `source` untouched and include every moving piece, such as rim and tyre.
6. Run `validate`, `sweep`, and `evaluate --set NAME=VALUE` with meaningful nonzero
   and asymmetric inputs. Check propagation, ratios, link lengths and relevant
   selector states. Set `status` to `ready` only once the declared motion is
   decided. Run `audit PLAN` before rigging and delivery; reconcile views and use
   `audit PLAN --require-reviewed` to check dispositions. An explicit deferral can
   pass that scope check; it still belongs in the delivery's omitted-work list.
7. Apply the plan to the inspected root, or use the background `rig` CLI to build
   and save without replacing an open scene. Reuse the bound GLB unless the
   source/selection changes. Add demonstration animation and expose the moving
   mechanisms as requested. Callable `apply_plan` and `check_clearance` avoid
   fake command-line arguments in live sessions.
8. Reopen the saved file, verify persistence, and inspect/render several poses,
   including limits. Run appropriate clearance checks before writing final
   limitations. Deliver the exact plan, blend, animation, reports and previews
   used for review, with unresolved/deferred mechanisms and untested assumptions.
   Equation/transform checks and visual plausibility do not prove physical
   feasibility or collision-free motion. See [validation](docs/validation.md).

## Curating selected results

The user visually reviews animations and selects promising outputs. When asked
to document one, reconstruct each subsystem from the source, plan, builder,
checks and saved Blender result. Write one Markdown reference per subsystem with
fresh diagrams, exact identities, equations, evidence and limitations; follow
[the curation guide](docs/reference/curation.md). Update the catalog so subsequent
agents can find the example. Selection establishes usefulness, not mechanical
proof; qualify or exclude unsupported relationships.

Before publishing reference docs, **copy, do not move**, their relevant sources,
plans, evidence, scripts and playback assets into `examples/reference/`. Link to
those committed copies, not `output/`; the working directory may be deleted.
Use the [archive guide](examples/README.md) for selection, path relocation and
`scripts/reference_assets.py check`. This applies to every future reference too.

Automatic `diagrams PLAN` exports remain optional diagnostics of recorded plan
fields. They do not reconstruct signal maths or unrecorded couplings and are not
reference documents. Neither preparation nor Blender inspection generates them.
Old generated diagrams should not be used as authority for curation.

## Evidence and operating rules

- Use offline `search submodels 'steering rack' --engine fts --limit 5` for
  precedents. Explicit `--engine jev` enables semantic reranking; its small
  billable availability check stops a batch on HTTP 402. `jev-status` runs that
  check alone. Never print credentials. Search relevance does not prove fit.
- Use [part information](docs/part-information.md) to choose a lookup source.
  `data/categories/parts` provides offline family tables and named components;
  `get_dimensions` provides rough local extents. They help selection and
  inventory, but do not establish joints or replace the model/submodel database.
  Check aliases, actual library availability and connector geometry. For figures,
  start with the [minifig reference](docs/reference/minifigs/README.md).
- Use `connectors MODEL --instance ID`, bounded `contacts MODEL --instances ...`,
  `gear-meshes MODEL` and `coaxial MODEL --instances ...` for measured candidates.
  Connector `position`/`frame` are part-local; `world_position`/`world_axis` are
  in the selected model. LDCad uses local Y; body joint axes are explicit.
  Rounded near-rigid frames are orthonormalized for analysis only; source
  matrices remain intact. `--raw-transforms` permits comparison. Review scale,
  shear, metadata gaps and unsupported gears. Coaxial lines alone do not prove
  contact or coupling; worm direction needs measurement. Cams, surface-bearing
  levers, friction and stops can exist without connector edges.
- Motion angles are radians; geometry and slide lengths are LDU. Discovery's
  explicitly named `angle_degrees` / `--angle-tolerance` uses degrees. Motion
  values are source-pose offsets. Body parenting composes motion, so wheel spin
  follows its steering knuckle or suspension carrier.
- Use pyldraw3 for parsing/connectors and the supplied mpd2glb wrapper for
  conversion. Identity binding must succeed; do not substitute an unbound GLB
  or infer identity from `.001` names. Preserve source attribution and original
  Blender reference scripts. Keep generated artifacts under `output/`.
  Selected reference snapshots are copied to `examples/reference/` for retention.
- Prefer background Blender for builds and previews. Live inspection is additive;
  pass an explicit root when copies exist. `remove(root)` restores the source
  pose. `set_moving_only` and `set_hidden` provide reversible visibility.
  `update_plan_notes` updates embedded prose without rebuilding; save the updated
  JSON/blend explicitly. Mechanical changes still require rebuild and checks.
- Use `--output` for large reports. Exit codes are 0 for successful operation,
  1 for failed checks, 2 for input/execution errors. Successful analysis is
  informational; missing contacts never establish freedom to move.

See the [analysis and Blender API guide](docs/discovery-and-blender.md) for focused
commands and live APIs, and [architecture](docs/architecture.md) for the code map.
Analysis stays independent of Blender. Run `.venv/bin/pytest -q` for pure tests;
adapter changes also require background Blender, reopening and lifecycle checks.
