# Analysis and Blender APIs

Start with inventory and measured candidates. Keep the full manifest for plans;
use compact reports for exploration. Source analysis runs without Blender.
Follow the [workflow](workflow.md) for the complete process and the
[reference catalog](reference/README.md) for worked mechanisms. These commands
support focused investigation; creating diagrams is optional.

```sh
# Offline FTS5/BM25 is the default, using the existing read-only SQLite indexes.
./ldraw-mecha search submodels 'engine piston' --engine fts --limit 8
# Opt in to advanced syntax; normal queries treat words literally and join with OR.
./ldraw-mecha search submodels 'engine NOT aircraft' --raw-fts
./ldraw-mecha submodels data/models-annotated/42083-1.mpd \
  --match engine --sort pistons --format table

./ldraw-mecha inspect data/models-annotated/42083-1.mpd \
  --section '42083 - engine.ldr' --ref 24505.dat --format table
./ldraw-mecha gear-meshes data/models-annotated/42083-1.mpd \
  --section '42083 - engine.ldr'
./ldraw-mecha coaxial data/models-annotated/42083-1.mpd \
  --section '42083 - engine.ldr' --instances 38 67 68
```

`submodels` reports recursive physical counts **per occurrence of each FILE**,
including repeated child assemblies. It shows direct parent sections and their
type-1 placement indices. Embedded DAT geometry counts as one piece. `pistons`,
`rods`, `crank_parts`, `gears`, and `axles` are catalog-description matches;
roles can overlap. Crank parts are not independent shafts. `--sort` accepts
those fields or `parts`; `--match` filters names/descriptions. This reports 16
pistons in the W16 despite the source description saying V8. Counts are better
complexity criteria than names: choose cylinder count and gear coupling first,
then report physical part count. The default sort is piston count, then parts.

`inspect --compact` returns a small JSON report. `--format table` returns TSV;
`--output` writes the selected format. Filter with repeatable `--ref`,
`--instances ID ...`, or `--mechanical-only`. Page with `--limit` and `--offset`;
the report states its total and whether more rows follow. Positions are LDU in
the selected section. X/Y/Z are normalized **part-local axes transformed into
that section**, not inferred joint axes. For actual connector frames, use
`connectors`; its `features` is a list and each item has `world_position` and
`world_axis`. Full `inspect` JSON remains the default without filters.

`gear-meshes` finds parallel, coplanar, external gear candidates from reviewed
profiles in `geometry.GEARS`. The initial profiles cover 8T `3647`/`10928`,
12T `32270`, 16T `4019`/`94925`, 20T `32269`/`18575`,
24T `24505`/`3648`/`3648b`, 36T `32498`, and 40T `3649`. Profiles use a nominal pitch
radius of 1.25 LDU per tooth, with local Z through the tooth midplane. This
recovers the W16's 40 LDU 12:20 pair and two 60 LDU 24:24 pairs. Unknown,
embedded, scaled and sheared gears are reported as unsupported. Extend profiles
only after checking LDraw geometry and nominal pitch; tooth-count words alone
are insufficient. Existing F1 rack equations retain their original calibration.
The separate `4716` worm profile detects finite perpendicular worm/spur
candidates. It reports a ratio magnitude and requires review of direction;
see [discovery quality](discovery-quality.md) for supported wheels and limits.

Both geometric commands accept `--distance-tolerance` in **LDU** (default 0.5)
and `--angle-tolerance` in **degrees** (default 1). Rounded rotations are
normalized. Gear results include measured/expected distance, plane/angle errors,
and, for parallel meshes, `b_per_a`, the signed angular ratio around the reported directed axes.
Tooth phase, engagement, backlash and collision still need review. `coaxial`
compares rotational connector lines, including arbitrary source rotations. It
returns the closest feature pair and negative results with residuals; feature
indices refer to `connectors.features`. Axial separation is reported explicitly:
coaxial infinite lines do not prove contact, fit, retention or torque transfer.
Use `contacts` for the separate pyldraw3 mating evidence.
Read its summary and placement warnings, especially axles without mating evidence.
`--raw-transforms` compares behavior without the bounded analysis-only correction.
Source/GLB matrices remain untouched. Before delivery run `audit PLAN`; every
known omitted mechanism needs an explicit unresolved/deferred view and reason.

