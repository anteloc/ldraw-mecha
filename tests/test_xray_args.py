"""xray-args must map occurrences and plan joints onto ldraw-xray's frames exactly."""

import json
import math
import os
from pathlib import Path
import shutil
import subprocess

import pytest

from ldraw_mechanisms import plan
from ldraw_mechanisms.cli import main
from ldraw_mechanisms.math3d import delta, direction, frame, point, unit
from ldraw_mechanisms.source import Document
from ldraw_mechanisms.xray import locate, study

XRAY = shutil.which("ldraw-xray")
LIBRARY = bool(os.getenv("LDRAW_DIR") or os.getenv("LDRAWDIR"))

# main places frame twice (rotated, then mirrored); frame places the arm.
SOURCE = """0 FILE main.ldr
0 Main
1 16 10 -8 30 0 0 1 0 1 0 -1 0 0 frame.ldr
1 16 -50 0 0 -1 0 0 0 1 0 0 0 1 frame.ldr
1 4 0 24 0 1 0 0 0 1 0 0 0 1 3001.dat
0 FILE frame.ldr
0 Frame
1 16 0 0 0 1 0 0 0 1 0 0 0 1 3001.dat
1 16 20 -24 0 1 0 0 0 1 0 0 0 1 arm.ldr
0 STEP
1 1 0 -48 0 1 0 0 0 1 0 0 0 1 3001.dat
0 FILE arm.ldr
0 Arm
1 14 0 0 0 1 0 0 0 1 0 0 0 1 3001.dat
1 14 0 -24 0 1 0 0 0 1 0 0 0 1 3002.dat
"""


@pytest.fixture
def source(tmp_path):
    path = tmp_path / "model.mpd"
    path.write_text(SOURCE)
    return path


def codes(result):
    return sorted(w["code"] for w in result["warnings"])


def rodrigues(p, origin, axis, degrees):
    """Right-hand rotation of point p about a line, as ldraw-xray poses parts."""
    k, a = unit(axis), math.radians(degrees)
    v = [x - o for x, o in zip(p, origin)]
    kv = sum(x * y for x, y in zip(k, v))
    kxv = [
        k[1] * v[2] - k[2] * v[1],
        k[2] * v[0] - k[0] * v[2],
        k[0] * v[1] - k[1] * v[0],
    ]
    return [
        o + x * math.cos(a) + c * math.sin(a) + kk * kv * (1 - math.cos(a))
        for o, x, c, kk in zip(origin, v, kxv, k)
    ]


def test_lines_are_absolute_file_lines_and_chains_follow_assemblies(source):
    manifest = Document(source).manifest()
    lines = SOURCE.splitlines()
    for n in manifest["nodes"]:
        words = lines[n["line"] - 1].split()
        assert words[0] == "1" and words[-1] == n["ref"]
    (occurrence,) = locate(manifest, ["0/1/1"])["occurrences"]
    assert occurrence["chain"] == [
        dict(block="main.ldr", line=3),
        dict(block="frame.ldr", line=9),
        dict(block="arm.ldr", line=15),
    ]


def test_whole_assembly_becomes_subject_with_its_placement_as_surroundings(source):
    located = locate(Document(source).manifest(), ["0/1/0", "0/1/1"])
    subject, around = located["subject"], located["surroundings"]
    assert (subject["block"], subject["selector"], subject["parent"]) == (
        "arm.ldr",
        "all",
        "frame.ldr",
    )
    assert subject["frame_instance"] == "0/1" and subject["nonempty_steps"] == 1
    assert (around["block"], around["selector"], around["parent"]) == (
        "frame.ldr",
        "line:9",
        "main.ldr",
    )
    # main places frame twice; parent-context poses would move both copies.
    assert codes(located) == ["shared_definition"] and not located["extra"]


def test_partial_assemblies_over_select_and_root_has_no_parent(source):
    manifest = Document(source).manifest()
    located = locate(manifest, ["0/1/1", "0/2"])
    assert located["subject"]["block"] == "frame.ldr"
    assert located["subject"]["selector"] == "line:9,11"
    assert located["surroundings"] is None and located["extra"] == ["0/1/0"]
    assert codes(located) == ["over_selects", "shared_definition"]
    root = locate(manifest, ["2"])
    assert (root["subject"]["block"], root["subject"]["parent"]) == ("main.ldr", None)
    assert codes(root) == ["no_parent"]
    with pytest.raises(ValueError, match="Unknown occurrence"):
        locate(manifest, ["9"])


