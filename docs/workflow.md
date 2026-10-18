# From model to working mechanism

Use the [reference catalog](reference/README.md) to find a useful precedent,
measure the target assembly, then author and test its motion. Visual review
selects successful outputs for later [reference curation](reference/curation.md).
Creating diagrams is not a prerequisite for rigging.

For part selection or inventory, consult [part information](part-information.md).
The category tables offer browsable families and individual components; the
database remains the broader description/model search. Neither categories nor
dimension hints determine mechanical connections. The
[minifig case](reference/minifigs/README.md) demonstrates using category constants
for selection and connector geometry for placement and articulation.

## Annotate before analysis

For an unannotated original, the semantic annotation pipeline is **part comments
→ agent-authored model/submodel descriptions → hierarchy review and enrichment
→ verification → prepare**. Rich descriptions and adequate semantic grouping
are required in the new annotated copy. Source reading and inventory calls
needed to author descriptions and infer groups are part of this pipeline.

By default, perform semantic enrichment only when annotating an originally
unannotated model (including intermediate copies produced in this task).
Reuse supplied already annotated models without rewriting their descriptions
or hierarchy; only revise/enrich those when explicitly requested. Preserve useful rich text
already present in any section. A filename or folder name cannot establish
annotation coverage or accuracy.

**First, annotate parts.** Part descriptions appear in type-0 comments starting
with `0 // ` immediately above type-1 part references:

```plaintext
0 // Plate  2 x  2 (black)
1 0 80 8 0 1 0 0 0 1 0 0 0 1 3022.dat
```

```sh
./ldraw-mecha annotate /path/to/original.mpd --output output/parts-annotated/model.mpd
# For external subfiles, annotate the complete source tree, keeping relative paths:
./ldraw-mecha annotate /path/to/models --output output/parts-annotated-models
```

Directory mode recursively processes `.ldr`, `.mpd` and `.dat` files, ignoring
extension case. Use separate, non-overlapping input/output trees. For single-file
input, `--output` may be a filename or an existing directory. Keep generated
copies under `output/`, outside the new study directory that `prepare` creates.
Single-file mode does not copy external dependencies; directory mode retains
the paths of LDraw subfiles but does not copy other assets such as textures.

`annotate` uses `data/ldraw-info.db` (`PARTS_DESCRIPTIONS(part, description)`) and
`LDConfig.ldr` from global `--library`, `LDRAW_DIR` or `LDRAWDIR`. Override them
with `--database FILE.db` and `--ldconfig FILE.ldr`; explicit `--ldconfig` needs
no configured library. No sibling checkout or Blender is required. Names match
case-insensitively; colour names are lowercase, retaining underscores, as in the
original `add_parts_descriptions.py`. Unknown colours retain their source code.

The command prints a JSON report with counts and per-file `unknown_references`
and `unknown_colours`. References absent from the part catalog, commonly MPD
assembly names or custom parts, remain unchanged. Review these before relying
on coverage; do not invent descriptions for missing entries. Matching existing
annotations are retained without duplication; other comments are preserved.
Original lines, transforms, FILE/STEP markers, attribution, UTF-8 BOM and line
endings are preserved. The command refuses to overwrite its source inputs and
reports the agent-authored semantic step as the next action. It does not infer
model/submodel semantics from the part catalog.

**Then, the agent writes model and submodel semantics.** Immediately after part
annotation, read all existing FILE sections and their part comments, children,
placements and parent context. `submodels MODEL --format table --limit 1000`
helps inventory assemblies; read the source for embedded DAT sections and check
for truncation. Use bounded `inspect` queries when geometry matters. Describe
children before parents where that helps explain the whole assembly.

Write a concise but informative single physical line describing what each model
or subgroup assembly represents, its role in the parent, distinctive components,
colours/patterns and supported features. Include mechanical function only when
the source evidence supports it; qualify uncertainty rather than inventing a
coupling or claiming proven motion. A filename expansion, bare part count or
generic label such as `main`, `car` or `assembly` is insufficient. Keep existing
section names in this description step; assess missing groups in the final
hierarchy review below.

The existing [106 example](../data/models-annotated/106-1.mpd) demonstrates the
expected difference from its original headers:

| Original description | Rich description in the annotated example |
| --- | --- |
| `main` | UNICEF promotional set: small blue car with UNICEF logo side panels, opening roof, headlights, doors, and a smiling driver minifig |
| `car` | Blue car body with UNICEF logo panels, windscreen, hinged roof, doors, headlight bricks, steering wheel, radio, shovel, and four wheels |
| `wheel assembly` | Wheel assembly: light grey rim with black offset-tread tyre |
| `Minifig` | Driver minifig: brown hair, smiling yellow head, blue torso with patch pocket, blue arms, hips and legs, yellow hands |

