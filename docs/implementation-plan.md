# Mechanical toolkit implementation plan

The deliverable is an agent CLI and Python library that turn LDraw source evidence
into a checked motion plan, then materialize that same plan in Blender. Source
analysis must work without Blender. Interactive controls must work after saving
and reopening the blend, without a Python frame handler or external service.

## Findings from the supplied resources

- `mpd2glb` preserves assembly/part `fileName`, `colorCode`, descriptions and
  hierarchy. Its root rotates by pi about X and scales LDU by 0.0004. Blender
  further changes the coordinate basis. Object display names are not identities.
- `ldraw-nova/ldraw-agent` and `instructions.md` demonstrate bounded inspection,
  source attribution, exact section selection and explicit coverage reporting.
  Reuse pyldraw3 for parsing and connector expansion; don't copy a whole builder.
- Shadow connectors locate possible joints, but a snapped axle can be a bearing
  or a rigid coupling. Descriptions and semantic search do not prove a mechanism.
- Jev's live availability check succeeded. A bounded semantic search located
  the 928 cargo hatch as a useful second study. Keep offline search available.
- Read-only inspection of the open Blender MCP scene found Blender 5.2.2 LTS,
  4,530 objects, `CTRL_42000` with steering/speed/four wheel controls and 22 valid
  drivers. The supplied rig uses rigid groups, frame/pivot empties, analytic
  steering and slider-crank equations, differential relations and rod constraints.

## Tools and boundaries

1. `inspect`: parse MPD/LDR; report source hashes, repeated occurrence identities,
   physical part boundaries, transforms, descriptions, mechanism candidates and
   unresolved evidence. `connectors` exposes pyldraw3/shadow feature frames.
2. `search`: a small Jev adapter and explicit offline keyword search over the
   supplied database. Return exact source/section/part references for follow-up.
3. `plan`: draft or studied recipe; JSON declares controls, rigid bodies, joint
   axes/pivots, dependency-ordered motion signals and rod endpoints. Agents can
   edit plans without editing Blender scripts.
4. `validate` / `evaluate`: source freshness, identities, ownership, dependency
   cycles, numeric domains, joint frames and reproducible control sweeps.
5. `convert`: use the existing exporter; bind source occurrence IDs into GLB
   extras after strict hierarchy/transform matching. Fail ambiguous bindings.
6. Blender adapter: preflight plan and metadata; create named controllers,
   pivots, drivers and constraints; preserve rest transforms; support scoped
   removal/rebuild. Save and reopen verification is required.

The plan/equation layer uses the standard library so Blender can import it.
Analysis uses pinned pyldraw3. Filesystem configuration and CLI processes work
headlessly and can move to a Linux container; no sibling checkout is required.

## Progressive acceptance

1. **106 car**: independently controlled roof, doors and rigid wheel/tyre groups;
   verify hinge axes, unchanged stationary parts and round-trip rest transforms.
2. **928 spaceship**: nested/repeated hatch groups, exact instance selection and
   dependency-closed standalone submodel conversion. Check parent context.
3. **42000 Technic car**: port the studied steering, differential and V8 motion
   into a reusable plan. Compare numeric and evaluated Blender results with the
   supplied rig, including unequal rear-wheel inputs and constant-length rods.

Acceptance distinguishes implemented kinematic behavior from general automatic
mechanism inference and collision/physical proof. Unsupported mechanisms remain
explicit findings; they must never silently become invented joints. Generic
arbitrary mechanisms, elastic deformation and full dynamics are future scope.
