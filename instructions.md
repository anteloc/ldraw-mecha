# Agent entry point

Build a controllable mechanism, check its propagation, and report the coverage
of the evidence. Do not mistake a suggestive description for a working joint.

1. Run `./ldraw-mecha inspect MODEL --output output/study/inspection.json`. Read
   the counts, candidate list, source diagnostics and exact occurrence IDs. Use
   `--section 'exact FILE name'` to study a smaller assembly; the selection has
   its own root coordinate frame and IDs. Keep the surrounding parent in view.
2. Find precedents with `search submodels 'steering rack' --engine jev --limit 5`
   or `search parts 'hinge' --engine keyword`. Jev errors are explicit; use the
   named offline keyword mode when it is unavailable. Jev requires its executable
   and a nonempty `TYPESAFE_API_KEY`; never print credentials. Its scores rank
   relevance, not mechanical fit. Source identities are in `model`, `section`
   and `part`, rather than unstable database view row numbers.
3. Inspect connector frames with `connectors MODEL --instance ID`. Ask about a
   bounded group with `contacts MODEL --instances ID1 ID2 ...`. For the 106 roof,
   use `--instances 0/39 0/40`; pyldraw3 confirms the coincident finger hinge.
   Connector `position`/`frame` are part-local; `world_position`/`world_axis`
   are in the selected model. Contacts return transformed connector frames.
   Axis convention is local Y for LDCad metadata; body joint axes are explicit.
4. Write a plan with `plan MODEL --output output/study/plan.json`, or use a
   studied `--recipe 106|928|42000`. A draft deliberately cannot rig a scene.
   Specify rigid groups, axes, origins, limits and equations following the
   [contract](docs/motion-plan.md). Keep `source` untouched. Use exact leaf IDs,
   including each rim and tyre, rather than Blender display names. Record
   evidence, missing parent interfaces and unresolved mechanisms in `notes`.
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
8. Reopen the file and verify persistence; render or inspect several poses,
   particularly limits. Use `scripts/blender/apply_plan.py --verify-existing`
   and `preview_plan.py` with Blender's usual `--` script argument separator.
   Report any clearance checks that remain unperformed. Deliver the exact plan,
   blend, reports and preview used for review.

All angles in JSON/CLI are radians, all geometry and slide lengths are LDU.
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

Code map: `source.py` owns parsing/identities; `analysis.py` evidence;
`search.py` discovery; `plan.py` validation/evaluation; `recipes.py` studied
examples; `glb.py` conversion/binding; `blender.py` scene construction. The
plan/equation layer imports neither bpy nor pyldraw3. Tests run with
`.venv/bin/pytest -q`; Blender integration scripts live in `scripts/blender`.
