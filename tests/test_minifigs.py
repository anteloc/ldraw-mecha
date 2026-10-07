"""Minifig movement catalog: connector-composed assembly, shared joint signs, clip rules and catalog export.

Clip and convention tests are pure Python. Assembly tests need the LDraw library (LDRAW_DIR); tests of the
generated plans and clip files read output/minifigs and are skipped when it has not been generated.
"""

import json
import math
import os
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from ldraw_mechanisms import plan as contract  # noqa: E402
import minifig_clips as mc  # noqa: E402

LIBRARY = bool(os.getenv("LDRAW_DIR") or os.getenv("LDRAWDIR"))
needs_library = pytest.mark.skipif(not LIBRARY, reason="Needs the LDraw parts library and shadow connectors")
CLIPS = mc.library()


def mat(a, b):
    return [[sum(a[i][k] * b[k][j] for k in range(len(b))) for j in range(len(b[0]))] for i in range(len(a))]


def apply(m, p):
    return [sum(m[i][k] * p[k] for k in range(3)) + m[i][3] for i in range(3)]


def rot(axis, a):
    x, y, z = axis
    c, s, t = math.cos(a), math.sin(a), 1 - math.cos(a)
    return [[t * x * x + c, t * x * y - s * z, t * x * z + s * y],
            [t * x * y + s * z, t * y * y + c, t * y * z - s * x],
            [t * x * z - s * y, t * y * z + s * x, t * z * z + c]]


# --------------------------------------------------------------------------- clip library
def test_ten_figures_with_three_distinct_clips_each():
    figures = {}
    for c in CLIPS:
        figures.setdefault(c.figure, []).append(c.name)
    assert len(figures) == 10 and all(len(v) == 3 for v in figures.values())
    assert len({c.id for c in CLIPS}) == 30


@pytest.mark.parametrize("clip", CLIPS, ids=[c.id for c in CLIPS])
def test_clip_rules(clip):
    """Neutral start/end (whole turns allowed on periodic channels), ranges, continuity, home return."""
    assert mc.check(clip) == []
    assert clip.frames <= mc.MAX_CLIP_FRAMES
    for ch in ("move_forward", "move_left", "move_up"):
        assert abs(clip.value(ch, clip.frames)) < 1e-9


def test_windows_do_not_overlap_and_fit_the_timeline():
    spans = sorted(mc.WINDOWS.values())
    assert all(a[1] < b[0] for a, b in zip(spans, spans[1:]))
    assert spans[-1][1] <= mc.FRAMES
    assert all(b - a + 1 == mc.MAX_CLIP_FRAMES for a, b in spans)


def test_wave_is_an_exact_sine_with_blender_easing():
    c = mc.Clip("T", "t", "t", "t", 60)
    mc.wave(c, "neck", 1, 24, 4, 0.5)
    for f in range(1, 50):
        assert c.value("neck", f) == pytest.approx(0.5 * math.sin(2 * math.pi * (f - 1) / 24), abs=1e-12)


def test_hop_is_a_parabola():
    c = mc.Clip("T", "t", "t", "t", 60)
    mc.hop(c, 10, 24, 36)
    for f in range(10, 35):
        u = (f - 10) / 24
        assert c.value("move_up", f) == pytest.approx(4 * 36 * u * (1 - u), abs=1e-9)


def test_gait_dips_by_the_straight_leg_geometry():
    walk = next(c for c in CLIPS if c.id == "MF01_police.walk_patrol")
    lowest = min(walk.value("move_up", f / 4) for f in range(4, 4 * walk.frames))
    assert lowest == pytest.approx(-mc.HIP_HEIGHT * (1 - math.cos(0.45)), abs=1e-9)
    assert max(walk.value("move_forward", f) for f in range(1, 145)) > 80


def test_figure_transform_sign_conventions():
    nose = [0.0, -12.0, -13.0]  # in front of the face
    head = [0.0, -24.0, 0.0]
    pivot = list(mc.PIVOT)
    t = mc.figure_transform(dict(move_forward=10))
    assert apply(t, pivot) == pytest.approx([0, 44, -10])  # forward is -Z
    t = mc.figure_transform(dict(move_left=10, move_up=5))
    assert apply(t, pivot) == pytest.approx([10, 39, 0])  # left +X, up -Y
    assert apply(mc.figure_transform(dict(turn=0.3)), nose)[0] > 0  # turning left moves the face to +X
    assert apply(mc.figure_transform(dict(pitch=0.3)), head)[2] < 0  # leaning forward moves the head forward
    assert apply(mc.figure_transform(dict(roll=0.3)), head)[0] > 0  # rolling left moves the head to +X
    assert apply(mc.figure_transform(dict(turn=1.0, pitch=0.5, roll=-0.4)), pivot) == pytest.approx(pivot)


