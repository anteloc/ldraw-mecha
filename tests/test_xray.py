"""`xray` must render exact occurrences in the plan frame and show what really moves."""

import json
import math
import os
from pathlib import Path

import pytest

from ldraw_mechanisms import mechanisms, plan, source as src, xray
from ldraw_mechanisms.cli import main
from ldraw_mechanisms.math3d import delta, frame, point, unit
from ldraw_mechanisms.source import Document



def _found(name):
    try:
        return src.find_tool(name)
    except ValueError:
        return None


XRAY = _found("ldraw-xray")
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


@pytest.fixture
def boards(monkeypatch):
    """Capture recipes instead of rendering them."""
    calls = []

    def fake(spec, output):
        calls.append((spec, Path(output)))
        return dict(image=str(Path(output) / "mosaic.png"), panels=len(spec["panels"]), notes=[])

    monkeypatch.setattr(xray, "run", fake)
    monkeypatch.setattr(xray, "executable", lambda: "ldraw-xray")
    return calls


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


def write_plan(source, path, bodies, controls, connections=None):
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
    p["mechanisms"] = mechanisms.motion_views(p)
    p["connections"] = connections or {}
    plan.save(path, p)
    return path


def test_flat_copy_places_every_occurrence_on_one_line_in_the_section_frame(source, tmp_path):
    manifest, path, lines = xray.render_source(source, None, tmp_path / "xray")
    text = path.read_text().splitlines()
    parts = {n["id"]: n for n in manifest["nodes"] if n["kind"] == "part"}
    assert sorted(lines) == sorted(parts) and len(set(lines.values())) == len(parts)
    for i, n in parts.items():
        tokens = text[lines[i] - 1].split()
        x, y, z, *m = map(float, tokens[2:14])
        world = [[*m[0:3], x], [*m[3:6], y], [*m[6:9], z]]
        assert tokens[14] == n["ref"] and tokens[1] == n["effective_colour"]
        for row, expected in zip(world, n["world"]):
            assert row == pytest.approx(expected)
    # The mirrored frame copy stays mirrored, so poses need no sign changes.
    m = parts["1/1/0"]["world"]
    det = (
        m[0][0] * (m[1][1] * m[2][2] - m[1][2] * m[2][1])
        - m[0][1] * (m[1][0] * m[2][2] - m[1][2] * m[2][0])
        + m[0][2] * (m[1][0] * m[2][1] - m[1][1] * m[2][0])
    )
    assert det < 0
    assert xray.selector([12, 3, 4, 5, 9, 11]) == "line:3-5,9,11-12"


def test_plan_rotation_matches_xray_right_hand_rule():
    origin, axis, angle = [5, -7, 11], [0.3, -0.5, 0.8], 0.37
    m = delta(frame(origin, axis), "revolute", angle)
    for p in ([1, 2, 3], [-40, 12, 9]):
        assert point(m, p) == pytest.approx(
            rodrigues(p, origin, axis, math.degrees(angle)), abs=1e-9
        )


def test_review_poses_each_body_with_its_descendants(source, tmp_path, boards):
    path = write_plan(
        source,
        tmp_path / "study" / "plan.json",
        {
            "frame": dict(
                kind="revolute", instances=["1/0", "1/2"], origin=[-70, -24, 0], axis=[0, 0, 1], signal="arm"
            ),
            "arm": dict(
                kind="revolute", instances=["1/1/0", "1/1/1"], origin=[-70, -24, 0], axis=[1, 0, 0],
                signal="spin", parent="frame",
            ),
            "block": dict(kind="prismatic", instances=["2"], origin=[0, 24, 0], axis=[0, -1, 0], signal="slide"),
        },
        dict(
            open=(-0.25, 1.1, 0.2, "radian"),
            turn=(-2 * math.pi, 2 * math.pi, 0, "radian"),
            push=(0, 16, 0, "ldu"),
        ),
    )
    out = tmp_path / "review.json"
    assert main(["xray", str(path.parent), "--output", str(out)]) == 0
    r = {b["board"]: b for b in json.loads(out.read_text())["boards"]}
    _, _, lines = xray.render_source(source, None, tmp_path / "check")
    assert r["frame"]["select"] == xray.selector(lines[i] for i in ["1/0", "1/2", "1/1/0", "1/1/1"])
    assert r["frame"]["degrees"] == pytest.approx(
        [math.degrees(v) for v in (-0.125, 0.0, 0.1, 0.55)], abs=1e-3
    )
    assert any("Descendant" in n for n in r["frame"]["notes"])
    assert r["arm"]["degrees"] == [0.0, 45.0, 90.0]
    assert any("parent 'frame' stays at rest" in n for n in r["arm"]["notes"])
    assert r["block"]["degrees"] == [] and any("cannot translate" in n for n in r["block"]["notes"])
    specs = {out.name: spec for spec, out in boards}
    assert {out.parent for _, out in boards} == {tmp_path / "study" / "xray"}
    assert all(len(s["panels"]) <= 12 for s in specs.values())
    assert len(specs["block"]["panels"]) == 2
    pose = specs["frame"]["panels"][2]["layers"]
    assert [x["layer"] for x in pose] == ["closeup", "pose", "axis", "highlight", "ghost"]
    assert pose[1]["direction"] == [0, 0, 1.0] and pose[1]["point"] == [-70, -24, 0]
    assert specs["arm"]["panels"][1]["view"] == "right"  # along the X axis


