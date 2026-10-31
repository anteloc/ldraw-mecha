# Visual inspection with ldraw-xray

`ldraw-xray` renders LDraw source with LeoCAD so an agent can **see** what the
evidence describes: how a mechanism submodel is built step by step, where it
sits in its parent, which placements a selection really contains, and where a
candidate or authored axis passes. Use it while studying geometry, before and
while authoring `plan.json`, and again whenever an axis, sign or boundary
changes. It complements the numerical [analysis tools](discovery-and-blender.md)
and the Blender [visual review](validation.md#clearance-and-visual-review); it
replaces neither.

`ldraw-xray` is an external CLI installed on `PATH`. ldraw-mecha never imports
or installs it. `./ldraw-mecha xray-args` only translates occurrence IDs and
plan joints into exact `ldraw-xray` arguments; agents run the printed commands.

```sh
ldraw-xray doctor          # expect "renders": true
```

Run `doctor` once per session. If it fails, record that xray evidence is
unavailable and continue with the numerical study; do not substitute guesses
for the missing images. `ldraw-xray` resolves its own LDraw library
(`LDRAW_DIR`), LeoCAD (`LEOCAD`) and optional shadow library (`LDRAW_SHADOW`);
see its README for setup.

## When to use it

1. **After annotation and `prepare`, before authoring motion.** For each
   mechanism you will plan, inspect its submodel's build, its fit in the parent
   and the candidate input, output and supports.
2. **Before accepting an axis.** Render a pivot board for each candidate axis
   taken from `connectors` `world_position`/`world_axis` or a `coaxial` line.
3. **After authoring each revolute or prismatic body, before `rig`.** Confirm
   pivot location, axis line, positive direction, mirrored pairs and limit poses.
   Re-run after every correction.

## Study a candidate

```sh
ldraw-xray sections data/models-annotated/106-1.mpd
./ldraw-mecha connectors data/models-annotated/106-1.mpd \
  --section '106 - main.ldr' --instance 0/40
./ldraw-mecha xray-args data/models-annotated/106-1.mpd \
  --section '106 - main.ldr' --instances 0/40 \
  --point 0 -92 36 --direction -1 0 0 --angles 0 40 75 \
  --xray-dir output/study/xray
```

`--point` and `--direction` are in the selected section frame (the frame of
`connectors` world fields and of `plan.json`). `--angles` are **degrees**, as
ldraw-xray expects; omit them for 0, 45 and 90. Without an axis, the result
still lists the overview, context and selection renders.

## Review an authored body

```sh
./ldraw-mecha xray-args --plan output/study --body roof
```

Plan mode reads the body's instances, `origin`, `axis` and signal from the plan.
Poses cover rest (0) and the body signal at each driving control's minimum,
default and maximum, converted from radians to degrees. Full-turn ranges show
0, 45 and 90 degrees. Prismatic and stretch bodies show the axis and selection
only, because xray cannot translate or scale parts. Child bodies are posed about
their rest-frame axis without their parent's motion. Renders default to
`xray/BODY/` beside the plan; `--xray-dir` overrides that. The source must be
unchanged since preparation.

## What xray-args reports

Both tools number source lines from 1 across the whole file, so an occurrence's
`line` is the line ldraw-xray selects. An xray `line:` term selects **direct
placements of the rendered block**, so the bridge chooses blocks for you:

- `subject` is the lowest block placing every requested occurrence, with a
  `line:` selector. When the occurrences are exactly one whole assembly, the
  subject is that assembly's own block (moving `all`): its overview is the
  mechanism's own build.
- `surroundings` is then the block that places the assembly, selected by its
  placement line, so the motion can be judged among its neighbours.
- `pivot` on each block gives the point and direction **in that block's frame**
  and the angles to pass. A mirrored placement negates the angles so the
  rendered motion matches the plan.
- `occurrences[].chain` lists each `(block, line)` from the selected section down.

Each command is an argv list plus a shell string. Run them from any directory;
paths are absolute.

| Command | Shows |
| --- | --- |
| `overview` | Block in its parent, isolated view, one cumulative image per source step with new parts edged (`--no-mosaic` when over 12 images) |
| `context` | Block highlighted in its parent, surroundings ghosted, home and front views |
| `selection` | Selected placements edged in the isolated block |
| `pivot` | Axis rod with joint context, the parent panel, and the moving selection posed at each angle (one fixed camera) |
| `pivot-in-parent` | The same motion in the surrounding block |
| `pivot-focus` | `board run` on a written recipe: close-up on the moving parts' rest bounds, axis rod, moving parts edged, everything else ghosted |
| `connections`, `axes` | JSON reports for the block, saved to the listed `stdout` file |

| Warning | Meaning and action |
| --- | --- |
| `over_selects` | A selected placement also contains parts outside the request; listed in `extra`. Expect them to move in the renders. |
| `shared_definition` | The parent places this block several times. Poses edit the definition, so parent panels move every copy and context highlights every copy; trust the isolated panels. |
| `mirrored` | The block is placed with a reflection; angles were negated. |
| `non_orthonormal` | The placement has scale or shear; confirm the rod against the hardware. |
| `several_parents`, `no_parent` | Context uses the first parent, or is omitted. |
| `external_file` | The block is a separate `.ldr` file; it renders alone because xray reads one file. |

## Read the boards

- **Build and boundary.** In `overview`, check that the mechanism's moving and
  supporting parts belong where the descriptions say, and that hidden internals
  (cranks, gears behind casings) are what discovery reported. A mechanism may
  cross FILE sections: look at the parent panel before fixing the scope.
- **Selection.** `selection` must edge exactly the parts you meant. A wrong
  occurrence ID is visible here before it reaches a plan.
- **Axis.** The green rod must pass through the joint hardware: hinge barrel,
  axle, pin or turntable centre. A rod that misses or lies across the hardware
  is the wrong frame, often part-local instead of connector axes.
- **Direction and sign.** The moving parts must open, lift or turn the intended
  way at positive plan values. Check mirrored pairs separately; one shared sign
  usually reverses one side.
- **Limits and neighbours.** Limit poses must not plainly pass through the
  surroundings. Use `pivot-in-parent` or `context` for neighbours that an
  extracted subsystem would hide.
- **Hidden or small moving parts.** If the `pivot` result lists
  `duplicate_panels` or the poses look alike, use `pivot-focus`. If the moving
  parts face away from the home view, copy the saved recipe, replace `home`
  with another view (`back`, `left`, ...) in each panel's `view`, in a fixed
  `camera`, or in the `closeup` layer, then run
  `ldraw-xray board run EDITED.json --output DIR`.

Re-running into a nonempty output directory needs `--force`. A mosaic holds 2–12
images; `ldraw-xray mosaic MANIFEST --output FILE.png` recomposes panels later.

## Record what you saw

Keep renders under `output/STUDY/xray/`. Cite the panel images and
`manifest.json` you relied on in mechanism view `notes`/`review` and in
connection `evidence` strings, stating what each image showed: for example
"rod through the 4213 roof's hinge fingers; 75 degrees opens upward
(xray/roof/pivot/panels/04-pose-75-degrees.png)". The plan contract does not
change. Report findings that changed an axis, sign, selection or scope.

## Limits

- Images are static poses. They are visual evidence, not proof of clearance,
  engagement or physical feasibility. Blender clearance checks and the review
  of the saved animation remain required before delivery.
- `collisions` layers and `connections` overlap candidates are axis-aligned box
  tests. pyldraw3 detection misses Technic pin/axle mating, so ldraw-mecha's
  corrected `contacts` remain the connection evidence.
- `axes` directions are sign-normalised and never decide a sign. Use
  `connectors` and the authored plan.
- `connections`, `axes`, `components` and `contacts` inspect source geometry in
  the isolated block and ignore poses.
