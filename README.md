# LDraw LEGO Mechanical Toolkit

Analyze LDraw models, describe mechanisms in a JSON motion plan, and build
controllable Blender rigs from metadata-preserving GLB files.

The workflow is **reuse references → study the model → rig and animate → verify
→ visual review**. User-selected successful results become documented examples
for later agents. Start at [instructions.md](instructions.md) and the
[workflow guide](docs/workflow.md).

The [reference catalog](docs/reference/README.md) covers the 42110 Defender's
gearboxes, differentials, shafts, steering, engine and winch; the 42083 W16's
crankshafts, rods and pistons; and standalone suspension with wishbones,
half-shafts and telescoping shocks. The
[Chiron mechanism studies](docs/reference/42083-mechanisms/README.md) add a wing
parallelogram, paddle/pawl geometry and a qualified eight-speed selector cascade.
The [minifig examples](docs/reference/minifigs/README.md) add articulated limbs,
held items, reusable animation clips and separate whole-figure staging.
Each subsystem has diagrams, identities,
relationships and evidence limits. Agents adapt these references without having
to create new diagrams during rigging.

## Start a study

```sh
./setup.sh
export LDRAW_DIR=/path/to/ldraw
./ldraw-mecha prepare data/models-annotated/106-1.mpd --output output/study
```

This saves `plan.json`, `preparation.json` and `model.glb`. The plan initially has
candidate evidence and no invented motion. Inspect discovery coverage and the
model, then author measured motion in that same plan. Preparation and Blender
inspection do not generate diagrams. The explicit `diagrams` command remains an
optional diagnostic; curated references are written after reviewing working rigs.

For a runnable example, adopt the studied 106 recipe into the prepared study:

```sh
./ldraw-mecha plan data/models-annotated/106-1.mpd --recipe 106 \
  --study output/study/plan.json --output output/study/plan.json
./ldraw-mecha audit output/study/plan.json
./ldraw-mecha validate output/study/plan.json
./ldraw-mecha sweep output/study/plan.json --output output/study/sweep.json
./ldraw-mecha rig output/study/plan.json --glb output/study/model.glb \
  --save output/study/rigged.blend --report output/study/blender-check.json --animate
```

The audit leaves original candidate views visible until reconciled; adopting a
recipe does not review them automatically. Open the blend, select `CTRL_car106`,
and use **Object Properties → Custom Properties** for doors, roof and wheels.
Drivers and constraints remain ordinary Blender data after reopening; no add-on
or Python auto-run is needed to operate them. `--animate` adds demonstration
keyframes. Follow the [validation guide](docs/validation.md) for reopening,
lifecycle, clearance and visual checks before delivery.

Studied CLI recipes are `106`, `928`, `42000`, `42083` and `10265`. They are
executable examples for exact source selections, with explicit limits. They are
separate from the curated documentation catalog; neither is automatic rigging
for an arbitrary model. Requests to animate one mechanism default to a standalone
subsystem, including agreed coupled elements. Study with `--section`, then
extract the chosen parts so the MPD, GLB and blend contain that subsystem only.
See [scope selection](docs/workflow.md#choose-the-deliverable).

## Documentation

- [Workflow](docs/workflow.md): preparation, inspection, authoring and delivery.
- [Reference catalog](docs/reference/README.md) and [curation guide](docs/reference/curation.md).
- [Analysis and Blender APIs](docs/discovery-and-blender.md): search, inventory,
  compact coordinates, contacts, gear/coaxial evidence and callable scene tools.
- [Discovery quality](docs/discovery-quality.md): coverage, rounded transforms
  and accounting for unresolved mechanisms.
- [Part information](docs/part-information.md): when to use the category tables,
  dimensions, description files, SQLite and connector metadata.
- [Motion contract](docs/motion-plan.md), [architecture](docs/architecture.md)
  and [validation](docs/validation.md).

## Requirements and scope

Python 3.12+, `uv`, Bun for the supplied exporter, an LDraw parts library, and
Blender for rigging. `BLENDER_BIN` or `--blender` selects Blender; `LDRAW_DIR`,
`LDRAWDIR`, or global `--library` selects the parts library. Source analysis needs
neither Blender nor Jev. Offline FTS search is the default; `jev-rerank` and
`TYPESAFE_API_KEY` enable optional semantic search.

The toolkit supplies evidence and executes declared kinematics. An agent still
decides rigid groups, joints, coupling and supported travel. Force, friction,
backlash and general contact dynamics are outside that contract; equation and
transform checks cannot establish physical feasibility. Original source data
and the supplied 42000 reference rig remain intact.

No sibling checkout is required. Library paths are configurable and the library
can be mounted read-only; set `LDRAW_MECHA_CACHE` to a writable cache location.
Container deployment has not been tested. Regenerate plans after moving the
workspace: they record absolute source paths and hashes. Saved Blender rigs
operate independently of those source paths.