FTS works without credentials or new dependencies. Ranking follows
[SQLite FTS5 BM25](https://www.sqlite.org/fts5.html#the_bm25_function);
`score` is its negation so higher is better. Keyword substring matching remains
available with `--engine keyword`. Jev remains explicit with `--engine jev`.
It first sends one small, uncached evaluation with a 15-second timeout and no
retries, stopping before reranking on HTTP 402 or other service failures.
`./ldraw-mecha jev-status` runs just that probe (exit 1 when unavailable).
The [documented TypeSafe API](https://docs.typesafe.ai/api) provides evaluations;
no documented balance endpoint was found. The probe is billable on success,
does not return credit balance, and cannot guarantee enough credit for a batch.
It honors `TYPESAFE_API_KEY` and `TYPESAFE_BASE_URL`, like `jev-rerank`.

## Selecting versus extracting

`--section` studies an assembly in its own coordinate frame while keeping the
original source as the plan dependency. For a request to animate one mechanism,
the default deliverable is a standalone subsystem with agreed coupled elements;
see [scope selection](workflow.md#choose-the-deliverable). To extract a complete
existing FILE section:

```sh
./ldraw-mecha extract data/models-annotated/42083-1.mpd \
  --section '42083 - engine.ldr' --output output/study/engine.mpd
```

Extraction includes referenced FILE sections and adjacent LDR dependencies,
preserves attribution, and does not copy the official parts library. It refuses
to overwrite a source dependency. Re-inspect the extracted file before making a
new plan: its hash and identities belong to that file. A source-only study can
use `--section` directly. For a custom selection spanning sections, use
`scripts/extract_subsystem.py --section 'exact FILE name' --keep KEEP.json ...`;
it preserves the selected frame and writes an old-to-new occurrence map. The
final MPD, GLB and blend contain only the chosen subsystem and coupled elements.

## Callable Blender workflows

Run in Blender's Python console or via MCP, with this repository on `sys.path`:

```python
from ldraw_mechanisms import plan as contract, blender as rigging
from ldraw_mechanisms.blender_tools import apply_plan, check_clearance

plan = contract.load('/absolute/path/output/study/plan.json')
# Add to the current scene. No reset, animation creation or save by default.
result = apply_plan(plan, glb='/absolute/path/output/study/model.glb')
rig = result['rig']
# Or reuse an existing rig; pass root explicitly when multiple copies exist:
# rig = rigging.context_from_scene(plan, root=model_root)

report = check_clearance(plan, rig=rig, controls=['drive'], steps=17)
rigging.set_moving_only(rig)        # expose pistons/rods/gears, hide static meshes
rigging.set_moving_only(rig, False) # restore the exact prior visibility

# Prose changes do not need a rebuild, re-import or new animation.
plan = rigging.update_plan_notes(rig, [*plan['notes'], 'Clearance report reviewed.'])
contract.save('/absolute/path/output/study/plan.json', plan)
# Save the .blend explicitly when wanted; updating notes does not save a file.
```

`apply_plan` accepts a plan dict or path, plus optional `root`, `glb`, `save`,
`report`, `animate`, `new_scene`, and `verify_existing`. It returns a rig context
and verification report; failed verification raises before saving. A new import
binds to the newly imported root even if another copy is already present.
`new_scene=True` explicitly clears the current scene and requires `glb`.
Use the background `rig` CLI when the open scene should stay untouched.

`check_clearance` accepts a plan dict or path, optional `rig` or `root`,
`controls` (all by default), `steps` (2..100), `report`, and explicit `rebuild`.
By default it sweeps each control alone. `poses` replaces that sweep with
combined states, `[{"label": ..., "controls": {name: value}}]` (unlisted
controls at their defaults), for example sampled animation frames. `shrink`
(LDU, default 0.4) moves surfaces inward before testing; a larger value, such as
1.5, keeps only crossings deeper than about twice the shrink.
The original CLI scripts delegate to these functions; importing them also exposes
the corresponding function. No manipulation of `sys.argv` is needed.

Verification and clearance temporarily release controller action/NLA/drivers and
restore action slots, mute flags, raw control values and time even on exceptions.
Exit NLA tweak mode before sampling. Clearance establishes excluded rest pairs at
the plan's declared defaults, independent of the current animated pose. It tests
sampled new surface crossings, excluding within-body and rest-contact pairs;
it does not prove containment clearance or collision-free motion between samples.
Run it before writing final claims, then use `update_plan_notes` to record results.

Moving-only mode affects meshes in this model only. Its first call snapshots
viewport/render visibility on the model root; repeated calls are idempotent,
and disabling restores the snapshot even after saving/reopening. It shows parts
assigned to rig bodies; excluded collections or a hidden root still take
precedence. `with rigging.moving_only(rig): ...` restores visibility on exit.
Rebuild/removal also restores visibility. `preview_plan.py --moving-only` renders
this view. `rigging.set_hidden(rig, ids)` is the complementary view for hiding
chosen static occurrences such as bodywork: it refuses rigged parts, shares the
same persisted snapshot (`set_hidden(rig, [], False)` or `set_moving_only(rig,
False)` restores it) and `preview_plan.py --hide FILE` applies a JSON `hidden` list. Notes-only updates accept only a list of strings; changes to bodies,
signals, limits or other mechanical fields still require a rebuild and checks.

Run source regressions with `.venv/bin/pytest -q`. Blender regression coverage:

```sh
"$BLENDER_BIN" --background --factory-startup --python-exit-code 1 \
  --python scripts/blender/check_workflows.py -- \
  --plan output/42083-w16/plan.json --glb output/42083-w16/model.glb \
  --output output/toolkit-improvements/w16
```
