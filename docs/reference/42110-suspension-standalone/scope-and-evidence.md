# Scope, evidence and provenance

This review describes the selected **standalone suspension**, not the complete
Defender or a combined suspension/drivetrain rig. Curation date: **2026-10-06**.
The diagrams were reconstructed from the source, motion and evidence rather
than the previous generated pictures.

## Fresh checks

| Check | Result | What it supports |
| --- | --- | --- |
| Source/plan validation | Pass; 259 physical parts, 117 moving occurrences | Valid identities and motion structure |
| Measured full-model builder reproduced | Controls, signals, bodies, anchors and checks exactly match | The saved suspension derives from the inspected geometry |
| Standalone remapping reproduced | Same five fields match exactly | The extract retains the full suspension's motion with new instance IDs |
| Extraction identity/colour/frame comparison | 259-part bijection; maximum matrix error about 5.7e-14 | No unintended repositioning during extraction |
| Control sweep | 49 values per control, 196 cases total; all 48 checks pass | Maximum declared-distance error about 0.003842 LDU |
| Combined poses | Rest, full bump and two asymmetric patterns pass | Independent corners and mixed travel agree with the full-model plan |
| Spring endpoints | Maximum sampled discrepancy below 1.4e-13 LDU | Fixed seats follow cylinders and free ends follow rods |
| Full animation timeline | 612 frames; every frame passes closure and continuity checks | The authored control sequence stays within the tested kinematic limits |
| Python tests | 21 passed across suspension and standalone modules | Includes shortcut splitting, extraction reproduction, asymmetric motion and animation |
| Saved animation reopened in background Blender | Blender 5.2.2 LTS; embedded motion matches | The selected file contains the documented plan |
| Fresh Blender transform samples | Four combined poses pass at 0.01 LDU tolerance | Maximum moving error 0.002091, static error 0.0000306, closure error 0.003873 LDU |
| Saved animation controls | Seven sampled frames match the source timeline within 1e-5 LDU | Confirms the inspected action's values at those frames |

The source-only continuity maxima are approximately 0.03141 rad/frame for
rotation, 1.23889 LDU/frame for slides and 0.02816/frame for spring scale.
These are sampled changes, not force or acceleration bounds.

No selected MPD, plan or Blender file was modified. Blender verification used
a separate process and did not save the opened animation.

## Retained and fresh evidence

| Artifact | Purpose |
| --- | --- |
| [Fresh review](../../../examples/reference/42110-suspension-standalone-reference-review/review.json) | Measured corner roles, geometry, samples, reconstruction and hashes |
| [Source review script](../../../examples/reference/42110-suspension-standalone-reference-review/review.py) | Reproduce the source-only curation checks |
| [Fresh Blender check](../../../examples/reference/42110-suspension-standalone-reference-review/blender-check.json) | Reopened action and evaluated transforms |
| [Blender inspection script](../../../examples/reference/42110-suspension-standalone-reference-review/inspect_blend.py) | Read-only saved-scene review |
| [ID map](../../../examples/reference/42110-suspension-standalone/source/idmap.json) and [selection](../../../examples/reference/42110-suspension-standalone/keep.json) | Original occurrences, extracted IDs and retained roles |
| [Original Blender check](../../../examples/reference/42110-suspension-standalone/blender-check.json) | Fourteen sampled poses |
| [Rig reopen](../../../examples/reference/42110-suspension-standalone/reopen-check.json) and [animation reopen](../../../examples/reference/42110-suspension-standalone/animated-reopen-check.json) | Saved-scene persistence |
| [Lifecycle report](../../../examples/reference/42110-suspension-standalone/lifecycle.json) | Restore/rebuild, isolated copies, defaults and clamping |
| [Original animation check](../../../examples/reference/42110-suspension-standalone/animation-check.json) | Every-frame closure and 17 Blender frame comparisons |
| [Standalone clearance](../../../examples/reference/42110-suspension-standalone/clearance.json) | Sampled crossings against retained geometry |
| [Full-model stop sweep](../../../examples/reference/42110-suspension/stop-sweep.json) | Front lower-arm contact limit evidence |
| [Full-model measured geometry](../../../examples/reference/42110-suspension/geometry.json) | Original pivot, shock and grouping measurements |

