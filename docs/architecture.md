# Toolkit architecture

The [workflow](workflow.md) uses one JSON motion plan from source study through
Blender execution. Curated references explain selected working implementations;
they are documentation, not another execution format.

## Boundaries

| Layer | Modules | Responsibility |
| --- | --- | --- |
| Source | `source.py` | pyldraw3 parsing, attribution, occurrence identities, transforms, section extraction |
| Source annotation | `annotate.py` | Part/colour comments and application of agent-authored model/submodel description lines; reports direct the agent to the final hierarchy review/enrichment and preservation checks |
| Evidence | `analysis.py`, `placements.py`, `discovery.py`, `geometry.py`, `search.py` | Connector expansion, analysis-only frame correction, inventory, bounded contacts/meshes/coaxial candidates, offline FTS and optional Jev |
| Preparation and scope | `prepare.py`, `mechanisms.py`, `audit.py` | Persist evidence, provisional views, recipe adoption, scope dispositions and optional diagnostic exports |
| Motion | `plan.py`, `math3d.py`, `linkages.py` | Contract validation, safe expressions, evaluation, linkage maths and sweeps |
| Studied examples | `recipes.py`, `recipe_42000_data.py`, `recipe_10265_data.py` | Measured motion for specific source selections |
| Geometry transfer | `glb.py`, `scripts/mpd2glb.sh` | Existing exporter plus strict source-ID binding in GLB extras |
| Blender | `blender.py`, `blender_tools.py`, `scripts/blender/` | Additive inspection, rigs, drivers, constraints, animation sampling, visibility, save/reopen and lifecycle verification |
| Entry points | `cli.py`, `ldraw-mecha` | Agent-friendly commands and artifact pointers |
| Reference library | `docs/reference/` | Reviewed subsystem explanations, diagrams, identities, equations and evidence limits |
| Retained examples | `examples/reference/`, `scripts/reference_assets.py` | Selected source/evidence/playback copies, hash manifest, dependency checks and source-path relocation for reuse |
| Part lookup data | `data/categories`, `data/ldraw-info.db`, description TSV | Family/name/size hints and catalog search; see [source selection](part-information.md), separate from connector geometry |

Source analysis imports no Blender API. The motion/equation layer uses the
standard library and imports neither bpy nor pyldraw3, so Blender can evaluate
the same plan. Source transforms and hashes remain intact; normalized placements
are analysis evidence only.

For originally unannotated models, the agent completes annotation with a
[hierarchy review](workflow.md#review-and-enrich-the-hierarchy), creating richly
described submodels and nested submodels when needed. The annotation commands
do not infer or create these groups. The agent edits a generated copy using
pyldraw3, records the grouping evidence and occurrence map, and verifies physical
equivalence before preparation. Regrouping changes source identities even when
the geometry is preserved; existing plans and bindings must be regenerated.

The exporter preserves hierarchy, part descriptions and metadata. Its geometry
basis and scale differ from Blender's; binding verifies identity through
hierarchy/transforms rather than guessing from display names. Missing or
ambiguous matches fail. A scene parent is not evidence of a mechanical joint.

Rigs use ordinary Blender drivers and constraints. Controls continue to work
after save/reopen without an add-on, persistent Python handler or external
service. Build/remove operate on an explicit imported root, preserve rest
transforms and isolate duplicate copies.

## Examples and references

Studied CLI recipes are executable for their exact source selections. Builders
such as `scripts/build_defender_rig.py`, `build_mustang_rig.py`,
`build_defender_suspension.py` and `build_suspension_standalone.py` hold larger
case-specific implementations; their tests check the associated equations.
`build_42083_mechanisms.py` and the Blender-safe `timeline_42083.py` provide the
five independent Chiron studies, including the qualified reconstruction described
in [their references](reference/42083-mechanisms/README.md).
They are useful provenance, not generic mechanism inference.

`build_minifigs.py` selects separate parts from category tables and authors
connector-based joint plans. `minifig_clips.py` is a pure Python library of shared
channels, sparse keys and staging transforms; `blender/animate_minifigs.py`
turns those clips into Actions and NLA tracks. The
[minifig references](reference/minifigs/README.md) document reuse and clearance
limits. Whole-figure staging remains outside the mechanical plan contract.

`build_movables.py` and `movable_clips.py` cover hinges, sliders, dependent
motion and reusable eased clips. `build_plants.py` authors plant joint plans;
`plant_catalog.py` and `wind_clips.py` describe the wind response and bake it into
clips. Wind computation is independent of Blender; the display controller does
not drive the plants live. The [plant and general wind references](reference/plants/README.md)
distinguish physical joints, approximated bending and authored response models.

Archived plans retain their original source metadata. `reference_assets.py plan`
writes a new working plan with checked source paths resolved to this checkout;
it preserves identities and motion. Review scripts read the archive and write
new reports under `output/`. See the [archive guide](../examples/README.md).

The [reference catalog](reference/README.md) provides reusable explanations
derived from selected outputs. Its diagrams are hand-curated; the optional
`diagrams` command is a limited plan diagnostic and cannot produce equivalent
documentation automatically. See [curation](reference/curation.md).

`scripts/blender/ldraw_mecha.py` and `rig_42000.py` are the original supplied
reference scripts; preserve them. `compare_reference.py` checks the portable
42000 equations against that implementation. `examples/build_examples.py`
reproduces the small-to-Technic baseline examples. The retained
`animate_10265_showcase.py` targets the studied `10265` recipe; the newer
`animate_mustang.py` targets its separate case-specific builder.

## Configuration and limits

The repository needs no sibling checkout. Analysis uses pinned pyldraw3 and
read-through library caches. Library, cache and Blender paths are configurable;
the library can be read-only. Subprocesses pass argument arrays. Container
deployment remains untested.

Discovery supplies candidates, not automatic mobility classification. The motion
contract supports declared kinematics; it does not solve arbitrary contact
dynamics, forces, friction or backlash. Case-specific constraints and
approximations must be qualified. See [motion-plan.md](motion-plan.md) and
[validation.md](validation.md).