Keep the description directly below its existing `0 FILE` line, as one ordinary
type-0 line, distinct from the `0 // ` comments on parts:

```plaintext
0 FILE 106 - wheel assembly.ldr
0 Wheel assembly: light grey rim with black offset-tread tyre
```

Author a JSON object mapping exact FILE names to the description text (without
the `0 ` prefix). For example, one entry is:

```json
{"106 - wheel assembly.ldr": "Wheel assembly: light grey rim with black offset-tread tyre"}
```

Include all sections needing enrichment, including the root model. Sections
already carrying useful rich descriptions may be omitted and remain untouched.
For a plain LDR/DAT without FILE markers, the key is its input basename and the
description goes at the start. Apply the agent's text with:

```sh
./ldraw-mecha annotate-semantics output/parts-annotated/model.mpd \
  --descriptions output/descriptions.json --output output/annotated/model.mpd
```

The helper applies only explicitly supplied text, validates names and single-line
syntax, and preserves unlisted headers, part comments, attribution, section
identities and geometry. A missing description is inserted before metadata or
part comments. It writes a separate copy and needs neither a library nor Blender.
It does not judge richness or completeness and does not create submodels. Its
report points to the required hierarchy review as the next action.
For a directory of models/external subfiles, perform this step per file; carry
all other part-annotated files into the final tree at the same relative paths.

### Review and enrich the hierarchy

**Finally, the agent assesses and, where necessary, extends the hierarchy.**
This review is required for every originally unannotated model in this pipeline,
including a flat file with no submodels and an MPD whose existing sections are
too coarse. Rich prose about an unstructured collection of parts is not a
substitute for representing its meaningful assemblies as submodels.

Review the root and every existing assembly, then repeat for newly inferred
assemblies until the meaningful semantic units are represented at useful levels.
Use annotated parts, placement, parent/child context, repeated arrangements and
measured interfaces to justify boundaries. Examples include a vehicle's wheel
assemblies or cab, or an engine's cylinder banks within an existing powertrain
submodel. These are candidates to substantiate in the target source, not a
required taxonomy. Neither spatial proximity, matching colours, build steps nor
the presence of gears is sufficient evidence by itself.

Preserve useful existing boundaries and add missing ones. Create actual `.ldr`
FILE sections and type-1 references, not just a sidecar list or prose mentioning
groups. For a flat LDR, introduce a root FILE section in the generated MPD and
add the inferred child sections. A new section may contain existing submodel
references as well as individual parts; nested submodels should represent
meaningful constituent assemblies. Give every new section a rich single-line
`0 DESCRIPTION` below `0 FILE NAME`, retain descriptive comments with their
parts, and revise parent descriptions if the added structure warrants it.
Preserve existing names and use distinct, descriptive names for additions.

Stop subdividing when further groups add no useful meaning. Do not manufacture
groups to reach a count, wrap every part, or split a physical library/embedded
DAT into fictitious independent pieces. A semantic assembly can include moving
parts; it is not automatically a rigid body or a proven mechanism. Overlapping
functional roles belong in descriptions or review notes: each physical occurrence
must still appear exactly once in the resulting assembly tree. If a boundary is
ambiguous, retain the parts at the appropriate parent and record the uncertainty
instead of claiming complete understanding.

Implement additions in the generated copy using pyldraw3 for parsing. Retain a
snapshot of the pre-grouping copy and its occurrence manifest. For a group of
direct children in one parent, a new submodel in that parent's coordinate frame,
referenced by an identity type-1 transform with colour 16, can retain the child
placement matrices and colour codes. If changing frames or grouping across
parents, explicitly recompute local transforms and colour inheritance from the
composed source placements. Never copy occurrences into a group while also
leaving their original placements in the parent.

Review every use of a shared submodel definition: an edit affects all its
instances. If a grouping applies to only one occurrence, create a derived
definition and redirect only that occurrence; preserve the other uses. Keep
external subfiles resolvable in the generated tree, and preserve attribution,
licences, embedded geometry, part comments and scoped STEP/BFC/TEXMAP/group
metadata. Moving lines across such directives requires preserving their meaning;
transform equality alone does not verify build instructions or textures.

Save `hierarchy-review.md` (or JSON) under the task's `output/` directory. Record
the sections reviewed, retained boundaries, new parent/child relationships,
source occurrence membership, the evidence/rationale for each inferred group,
and unresolved ambiguities. If the existing hierarchy is sufficient, record a
reasoned no-change conclusion; no new groups are required in that case. This
review is an agent judgment, not an automatic completeness claim.

After regrouping, save an explicit old-to-new **physical occurrence** ID map and
reparse the finished file. Check a bijection over all original and final physical
leaves, including repeated identical parts: same reference, effective colour and
world matrix for every mapped occurrence, with any numeric tolerance and maximum
error reported. Check reference resolution and absence of cycles. Compare using
the map, not flattened-list order, which regrouping may change. Check shared
submodel instances under nonzero translations/rotations and asymmetric placements
when present. Preserve the source unchanged and inspect any metadata affected by
the moves. These checks establish source equivalence, not mechanical feasibility.