Run `.venv/bin/python examples/reference/42110-suspension-standalone-reference-review/review.py`
from the repository root to reproduce the source review. It requires the retained
study inputs, configured LDraw library and local parts database.

## Travel limits and clearance coverage

The front limit is **30.5 LDU wheel rise**. A named-pair sweep at 0.25 LDU
increments reported its first tile/liftarm crossing at **31.0 LDU**, using a
0.4 LDU mesh shrink. This is an evidence-based animation limit, not an exact
unshrunk contact threshold. Whether the tile cluster is an intended bump stop
was not established.

Rear travel is limited to **40.5 LDU**, slightly below the calculated 40.749 LDU
that would compress a shock by 16 LDU. The 16 LDU choice leaves margin within
the reported 20 LDU stroke; actual compression at the saved rear limit is about
15.8983 LDU.

The retained standalone clearance report samples nine positions for each of the
four controls, with other controls at their defaults. It reports no new surface
crossings, using a 0.4 LDU shrink and 0.05 LDU touching tolerance, excluding
43 rest pairs and 16 touching pairs in addition to same-body comparisons.

That report tests only the retained frame and components. It does not cover
all simultaneous corner combinations, continuous collision detection, containment
or interaction with omitted vehicle parts. The complete-car study has separate
clearance evidence; neither report establishes force-supported physical motion.
No fresh clearance run was performed for documentation.

## Qualifications discovered or clarified

| Topic | What this example actually does |
| --- | --- |
| Coupler geometry | Inner attachments are 80 LDU from the wishbone pivots; outer ball joints are 100 LDU out. Older notes describing every link as 100 LDU are too broad. |
| Shock free length | Measured 110.028 LDU in the rounded source, nominally 110. The equations retain the measured value. |
| Ball/socket fit | Front arm metadata differ by about 2.01 LDU; one rear toe link per side differs by about 1.99 LDU. The plan closes its chosen cup/socket points, not an independently solved surface contact. |
| Half-shaft fit | The shaft vector differs from the arm vector by about 0.00975 LDU. Declared distance errors stay within 0.02 LDU; exact endpoint coincidence is not established. |
| Spring mesh | Axial scaling preserves the selected endpoints but also changes the mesh's axial wire dimensions. |
| Fixed mounts | The front inner tie-rod pins and cut Cardan inputs rely on prescribed boundary locations; some visible supports are absent. |
| Zero camber/toe change | A result of this reviewed parallelogram construction, not a property to impose on every suspension. |
| Physics | No spring rates, damping, vehicle mass, tyre/road contact or weight transfer. |
| Other mechanisms | Steering, wheel spin and drivetrain motion require additional coupled kinematics and body ownership decisions. |

These qualifications identify where adaptation needs new measurements or a
different solver. The demonstrated geometry remains a useful independent-corner
and telescoping-shock example.

## Provenance

All six Mermaid diagrams rendered successfully. Documentation checks resolved
46 local links and 92 occurrence references (including explicitly labelled old
IDs). The wishbone, shock and animation renders were also inspected for readability.

The source derives from Philippe Hurbain's 42110 MPD, retaining its attribution
and CCAL 2.0 license information. The extraction and shock-splitting scripts
record their derivations.

| Item | SHA-256 or semantic digest |
| --- | --- |
| Standalone source SHA-256 | `30c62143630438e51b3a6bfa83b78fffc4f8fe06b6b6898b3904944d5f33fc16` |
| Plan semantic digest | `c082e30bbfdea1b183324510cd60c5f29a3318028d88f4b5219340ab208870c6` |
| Plan file SHA-256 | `bf7d31a66b08333299c53c1f3543edbb5e0405f87c40be4514c652285c47da61` |
| ID map SHA-256 | `f6b6c8829c30075e8b2e3522ec215529deadcfb88c396f7d5ea6752a054e7800` |
| Measured builder SHA-256 | `ccfb433ae6c894381c2f484430721754fc65acb23948f275785a96ddba9fd5c0` |
| Selected animated blend SHA-256 | `de2c5d398b79e882350a004e75bfcbb0eeee12754cf69b3aeebc4e9367955904` |

The [example archive](../../../examples/README.md) retains the selected evidence,
derived source files and playback assets alongside these references.
A changed source, plan or builder requires a review of the affected measurements
and claims; the hand-curated diagrams do not update themselves.

[Back to suspension index](README.md)
