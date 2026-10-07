# Minifig scope and evidence

Reviewed **2026-10-07**, from [output/minifigs](../../../output/minifigs) and the
implementation in commit `a31034a`. The ten generated standalone figures share
a seven-joint architecture; themed parts and clips differ. They were constructed
from separate library parts, not extracted from one existing set. The selected
MPDs, plans, GLBs and saved blend were left untouched during curation.

## Sources and checks

| Artifact | Use |
| --- | --- |
| [build_minifigs.py](../../../scripts/build_minifigs.py) | Roster, taxonomy constants, connector placement, grip choices, source writer and plan author |
| [minifig_clips.py](../../../scripts/minifig_clips.py) | Thirteen channel conventions, sparse keys/easing, pure evaluator, whole-figure transform |
| [animate_minifigs.py](../../../scripts/blender/animate_minifigs.py) | Imported roots, controller properties, Action slots, NLA tracks and scene checks |
| [REPORT.md](../../../output/minifigs/REPORT.md) and [CATALOG.md](../../../output/minifigs/CATALOG.md) | Original implementation notes, reproduction commands and clip compatibility matrix |
| Per-figure `source/parts.json`, `plan.json`, `kinematics.json` | Occurrence roles, measured axes, semantic sign tests and contact evidence |
| Per-figure `clearance*.json`, `lifecycle.json` | Original sampled crossing and lifecycle evidence |

Fresh [review.py](../../../output/minifigs-reference-review/review.py) and its
[report](../../../output/minifigs-reference-review/review.json) check all ten
source hashes, current builder versus saved motion fields, nonzero/asymmetric
evaluation, semantic sign choices and all thirty exported baked clips. File
hashes bind that report to the source scripts, plans and selected blend.

The relevant Python tests passed **62/62** during this review. They cover
connector coincidence, reference placement, mirrored/asymmetric movement,
clip interpolation, neutral endpoints, channel limits and staging transforms.
Plans have no declared closure checks: a generic plan sweep alone does not
verify these semantics. The dedicated tests and Blender comparisons provide
that evidence.

A fresh background **Blender 5.2.2 LTS** process reopened the selected blend.
The [new reopen report](../../../output/minifigs-reference-review/reopen-check.json)
passes for ten figures at eleven timeline frames each, thirty Actions and one
cross-figure Action transfer at fourteen frames. It checks NLA tracks/slots,
drivers, controller samples, root-relative joint matrices and separate root
staging. Worst joint-matrix error is about **0.000181 LDU**, below the 0.002
tolerance. Embedded plans are compared excluding `notes`; this is not a
byte-for-byte prose comparison. The transfer check compares keys, joint motion
and root translation; it is not a general retargeting or collision test.

The original build report has 230 figure/frame samples. All ten saved lifecycle
reports pass. Those lifecycle and clearance runs were reviewed, not rerun for
this documentation-only curation. Existing overview and seated/get-up previews
were visually inspected. These are sampled observations, not a review of every
rendered frame. Fresh diagrams describe the hierarchy, data flow and seated
clip phases; they are hand-curated views, not executable motion definitions.
All four Mermaid blocks rendered successfully, and the new/updated documents'
local links resolved; see the [documentation check](../../../output/minifigs-reference-review/docs-check.json).

## Boundaries to preserve when reusing

- Only neck, shoulders, wrists and hips are mechanical joints. Torso/hips/back
  items are fixed together; headgear, hand items and flippers follow their bodies.
- Source placements use connector conventions. Some accessories lack mated
  contact evidence, and comparison with the 6682 minifig retains a roughly
  1 LDU shoulder/hand offset difference.
- Joint limits are authored choices. Three own-figure clips have known mesh
  crossings; [pose clearance](pose-clearance.md) records them and the exclusions.
- Walking/running can slide feet. Jumps, levitation, swimming and getting up
  are staged motion, with approximate ground heights and no contact dynamics.
  There is no physical ladder, water, pot, hose, pancake or seat in the scene.
- Clip compatibility requires the same channel semantics and fresh geometry
  checks. A transferable Action is not automatically safe with a new accessory.

## Reproduce without overwriting the selected case

From the repository root with its Python environment and LDraw library:

```sh
.venv/bin/pytest -q tests/test_minifigs.py
.venv/bin/python output/minifigs-reference-review/review.py
"$BLENDER_BIN" --background output/minifigs/minifigs.blend --python-exit-code 1 \
  --python scripts/blender/check_minifigs_reopen.py -- \
  --report output/minifigs-reference-review/reopen-check.json
```

Set `BLENDER_BIN` to the installed Blender executable. The review code/reports
are generated artifacts under `output/`; include them when sharing this case.
For a complete rebuild, see the original report. The source/catalog builder and
case clearance script write to their fixed `output/minifigs` paths: use a
separate checkout or deliberately adapt those output paths for another study.
Reprepare source identities after changing parts/placements. Keep the MPD
attribution and each supplied data/library notice rather than assuming all
taxonomy, geometry and shadow metadata share a single licence.