Only after semantic coverage and preservation are reviewed, use the finished
copy for study, extraction, plans and conversion:

```sh
./ldraw-mecha prepare output/annotated/model.mpd --output output/model-study
```

Header/comment edits change source hashes and sometimes line numbers. Hierarchy
edits also change occurrence paths/IDs and may change traversal order, even when
the physical model is identical. Finish grouping before creating a plan or bound
GLB; otherwise regenerate/rebind them from the final source. Descriptions and
assembly parenting provide context; they do not establish joints.

## Choose the deliverable

When asked to animate a particular mechanism, the default deliverable is **that
subsystem on its own**: the mechanism and the coupled elements the user wants
to inspect, such as mounts or adjacent drive components. Everything else is
absent from the extracted MPD, GLB and blend. This lets the user judge the
mechanism in Blender without the surrounding vehicle.

Clarify the boundary early: which coupled elements should remain, and which of
them should move? Reuse any scope already established in the conversation.
Explicit requests for a whole vehicle, an in-place mechanism or hidden bodywork
take precedence. A whole-vehicle rig can be a separate deliverable; hiding its
bodywork alone does not produce the requested standalone subsystem.

Use `--section` for investigation, then `scripts/extract_subsystem.py` to write
the chosen physical occurrences with their composed matrices, attribution and
identity map. Include `--section` there when the keep IDs belong to that FILE.
Remap the plan to the extracted source and convert that file. Keep any extra
bodywork needed for clearance checks in a separate study rather than the final
presentation. Examples: [standalone suspension](reference/42110-suspension-standalone/extraction-and-mounts.md)
and [independent Chiron mechanisms](reference/42083-mechanisms/independent-rigs.md).

## Prepare once

```sh
./ldraw-mecha prepare data/models-annotated/106-1.mpd --output output/study
```

| Artifact | Purpose |
| --- | --- |
| `plan.json` | Stable occurrence identities, candidate connections and provisional mechanism views; initially a draft with no motion |
| `preparation.json` | Discovery coverage, warnings, scope audit and conversion result |
| `model.glb` | Source geometry with verified occurrence-ID binding |

Evidence is saved before conversion. On conversion failure, correct the cause
and run `convert MODEL --plan PLAN --output FILE.glb`; the saved study survives.
Preparation refuses a nonempty directory so a rerun cannot erase corrections.
Use `--section 'exact FILE name'` for an assembly, `--no-glb` for source-only
analysis, and global `--library` or `LDRAW_DIR` for library configuration.
An absent library is reported; an explicitly invalid library path is an error.

Source IDs identify occurrences, not part types: repeated placements have
different IDs. They survive conversion into Blender custom properties.
Descriptions and assembly parenting do not establish joints. Selecting a
different section changes the reference frame and identities; reprepare/rebind
when changing source or selection.

## Establish coverage and scope

Read discovery warnings before choosing rigid groups. Automatic discovery uses
pyldraw3 contacts and bounded gear/coaxial candidates. Contacts inspect up to
300 physical library parts by default; use `--contact-limit 2..2000` or bounded
studies for larger models. Embedded DATs keep their geometry and are excluded
from library connector substitution. Coaxial supplementation considers at most
100 catalog axle/gear/crankshaft candidates and retains lines within 80 LDU axial
separation. These are search bounds, not proof of engagement.

When searches are skipped, run focused `contacts`, `connectors`, `gear-meshes`
and `coaxial` queries. Keep those reports beside the plan and record the findings
used for motion. Zero axle coverage in a drivetrain is a warning sign. Near-rigid
rounded frames are corrected only for analysis; inspect unsupported scale/shear
and use `--raw-transforms` for comparison. See [discovery quality](discovery-quality.md).

Provisional views are an inventory of candidates, not complete mechanisms or
rigid-body groups. Regroup them after visual inspection; shared supports may
belong to several views. Record each newly found mechanism, its input/output,
evidence and unresolved interfaces. Account for findings as planned, deferred or
static, with review notes. The scope audit cannot discover omissions or establish
mechanics by itself.

## Inspect in Blender before finalizing motion

With this repository on Blender's `sys.path`:

```python
from ldraw_mechanisms import blender_tools as tools, plan as contract

p = contract.load('/absolute/path/output/study/plan.json')
context = tools.inspect_prepared(p, glb='/absolute/path/output/study/model.glb')
# Choose a mechanism key from p['mechanisms'] after reviewing the inventory.
tools.select_mechanism(context, 'MECHANISM_ID')
```