def test_pose_angles_wrap_and_stay_on_one_mosaic():
    assert xray.poses([0.0, 6.18]) == pytest.approx([math.degrees(6.18) - 360, 0.0])
    assert len(xray.poses([i / 10 for i in range(20)])) == xray.MAX_POSES
    assert xray.poses([-math.pi, math.pi]) == [0.0, 45.0, 90.0]


def test_unmeasurable_moving_sets_share_one_camera(monkeypatch):
    calls = []

    def fake(spec, output):
        calls.append(spec)
        if any(x["layer"] == "closeup" for p in spec["panels"] for x in p["layers"]):
            return dict(error="No measurable geometry for bounds")
        return dict(image="mosaic.png", panels=len(spec["panels"]), notes=[])

    monkeypatch.setattr(xray, "run", fake)
    axis = dict(point=[0, 0, 0], direction=[0, 1, 0])
    board = xray.look("flat.mpd", "disc", "disc", ["7"], {"7": 3}, "out", axis, [0, 45])
    assert len(calls) == 2 and "error" not in board
    assert calls[1]["panels"][2]["camera"] == dict(fixed="home")
    assert any("whole-block camera" in n for n in board["notes"])
    calls.clear()
    xray.look("flat.mpd", "disc", "disc", ["7"], {"7": 3}, "out", axis, [0, 45], embedded={"7"})
    assert len(calls) == 1  # Embedded parts skip the doomed close-up.


def test_candidate_selection_is_audited_against_study_contacts(source, tmp_path, boards):
    contact = lambda a, b, position: dict(  # noqa: E731
        a=a, b=b, kind="contact", status="candidate", evidence="fixture",
        measurements=dict(first_kind="pin", second_kind="pin_hole", position=position, axis=[0, 0, 1]),
    )
    path = write_plan(
        source,
        tmp_path / "study" / "plan.json",
        {},
        {},
        {"hinge": contact("1/0", "2", [-70, -24, 0]), "latch": contact("1/2", "2", [-70, -72, 0])},
    )
    out = tmp_path / "look.json"
    args = ["xray", str(path), "--instances", "1/0", "1/2", "--point", "-70", "-24", "0"]
    assert main(args + ["--direction", "0", "0", "1", "--name", "frame", "--output", str(out)]) == 0
    r = json.loads(out.read_text())
    assert [g["pairs"] for g in r["boundary"]] == [[["1/2", "2"]]]
    assert r["boards"][0]["board"] == "frame" and r["boards"][0]["degrees"] == [0, 45, 90]


def test_cli_rejects_incomplete_or_mixed_requests(source, tmp_path, capsys, monkeypatch):
    study = write_plan(source, tmp_path / "study" / "plan.json", {}, {})
    for argv in (
        [str(source), "--xray-dir", str(tmp_path)],
        [str(source), "--instances", "0/0"],
        [str(source), "--instances", "0/1", "--xray-dir", str(tmp_path)],
        [str(source), "--body", "x", "--xray-dir", str(tmp_path)],
        [str(study), "--point", "0", "0", "0"],
        [str(study), "--section", "main.ldr"],
        [str(study), "--body", "x", "--instances", "0/0"],
        [str(study), "--body", "missing"],
    ):
        assert main(["xray", *argv]) == 2, argv
        assert "error" in json.loads(capsys.readouterr().err.splitlines()[-1])
    monkeypatch.setattr(src, "ROOT", tmp_path)
    monkeypatch.setattr(src.shutil, "which", lambda name: None)
    assert main(["xray", str(source), "--instances", "0/0", "--xray-dir", str(tmp_path)]) == 2
    assert "setup-macos.sh" in capsys.readouterr().err


@pytest.mark.skipif(not (XRAY and LIBRARY), reason="needs ldraw-xray and an LDraw library")
def test_real_render_writes_one_mosaic(source, tmp_path):
    out = tmp_path / "look.json"
    argv = ["xray", str(source), "--instances", "1/1/0", "1/1/1", "--point", "-70", "-24", "0"]
    argv += ["--direction", "0", "0", "1", "--angles", "0", "30", "--xray-dir", str(tmp_path / "xray")]
    assert main(argv + ["--output", str(out)]) == 0
    board = json.loads(out.read_text())["boards"][0]
    assert Path(board["image"]).is_file() and board["panels"] == 4
    assert not any("empty" in n.lower() for n in board["notes"])