def test_blender_move_drivers_match_the_figure_transform():
    """MOVE_ location/euler drivers reproduce figure_transform under the LDraw -> Blender basis (x, z, -y)."""
    assert all("%" not in e and "**" not in e for _, _, e, _ in mc.MOVE_DRIVERS)
    assert {ch for *_, ch in mc.MOVE_DRIVERS} == set(mc.FIGURE)
    a = [[1, 0, 0], [0, 0, 1], [0, -1, 0]]  # LDraw direction -> Blender direction (root Rx(pi) after glTF C)
    at = [list(r) for r in zip(*a)]
    values = dict(move_forward=12.0, move_left=-7.0, move_up=3.0, turn=0.7, pitch=-0.4, roll=0.25)
    driven = {}
    for path, index, expression, channel in mc.MOVE_DRIVERS:
        driven[(path, index)] = eval(expression, {}, {"v": values[channel]})
    f = mc.figure_transform(values)
    # Rotation: Blender rotation_mode 'YXZ' -> R = Rz(turn) Rx(pitch) Ry(roll).
    r_blender = mat(mat(rot((0, 0, 1), driven[("rotation_euler", 2)]), rot((1, 0, 0), driven[("rotation_euler", 0)])),
                    rot((0, 1, 0), driven[("rotation_euler", 1)]))
    r_ldraw = mat(mat(a, [row[:3] for row in f[:3]]), at)
    assert sum(r_blender, []) == pytest.approx(sum(r_ldraw, []), abs=1e-12)
    # Translation of the pivot (MOVE_ origin) in metres.
    moved = apply(f, list(mc.PIVOT))
    delta = [m - p for m, p in zip(moved, mc.PIVOT)]
    expected = [sum(a[i][k] * delta[k] for k in range(3)) * mc.LDU for i in range(3)]
    assert [driven[("location", i)] for i in range(3)] == pytest.approx(expected, abs=1e-12)


def test_clip_json_round_trip():
    names = {v: k for k, v in mc.INTERPOLATIONS.items()}
    for clip in CLIPS:
        doc = json.loads(json.dumps(mc.clip_document(clip, CLIPS)))
        assert doc["blender"]["action"] == clip.id
        for ch in mc.CHANNELS:
            keys = [(k["frame"], k["value"], names[(k["interpolation"], k["easing"])]) for k in doc["channels"][ch]]
            for f in range(1, clip.frames + 1):
                assert mc.value_at(keys, f) == pytest.approx(doc["baked"][ch][f - 1], abs=2e-6)


def test_conventions_document_is_json():
    doc = json.loads(json.dumps(mc.conventions()))
    assert doc["channel_order"] == mc.CHANNELS and doc["pivot"] == list(mc.PIVOT)


# --------------------------------------------------------------------------- assembly (LDraw library)
def builder():
    import build_minifigs

    return build_minifigs


@needs_library
@pytest.mark.parametrize("index", range(10))
def test_joint_connectors_coincide(index):
    import numpy as np

    b = builder()
    fig = b.ROSTER[index]
    parts, evidence = b.assemble(fig)
    m = {p["role"]: p["matrix"] for p in parts}
    refs = {p["role"]: p["ref"] for p in parts}
    checks = [
        ("neck", "head", b.connector(refs["head"], "pin_hole", near=(0, 24, 0))),
        ("shoulder_l", "arm_l", b.connector(refs["arm_l"], "pin", near=(0, 0, 0))),
        ("shoulder_r", "arm_r", b.connector(refs["arm_r"], "pin", near=(0, 0, 0))),
        ("wrist_l", "hand_l", b.connector("3820", "pin", near=(0, 0, 0))),
        ("wrist_r", "hand_r", b.connector("3820", "pin", near=(0, 0, 0))),
        ("hip_l", "leg_l", b.connector(refs["leg_l"], "pin_hole", near=(2, 0, 0))),
        ("hip_r", "leg_r", b.connector(refs["leg_r"], "pin_hole", near=(-2, 0, 0))),
    ]
    for joint, role, male in checks:
        e = evidence[joint]
        assert np.allclose(b.world_point(m[role], male["position"]), e["origin"], atol=1e-9), joint
        axis = b.world_dir(m[role], male["axis"])
        assert abs(abs(float(np.dot(axis, e["axis"]))) - 1) < 1e-9, joint


