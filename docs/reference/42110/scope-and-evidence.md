# Scope, evidence and provenance

The user selected this bodywork-hidden Defender because its animation looked
convincing. These references document the implementation behind that result.
They support reuse of the checked relationships and expose approximations that
visual inspection alone can miss.

## What was reviewed

- [Source model](../../../data/models-annotated/42110-1.mpd), by Philippe Hurbain,
  selecting `42110 - main.ldr`.
- [Saved plan](../../../output/42110/plan.json), [rig builder](../../../scripts/build_defender_rig.py)
  and [animation script](../../../scripts/blender/animate_defender.py).
- [Bounded connector evidence](../../../output/42110/evidence/contacts-mechanical.json):
  3,894 contact records over 1,538 selected parts. Contacts inform grouping;
  their existence does not by itself prove a rigid lock.
- Saved numerical reports, lifecycle/reopen reports and rendered previews.
  The old generated diagrams were excluded.

The curation review is dated **2026-10-05**. It preserves the selected rig and
its animation. No fresh Blender rebuild, reopen or clearance run was performed
during curation; Blender results below are retained reports from the original run.

Documentation checks passed: all 14 Mermaid blocks rendered, all 72 local links
resolved, and 146 occurrence references matched the source manifest (including
explicit assembly prefixes). The nine tests in `tests/test_defender_rig.py` passed.
The two gearbox flowcharts were also inspected as rendered images for readability.

| Check | Result | What it establishes |
| --- | --- | --- |
| Plan validation against source | Pass; 91 bodies, 301 moving occurrences, 194 signals | Valid identities, motion definitions and plan structure |
| Rebuild definitions in memory | Controls, signals, bodies, anchors and checks exactly match the saved plan | The inspected builder reproduces the saved motion definition |
| Dedicated drivetrain verifier | 37 gear meshes across 16 engaged direction/range/gear combinations; clutch checks pass | Recorded incremental gear/carrier/lock relationships agree with the evaluated motion |
| Nonzero asymmetric poses | Forward and reverse, independent differential splits, steering and winch | Both tie-rod distance checks pass; maximum sampled error below 4e-7 LDU |
| Neutral samples | Direction, range and between-detent cases evaluated | Which branches stop propagating in the implemented equations |
| Animation timeline | 696 frames at 24 fps; 24 state changes; continuity check passes | No joint step exceeds the script's 0.8 rad/frame or 6 LDU/frame limits |
| Existing Blender/reopen/lifecycle reports | Passing reports retained | Evaluated transforms and saved-scene lifecycle matched the plan within the reported tolerances |
| Existing clearance samples | Surface crossings reported | This is **not** a collision-free reference |

The dedicated gear checker tests small angular increments, including
carrier-relative differential motion. It does not establish the correct absolute
tooth phase. The timeline check does not establish smooth subframe motion,
synchronization, forces or clutch engagement under load.

Fresh review artifacts: [review.json](../../../output/42110-reference-review/review.json)
and [reproduction script](../../../output/42110-reference-review/review.py).
Run the latter from the repository root with `.venv/bin/python`. The script
evaluates existing definitions in memory and writes its report under `output/`.

## Retained evidence

| Evidence | Artifact |
| --- | --- |
| Original drivetrain checks | [kinematics.json](../../../output/42110/kinematics.json) |
| Plan/control sweep | [sweep.json](../../../output/42110/sweep.json) |
| Blender transform verification | [blender-check.json](../../../output/42110/blender-check.json) |
| Saved rig reopened | [reopen-check.json](../../../output/42110/reopen-check.json) |
| Remove/rebuild lifecycle | [lifecycle.json](../../../output/42110/lifecycle.json) |
| Animation verification | [animation-check.json](../../../output/42110/animation-check.json) |
| Saved animation reopened | [animated-reopen-check.json](../../../output/42110/animated-reopen-check.json) |
| General clearance samples | [clearance.json](../../../output/42110/clearance.json) |
| Steering clearance samples | [clearance-steering.json](../../../output/42110/clearance-steering.json) |
| Whole-model context | [rest preview](../../../output/42110/preview-rest.png) |
| Bodywork visibility selection | [bodywork.json](../../../output/42110/bodywork.json) |

