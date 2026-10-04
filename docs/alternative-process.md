# Prepare, diagram, inspect, rig

This branch moves mechanical diagrams before GLB conversion and visual inspection
before final motion decisions. The existing plan JSON remains the editable source
of truth. Mermaid files and Blender objects are generated from it.

```text
MPD/LDR → stable occurrence IDs → candidate connections → mechanism diagrams
                                                        ↓
                                              GLB → Blender inspection
                                                        ↓
                                              correct the plan JSON
                                                        ↓
                                            regenerate diagrams → rig/test
```

## Prepare once

```sh
./ldraw-mecha prepare data/models-annotated/106-1.mpd --output output/study
```

This writes, in order:

1. `plan.json`: the source manifest, candidate connections and mechanism views;
   initially a draft with no invented motion.
2. `diagrams/*.mmd`, `diagrams/README.md`, `diagrams/index.json`: one flowchart per
   provisional mechanism view, with the plan digest and shared-part identities.
3. `model.glb`: the existing exporter and verified occurrence-ID binding.

`preparation.json` records discovery coverage and conversion results. Conversion
failure leaves the plan and diagrams available; resolve it and use the existing
`convert MODEL --plan PLAN --output FILE.glb` command. Preparation refuses a
nonempty output directory so a rerun cannot erase agent corrections.

Use `--section 'exact FILE name'` for a selected assembly, `--no-glb` for source-only
analysis, and global `--library` or `LDRAW_DIR` for the parts library. Missing library
configuration is reported explicitly; geometric gear discovery can still run.
A supplied invalid `--library` is an error. No Jev call is required.

## Read the diagrams as hypotheses

Parts have the same source occurrence IDs in JSON, diagrams and Blender metadata.
Node identifiers are deterministic encodings of those IDs; repeated placements
are distinct. Descriptions are labels, never executable Mermaid markup.

Automatic discovery reuses pyldraw3 contacts and the existing gear/coaxial tools.
It groups connected mechanical candidates into provisional views. Ordinary
support parts can appear in several views without merging the whole chassis.
Descriptions help choose candidates; assembly parenting never becomes a joint.

These groups are not automatically complete mechanisms or rigid bodies. Missing
connectors may split one mechanism into several views; incidental contacts may
join candidates that should be separated. Counts depend on available metadata and
discovery rules. An agent should combine/split views after inspecting the model.
Unclassified parts, unsupported gears and skipped searches remain in `discovery`.
The tool does not equate a missing edge with freedom to move.

Contacts inspect up to 300 physical library parts by default. Set
`--contact-limit 2..2000` or select a section for larger sources. Embedded DAT
geometry is preserved but excluded from library connector substitution. Coaxial
supplementation selects catalog axle/gear/crankshaft parts, at most 100, and keeps
positive line evidence within 80 LDU axial separation (worms are included). These are stated discovery
bounds, not physical reach or contact tests. Explicit `contacts` and `coaxial`
commands remain available for focused investigation.
Read the contact summary and warnings before planning. Near-rigid rounded frames
are corrected only in analysis; `--raw-transforms` on focused analysis commands
reproduces source-frame behavior. Discovery includes finite worm/spur candidates
and lists unsupported gears. See [discovery quality](discovery-quality.md) for the
10265 regression, numerical policy and required coverage review.

Dashed edges are candidates. A reviewed edge means an agent supplied a review
note; it does not certify mechanics. Inputs and outputs initially appear as
unidentified. A motion view derives body joints, rod endpoints and control
propagation from the actual executable plan. Candidate gear ratios in the part
view use the source gears' directed axes; they are not copied onto differently
oriented body axes.

```sh
# Regenerate after editing JSON. No conversion or Blender rebuild needed.
./ldraw-mecha diagrams output/study/plan.json
# Inspect part-level evidence after adding body groups.
./ldraw-mecha diagrams output/study/plan.json --view connections \
  --output output/study/connections
# Restrict output to one named view, preferably in a separate directory.
./ldraw-mecha diagrams output/study/plan.json --mechanism MECHANISM_ID \
  --output output/study/detail
```

