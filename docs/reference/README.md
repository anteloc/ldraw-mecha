# Curated mechanism references

Start with a mechanism that matches the target assembly, then read that page's
identity map, motion relationships and qualifications. These references were
recovered from working rigs selected by the user. They are documentation for
reuse; agents do not have to generate their own reference diagrams to use them.

| Mechanism | Example |
| --- | --- |
| Crankshaft, connecting rods and pistons | [42083 W16 linkage](42083-w16/slider-crank.md) |
| Geared multiple crankshafts | [42083 W16 gear train](42083-w16/gear-train.md) |
| Paired rods and mirrored cylinder banks | [Central eight](42083-w16/central-eight.md), [lower banks](42083-w16/lower-banks.md) |
| Cam-driven piston followers | [42110 Defender engine](42110/engine.md) |
| Axle and centre differentials | [Front axle](42110/front-axle.md), [rear axle](42110/rear-axle.md), [centre differential](42110/centre-differential.md) |
| Direction/range clutches and sequential gearbox | [Range/direction](42110/range-direction-gearbox.md), [four-speed](42110/sequential-gearbox.md) |
| Paired Cardan joints | [Defender internal propshafts](42110/internal-propshafts.md) |
| Rack steering and closed tie rods | [Defender steering](42110/steering.md) |
| Bevel-driven drum | [Defender winch](42110/winch.md) |
| Continuous shaft angles through ratio changes | [Shift animation](42110/shift-animation.md) |
| Independent double-wishbone suspension | [Wishbones and guide links](42110-suspension-standalone/wishbones-and-links.md) |
| Articulating half-shafts without drive | [Suspension half-shafts](42110-suspension-standalone/halfshafts.md) |
| Telescoping shocks and coil compression | [Shock absorbers](42110-suspension-standalone/shocks.md) |
| Extracting mechanisms with fixed interfaces | [Suspension extraction](42110-suspension-standalone/extraction-and-mounts.md) |
| Four-corner travel demonstrations | [Suspension animation](42110-suspension-standalone/animation.md) |

Case indexes: [42110 Defender](42110/README.md), [42083 W16](42083-w16/README.md),
[standalone suspension](42110-suspension-standalone/README.md).

Each page describes a particular implementation, including approximations and
unimplemented interfaces. Visual acceptance selects a useful candidate; numerical
and geometric evidence determine which relationships are suitable to reuse.
Remeasure the new model and test nonzero inputs. Output evidence is kept under
`output/` and may need to accompany the documents when sharing them.
