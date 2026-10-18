# Agent entry point

Build controllable mechanisms, check their propagation, and report exactly what
was implemented and tested. The workflow is **reference → study → rig and animate
→ verify → visual review**. Selected successful results can then become new
references. See [the workflow](docs/workflow.md) for commands and Python examples.

## Prerequisite: semantic annotation of unannotated sources

When starting from an unannotated original, create a separate working copy and
complete **parts → agent-authored model/submodel descriptions → hierarchy review
and enrichment → verification** before `prepare` or motion planning. A directory
name, part comments or rich headers alone do not establish semantic coverage.

1. Run `annotate` to add type-0 `0 // Part description (colour)` comments directly
   above type-1 part lines. Review unknown references against the source/library.
2. Immediately inspect this part-annotated copy and its existing hierarchy.
   Source reading, `submodels` and bounded `inspect` calls are allowed here to
   establish what to describe. The agent must write a rich **single-line**
   description for the whole model and each existing submodel/group assembly.
   Describe its role, distinguishing components and supported visible/mechanical
   features in context. Use the description line `0 DESCRIPTION` directly after
   `0 FILE NAME`; this is distinct from a `0 // ` part comment. For plain LDR/DAT
   files, use the initial description line. Keep existing section names while
   writing descriptions; assess additional grouping in the final step below.
3. Apply the authored descriptions with `annotate-semantics`, then review every
   section for coverage and accuracy. Preserve any already useful rich description.
   Neither the part catalog nor this helper writes or verifies semantic prose.
   Do not infer functioning mechanisms, ratios or proven travel from names alone.
4. Review whether the existing hierarchy expresses the model's meaningful
   assemblies and their constituent subassemblies. This is required even when
   the original has no submodels or has already named some of them. Recursively
   inspect the root, existing submodels and any newly inferred groups. When
   source evidence supports a missing semantic unit, create an actual `.ldr`
   submodel and reference it from its parent, nesting further submodels where
   useful. Give every new section a rich single-line description, retain its
   part comments and update parent descriptions when needed. Preserve useful
   existing boundaries; do not split arbitrarily or equate a semantic group
   with a rigid body. If grouping is already sufficient, explicitly record that
   conclusion; creating new groups is conditional, reviewing coverage is not.
5. Save the grouping rationale, provenance, unresolved ambiguities and validation
   under `output/`, including an old-to-new physical occurrence ID map for any
   regrouping. Reparse the result with pyldraw3 and verify every original physical
   occurrence is present exactly once with the same part reference, effective
   colour and world transform. Keep original files, attribution and metadata;
   check reused definitions, inherited colours and external dependencies. Finish
   this verification before creating plans or bound GLBs. See the
   [hierarchy procedure](docs/workflow.md#review-and-enrich-the-hierarchy).

```sh
./ldraw-mecha annotate ORIGINAL.mpd --output output/parts-annotated/MODEL.mpd
# Inspect the copy and author output/descriptions.json: exact section name -> text.
./ldraw-mecha annotate-semantics output/parts-annotated/MODEL.mpd \
  --descriptions output/descriptions.json --output output/annotated/MODEL.mpd
# Agent: review/enrich the hierarchy, describe new groups, and verify the final copy.
# Keep hierarchy-review.md and any occurrence map/verification report under output/.
./ldraw-mecha prepare output/annotated/MODEL.mpd --output output/STUDY
```

Unless the user explicitly requests otherwise, write these semantic descriptions
and infer/create submodels **only as part of annotating an originally unannotated
model**, including its intermediate copies in this pipeline. Reuse supplied
already annotated models and curated references without opportunistic semantic
rewrites or regrouping. If their descriptions or hierarchy seem insufficient,
report that limitation during study.

Use the finished annotated path consistently for study, extraction, plans and
conversion; retain original sources and attribution. External subfiles need
directory part annotation and per-file semantic edits with relative paths kept
intact. See [the pipeline, examples and options](docs/workflow.md#annotate-before-analysis).
Complete the whole pipeline before creating a plan: header/comment edits change
source hashes and sometimes line numbers; regrouping also changes occurrence
paths/IDs and may change traversal order. Regenerate/rebind after a source change.

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
