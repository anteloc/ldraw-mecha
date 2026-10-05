# Agent entry point

Build a controllable mechanism, check its propagation, and report the coverage
of the evidence. Do not mistake a suggestive description for a working joint.

## Alternative process on this branch

Start with `./ldraw-mecha prepare MODEL --output output/STUDY` (add `--section`
when appropriate). It writes a draft plan and one Mermaid diagram per provisional
mechanism view **before** converting to GLB. `--no-glb` keeps it source-only.
Read `diagrams/README.md` and the explicit discovery gaps in `preparation.json`.
Check `contacts.summary` (counts, kinds and axle coverage), skipped searches and
placement warnings before authoring motion. For large models set
`--contact-limit 2000` or study sections; successful command execution alone is
not a discovery gate. Zero axle coverage in a shaft-driven assembly requires
investigation. See [discovery quality](docs/discovery-quality.md).
Inspect the imported model with `blender_tools.inspect_prepared`, select diagram
members with `select_mechanism`, and correct the JSON. Mechanism boundaries are
hypotheses, not rigid-body groups; shared parts retain their source identities.
Add any mechanism found visually to the JSON immediately, including its input,
output and the unresolved link. Keep it visible until it is planned, explicitly
deferred, or reviewed as static. Run `audit PLAN` before rigging and delivery;
`audit PLAN --require-reviewed` checks that every recorded view has a disposition.
That check covers bookkeeping, not mechanical completeness or physical proof.

Use the existing motion contract or `mechanisms.add_joint` to declare measured
motion. Regenerate diagrams with `diagrams PLAN`. After review, validation and
sweeps, apply the plan to the same imported root; reconversion is needed only if
source/selection changes. `plan ... --recipe ... --study PLAN` adopts a studied
recipe while retaining evidence. Follow the [alternative workflow](docs/alternative-process.md)
for exact CLI/API examples and limitations. Mermaid is generated output; edit
the plan rather than maintaining a separate diagram by hand.

The commands below remain available for focused analysis and verification.

1. Start with `./ldraw-mecha submodels MODEL --match engine --format table`
   to compare recursive part counts and parent sections. Rank complexity by
   pistons/gear coupling, then size; do not trust names alone. Run
   `./ldraw-mecha inspect MODEL --format table --mechanical-only` for positions
   and transformed part-local axes. Save the full manifest with
   `./ldraw-mecha inspect MODEL --output output/study/inspection.json`. Read
   the counts, candidate list, source diagnostics and exact occurrence IDs. Use
   `--section 'exact FILE name'` to study a smaller assembly; the selection has
   its own root coordinate frame and IDs. Keep the surrounding parent in view.
2. Find precedents with `search submodels 'steering rack' --engine fts --limit 5`
   (the offline default), or use explicit `--engine jev` for semantic reranking.
   Jev checks availability with one small billable inference before a batch;
   `jev-status` runs just that check. HTTP 402 stops before reranking; continue
   with FTS. No balance endpoint is assumed. Jev requires its executable
   and a nonempty `TYPESAFE_API_KEY`; never print credentials. Search scores rank
   relevance, not mechanical fit. Source identities are in `model`, `section`
   and `part`, rather than unstable database view row numbers.
3. Inspect connector frames with `connectors MODEL --instance ID`. Ask about a
   bounded group with `contacts MODEL --instances ID1 ID2 ...`. For the 106 roof,
   use `--instances 0/39 0/40`; pyldraw3 confirms the coincident finger hinge.
   Connector `position`/`frame` are part-local; `world_position`/`world_axis`
   are in the selected model. Contacts return transformed connector frames.
   Axis convention is local Y for LDCad metadata; body joint axes are explicit.
   `gear-meshes MODEL` reports parallel-axis and supported worm/spur candidates;
   `coaxial MODEL --instances ID1 ID2` reports rotational connector-line evidence
   even for arbitrary source rotations. Residual tolerances are LDU and explicitly
   named degrees. Coaxial lines alone do not establish contact or coupling.
   Rounded near-rigid placement frames are orthonormalized for analysis only;
   source matrices remain untouched. `--raw-transforms` permits comparison on
   connector/contact/coaxial/gear commands. Review reported substantial scale,
   shear and metadata gaps. Worm ratios are unsigned until direction is measured.
   No connector edge does not rule out a lever bearing on a beam, a cam, a stop
   or friction. Record these as unresolved surface-contact hypotheses.
