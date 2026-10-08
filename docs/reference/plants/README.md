# Plants and shared wind-driven animation

Reviewed **2026-10-08**, from the twenty plant cases and sixty clips introduced
in commit `6c1d5c7`. The [preserved bundle](../../../examples/reference/plants)
includes [plants.blend](../../../examples/reference/plants/plants.blend), plans,
source models, clips, evidence, preview sheets and the
[overview video](../../../examples/reference/plants/previews/overview.mp4).

There are **two independent lessons** here: how LEGO plant parts may articulate,
and how a shared wind signal can animate measured joints on plants or other
objects. A wind recipe must not invent a freedom that the object does not have.

| Reference | Use it for |
| --- | --- |
| [Plant joints](plant-joints.md) | Ball-chain trunks, clip/bar leaves, twist joints and qualified bending approximations |
| [Flexible vines](flexible-vines.md) | Splitting official flexible geometry into rigid links; respecting both fixed ends |
| [Shared wind field](wind-field.md) | A coherent gust moving through a scene, with spatial delay and reusable forcing |
| [Wind response and reuse](wind-responses.md) | Oscillators, rotors, vanes, loop construction and adaptation to shutters/signs/other objects |
| [Scope and evidence](scope-and-evidence.md) | Checks, contact coverage, source corrections and approximation limits |

The [catalog](../../../examples/reference/plants/CATALOG.md) lists palms, bamboo,
flowers, grass, reeds, vines, hinged branches, shrubs and leaf vanes. Each plan
declares its body hierarchy. The wind recipes live separately in
[wind_clips.py](../../../scripts/wind_clips.py), whose Python/NumPy calculations
are baked into ordinary Blender Actions. Source construction is in
[build_plants.py](../../../scripts/build_plants.py), presentation in
[animate_plants.py](../../../scripts/blender/animate_plants.py).

In scene `Wind`, twenty controllers `CTRL_plant_xx_*` play three regimes:
**breeze 1–240**, **gusty 257–496**, **storm 513–752**, at 24 fps. The `WIND`
controller shows the field-centre `u`, `v`, `speed` and drives an arrow.
**It is a keyed display, not a live simulator driving all the plants.** Editing
that controller alone does not rebake their Actions. Regenerate responses when
changing wind, placement or response parameters.

All parts remain rigid except the appearance of bending approximated by small
relative rotations. Twenty-five joints are explicitly `flex_approx`; those
must not be presented as real LEGO hinges. Wind response is an artistic model,
not measured airflow, joint torque, friction or structural dynamics.
