# Movables: scope and evidence

Reviewed **2026-10-08**, implementation commit `036c31e`. The
[archived bundle](../../../examples/reference/movables) preserves twenty mock
scenarios, sixty clips, plans/identity maps, bound GLBs, the saved scene and
selected preview sheets. The [original report](../../../examples/reference/movables/REPORT.md)
is retained as historical evidence; the axis/sign correction in
[dependent motion](dependent-motion.md) takes precedence over its shorthand.

Fresh [source review](../../../examples/reference/movables-reference-review/review.json)
reproduces the builder's motion fields for all twenty cases, compares part
references and matrices with saved manifests, checks source hashes, evaluates
asymmetric controls and compares all sixty exported clip series with their
Python definitions. It runs through [review_catalog.py](../../../scripts/review_catalog.py).
It reads original clearance evidence rather than rerunning it.

The relevant movable/plant tests pass together: **195 tests** (93 movables,
102 plants). The fresh [Blender reopen check](../../../examples/reference/movables-reference-review/reopen-check.json)
passes in **5.2.2 LTS** with auto-run disabled: twenty rigs, sixty clip Actions,
21 scenes, eleven timeline samples per rig, three scene-comparison frames per
scenario and one transferred Action. Embedded plan comparison excludes prose
`notes`; sampled values/transforms do not prove physical feasibility. Existing
lifecycle reports cover S13, S16 and S19. The crane preview sheet was inspected
during this curation; this is not a frame-by-frame visual review of all clips.

## Clearance and approximation boundaries

The [saved clearance summary](../../../examples/reference/movables/clearance-summary.json)
reports no new sampled crossings in sixteen scenarios. S02 panes, S04 gate/post
and S12 canopy/hull have reported vertex depths up to about 0.12 LDU near
closure. S13's scaled spring reaches about 1.6 LDU. Depths sample vertices of
reported pairs; they are not exact maximum penetration depths over continuous
motion. Rest-contact and same-body pairs are excluded. A larger surface shrink
is unreliable for thin frames/shells and must not turn a crossing into a claim
of safety. Forces, friction, stops and impact dynamics are not simulated.

Rigid roller shutters, unsupported connector pairs and unmeasured candidates
were excluded explicitly rather than assigned invented motion. Connector
workarounds, official-placement residuals and authored travel belong to the
individual scenario. Remeasure the target instead of copying a part number's
range as a universal limit.

## Recheck the preserved example

```sh
.venv/bin/python scripts/review_catalog.py movables \
  --report output/new-movables-review/review.json
"$BLENDER_BIN" --background examples/reference/movables/movables.blend \
  --disable-autoexec --python-exit-code 1 \
  --python scripts/blender/check_movables_reopen.py -- \
  --bundle examples/reference/movables \
  --report output/new-movables-review/reopen-check.json
```

These commands read the archive and write fresh evidence under `output/`.
For a new rig from a saved plan, use the path-relocation command in the
[example archive guide](../../../examples/README.md). Historical plans and
reports keep their original path strings and hashes; snapshots are not silently
rewritten to match a new workstation.

The [archive portability review](../../../examples/reference/reference-portability/verification.json)
repeated source/reopen checks on **2026-10-12** without the working bundle and
built, reopened and lifecycle-tested S01 from its relocated plan. All four
Mermaid blocks in this reference rendered successfully.
