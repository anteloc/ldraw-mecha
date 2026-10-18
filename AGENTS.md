# Working in this repository

Read `instructions.md` for the agent workflow and `docs/motion-plan.md` before
changing the motion contract. Keep source analysis independent of Blender.

Before studying or preparing a model, ensure it has descriptive `0 // ` comments
immediately above its type-1 part lines. If unannotated or partially annotated,
run `./ldraw-mecha annotate ORIGINAL --output output/annotated/MODEL.mpd` first
and use that copy for analysis and subsequent plans. Preserve the original;
review unknown references reported by the command. See the prerequisite in
`instructions.md` and `docs/workflow.md` for metadata and directory options.

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
