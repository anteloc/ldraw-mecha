"""Prepare the original supported spur-drive starter using explicit interfaces."""

import argparse
import json
import math
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ldraw_mechanisms import glb, plan  # noqa: E402
from ldraw_mechanisms.recipes import Builder  # noqa: E402
from ldraw_mechanisms.source import Document  # noqa: E402
from ldraw_mechanisms.transmission import mesh, port, shaft  # noqa: E402
from ldraw_mechanisms.workflow import check  # noqa: E402


def motion(manifest):
    """The starter's stable section IDs; source changes require remeasurement."""
    b = Builder(manifest, "gear_drive")
    drive = b.control("drive", -6 * math.pi, 6 * math.pi, "Input shaft angle")
    for name, prefix, bearings in (
        ("input", "1", ("0/5", "0/7")),
        ("output", "2", ("0/6", "0/8")),
    ):
        shaft(
            b.plan,
            name,
            axle=port(prefix + "/0", [0, 0, 0], [1, 0, 0], [-79.5, 79.5]),
            keyed=[
                port(prefix + "/1", [0, 0, 0], [0, 0, 1], [-9.5, 9.5]),
                *[
                    port(prefix + f"/{i}", [0, 0, 0], [0, 0, 1], [-5, 5])
                    for i in (2, 3)
                ],
                *[
                    port(prefix + f"/{i}", [0, 0, 0], [0, 0, 1], [-10, 10])
                    for i in (4, 5)
                ],
            ],
            bearings=[port(i, [0, 10, 0], [0, 0, 1], [-10, 10]) for i in bearings],
            signal=drive if name == "input" else None,
            evidence="Central cross holes on the gear and four bushes share the axle phase. "
            "Two 3700 round holes permit spin. Inner half bushes retain the gear; "
            "outer full bushes at +/-60 retain the axle against rail faces at +/-50.",
        )
    mesh(
        b.plan,
        "input",
        "output",
        gear_a="1/1",
        gear_b="2/1",
        evidence="3647/3648b external spur gears, 8/24 teeth, parallel Z axes, "
        "40-LDU pitch spacing and coincident tooth midplanes. Output shaft starts "
        "at 7.5 degrees for tooth/gap phase; all its keyed parts share that phase.",
    )
    b.plan["connections"] = {}
    b.plan["mechanisms"] = dict(
        transmission=dict(
            label="Supported 8:24 spur reduction",
            parts=[],
            bodies=["input", "output"],
            inputs=["control:drive"],
            outputs=["body:output"],
            notes=[
                "One independent input; two retained shafts and four round bearings."
            ],
            disposition="planned",
            review="Original construction with explicitly selected finite interfaces and coupled motion checks.",
        ),
        frame=dict(
            label="Fixed support frame",
            parts=[f"0/{i}" for i in range(11)],
            bodies=[],
            inputs=[],
            outputs=[],
            notes=["Bonded base, rails and caps."],
            disposition="static",
            review="All eleven support parts remain fixed; bearing holes permit axle rotation.",
        ),
    )
    return b.finish(
        b.plan["notes"]
        + [
            "Model hierarchy deliberately follows the fixed frame and two rigid shafts.",
            "Nominal geometry and kinematic checks only; no claim of load capacity or manufactured fit.",
        ]
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default=str(ROOT / "output/gear-drive"))
    parser.add_argument("--no-glb", action="store_true")
    args = parser.parse_args()
    out = Path(args.output).resolve()
    out.mkdir(parents=True, exist_ok=False)
    source = out / "gear-drive.mpd"
    shutil.copyfile(ROOT / "examples/gear-drive/gear-drive.mpd", source)
    p = motion(Document(source).manifest())
    report = check(
        p,
        steps=97,
        values={"drive": 0.731},
        require_constrained=True,
        require_reviewed=True,
    )
    (out / "check.json").write_text(json.dumps(report, indent=2) + "\n")
    if not report["passed"]:
        raise ValueError(f"Starter check failed: {out / 'check.json'}")
    plan.save(out / "plan.json", p)
    if not args.no_glb:
        glb.convert(p["source"], out / "model.glb")
    print(out)


if __name__ == "__main__":
    main()