Inspection adds a model, binds draft identities and stores the study/digest on
its root. Each part gets `mecha_mechanisms` for selection. It creates no rig,
clears no scene, saves no file and generates no diagram text blocks.
Pass `root=existing_root` instead of `glb` to refresh annotations on that model.
Refreshing also removes that root's old auto-generated diagram cache; unrelated
text blocks and other models are preserved. Existing output directories and
saved files are not migrated automatically.

Use an explicit root when several copies exist. Prefer background Blender for
builds and previews if the user's open scene is only a reference. The callable
APIs and reversible visibility are documented in [the API guide](discovery-and-blender.md).

## Author and test motion

Edit the existing [motion fields](motion-plan.md), or use the joint helper for a
measured hinge/slider. For the 106 roof, after selecting its mechanism view:

```python
from ldraw_mechanisms import mechanisms

p = mechanisms.add_joint(
    p, mechanism='MECHANISM_ID', name='roof', instances=['0/40'],
    origin=[0, -92, 36], axis=[-1, 0, 0],
    minimum=0, maximum=1.3089969389957472,
    description='Open the roof',
)
contract.save('/absolute/path/output/study/plan.json', p)
```

This writes ordinary controls, signals and bodies, preserves evidence and leaves
the plan a draft. The moving part, opening sign and 75-degree limit are deliberate
decisions from the studied roof. A coincident connector cannot choose them.
Coupled motion uses signals, anchors and checks; record the mechanical meaning,
conditions, signs and approximations alongside those equations.

For a matching studied recipe, retain preparation evidence while adopting motion:

```sh
./ldraw-mecha prepare data/models-annotated/42083-1.mpd \
  --section '42083 - engine.ldr' --output output/engine-study
./ldraw-mecha plan data/models-annotated/42083-1.mpd \
  --section '42083 - engine.ldr' --recipe 42083 \
  --study output/engine-study/plan.json --output output/engine-study/plan.json
./ldraw-mecha audit output/engine-study/plan.json
./ldraw-mecha validate output/engine-study/plan.json
./ldraw-mecha sweep output/engine-study/plan.json
```

`--study` requires the same source manifest and retains all views, including
manual/deferred findings. It expands old body/control references into parts,
clears those references, and returns previously planned views to unresolved
until reconciled with the new motion. New views follow control dependencies.
`prepare --plan EXISTING_PLAN.json` attaches evidence to a pre-existing plan.
Plans without optional evidence views remain valid.

Use nonzero/asymmetric inputs and all relevant selector states to check ratios,
directions, link closures and propagation. Review the mechanism inventory and
run `audit PLAN --require-reviewed` after giving each finding a disposition.
Set `status` to `ready` when the declared motion is decided; that flag does not
mean every mechanism was discovered or implemented.

## Build, animate and deliver

Reuse the inspected GLB/root; motion edits do not require conversion:

```python
p = contract.load('/absolute/path/output/study/plan.json')
result = tools.apply_plan(p, root=context['root'], animate=True)
rig = result['rig']
report = tools.check_clearance(p, rig=rig, controls=['roof'])
```

The example above expects the authored ready roof plan. For a separate process:

```sh
./ldraw-mecha rig output/study/plan.json --glb output/study/model.glb \
  --save output/study/rigged.blend --report output/study/blender-check.json --animate
```

The generic animation demonstrates controls; coupled state transitions may need
a case-specific animation script. Verify the actual saved animation, reopen the
blend and inspect/render its nonzero poses and limits. Run clearance checks
before finalizing claims; save notes updates explicitly. Follow
[validation](validation.md) for background, reopening and lifecycle checks.

Deliver the exact source selection, plan, blend, animation, relevant builder,
reports and previews under `output/`, with scope and limitations. The user can
then visually select a useful case for the reference catalog. Curation is a
separate requested task; normal rigging agents need not write reference diagrams.
When a selected result becomes a reference, copy its relevant source, evidence,
scripts and playback assets into `examples/reference/` before linking them in
docs. Keep the originals under `output/`. The [archive guide](../examples/README.md)
explains selection, portable review commands and dependency checks.

## Optional diagnostic exports

```sh
./ldraw-mecha diagrams output/study/plan.json --mechanism MECHANISM_ID \
  --output output/study/diagnostics
```

This renders recorded connections, joint/rod definitions and control
dependencies. It does not recover signal-only mechanical couplings, clutch
conditions or complete power paths. A sparse or plausible-looking diagram is
not a completeness or correctness check. `--view connections` exposes part-level
evidence; default `auto` uses motion views when bodies exist.

Dashed edges denote candidates; reviewed edges require a review note, not proof.
Exports include the plan digest and replace only files owned by their previous
index. They are disposable diagnostics. Curated Markdown references are authored
from selected results using [the curation guide](reference/curation.md), including
diagram types suited to each subsystem.
