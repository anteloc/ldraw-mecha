# LDraw LEGO Mechanical Toolkit

Analyze LDraw models, describe their mechanisms in a JSON motion plan, and build
controllable Blender rigs from metadata-preserving GLB files.

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

For a standalone assembly:

```sh
./ldraw-mecha plan data/models-annotated/928-1.mpd --recipe 928 \
  --section '928 - Space Ship - Cargo Hatchway.ldr' --output output/hatch/plan.json
./ldraw-mecha convert data/models-annotated/928-1.mpd --plan output/hatch/plan.json \
  --output output/hatch/model.glb
```

Agents start at [instructions.md](instructions.md). Read the [plan contract](docs/motion-plan.md),
[implementation plan](docs/implementation-plan.md) and [validation evidence](docs/validation.md).

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
