# Working in this repository

Read `instructions.md` for the agent workflow and `docs/motion-plan.md` before
changing the motion contract. Keep source analysis independent of Blender.

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
