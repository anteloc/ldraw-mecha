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

An annotated source is a prerequisite for structural/mechanical study. Check
the actual file, including its MPD sections: part descriptions must appear in
type-0 comments starting with `0 // ` immediately above type-1 part references:

```plaintext
0 // Plate  2 x  2 (black)
1 0 80 8 0 1 0 0 0 1 0 0 0 1 3022.dat
```

Reuse a file already annotated this way. Otherwise generate a copy before
`submodels`, `inspect`, `prepare`, extraction or motion planning:

```sh
./ldraw-mecha annotate /path/to/original.mpd --output output/annotated/model.mpd
./ldraw-mecha prepare output/annotated/model.mpd --output output/model-study
# For external subfiles, annotate the complete source tree, keeping relative paths:
./ldraw-mecha annotate /path/to/models --output output/annotated-models
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
endings are preserved. The command refuses to overwrite its source inputs.

Use the annotated copy consistently throughout the study. Annotation changes
source hashes and line numbers even though geometry and occurrence order stay
the same. Annotate before creating a plan, or regenerate/rebind plans after
switching source files. Comments describe parts; they do not establish joints.

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
