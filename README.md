# LDraw LEGO Mechanical Toolkit

Study an LDraw model, describe its motion in one JSON plan, and build a
controllable Blender rig. Agents decide what moves and why; the tools collect
evidence, execute the plan and check the result.

**Prepare → edit the plan → check → rig → visual review.**
Start with [how it works](docs/how-it-works.md) for the explanation or
[the workflow](docs/workflow.md) for commands. Agents follow [instructions.md](instructions.md).
See what agents have built with it in the [samples gallery](GALLERY.md).

## Try an existing example

```sh
./setup-macos.sh  # once per machine, or setup-linux.sh / setup-win-wsl.sh (docs/setup.md);
                  # then add the printed exports to your shell profile

./ldraw-mecha prepare data/models-annotated/106-1.mpd --recipe 106 --output output/study
./ldraw-mecha check output/study
./ldraw-mecha rig output/study --animate --reopen
```

Open `output/study/ai-animated.blend`, select `CTRL_car106`, and use **Object
Properties → Custom Properties** for doors, roof and wheels. Controls persist
after reopening without an add-on or Python auto-run. The blend includes a
demonstration animation; verification reports sit beside the plan.

This recipe declares studied motion for this exact car. Discovery findings
remain visible for review; `check --require-reviewed` will fail until they are
reconciled. Reopening checks the saved rig's transforms. Clearance and visual
review remain separate [delivery checks](docs/validation.md).

## Work on another model

To pick one, browse the annotated models with their descriptions and a 3D view:
`python3 model-selector/serve.py`, then **Copy path** on the model you want
(see [model-selector/README.md](model-selector/README.md)).

Run `prepare MODEL --output output/STUDY` without `--recipe`, inspect the
evidence and geometry, then author measured joints in `plan.json`. A study
directory contains ordinary files; commands also accept explicit plan paths.
Existing commands, flags and version-1 plans continue to work.

For complex drivetrains, read the [mechanism authoring guide](docs/mechanisms.md). New physical
occurrence checks catch independent gear spin, wrong shaft axes and carrier
relations; `check` and `rig` accept `--require-constrained` to reject unchecked
moving bodies before producing an animation.
The original [supported gear drive](examples/gear-drive/README.md) provides a
small complete source, authoring recipe and validation record. Blender checks
off-grid inputs and samples saved animation with its timeline active.

An **unannotated original** must be [annotated](docs/annotation.md) first: the
agent offers to do it with `ldraw-annotator`, with a token estimate, and stops if
you decline. Already annotated sources are reused as they are. For a single mechanism, deliver an
extracted subsystem with its agreed mounts/coupled parts; see [scope selection](docs/workflow.md#choose-the-deliverable).

The CLI recipes `106`, `928`, `42000`, `42083` and `10265` are executable examples
for exact source selections. The [reference catalog](docs/reference/README.md)
explains gears, steering, engines, suspension, minifigs, movable elements and
plant/wind animation. Adapt their reasoning and checks, then remeasure the target.

## Find the details

| Need | Read |
| --- | --- |
| The whole process, step by step, on one example | [Process](PROCESS.md) |
| Setting up a machine (macOS, Linux, Windows) | [Setup](docs/setup.md) |
| Everyday commands and recovery | [Workflow](docs/workflow.md) |
| Joint types, equations, frames and fields | [Motion plan](docs/motion-plan.md) |
| Source discovery and live Blender tools | [API guide](docs/discovery-and-blender.md) |
| Look boards for candidates and authored joints | [Visual inspection with ldraw-xray](docs/xray.md) |
| Missed contacts, rounded transforms, coverage | [Discovery quality](docs/discovery-quality.md) |
| Part families, descriptions and dimensions | [Part information](docs/part-information.md) |
| Testing, clearance and evidence limits | [Validation](docs/validation.md) |
| Code boundaries | [Architecture](docs/architecture.md) |
| Publishing a selected working example | [Curation](docs/reference/curation.md) and [asset archive](examples/README.md) |

## Requirements

Python 3.12+, `uv`, an LDraw library, Bun for conversion, and Blender for rigging.
`./setup-macos.sh`, `./setup-linux.sh` or `./setup-win-wsl.sh` (WSL2) installs all
of them, with ldraw-xray, LeoCAD and ldraw-annotator, inside the project (`bin/`, `data/ldraw`,
`.venv`); see [setup](docs/setup.md). Tools are taken from `bin/`, else `PATH`.
Visual inspection (`./ldraw-mecha xray`) runs the `ldraw-xray` CLI (with LeoCAD);
check it with `bin/ldraw-xray doctor`. Source analysis needs neither
Blender, ldraw-xray nor Jev. `--blender`/`BLENDER_BIN` selects
Blender; global `--library`, `LDRAW_DIR` or `LDRAWDIR` selects the parts library.
Offline FTS search is the default; `jev-rerank` and `TYPESAFE_API_KEY` enable
optional semantic search. No sibling checkout is required. A read-only library
works with a writable `LDRAW_MECHA_CACHE`; container deployment is untested.

Plans record source paths/hashes; regenerate after moving the workspace, or use
the archive's checked path-relocation helper for retained examples. Saved rigs
operate independently. Declared kinematics do not simulate forces, friction,
backlash or general contact dynamics; passing checks alone cannot establish
physical feasibility.
