# From model to working mechanism

Use **prepare → edit the plan → check → rig → visual review**. Start with a
matching [reference](reference/README.md), then measure the target assembly.
Creating diagrams is not a prerequisite for rigging. For the concepts behind
these steps, read [how it works](how-it-works.md).

```sh
./ldraw-mecha prepare MODEL.mpd --output output/study
# Inspect the study and author measured motion in output/study/plan.json.
./ldraw-mecha check output/study
./ldraw-mecha rig output/study --animate --reopen
```

Plan-taking commands accept either a study directory or a plan JSON filename.
The directory is just a convenient set of ordinary files, with no separate
project configuration. Set `LDRAW_DIR` for conversion and `BLENDER_BIN` for
background Blender (or use global `--library` and `rig --blender`).

For part selection or inventory, consult [part information](part-information.md).
The category tables offer browsable families and individual components; the
database remains the broader description/model search. Neither categories nor
dimension hints determine mechanical connections. The
[minifig case](reference/minifigs/README.md) demonstrates using category constants
for selection and connector geometry for placement and articulation.

## Annotate before analysis

For an unannotated original, follow [the annotation procedure](annotation.md)
first: part comments → agent-authored descriptions → recursive hierarchy review
and enrichment → occurrence-preservation verification. Keep originals intact.
Use the finished copy for all subsequent study, extraction and conversion.
Already annotated sources are reused without semantic rewrites unless requested.

### Review and enrich the hierarchy

The required [hierarchy review](annotation.md#review-and-enrich-the-hierarchy)
includes flat models, nested assemblies, grouping rationale and an old-to-new
physical occurrence map after regrouping. Semantic groups describe the model;
they do not declare rigid bodies or prove mechanics.

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

## Inspect geometry with ldraw-xray

When a candidate's parts or axis are uncertain, look at them before authoring
with the globally installed [ldraw-xray CLI](xray.md). Take the axis from
`connectors` world fields or a `coaxial` line:

```sh
ldraw-xray doctor
./ldraw-mecha xray data/models-annotated/106-1.mpd --section '106 - main.ldr' \
  --instances 0/40 --point 0 -92 36 --direction -1 0 0 --angles 0 40 75 \
  --xray-dir output/study/xray --name roof
```

One board per call (`output/study/xray/roof/mosaic.png`): the selection
coloured and the rest ghosted, the axis rod and close-up poses, with a check
list in the result. Passing a prepared study instead of the model, section and
directory also audits the candidate against the study's contacts (`boundary`).
Answer the check list and record what the image showed in view notes or
connection evidence. Renders are study evidence, not proof of engagement or
clearance.

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
Before rigging, `./ldraw-mecha check output/study` must show no `body_boundary`
warning (a pin or axle shared off the joint between two bodies), and
`./ldraw-mecha xray output/study --body roof` must show only the roof coloured,
the rod through the hinge, positive values opening outward and limit poses clear
of the grey surroundings. Correct the plan and re-run until they agree.
Coupled motion uses signals, anchors and checks; record the mechanical meaning,
conditions, signs and approximations alongside those equations.

For a matching studied recipe, retain preparation evidence while adopting motion:

```sh
./ldraw-mecha prepare data/models-annotated/42083-1.mpd \
  --section '42083 - engine.ldr' --recipe 42083 --output output/engine-study
./ldraw-mecha check output/engine-study --set drive=0.37
```

`prepare --recipe NAME` is equivalent to preparing, then adopting motion with
`plan MODEL --recipe NAME --study PLAN --output PLAN`. The longer command remains
useful for adopting a recipe into an existing study. Both retain all evidence
and findings, including manual/deferred views. Replacing motion expands old
body/control references into parts, clears those references and returns
previously planned views to unresolved until reconciled. New views follow
control dependencies. `prepare --plan EXISTING_PLAN.json` instead attaches
evidence to an existing plan; choose either `--recipe` or `--plan`.

`check` saves `check.json` beside the plan (override with `--output`). It combines
source freshness and contract validation, independent control sweeps (17 steps
by default), default/mixed poses, and the scope audit. Repeated `--set` flags
define one additional combined pose. The report keeps requested and clamped
values, results, scope findings and a plan digest. No motion or dispositions
are changed. `--steps` adjusts the sweep density.

Use nonzero/asymmetric inputs and all relevant selector states to check ratios,
directions, link closures and propagation. Review the mechanism inventory and
run `check PLAN --require-reviewed` after giving each finding a disposition.
This can pass with explicit deferrals; list them in the delivered limitations.
Set `status` to `ready` when the declared motion is decided; that flag does not
mean every mechanism was discovered or implemented.

The focused `validate`, `sweep`, `evaluate` and `audit` commands remain available.
Plans without optional evidence views remain valid, but cannot pass the strict
scope review. A valid draft may pass numerical checks; rigging still requires
`ready`. Exit codes are 0 for success, 1 for failed checks (including closure
failures from `evaluate`), and 2 for input/execution errors.

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
./ldraw-mecha rig output/study --animate --reopen
```

This uses `model.glb` beside the plan, saves `rigged.blend` there, and writes
`blender-check.json` beside the blend. `--reopen` verifies the saved rig in a fresh
Blender process with auto-run disabled, writing `blender-check-reopen.json`.
Explicit `--glb`, `--save`, `--report`, `--blender` and `--tolerance` still work;
with a custom report name, the reopen report adds `-reopen` to its stem.
`rig` runs the existing adapter checks; run `check` separately to collect the
denser Python sweeps and scope audit. Neither command automatically marks
findings reviewed. Omit `--animate` to build controls without demonstration keys.

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