@needs_library
def test_placement_matches_the_official_6682_minifig():
    b = builder()
    parts, _ = b.assemble(b.ROSTER[0])
    report = b.compare_reference(parts)
    assert all(v["rotation_offset"] < 1e-3 for v in report.values())
    # The shadow torso sockets sit at y=9; 6682 places the arms at y=8, so arms and hands differ by ~1 LDU.
    assert all(v["position_offset"] <= 1.01 for v in report.values())
    assert report["hips"]["position_offset"] == 0 and report["leg_l"]["position_offset"] == 0


@needs_library
def test_joint_signs_mean_the_same_on_both_sides(tmp_path):
    from ldraw_mechanisms.source import Document

    b = builder()
    fig = b.ROSTER[7]  # athlete: no hand items
    parts, evidence = b.assemble(fig)
    path = tmp_path / "minifig.mpd"
    b.write_mpd(fig, parts, path)
    study = contract.draft(Document(path).manifest(None), name=fig["plan"])
    roles = [dict(role=p["role"], id=str(k)) for k, p in enumerate(parts)]
    plan, semantics = b.author_plan(fig, study, roles, evidence)
    contract.validate(plan)
    assert {k for k, v in semantics.items() if v["flipped"]} == {"shoulder_r", "wrist_r", "hip_l"}
    nodes = {n["id"]: n for n in plan["source"]["nodes"]}
    ids = {r["role"]: r["id"] for r in roles}

    def moved(values, body, role, local):
        world = nodes[ids[role]]["world"]
        p = apply(world, local)
        return [x - y for x, y in zip(apply(contract.evaluate(plan, values)["transforms"][body], p), p)]

    for a in (0.4, 1.3, -0.7):
        left = moved({"shoulder_l": a, "shoulder_r": a}, "arm_l", "hand_l", [0, 0, 0])
        right = moved({"shoulder_l": a, "shoulder_r": a}, "arm_r", "hand_r", [0, 0, 0])
        assert left == pytest.approx([-right[0], right[1], right[2]], abs=1e-9)
        legs = [moved({"hip_l": a, "hip_r": a}, f"leg_{s}", f"leg_{s}", [0, 28, 0]) for s in "lr"]
        assert legs[0] == pytest.approx(legs[1], abs=1e-9)
    # Asymmetric inputs: each joint moves only its own side, with the documented meaning.
    values = dict(neck=0.8, shoulder_l=1.2, shoulder_r=-0.7, wrist_l=-0.4, wrist_r=0.9, hip_l=0.5, hip_r=-0.3)
    assert moved(values, "arm_l", "hand_l", [0, 0, 0])[2] < 0  # left arm forward
    assert moved(values, "arm_r", "hand_r", [0, 0, 0])[2] > 0  # right arm back
    assert moved(values, "leg_l", "leg_l", [0, 28, 0])[2] < 0
    assert moved(values, "leg_r", "leg_r", [0, 28, 0])[2] > 0
    assert moved(values, "head", "head", [0, 12, -13])[0] > 0  # face turned left


# --------------------------------------------------------------------------- generated outputs
def generated(figure, name):
    path = mc.OUT / figure / name
    if not path.exists():
        pytest.skip(f"{path} not generated")
    return path


@pytest.mark.parametrize("figure", sorted({c.figure for c in CLIPS}))
def test_generated_plan_uses_the_shared_joint_layout(figure):
    plan = contract.load(generated(figure, "plan.json"))
    contract.validate(plan)
    assert plan["status"] == "ready"
    assert list(plan["controls"]) == list(mc.JOINTS)
    for name, c in plan["controls"].items():
        assert (c["min"], c["max"]) == (mc.JOINTS[name]["min"], mc.JOINTS[name]["max"])
    assert set(plan["bodies"]) == {"head", "arm_l", "arm_r", "hand_l", "hand_r", "leg_l", "leg_r"}
    assert plan["bodies"]["hand_l"]["parent"] == "arm_l" and plan["bodies"]["hand_r"]["parent"] == "arm_r"
    assert {m["disposition"] for m in plan["mechanisms"].values()} == {"planned", "static"}


def test_exported_clip_files_are_fresh():
    folder = mc.OUT / "clips"
    if not folder.exists():
        pytest.skip("clips not exported")
    for clip in CLIPS:
        doc = json.loads((folder / f"{clip.id}.json").read_text())
        assert doc["baked"] == mc.baked(clip), clip.id
