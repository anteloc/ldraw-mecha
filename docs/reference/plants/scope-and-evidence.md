# Plants and wind: scope and evidence

Reviewed **2026-10-08**, implementation commit `6c1d5c7`. The
[example archive](../../../examples/reference/plants) preserves twenty plant
assemblies, sixty joint-animation clips, three wind-display Actions, source
and recipe metadata, plans, bound GLBs, the saved scene and selected previews.
The [original report](../../../examples/reference/plants/REPORT.md) remains a
historical record. The response page qualifies its broad “exact periodic steady
state” description: nonlinear vane breeze uses finite warm-up integration.

Fresh [source review](../../../examples/reference/plants-reference-review/review.json)
reproduces all twenty plans' motion fields, checks source hashes and part
placements, evaluates asymmetric values and compares all sixty baked clips with
the current Python definitions. It also repeats the geometry/recipe checks for
112 controls and records 25 `flex_approx` joints. Use
[review_catalog.py](../../../scripts/review_catalog.py) to rerun it without Blender.

The related pure tests pass: **195 combined** (102 plant, 93 movable). Wind
tests cover advection delay, periodic forcing, linear steady-state versus a long
RK4 run, mirrored frond direction, lag toward a chain tip, shelter thresholds,
vane heading, bounds and loop equivalence. Geometric tests cover assembly and
semantic axis signs. These are implementation checks, not measured dynamics.

The fresh [saved-scene check](../../../examples/reference/plants-reference-review/reopen-check.json)
passes in Blender **5.2.2 LTS** with auto-run disabled. It covers twenty rigs at
fourteen timeline frames each, sixty plant Actions/NLA tracks, saved plans
(excluding prose notes), valid pass-through drivers, the `Wind` scene, markers,
wind-display tracks and the arrow. One cross-controller clip transfer passes
with explicitly reported range clamping. Existing lifecycle reports cover P01,
P03 and P09; the earlier workflow regression covers P03. These are retained
evidence, not newly rerun lifecycle/clearance checks for this curation.

Palm, hanging-vine and vane preview sheets were inspected during curation.
They show useful motion differences but are only sampled visual evidence; the
overview video and full clip data accompany the archive for further review.

## Limits and remaining crossings

The [clearance summary](../../../examples/reference/plants/clearance-summary.json)
reports no new sampled mesh crossings for fourteen cases. P17 has contact at
the curl/clip (about 0.28 LDU reported vertex depth). P01, P05, P07, P09 and
P14 have shallow crossings, up to about 1.4 LDU, involving approximate bends,
seats or neighbouring parts. These are not erased by a visually convincing
render. Vertex depths are a sampled diagnostic on detected pairs; rest-contact
pairs are excluded, and a larger shrink is unreliable on thin leaves/shells.

Other boundaries to keep explicit:

- Ball chains use one chosen tilt per joint, not all ball freedoms. Their wind
  inputs are delayed independent oscillators, not coupled forces.
- Root tilts of stud-mounted parts approximate material bending. P09 is a
  piecewise rigid approximation of a flexible stem; P16 only rocks about its
  two-end grip line.
- Wind amplitude, lift/asymmetry gains, shelter thresholds and damping are
  authored. There is no aerodynamic wake, friction, gravity/contact solve or
  physical blade pitch in the flower rotors.
- Clips are baked for their field placement. Changing the wind display, moving
  the root or rotating the assembly does not recompute them.
- Joint-contact coverage is incomplete (73/112 confirmed pairs); source geometry
  and named precedents provide the remaining placement evidence, not proof of
  free motion. Authored ranges are not measured stops.

## Recheck the preserved example

```sh
.venv/bin/python scripts/review_catalog.py plants \
  --report output/new-plants-review/review.json
"$BLENDER_BIN" --background examples/reference/plants/plants.blend \
  --disable-autoexec --python-exit-code 1 \
  --python scripts/blender/check_plants_reopen.py -- \
  --bundle examples/reference/plants \
  --report output/new-plants-review/reopen-check.json
```

The archive is input; fresh reports go to `output/`. To rebuild a rig from a
snapshot, first relocate its source paths into a working plan using the
[archive guide](../../../examples/README.md). Preserve source attribution and
the separate library/shadow notices when constructing further examples.

The [archive portability review](../../../examples/reference/reference-portability/verification.json)
repeated source/reopen checks on **2026-10-12** without the working bundle.
Both wind code examples executed successfully, and all three Mermaid blocks
in these plant/wind references rendered successfully.
