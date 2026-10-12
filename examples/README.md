# Preserved examples

`output/` is the working directory. This directory retains **copies** of the
selected results used by the [reference library](../docs/reference/README.md),
so documentation remains useful after that working directory is deleted.
Original sources and results are not moved or rewritten during archiving.

The [selection](reference/selection.json) records which artifacts were chosen.
The [manifest](reference/manifest.json) records each original working path,
source SHA-256, archived SHA-256 and size. Plans/reports keep their original
provenance, including historical machine-specific filenames. Adapted review
scripts are identified in the manifest with both hashes and an adaptation note.

| Bundle | Contents and documentation |
| --- | --- |
| [42110](reference/42110) | [Defender drivetrain, steering, engine and winch](../docs/reference/42110/README.md) |
| [42083-w16](reference/42083-w16) | [Geared crankshafts and slider-crank engine](../docs/reference/42083-w16/README.md) |
| [42110-suspension-standalone](reference/42110-suspension-standalone) | [Suspension](../docs/reference/42110-suspension-standalone/README.md), with retained full-model measurement inputs |
| [42083-mechanisms](reference/42083-mechanisms) | [Five independent Chiron rigs](../docs/reference/42083-mechanisms/README.md) |
| [minifigs](reference/minifigs) | [Articulated figures and clips](../docs/reference/minifigs/README.md) |
| [movables](reference/movables) | [Doors, windows, hatches, slides and motion styles](../docs/reference/movables/README.md) |
| [plants](reference/plants) | [Plant articulation and shared wind responses](../docs/reference/plants/README.md) |

Corresponding `*-reference-review` directories hold the evidence behind the
documents. Other small bundles preserve the discovery and workflow regressions
specifically cited by the docs. This is a selected archive, not a copy of every
experiment, backup scene, generated diagram or rendered frame.

## Read and play back

Fetch Git LFS content when cloning (`git lfs pull`): GLB, blend and selected
image/video files are LFS-managed. Open an archived blend directly to inspect
its native controls and Actions; save any edits as a new working file. Saved
Blender playback does not need the original MPD paths, but rebuilding/checking
source dependencies needs the relocated paths below. Follow the case's evidence
page for an archived-input reopen command (`--bundle` on catalog checkers).

Archived `REPORT.md`/`CATALOG.md` files describe the original work. Their prose
and code samples can still name original `output/` locations; these are provenance,
not the current location or instructions to overwrite a retained example. The
curated docs provide current commands. Maintained builders remain in `scripts/`;
original LDraw geometry/shadow libraries still come from the configured library.

## Reuse a saved plan in this checkout

Never edit an archived source manifest merely to change workstations. Create a
new working plan with only its source/dependency filenames relocated; hashes,
coordinates, occurrence IDs and motion are preserved:

```sh
.venv/bin/python scripts/reference_assets.py plan \
  examples/reference/movables/S01_house_door/plan.json \
  --output output/door-study/plan.json
./ldraw-mecha validate output/door-study/plan.json
./ldraw-mecha rig output/door-study/plan.json \
  --glb examples/reference/movables/S01_house_door/study/model.glb \
  --save output/door-study/rigged.blend --report output/door-study/check.json
```

The relocation refuses missing or hash-mismatched sources and existing output
files. It resolves archived generated MPDs under `examples/reference/` and
original model data under `data/`, never falls back to a stale working copy.
For Python review code, `scripts/reference_assets.load_plan(path)` performs the
same relocation in memory. This is a portability helper, not a new motion format.
If the source selection/geometry changes, prepare and bind a new source normally.

## Add future references

1. Work and verify under `output/NEW_CASE`, following the
   [curation guide](../docs/reference/curation.md). Select the minimal inputs,
   evidence, scripts and playback assets needed to support and reuse the result.
2. Add the bundle's explicit file patterns to `reference/selection.json`, then run
   `.venv/bin/python scripts/reference_assets.py copy NEW_CASE`. Include its
   review bundle separately when applicable. This copies files, checks existing
   hashes and refuses to overwrite a changed snapshot. Earlier output directories
   do not need to exist when a new bundle is selected explicitly.
3. Link the documentation to the retained copies. Keep new runs under `output/`.
   If copied scripts need path adaptations, record the adaptation and new archived
   hash in the manifest while preserving `source_sha256`. Keep the original script
   in its working location unchanged. A materially changed result gets a new
   versioned bundle and a fresh review of its claims.
4. Run `.venv/bin/python scripts/reference_assets.py check`. It validates hashes,
   local document links, source dependencies and rejects links into `output/`.
   Check that every added artifact is eligible for Git tracking and that LFS
   objects are included with the change. Commit examples and docs together.

`build_examples.py` remains the separate executable baseline-example generator;
its newly generated results belong in `output/`, not in this archive.

## Verification of the archive

The [2026-10-12 portability review](reference/reference-portability/verification.json)
ran all seven source reviews in a separate checkout with no original working
artifacts copied and Python access to the original `output/` blocked. Six saved
Blender bundles passed background reopen checks there. A relocated door plan
also passed a fresh build, reopen and lifecycle check. The detailed reports are
retained beside that summary. The 200 relevant Python tests passed, as did the
two wind code examples and all seven new Mermaid renders.

These checks establish reproducibility of the retained definitions and sampled
motion. They do not replace the individual references' clearance qualifications
or establish physical feasibility.