4. Write a plan with `plan MODEL --output output/study/plan.json`, or use a
   studied `--recipe 106|928|42000|42083|10265`. A draft deliberately cannot rig a scene.
   Specify rigid groups, axes, origins, limits and equations following the
   [contract](docs/motion-plan.md). Keep `source` untouched. Use exact leaf IDs,
   including each rim and tyre, rather than Blender display names. Record
   evidence and missing parent interfaces in `notes`. Track each unresolved
   mechanism as a view with a disposition; a sentence buried in global notes
   does not account for omitted work. Include unresolved/deferred items in delivery.
5. Run `validate` and `sweep`. Check the linkage lengths and transmission ratios
   with meaningful nonzero and asymmetric inputs using `evaluate --set NAME=VALUE`.
   Set `status` to `ready` only after the mechanical decisions are complete.
6. `convert MODEL --plan PLAN --output model.glb` uses the existing exporter and
   binds source IDs to GLB extras. Missing or ambiguous bindings fail. Do not
   substitute an unbound GLB or infer identity from Blender's `.001` names.
7. `rig PLAN --glb model.glb --save rigged.blend --report blender-check.json`
   imports, builds, sweeps controls, checks evaluated transforms and saves only
   after success. It uses a separate background Blender process. Existing open
   scenes need not be replaced. Use `ldraw_mechanisms.blender.build(plan, root)`
   inside Blender for an explicit imported root. `remove(root)` restores it.
   The callable `blender_tools.apply_plan` and `check_clearance` APIs avoid fake
   argv in live sessions. Sampling restores controller animation and pose.
8. Reopen the file and verify persistence; render or inspect several poses,
   particularly limits. Use `scripts/blender/apply_plan.py --verify-existing`
   and `preview_plan.py` with Blender's usual `--` script argument separator.
   Report any clearance checks that remain unperformed. Deliver the exact plan,
   blend, reports and preview used for review.

See [discovery and Blender workflows](docs/discovery-and-blender.md) for copyable
commands, compact filters, `extract`, and live Python APIs. `--section` studies
the original source in place; use `extract` only when a standalone MPD is needed.
Run clearance before finalizing limitations. `blender.update_plan_notes` updates
embedded prose without rebuilding; save the revised JSON/blend explicitly.
`blender.set_moving_only` exposes rigged parts and restores prior visibility on
disable; `preview_plan.py --moving-only` renders that view. `blender.set_hidden`
hides chosen static occurrences (e.g. bodywork) the same reversible way.

Motion angles in JSON/CLI are radians, all geometry and slide lengths are LDU.
Discovery's explicitly named `angle_degrees` / `--angle-tolerance` uses degrees.
Blender's angle UI displays the chosen angle unit, normally degrees. Motion
values are offsets from the source pose. A body's `parent` composes its motion
with the parent's, so front wheel spin naturally follows steering knuckles.

The existing 42000 reference was studied through Blender MCP without changing
its scene. Its motion definitions inform the portable recipe. Its speed/path
integration and collision helper remain available in `scripts/blender`.

Use `--output` for large reports; stdout returns a short artifact pointer.
Commands return 0 on successful operation, 1 on failed checks and 2 on input or
execution errors. A successful inspect/search is informational. Missing connector
coverage or zero contacts never proves that parts are free or disconnected.
The supplied categories are descriptive/dimensional hints; inspect the actual
library and shadow frames before choosing an axis or pivot.

Code map: `source.py` owns parsing/identities; `analysis.py` connector evidence;
`discovery.py` compact reports/inventory; `geometry.py` mesh/coaxial candidates;
`search.py` discovery; `plan.py` validation/evaluation; `recipes.py` studied
examples; `glb.py` conversion/binding; `blender.py` scene construction/state;
`blender_tools.py` callable import/verification/clearance workflows. The
plan/equation layer imports neither bpy nor pyldraw3. Tests run with
`.venv/bin/pytest -q`; Blender integration scripts live in `scripts/blender`.