@pytest.mark.parametrize("instance,mirrored", [("0", False), ("1", True)])
def test_block_pivot_reproduces_section_motion(source, tmp_path, instance, mirrored):
    manifest = Document(source).manifest()
    world = {n["id"]: n["world"] for n in manifest["nodes"]}[f"{instance}/1"]
    local_point, local_axis = [3, -5, 7], [0.866, 0, 0.5]
    origin, axis = point(world, local_point), direction(world, local_axis)
    result = study(
        source,
        [f"{instance}/1/1"],
        origin=origin,
        axis=axis,
        angles=[10, -35],
        xray_dir=tmp_path / "xray",
    )
    pivot = result["subject"]["pivot"]
    assert result["subject"]["block"] == "arm.ldr" and pivot["mirrored"] is mirrored
    assert pivot["point"] == pytest.approx(local_point)
    assert pivot["direction"] == pytest.approx(unit(local_axis))
    assert pivot["angles_degrees"] == ([-10, 35] if mirrored else [10, -35])
    # Posing in the block and placing the result equals posing in the section.
    leaf = [11, -24, 4]
    for section_angle, block_angle in zip([10, -35], pivot["angles_degrees"]):
        expected = rodrigues(point(world, leaf), origin, axis, section_angle)
        posed = rodrigues(leaf, pivot["point"], pivot["direction"], block_angle)
        assert point(world, posed) == pytest.approx(expected, abs=1e-9)
    names = [c["name"] for c in result["commands"]]
    assert names == [
        "overview",
        "context",
        "selection",
        "pivot",
        "pivot-focus",
        "connections",
        "axes",
    ]


def test_plan_rotation_matches_xray_right_hand_rule():
    origin, axis, angle = [5, -7, 11], [0.3, -0.5, 0.8], 0.37
    m = delta(frame(origin, axis), "revolute", angle)
    for p in ([1, 2, 3], [-40, 12, 9]):
        assert point(m, p) == pytest.approx(
            rodrigues(p, origin, axis, math.degrees(angle)), abs=1e-9
        )


def write_plan(source, path, bodies, controls):
    p = plan.draft(Document(source).manifest())
    p["controls"] = {
        name: dict(min=lo, max=hi, default=default, unit=unit_, description=name)
        for name, (lo, hi, default, unit_) in controls.items()
    }
    p["signals"] = {
        name: dict(expression=expr, variables={"a": f"control:{control}"})
        for name, (expr, control) in {
            "arm": ("0.5*a", "open"),
            "spin": ("a", "turn"),
            "slide": ("a", "push"),
        }.items()
        if control in controls
    }
    p["bodies"] = bodies
    plan.save(path, p)
    return path


def test_plan_body_limits_become_mirrored_degrees_through_cli(source, tmp_path):
    path = write_plan(
        source,
        tmp_path / "study" / "plan.json",
        {
            "arm": dict(
                kind="revolute",
                instances=["1/1/0", "1/1/1"],
                origin=[-70, -24, 0],
                axis=[0, 0, 1],
                signal="arm",
            ),
            "wheel": dict(
                kind="revolute",
                instances=["0/0"],
                origin=[10, -8, 30],
                axis=[1, 0, 0],
                signal="spin",
            ),
            "block": dict(
                kind="prismatic",
                instances=["2"],
                origin=[0, 24, 0],
                axis=[0, -1, 0],
                signal="slide",
            ),
        },
        dict(
            open=(-0.25, 1.1, 0.2, "radian"),
            turn=(-2 * math.pi, 2 * math.pi, 0, "radian"),
            push=(0, 16, 0, "ldu"),
        ),
    )
    out = tmp_path / "arm.json"
    assert (
        main(
            [
                "xray-args",
                "--plan",
                str(path.parent),
                "--body",
                "arm",
                "--output",
                str(out),
            ]
        )
        == 0
    )
    r = json.loads(out.read_text())
    radians = [-0.125, 0.0, 0.1, 0.55]
    assert r["axis"]["radians"] == pytest.approx(radians)
    degrees = [-math.degrees(v) for v in radians]  # under the mirrored frame copy
    assert r["subject"]["block"] == "arm.ldr" and r["subject"]["selector"] == "all"
    assert r["subject"]["pivot"]["angles_degrees"] == pytest.approx(degrees)
    assert r["surroundings"]["pivot"]["angles_degrees"] == pytest.approx(degrees)
    assert "mirrored" in codes(r)
    pivot = next(c for c in r["commands"] if c["name"] == "pivot")["argv"]
    angles = pivot[pivot.index("--angles") + 1 : pivot.index("--output")]
    assert [float(a) for a in angles] == pytest.approx(degrees, abs=1e-3)
    assert pivot[pivot.index("--output") + 1] == str(
        tmp_path / "study" / "xray" / "arm" / "pivot"
    )
    # The focus recipe poses the surroundings' line selector, never `all`.
    (recipe_path,) = r["recipes"]
    recipe = json.loads(Path(recipe_path).read_text())
    assert recipe["section"] == "frame.ldr"
    poses = [x for p in recipe["panels"] for x in p["layers"] if x["layer"] == "pose"]
    assert {x["select"] for x in poses} == {"line:9"}
    assert [x["angle"] for x in poses] == pytest.approx(degrees)

    wheel = tmp_path / "wheel.json"
    assert (
        main(
            [
                "xray-args",
                "--plan",
                str(path),
                "--body",
                "wheel",
                "--output",
                str(wheel),
            ]
        )
        == 0
    )
    w = json.loads(wheel.read_text())
    assert w["subject"]["pivot"]["angles_degrees"] == [0.0, 45.0, 90.0]
    assert any("Full-turn" in n for n in w["notes"])
    slide = tmp_path / "slide.json"
    assert (
        main(
            [
                "xray-args",
                "--plan",
                str(path),
                "--body",
                "block",
                "--output",
                str(slide),
            ]
        )
        == 0
    )
    s = json.loads(slide.read_text())
    assert s["subject"]["pivot"]["angles_degrees"] == [0.0] and s["axis"]["values"] == [
        0.0,
        16.0,
    ]
    assert any("cannot translate" in n for n in s["notes"])


