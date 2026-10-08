# 10265 discovery regression

Source analysis only. Existing 10265-v2 artifacts and Blender scenes were not modified.

- [Comparison](comparison.json): 29 → 921 contact records across 1441 parts;
  straight axles with axle-hole evidence 0/25 → 25/25 (pins/joiners excluded).
- [Raw contacts](contacts-raw.json) and [corrected contacts](contacts-normalized.json).
- [New study](study/plan.json) and [mechanism diagrams](study/diagrams/README.md).
- [Adjuster candidate diagram](ride-height-candidate.svg): knob → axle → worm → 8T
  → output axle → both liftarm cranks. The crank-to-frame coupling remains unverified.
- [Old study audit](previous-study-audit.json): flags the missing coverage diagnostics.
- [Adopted plan](adopted-plan.json) and [audit](adopted-audit.json): 90 unresolved
  provisional views retained alongside six planned control views.
- [Sweep](adopted-sweep.json) and [asymmetric evaluation](adopted-asymmetric.json):
  existing declared motion still evaluates; these do not prove physical clearance.

Six unsupported bevel gears and three library connector warnings remain explicit.
The diagram was rendered with Mermaid CLI. The pure test suite passes 82 tests.