Diagrams default to part connections for unplanned views and body motion for views
with bodies. Regeneration removes obsolete `.mmd` files listed in its previous
index; unrelated files are retained. Mermaid-capable Markdown viewers render
`README.md`. Mermaid CLI can optionally render SVG/PNG; it is not a runtime
requirement of source analysis. Syntax follows the
[Mermaid flowchart reference](https://mermaid.js.org/syntax/flowchart.html).

## Inspect early in Blender

With this repository on Blender's `sys.path`:

```python
from ldraw_mechanisms import blender_tools as tools, plan as contract

p = contract.load('/absolute/path/output/study/plan.json')
context = tools.inspect_prepared(p, glb='/absolute/path/output/study/model.glb')
tools.select_mechanism(context, next(iter(p['mechanisms'])))
```

Inspection adds the imported model to the current scene and binds draft identities.
It creates no rig, clears no scene, and saves no file. `select_mechanism` selects a
view's source parts and meshes, including shared supports. Each part gets a
`mecha_mechanisms` property. The root stores the study/digest; Mermaid diagrams
are ordinary Blender Text blocks, not scripts. The blocks are reviewable text;
Blender does not natively render Mermaid.

Pass `root=existing_root` instead of `glb` to refresh annotations without importing
again. Multiple imported copies use explicit roots; a new import binds only to
its own root. `apply_plan` refreshes the embedded study/diagrams when building or
verifying a plan containing mechanism views. Direct `blender.build` remains the
lower-level rig API.

## Turn a reviewed joint into motion

Edit the existing plan fields, or use the small joint-authoring helper. It writes
the same controls, signals and bodies that the evaluator and Blender already use:

```python
from ldraw_mechanisms import mechanisms, plan as contract

# Example: the measured 106 roof hinge. Choosing the moving roof and its safe
# range is a mechanical decision; connector coincidence does not supply them.
p = mechanisms.add_joint(
    p, mechanism='MECHANISM_ID', name='roof', instances=['0/40'],
    origin=[0, -92, 36], axis=[-1, 0, 0],
    minimum=0, maximum=1.3089969389957472,
    description='Open the roof',
)
contract.save('/absolute/path/output/study/plan.json', p)
mechanisms.write_diagrams(p, '/absolute/path/output/study/diagrams')
```

Replace `MECHANISM_ID` with the roof view's key. The axis sign is chosen for
outward opening; the opposite sign is the same hinge line but closes into the
car. The clearance check caught that wrong-sign case during this implementation. The helper supports revolute and
prismatic joints, preserves other views and evidence, validates ownership, and
leaves the plan a draft. It never automatically promotes a contact into a joint.
Couplings and closed loops use the existing signals, anchors and checks in the
[motion contract](motion-plan.md).

After inspecting the moving group, support, axis, range and propagation, set the
plan ready, validate and sweep it. In Blender:

```python
p = contract.load('/absolute/path/output/study/plan.json')
result = tools.apply_plan(p, root=context['root'])
rig = result['rig']
report = tools.check_clearance(p, rig=rig, controls=['roof'])
```

The previously imported GLB is reused. Regenerate it only when the source/selection
changes. A ready plan describes its declared motion; unrelated unresolved views
remain findings, not automatically implemented mechanisms. Save/reopen and perform
lifecycle checks before delivery. Sampled checks do not prove continuous clearance.

## Reuse an existing studied mechanism

```sh
./ldraw-mecha prepare data/models-annotated/42083-1.mpd \
  --section '42083 - engine.ldr' --output output/engine-study
./ldraw-mecha plan data/models-annotated/42083-1.mpd \
  --section '42083 - engine.ldr' --recipe 42083 \
  --study output/engine-study/plan.json --output output/engine-study/plan.json
./ldraw-mecha diagrams output/engine-study/plan.json
./ldraw-mecha sweep output/engine-study/plan.json
```

`--study` explicitly adopts the recipe's motion, retains discovered connections
and their reviews, and requires exactly matching source manifests. It preserves
all study views (including deferred/manual findings) and adds views grouped by
the new control dependencies. Old body/control references in retained views are
expanded to parts and cleared; previously planned views become unresolved until
reconciled with the new motion. Bodies shared by
controls retain one identity and one owner. Agents can edit view boundaries
without changing motion. This path reuses prior mechanical knowledge; it is not
an automatic solution of the W16 from its candidate graph.

Alternatively, `prepare --plan EXISTING_PLAN.json` attaches evidence and diagrams
to a pre-existing motion plan before conversion. Older plans without the optional
graph fields remain supported by the original CLI and Blender adapter.

## Validation of this branch

`tests/test_mechanisms.py` covers identities, shared boundaries, invalid/reviewed
edges, draft authoring, nonzero motion, deterministic diagrams, source-label
escaping, stale-file cleanup, discovery bounds, conversion failure ordering and
source compatibility. Existing pure tests remain part of the regression suite.

`check_prepared.py` exercises the actual draft-to-rig workflow in a disposable
background Blender process:

```sh
"$BLENDER_BIN" --background --factory-startup --python-exit-code 1 \
  --python scripts/blender/check_prepared.py -- \
  --study output/study/plan.json --glb output/study/model.glb \
  --output output/study/rig
```

It authors the 106 roof from detected hinge evidence, reuses the imported root,
checks nonzero poses, clearance state restoration, diagram freshness and reopening.
Use the existing `check_lifecycle.py` and `apply_plan.py --verify-existing` scripts
for rebuilding, duplicate-model isolation and fresh-process verification.
Generated evidence for this implementation is under `output/alt-process/`.
