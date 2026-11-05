# Working in this repository

Read `instructions.md` for the agent workflow and `docs/motion-plan.md` before
changing the motion contract. Keep source analysis independent of Blender.
If Blender, LeoCAD, ldraw-xray, ldraw-annotator, Bun or the LDraw library is missing, ask the
user to run their system's `setup-*.sh` script (`docs/setup.md`); don't install them yourself.

When the user supplies an unannotated model, offer to annotate it yourself with
`bin/ldraw-annotator` (else `ldraw-annotator` on `PATH`), following
`docs/annotation.md`. First run `prep` (no tokens) and give the user its size and
a token estimate, warning that a large model can take many tokens. If they
decline, stop: don't prepare, plan or animate an unannotated model. If they
accept: `prep --mpd` writes a copy, `prompt` gives the instructions for
structuring and describing it, and `check` must end with `"ok": true`. From then
on, use the annotated copy as if the user had supplied it. Preserve the original.
Don't rewrite or regroup already annotated models unless asked to.

When a candidate's parts or axis are uncertain, and before rigging authored
joints (again after each correction), render look boards with
`./ldraw-mecha xray` (`docs/xray.md`). It runs the
`ldraw-xray` CLI from `bin/` (else `PATH`); never import or install ldraw-xray. Answer each board's check
list and cite `xray/<board>/mosaic.png` in plan notes or evidence. Fix or review
every `body_boundary` warning from `check` before rigging.

Use pyldraw3 for LDraw parsing and connector expansion; use the supplied
mpd2glb wrapper for conversion. Preserve source files, model attribution and
the original Blender reference scripts. Put generated artifacts in `output/`.
For published references, copy the selected source, evidence and playback assets
to `examples/reference/`; never move or rely on the working copies. Follow
`docs/reference/curation.md` and check the archive before publishing links.
To publish a past result under `samples/`, run `./add-sample.sh` and write
the summary as described in `docs/samples.md`.

Always name the delivered animated file `ai-animated.blend`, and a delivered rig
without animation `ai-rigged.blend`, so users can recognize them. `rig` saves
under these names by default (with and without `--animate`); custom animation
scripts must save under them too.

When a run is finished, hand it over as described in `docs/workflow.md`
("Hand over the result"): clickable workspace-relative links to the `.blend`, the
xray boards, stills and reports. Then offer to open the `.blend` in Blender's user
interface (not headless), and launch it detached only if the user agrees.

For mechanism changes, run the relevant pure Python tests and evaluate
nonzero/asymmetric inputs. Adapter changes also need a background Blender
verification, reopening and lifecycle checks. Do not claim collision-free or
physically proven motion from equation or transform checks alone.