def test_cli_rejects_incomplete_or_mixed_requests(source, tmp_path, capsys):
    assert main(["xray-args", str(source), "--instances", "0"]) == 2
    assert (
        main(
            ["xray-args", str(source), "--instances", "9", "--xray-dir", str(tmp_path)]
        )
        == 2
    )
    assert (
        main(
            [
                "xray-args",
                str(source),
                "--instances",
                "0",
                "--point",
                "0",
                "0",
                "0",
                "--xray-dir",
                str(tmp_path),
            ]
        )
        == 2
    )
    path = write_plan(source, tmp_path / "plan.json", {}, {})
    assert main(["xray-args", "--plan", str(path)]) == 2
    assert (
        main(["xray-args", "--plan", str(path), "--body", "x", "--instances", "0"]) == 2
    )
    assert "error" in json.loads(capsys.readouterr().err.splitlines()[-1])
    assert (
        main(
            [
                "xray-args",
                str(source),
                "--instances",
                "0/1",
                "--xray-dir",
                str(tmp_path),
            ]
        )
        == 0
    )
    shells = [c["shell"] for c in json.loads(capsys.readouterr().out)["commands"]]
    assert (
        shells[0].startswith("ldraw-xray board overview ")
        and "--section arm.ldr" in shells[0]
    )


@pytest.mark.skipif(not XRAY, reason="ldraw-xray CLI is not on PATH")
def test_xray_sections_agree_with_source_lines(source):
    run = subprocess.run(
        [XRAY, "sections", str(source)], capture_output=True, text=True, check=True
    )
    sections = {s["name"]: s for s in json.loads(run.stdout)["sections"]}
    nodes = Document(source).manifest()["nodes"]
    for n in nodes:
        assert sections[n["section"]]["first_line"] <= n["line"]
    # Direct placements of one instance of each block.
    for block, parent in (("main.ldr", "root"), ("frame.ldr", "0"), ("arm.ldr", "0/1")):
        direct = [n for n in nodes if n["parent"] == parent]
        assert {n["section"] for n in direct} == {block}
        assert sections[block]["placements"] == len(direct)


@pytest.mark.skipif(
    not (XRAY and LIBRARY), reason="needs ldraw-xray and an LDraw library"
)
def test_xray_connection_line_paths_match_chains(source):
    run = subprocess.run(
        [XRAY, "connections", str(source), "--section", "frame.ldr"],
        capture_output=True,
        text=True,
        check=True,
    )
    members = [m for g in json.loads(run.stdout)["groups"] for m in g["members"]]
    manifest = Document(source).manifest("frame.ldr")
    parts = [n["id"] for n in manifest["nodes"] if n["kind"] == "part"]
    chains = {
        tuple(c["line"] for c in o["chain"])
        for o in locate(manifest, parts)["occurrences"]
    }
    assert members and all(tuple(m["lines"]) in chains for m in members)