Saved Blender comparisons used a 0.01 LDU transform tolerance. Reported maximum
moving/static matrix errors are approximately 0.00363/0.00403 respectively;
those comparisons check the adapter's agreement with the plan. They cannot
establish that the plan's mechanical assumptions are correct.

Clearance samples include clutch/fork, selector/bracket, tie-rod/wishbone,
steering-cross/axle, spindle/bearing and winch-pawl crossings. Classification as
intentional contact, source overlap or actual interference requires examining
the particular surfaces and pose. The reference does not dismiss them collectively.

## Mechanisms that this rig does not demonstrate

| Subsystem | Saved treatment | Missing work before it can become an animated reference |
| --- | --- | --- |
| Suspension | Wishbones, springs and suspension frames stay at source height | Travel, shock geometry, moving hub/shaft interfaces and loop closure |
| Winch ratchet | Pawl `0/113` stays fixed beside rotating ratchet `0/111` | Pawl lift/contact, one-way engagement and release |
| Winch rope and hook | Rope `0/103` and hook `0/98` remain static | Winding, payout, attachment and changing free length |
| Other flexible elements | Hoses and bands retain source geometry | Deformation and any associated tension/contact assumptions |
| Body openings | Hidden bodywork is outside the demonstrated motion | Hinges, travel, parent interfaces and clearance |
| Supports and brackets | Fixed surroundings for the moving assemblies | These are context, not separate moving mechanisms |

These omissions do not prevent using the completed gear, shaft and linkage
examples. They do prevent treating this vehicle as proof that every mechanism
has been animated. No subsystem document is provided as a completed suspension
or ratchet example.

## Corrections to older descriptions

The diagrams and text follow the equations and checks where older prose differs.

1. **Hub rotation is approximate.** The wheel signals use
   `±0.978102966480559 * halfshaft_angle`, from an axis projection. A 2*pi
   equal-side input gives a wheel angle of 6.145602 rad, not 2*pi. This is not an
   exact constant-velocity coupling and should not be copied as one.
2. **The winch has two checked bevel meshes connecting three rotating bodies.**
   An earlier description counted three meshes.
3. **The two internal propshaft fork corrections are approximately 0.0117° and
   0.0191°.** “Within 0.01°” was too tight a description. The builder explicitly
   corrects small source rounding before using the phased joint geometry.
4. **Forward engine ratios are negative about +ZC; reverse is positive.**
   Some older summaries listed only magnitudes. These are ratios to the
   `drive` parameter, not exact road-wheel angles given the hub approximation.
5. **Selector and engine cam motion are assumed profiles.** Checked gearbox
   ratios and rendered followers do not establish continuous surface contact.

## Stable provenance

These hashes identify the version reviewed. Output artifacts are local generated
files and may be absent in another checkout; keep the selected output bundle
with this documentation when sharing its evidence.

| Item | SHA-256 or semantic digest |
| --- | --- |
| LDraw source SHA-256 | `b27fb06903785d25418371314af7aec01ffe4b5df3b0154a4a1ea7accb0267dc` |
| Plan semantic digest | `956fe45dcd5234f825660302be0da06a3294c9665eef3fac3b78422b52e74f16` |
| Plan file SHA-256 | `5cdaaa8ec9715c6b50a3ecd41a2f8c6900018bb6a3ca1bdc6c3fe4c54b999805` |
| Builder SHA-256 | `347314aea903abd6a3f8856e947d8b2a02ec6f0672cdf3bff1241bdf15bd7295` |
| Animation script SHA-256 | `bb7c9e4a8032b75ba9969ce94ca694027952a6c89c3d26675fb782481474d1b8` |

Full reviewed-file hashes are in `review.json`. Updating a builder or plan does
not automatically update these hand-curated references: compare the changed
relationships and recheck the affected examples before retaining the same claims.

[Back to subsystem index](README.md)
