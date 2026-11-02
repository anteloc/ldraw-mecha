# Visual inspection with ldraw-xray

`./ldraw-mecha xray` renders **look boards** with the globally installed
`ldraw-xray` CLI (LeoCAD): the moving set coloured and edged, everything else
ghosted, the green axis rod and close-up poses. Each board is one `mosaic.png`,
and the JSON result carries its check list. ldraw-mecha runs the CLI; it never
imports or installs it. Run `ldraw-xray doctor` once per session (`"renders":
true`); if it fails, record that xray evidence is unavailable and continue
numerically.

## Read every board with this check list

1. **Coloured = exactly what moves.** Mirror twins are coloured alike; nothing
   coloured sits on a grey axle or pin off the rod; nothing grey that should
   move is left behind (a slewing turret carries its whole boom).
2. **The rod passes through the joint hardware**: hinge barrel, axle, pin or
   turntable centre. A rod beside or across it is the wrong frame.
3. **Positive poses turn the intended way.** Compare each pose with rest;
   check mirrored pairs separately.
4. **Limit poses do not cut through grey neighbours.**

A round part spinning on its own axis (wheel, gear, crank) looks alike in every
pose; judge it by items 1 and 2. Fix the selection or plan, then re-render.

## When to use it

| Moment | Command |
| --- | --- |
| A candidate's parts or axis are uncertain (after `prepare`, before authoring), or the user reports a part | `./ldraw-mecha xray output/study --instances IDS --point X Y Z --direction X Y Z [--angles DEG ...] --name NAME` |
| Authored motion: before `rig`, and after every correction | `./ldraw-mecha xray output/study` (all bodies) or `--body NAME ...` (changed ones) |

Take axes from `connectors` `world_position`/`world_axis` or a `coaxial` line
first: xray confirms, it does not discover. Coordinates are the section frame
of `connectors` and `plan.json`; `--angles` are degrees, plan values radians.
Without a study, pass the model, `--section` and `--xray-dir`.

- **Candidate with a study and an axis:** the selection is also audited as one
  body on that axis against the study's contacts. `boundary` lists parts outside
  it that are pinned or keyed off the axis: a wrong grouping, before authoring.
- **Review:** each body is posed with its descendant bodies, as the rig
  composes motion; its parent stays at rest. Revolute bodies show rest and each
  driving control's min/default/max (full turns: 0, 45, 90 degrees).
  Prismatic and stretch bodies show the axis and selection only: xray cannot
  translate parts.
- Boards land in `output/study/xray/<board>/` (with `panels/`, `recipe.json`
  and `manifest.json`); a re-run replaces them. Boards render in parallel,
  about 7 s each.

## Record what you saw

Cite the mosaic and what it showed in view notes or connection evidence, for
example "rod through the 4213 hinge fingers; +75 degrees opens upward
(xray/roof/mosaic.png)". Report findings that changed an axis, sign, selection
or scope.

## Other questions: run ldraw-xray directly

The result gives `render_source`, a flat copy of the section with one line per
occurrence, and each board's `select` (`line:` ranges). Reuse them with
ldraw-xray's own commands (`ldraw-xray --help`, its README):

| Question | Command |
| --- | --- |
| What is behind a shell? | `ldraw-xray render SRC --xray 'line:...' --highlight 'line:...' --output DIR` |
| What is inside? | `ldraw-xray board cutaway SRC --view front --depths 0.35 0.5 0.65 --output DIR` |
| How is a submodel built? | `ldraw-xray board overview MODEL --section S --steps 3,7-9 --output DIR` on the original model. Build order is not motion grouping. |
| Another view or camera? | Edit `<board>.recipe.json`, then `ldraw-xray board run FILE --output DIR --force` |

## Limits

- Images are static poses: not proof of clearance, engagement or physical
  feasibility. Blender clearance checks and the saved animation review remain
  required.
- Embedded or library-unknown parts have no measurable bounds; a moving set made
  only of them is posed with one whole-block camera (the board notes say so).
- `check` audits body membership against connector contacts (`body_boundary`).
  Boards cover what that audit cannot see: embedded parts, surface contacts,
  stops, axes and signs.
