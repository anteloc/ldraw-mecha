# Working in this repository

Read `instructions.md` for the agent workflow and `docs/motion-plan.md` before
changing the motion contract. Keep source analysis independent of Blender.

For an unannotated model, complete the semantic annotation pipeline before
`prepare` or motion planning: (1) `annotate` adds `0 // ` part/colour comments
to a separate copy; (2) the agent immediately inspects that copy and authors rich,
single-line descriptions for the model and each existing submodel/group assembly,
placed as `0 DESCRIPTION` directly below its `0 FILE` line, applied with
`annotate-semantics`; (3) the agent reviews semantic coverage of the hierarchy
recursively, including flat models, and creates and richly describes missing
submodels/sub-submodels when supported by the source. Record why retained or
inferred groupings are sufficient. Preserve every physical occurrence and verify
references, effective colours and world transforms with an old-to-new ID map
after regrouping. Use the finished hierarchy for study and plans.
Preserve originals, section names, attribution and existing rich descriptions.
Unless explicitly instructed otherwise, semantic enrichment belongs only to
this unannotated-model pipeline; do not rewrite or regroup already annotated
models during other work. See `instructions.md` and `docs/workflow.md` for the
full procedure.

Use pyldraw3 for LDraw parsing and connector expansion; use the supplied
mpd2glb wrapper for conversion. Preserve source files, model attribution and
the original Blender reference scripts. Put generated artifacts in `output/`.
For published references, copy the selected source, evidence and playback assets
to `examples/reference/`; never move or rely on the working copies. Follow
`docs/reference/curation.md` and check the archive before publishing links.

For mechanism changes, run the relevant pure Python tests and evaluate
nonzero/asymmetric inputs. Adapter changes also need a background Blender
verification, reopening and lifecycle checks. Do not claim collision-free or
physically proven motion from equation or transform checks alone.
