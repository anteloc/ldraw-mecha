# LDraw LEGO Mechanical Toolkit

Study an LDraw model, describe its motion in one JSON plan, and build a
controllable Blender rig. Agents decide what moves and why; the tools collect
evidence, execute the plan and check the result.

**Prepare → edit the plan → check → rig → visual review.**
Start with [how it works](docs/how-it-works.md) for the explanation or
[the workflow](docs/workflow.md) for commands. Agents follow [instructions.md](instructions.md).

## Try an existing example

```sh
./setup.sh
export LDRAW_DIR=/path/to/ldraw
export BLENDER_BIN=/path/to/blender

./ldraw-mecha prepare data/models-annotated/106-1.mpd --recipe 106 --output output/study
./ldraw-mecha check output/study
./ldraw-mecha rig output/study --animate --reopen
```

Open `output/study/rigged.blend`, select `CTRL_car106`, and use **Object
Properties → Custom Properties** for doors, roof and wheels. Controls persist
after reopening without an add-on or Python auto-run. The blend includes a
demonstration animation; verification reports sit beside the plan.

This recipe declares studied motion for this exact car. Discovery findings
remain visible for review; `check --require-reviewed` will fail until they are
reconciled. Reopening checks the saved rig's transforms. Clearance and visual
review remain separate [delivery checks](docs/validation.md).

## Work on another model

Run `prepare MODEL --output output/STUDY` without `--recipe`, inspect the
evidence and geometry, then author measured joints in `plan.json`. A study
directory contains ordinary files; commands also accept explicit plan paths.
Existing commands, flags and version-1 plans continue to work.

For an **unannotated original**, complete [annotation](docs/annotation.md) before
preparation: part comments, authored model/assembly descriptions, recursive
hierarchy review and preservation checks. Reuse already annotated sources
without semantic rewrites unless requested. For a single mechanism, deliver an
extracted subsystem with its agreed mounts/coupled parts; see [scope selection](docs/workflow.md#choose-the-deliverable).

The CLI recipes `106`, `928`, `42000`, `42083` and `10265` are executable examples
for exact source selections. The [reference catalog](docs/reference/README.md)
explains gears, steering, engines, suspension, minifigs, movable elements and
plant/wind animation. Adapt their reasoning and checks, then remeasure the target.

## Find the details

| Need | Read |
| --- | --- |
| Everyday commands and recovery | [Workflow](docs/workflow.md) |
| Joint types, equations, frames and fields | [Motion plan](docs/motion-plan.md) |
| Source discovery and live Blender tools | [API guide](docs/discovery-and-blender.md) |
| Missed contacts, rounded transforms, coverage | [Discovery quality](docs/discovery-quality.md) |
| Part families, descriptions and dimensions | [Part information](docs/part-information.md) |
| Testing, clearance and evidence limits | [Validation](docs/validation.md) |
| Code boundaries | [Architecture](docs/architecture.md) |
| Publishing a selected working example | [Curation](docs/reference/curation.md) and [asset archive](examples/README.md) |

## Requirements

Python 3.12+, `uv`, an LDraw library, Bun for conversion, and Blender for rigging.
Source analysis needs neither Blender nor Jev. `--blender`/`BLENDER_BIN` selects
Blender; global `--library`, `LDRAW_DIR` or `LDRAWDIR` selects the parts library.
Offline FTS search is the default; `jev-rerank` and `TYPESAFE_API_KEY` enable
optional semantic search. No sibling checkout is required. A read-only library
works with a writable `LDRAW_MECHA_CACHE`; container deployment is untested.

Plans record source paths/hashes; regenerate after moving the workspace, or use
the archive's checked path-relocation helper for retained examples. Saved rigs
operate independently. Declared kinematics do not simulate forces, friction,
backlash or general contact dynamics; passing checks alone cannot establish
physical feasibility.
