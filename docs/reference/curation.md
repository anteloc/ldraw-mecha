# Curating a mechanism reference

Use this process when the user selects a promising working animation for the
[reference catalog](README.md). The result is one Markdown document per
mechanical subsystem, supported by the actual implementation and evidence.
The rigging agent can use existing references without writing new diagrams.

## Inspect the selected result

Start from the supplied output directory. Locate its exact plan, source selection,
builder, animation script, saved blend, numerical/Blender checks and previews.
Record paths and hashes for the artifacts on which the reference relies.
If evidence is missing, investigate or state the gap; a visually accepted
animation does not validate every coupling.

Read the source geometry, motion signals, body ownership, anchors, selector
logic and tests. Reconcile them with the saved blend; rerun relevant checks or
render nonzero/limit poses in a separate Blender process when needed. Preserve
the selected output bundle and the user's live scene. Put fresh checks and
renders under `output/CASE-reference-review/`.

Do not inherit old generated diagrams as facts. Trace each claimed power path,
link closure or state condition to source measurements and implemented motion.
Distinguish physical assembly, evaluation direction and presentation choices:
a wheel-driven demonstration may evaluate opposite to engine power flow.
Document disagreements with older notes rather than copying them.

## Choose subsystem boundaries

Group rigidly moving parts into shafts, carriers, links or bodies that explain
the mechanism. Give each group exact occurrence IDs or an explicit mapping.
Show shared interfaces across pages: input/output shafts, fixed mounts, axis
conventions and omitted neighbours. Avoid a diagram of every decorative part.

Split pages by reusable function: differential, gearbox, shaft coupling,
steering linkage, piston mechanism, suspension or winch. Keep an animation page
when timing/state transitions are important, and an extraction page when fixed
interfaces or identity remapping affect reuse.
For a standalone result, record which coupled elements were retained and whether
they move or act as fixed supports; this is part of the
[requested subsystem boundary](../workflow.md#choose-the-deliverable).

## Write each page

Include the following where relevant:

- Purpose, scope and a link to the case's evidence page.
- Input/output controls, units, limits, fixed supports and source-pose convention.
- Part/body identity map and measured axes, centres, lengths or tooth counts.
- Diagram(s) with meaningful connection labels and legible subsystem boundaries.
- Equations, ratios, signs, phases, selector conditions and expected propagation.
- Checks that support each relationship, including nonzero/asymmetric cases.
- Approximations, unresolved contacts, unsupported effects and what must be
  remeasured for another model.

Use a diagram only when it adds information:

| Diagram | Use |
| --- | --- |
| Mermaid flowchart | Assembly relationships, shafts, couplings and power/evaluation paths |
| Mermaid state diagram | Discrete states such as engaged/neutral, selected gear or an animation phase |
| Mermaid sequence diagram | Ordered control events, engagement/disengagement or shifting continuity |
| Table/equation | Ratios, coordinates, continuous angles, conditions and tolerances |

A door usually has continuous travel; “open/closed” alone does not describe its
kinematics. A state diagram can explain endpoints or a demonstration's phases
without treating intermediate motion as discrete. A sequence diagram describes
event order, not a spatial linkage.

Label unknown or approximated relationships explicitly. A connection's label
must say what it means: rigid lock, bearing, gear relation, imposed motion or
surface-contact hypothesis. Do not imply that connector contact proves torque
transfer. The plan format does not enforce a complete typed coupling graph;
cross-check diagrams against the implemented equations and evidence.

## Validate and publish in the repository

Resolve part/body/control IDs against the exact plan and source. Check equations
and conditions against saved motion; inspect relevant animation states, not only
the default pose. Render every Mermaid block with Mermaid CLI when available
and fix syntax/legibility problems. Check local document links. Keep rendering
and check outputs under `output/` while working.

Before publishing, copy the relevant inputs and evidence into
`examples/reference/CASE` and the review evidence into
`examples/reference/CASE-reference-review`. **Copy, never move** the originals.
Retain source MPDs and dependencies, occurrence maps, plans, required contact
evidence, clips, saved playback and selected previews. Keep maintained builders
under `scripts/`; copy any review code that previously existed only in `output/`.
Exclude backup blends, logs, bulk frame renders and obsolete automatic diagrams
unless a claim specifically needs one. Preserve attribution and original hashes.

Follow the [archive guide](../../examples/README.md): record the selection and
hashes, make copied review code read archived inputs and write new results under
`output/`, and relocate plan filenames only in a working copy. Check source
dependencies and LFS assets in a checkout without the original working tree.
All published artifact links must resolve under `examples/`, `data/` or
`scripts/`, never `output/`. Generated command destinations still use `output/`.

Create `docs/reference/CASE/README.md` as the case index and
`scope-and-evidence.md` for provenance, hashes, check coverage and shared limits.
Link subsystem pages from that index and add mechanism-oriented entries to the
main [catalog](README.md). A reference may be useful with explicit approximations;
do not label sampled or visually plausible motion as physically proven or
collision-free.

These documents describe a particular version of a working result. If the
source, plan, builder or saved animation changes, review the affected claims and
diagrams. The Markdown does not update itself. Include the archived assets in the
same change as their documentation. Run `.venv/bin/python scripts/reference_assets.py check`
to catch missing snapshots, source dependencies, hashes and working-directory links.
