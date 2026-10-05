# LDraw LEGO Mechanical Toolkit

Analyze LDraw models, describe their mechanisms in a JSON motion plan, and build
controllable Blender rigs from metadata-preserving GLB files.

The [curated 42110 Defender references](docs/reference/42110/README.md) explain ten
mechanisms and animation behaviours from a selected working rig. Each page pairs
fresh diagrams with part identities, motion relationships and the evidence's
limits, so agents can adapt a subsystem without studying the entire vehicle.

On the `alt-process` branch, start with a mechanism study before rigging:

```sh
./ldraw-mecha prepare data/models-annotated/106-1.mpd --output output/study
```

This creates candidate connections, a Mermaid flowchart per provisional mechanism,
and a GLB, in that order. Inspect the model in Blender, refine the same plan JSON,
then regenerate diagrams and build the rig without converting again. See the
[alternative workflow](docs/alternative-process.md) for the full process, draft
inspection APIs and coverage limits. The original commands below still work.

Discovery reports axle coverage and rounded-placement corrections, includes
supported worm-drive candidates, and preserves unresolved views when adopting
motion. Run `./ldraw-mecha audit output/study/plan.json` before rigging and delivery.
See [discovery quality](docs/discovery-quality.md) for the 10265 regression and
how to account for mechanisms that connector metadata cannot represent.

```sh
./setup.sh
export LDRAW_DIR=/path/to/ldraw

./ldraw-mecha inspect data/models-annotated/106-1.mpd --output output/106/inspection.json
./ldraw-mecha plan data/models-annotated/106-1.mpd --recipe 106 --output output/106/plan.json
./ldraw-mecha validate output/106/plan.json
./ldraw-mecha sweep output/106/plan.json --output output/106/sweep.json
./ldraw-mecha convert data/models-annotated/106-1.mpd --plan output/106/plan.json --output output/106/model.glb
./ldraw-mecha rig output/106/plan.json --glb output/106/model.glb \
  --save output/106/rigged.blend --report output/106/blender-check.json
```

Open the blend, select `CTRL_car106`, and use **Object Properties → Custom
Properties**. The doors, roof, and wheel assemblies have separate controls. Hover
over a control for its explanation. Right-click a property to insert a keyframe,
or add `--animate` to `rig` for demonstration keyframes. Drivers and constraints
remain ordinary Blender data after reopening; no add-on or Python auto-run is
needed to operate them.

Recipes `106`, `928` and `42000` demonstrate increasing complexity. The 42000
controller exposes steering and four wheel angles; steering propagates through
the gear train, rack, tie rods and knuckles, while the rear wheels drive the
differential and V8. The supplied specialized rig still provides vehicle path
integration through speed. The generic adapter operates the mechanisms in place.
Recipe `42083` studies the Bugatti Chiron W16 section `42083 - engine.ldr`:
one `drive` control turns the input shaft, a 20:12 double-bevel pair drives the
centre crank and 24:24 gears drive two lower cranks, moving 16 pistons and
conrods. Generated artifacts live in `output/42083-w16`.

Recipe `10265` rigs the Ford Mustang B-model: four wheels plus a complete
steering chain, where the wheel drives a universal joint, a 16T/40T mesh, a
pitman crank, two 100 LDU steering links and both kingpin knuckles, and the
engine's valve covers hinge open. Both tie-rod closures are checked. The
steering and valve ranges are deliberately small because the source packs those
mechanisms tightly; `docs/validation.md` records the clearance evidence, the
one checker artefact and the mechanisms left unresolved. Artifacts live in
`output/10265-v2`.

For a standalone assembly:

```sh
./ldraw-mecha plan data/models-annotated/928-1.mpd --recipe 928 \
  --section '928 - Space Ship - Cargo Hatchway.ldr' --output output/hatch/plan.json
./ldraw-mecha convert data/models-annotated/928-1.mpd --plan output/hatch/plan.json \
  --output output/hatch/model.glb
```

Agents start at [instructions.md](instructions.md). Read the [plan contract](docs/motion-plan.md),
[implementation plan](docs/implementation-plan.md) and [validation evidence](docs/validation.md).
The [discovery and Blender API guide](docs/discovery-and-blender.md) covers offline
FTS search, recursive submodel summaries, compact coordinate tables, gear meshes,
coaxial evidence, callable clearance checks and reversible moving-parts views.

```sh
./ldraw-mecha search submodels 'engine piston' --engine fts
./ldraw-mecha submodels data/models-annotated/42083-1.mpd --match engine --format table
./ldraw-mecha gear-meshes data/models-annotated/42083-1.mpd --section '42083 - engine.ldr'
```

Requirements: Python 3.12+, `uv`, Bun for the supplied exporter, an LDraw parts
library, and Blender for rigging. Headless rigs were tested in Blender 4.5.6 LTS;
the supplied reference was inspected through a live Blender 5.2.2 LTS MCP session. `BLENDER_BIN` or
`--blender` selects its executable; `LDRAW_DIR`, `LDRAWDIR`, or global `--library`
selects the library. Analysis needs neither Blender nor Jev. `jev-rerank` and
`TYPESAFE_API_KEY` enable optional semantic discovery.

The toolkit identifies candidates and connector evidence. An agent must still
decide which parts form rigid bodies, what joints exist, and which motion ranges
are supported. The studied recipes are executable examples, not universal
automatic rigging. Verification covers kinematics; mesh collision, force,
backlash, friction, flexible parts and general closed-loop solving are separate
work. Original source data and the supplied reference rig stay intact.

The repository works without sibling projects. It uses subprocess arguments,
configurable library paths and a read-through cache; the library can be mounted
read-only in a Linux container. Set `LDRAW_MECHA_CACHE` to a writable cache path.
Container deployment itself has not been tested.
Regenerate plans after moving the workspace: they record absolute source paths
and content hashes. Saved Blender rigs operate independently of those paths.
