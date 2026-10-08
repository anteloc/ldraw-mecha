# Wind responses for plants and other objects

Part of the [plants/wind reference](README.md); [evidence](scope-and-evidence.md).
The model separates a [shared field](wind-field.md) from three joint responses:
an oscillator, a spinning rotor and a direction-seeking vane. This is reusable
for suitable shutters, signs, flags represented as rigid panels, pendants or
rotors after establishing their real degrees of freedom. Those extensions are
applications of the method, not additional verified assemblies in this bundle.

## Geometry chooses the sign of the forcing

For a directed unit axis `a`, origin `o` and a representative tip point `p`,
compute `v = a × (p-o)`. The builder stores the **normalized** horizontal
projection `swing=(v.x,v.z)/|v|`, or zero when the lever vanishes. This encodes
motion direction, not a physical lever arm or surface area. The lever length
is recorded separately and does not automatically scale wind torque.

For an oscillator's default drag drive, with `s=√(U²+V²)`:

```text
raw_drive = s * (U*swing_x + V*swing_z) + lift*s²
drive = gain * sign(raw_drive) * max(abs(raw_drive) - threshold, 0)
theta'' + 2*zeta*omega*theta' + omega²*theta = omega²*drive
omega = 2*pi*f_hz / 24                  # derivatives are per frame
```

A geometry-derived sign makes an upwind frond fold upward and the opposite
frond flatten under the same +X wind. Blindly applying the same positive angle
to both would be wrong. Flat leaves with little horizontal tip motion use an
explicit `lift` term; asymmetric axial twist can use `drive="speed"` with
`asym*s² + asym_v*s*V`. Those gains are authored visual choices, not measured
lift coefficients. A `lag` delays the oscillator's driving field in frames.

`build_plants.wind_geometry()` measures these directions. `roster_check()`
allows joint-X error up to 15 LDU and swing-component error up to 0.08; passing
it means consistency within those tolerances, not exact equality.

## Three response families

| Recipe | Implemented equation | Example and limitation |
| --- | --- | --- |
| `osc(f,zeta,gain,x,...)` | Damped second-order equation above | Trunks, branches and pendants; rest-frame projection and independent joints, not a multibody solve |
| `spin(k,u0,damping,x,...)` | `omega' = k*max(s-u0,0) - damping*omega`, integrate angle | P06 daisies; artistic rotor response, no blade-pitch proof |
| `vane(stiffness,damping,heading,x,...)` | `theta'' = -K*s²*sin(heading+theta-atan2(V,U)) - damping*theta'` | P19 leaves on vertical bars; seeks a downwind heading within declared travel |

Oscillator/vane results add optional flutter, then use a sign-dependent `tanh`
soft limit to approach the positive/negative travel bounds. Flutter amplitude
scales with `s²`; its frequencies snap to harmonics of the four-second breeze.
This gives repeatable bounded animation. It does not solve an impact against
a hard stop, or update drag as a leaf folds into a new orientation.

Breeze oscillators use an FFT of sampled periodic forcing multiplied by the
linear transfer function. That is a steady response for the sampled linear
system; it is not the solution of a full plant. Vane breeze uses **ten warm-up
periods of RK4**, then repeats one period; it is not an exact linear frequency
solution. Rotor breeze speed is rescaled to a chosen number of symmetry steps
per period. Gusty/storm responses use RK4 with eight substeps per frame, plus
authored endpoint adjustments. Their final fades to rest are editing choices.

Rotor endpoints are quantized to `2*pi/symmetry`; this only preserves apparent
pose when geometry, colours and markings actually have that symmetry. Rotor
angles can advance across a loop even while their visible pose repeats.

## Apply it to other objects

1. Establish the moving group, support, axis, rest pose and allowed travel. A
   latched shutter or a two-point rigid mounting must not acquire a free hinge
   merely because the wind is strong. Use [movable joints](../movables/hinges-and-sliders.md).
2. Measure the tip's swing and the joint's X in the field frame. Pick `osc`
   for deflect/settle, `spin` for a rotor, `vane` for heading alignment.
3. Choose response frequency/damping/gain and limits, explicitly noting any
   assumed restoring tendency. `osc` returns toward zero even if a real free
   hinge has no spring or gravity component that would do that.
4. Generate/bake the response, then verify its controller values, joint
   transforms, phase delay and clearance against the object's actual context.

Source-only example for an **illustrative** panel whose measured tip moves
toward +X under positive rotation (not a verified new door rig):

```python
import sys
sys.path.insert(0, "scripts")
import wind_clips as wc

spec = wc.control("radian", 0, 1.2, "+ opens the panel downwind",
                  wc.osc(f=0.7, zeta=0.5, gain=0.6, x=0,
                         swing=(1, 0), threshold=0.02))
values = wc.respond(spec, "B", slot_x=120)  # 240 samples, frame 1 starts at rest
assert len(values) == 240 and all(0 <= v <= 1.2 for v in values)
```

Key these values on the corresponding measured plan control, using LINEAR
interpolation at each integer frame, as `animate_plants.build_action()` does.
The wind response is animation input; it does not replace the joint equations.
For cloth-like flags, continuous material bending, or collisions that should
change the motion, this rigid-joint approximation needs additional modelling.

## Reuse must preserve timing and target limits

Every clip is one Action with a `plant_controller` slot; all controls get 240
keys, plus metadata naming the regime, recipes, joint kinds and spatial delay.
Reusing an Action requires compatible channel meanings and geometry. Blender's
target property limits can clamp keyed values: the tested transfer from
`P02_swordleaf_palm.storm` to P13's fern clamps five of twenty-two sampled
frames. That is a documented altered response, not exact retargeting.

Test a new response with nonzero/asymmetric motion and strong gusts. Repeat
the 96-frame breeze phase check; compare loop endpoints modulo rotor symmetry
and inspect seam velocities if editing the curves. Reopen the saved blend and
check small angles too: this case exposed identity keys on driver F-curves
snapping tiny outputs toward zero. The adapter now removes those keys; old
saved rigs may still contain them. The plant reopen checker tests key-free
pass-through drivers as well as matrix agreement.
