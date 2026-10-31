# Supported 8:24 gear drive

An original 23-part starter for building a mechanism before animating it.
The [MPD](gear-drive.mpd) contains a fixed base/frame and two complete keyed
shafts. Four round Technic-brick holes support them. Inner half bushes locate
the gears; outer full bushes retain the shafts. The pitch centres are 40 LDU
apart, 62 LDU above the base, with tooth midplanes at Z = 0.

The 24-tooth shaft starts at 7.5 degrees to phase the teeth against the 8-tooth
gear. That rotation applies to its axle and all bushes as well. One control
drives the input; the output turns oppositely at one third of its speed.
No part stretches and the fixed bearings do not spin.

```sh
export LDRAW_DIR=/path/to/ldraw
.venv/bin/python scripts/gear_drive.py --output output/gear-drive
./ldraw-mecha check output/gear-drive --require-reviewed --require-constrained --set drive=0.731
./ldraw-mecha rig output/gear-drive --require-constrained --animate --reopen
```

The preparation script copies the source, creates a fresh manifest, writes the
ordinary plan, checks 97 drive positions plus an off-grid input, and converts
the bound GLB once. Choose a new directory when rebuilding. `--no-glb` performs
only source/plan preparation. Set `BLENDER_BIN` or pass `--blender` if necessary.

Read the [authoring guide](../../docs/mechanisms.md) before adapting it.
[scripts/gear_drive.py](../../scripts/gear_drive.py) is the motion recipe;
the construction generator and the same MPD are retained in LDraw Nova at
`examples/technic-studies/gear-drive/`. Neither project needs the other at
runtime. Regenerate both source copies together when changing the design.

These are nominal geometry and kinematic checks. They do not certify real
material fit, load capacity, friction or backlash. The bearing/retaining-bush
contacts are intentional. Generated animation, renders and reports belong in
`output/`; this maintained source and recipe remain usable without it.
See [validation](validation.md) for the inspected revision, measured results
and reproduction commands for the additional clearance diagnostics.
