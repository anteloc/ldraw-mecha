"""Movable-element catalog: scenario assembly, official placements, plan semantics, clip rules and export.

Clip and easing tests are pure Python. Assembly tests need the LDraw library (LDRAW_DIR); tests of the generated
plans and clip files read output/movables and are skipped when it has not been generated.
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
import movable_clips as mv  # noqa: E402

LIBRARY = bool(os.getenv("LDRAW_DIR") or os.getenv("LDRAWDIR"))
needs_library = pytest.mark.skipif(not LIBRARY, reason="Needs the LDraw parts library and shadow connectors")
GENERATED = all((mv.OUT / sc["key"] / "plan.json").exists() for sc in mv.SCENARIOS)
needs_output = pytest.mark.skipif(not GENERATED, reason="output/movables has not been generated")
CLIPS = mv.library()


# --------------------------------------------------------------------------- clip library
def test_twenty_scenarios_with_three_distinct_clips_each():
    by = {}
    for c in CLIPS:
        by.setdefault(c.scenario, []).append(c.name)
    assert list(by) == [sc["key"] for sc in mv.SCENARIOS]
    assert len(by) == 20 and all(len(set(v)) == 3 for v in by.values())
    assert len({c.id for c in CLIPS}) == 60


@pytest.mark.parametrize("clip", CLIPS, ids=[c.id for c in CLIPS])
def test_clip_rules(clip):
    """Rest at start and end (whole turns on periodic channels), ranges, continuity, known styles."""
    assert mv.check(clip) == []
    assert clip.frames <= mv.MAX_CLIP_FRAMES
    assert clip.styles and set(clip.styles) <= set(mv.STYLES)
    assert clip.channels == list(mv.BY_KEY[clip.scenario]["controls"])


def test_every_style_is_used():
    used = {s for c in CLIPS for s in c.styles}
    assert used == set(mv.STYLES)


def test_windows_do_not_overlap_and_fit_the_timeline():
    spans = sorted(mv.WINDOWS.values())
    assert all(a[1] < b[0] for a, b in zip(spans, spans[1:]))
    assert spans[-1][1] <= mv.FRAMES and all(b - a + 1 == mv.MAX_CLIP_FRAMES for a, b in spans)


def test_bounce_out_matches_blender_curve():
    """BLI_easing bounce ease-out: reaches the target at t = 1/2.75, rebounds, settles exactly at the end."""
    keys = [(1, 0.0, "BOUNCE_OUT"), (12, 1.0, "SINE_IN_OUT")]
    d = 11
    assert mv.value_at(keys, 1 + d / 2.75) == pytest.approx(1.0)
    assert mv.value_at(keys, 1 + d * 1.5 / 2.75) == pytest.approx(0.75)  # first rebound apex
    assert mv.value_at(keys, 12) == pytest.approx(1.0)
    samples = [mv.value_at(keys, 1 + d * k / 400) for k in range(401)]
    assert max(samples) <= 1.0 + 1e-12 and min(samples) >= 0.0


def test_back_out_overshoots_about_ten_percent():
    keys = [(1, 0.0, "BACK_OUT"), (101, 1.0, "SINE_IN_OUT")]
    samples = [mv.value_at(keys, 1 + k / 4) for k in range(401)]
    assert 1.09 < max(samples) < 1.11
    assert samples[-1] == pytest.approx(1.0)


def test_spin_clips_end_on_whole_turns_and_constant_spin_is_linear():
    spin = [c for c in CLIPS if c.scenario == "S15_radar"]
    for c in spin:
        turns = c.value("spin", c.frames) / mv.TAU
        assert abs(turns - round(turns)) < 1e-9
    const = next(c for c in spin if c.name == "constant_spin")
    speeds = {round(const.value("spin", f + 1) - const.value("spin", f), 9) for f in range(1, const.frames)}
    assert len(speeds) == 1


def test_spin_up_down_has_no_velocity_jump():
    c = next(c for c in CLIPS if c.id == "S15_radar.spin_up_down")
    v = [c.value("spin", f + 0.5) - c.value("spin", f) for f in [x / 2 for x in range(2, 2 * c.frames - 1)]]
    assert max(abs(b - a) for a, b in zip(v, v[1:])) < 0.01


def test_clip_document_bakes_the_evaluated_values(tmp_path):
    clip = next(c for c in CLIPS if c.id == "S01_house_door.slam")
    doc = mv.clip_document(clip, CLIPS)
    assert doc["blender"]["nla_track"] == "B slam" and doc["blender"]["controller"] == "CTRL_movable_01_house_door"
    assert doc["baked"]["door"][69] == pytest.approx(clip.value("door", 70), abs=1e-6)
    keys = doc["channels"]["door"]["keys"]
    assert any(k["interpolation"] == "BOUNCE" and k["easing"] == "EASE_OUT" for k in keys)


# --------------------------------------------------------------------------- assembly (LDraw library)
@needs_library
def test_scenarios_assemble_from_library_parts():
    import build_movables as bm
    for sc in mv.SCENARIOS:
        b = bm.assemble(sc)
        roles = [p["role"] for p in b.parts]
        assert len(roles) == len(set(roles))
        for name, spec in b.bodies.items():
            assert spec["joint"] in b.joints
            assert set(spec["roles"]) <= set(roles)
        assert all(p["table"] or p["ref"] in bm.LIBRARY_ONLY for p in b.parts)


@needs_library
def test_connector_placements_match_official_models():
    """Where an official model holds the same pair, the composed placement matches one of its occurrences."""
    import build_movables as bm
    exact, close = 0, 0
    for sc in mv.SCENARIOS:
        for r in bm.assemble(sc).references:
            assert r["rotation_offset"] < 1e-3, (sc["key"], r)
            assert r["position_offset_ldu"] <= 3.2, (sc["key"], r)
            exact += r["position_offset_ldu"] < 0.01
            close += r["position_offset_ldu"] >= 0.01
    assert exact >= 15 and close <= 5


@needs_library
def test_shadow_hinge_axis_quirk_is_documented():
    """4275b's shadow hinge frame lies along the plate; the bucket turns about 4531's finger axis."""
    import build_movables as bm
    h4275 = bm.find_connector("4275b", "hinge")
    h4531 = bm.find_connector("4531", "hinge")
    assert abs(h4275["axis"][0]) == pytest.approx(1.0)
    assert abs(h4531["axis"][2]) == pytest.approx(1.0)


# --------------------------------------------------------------------------- generated plans
@needs_output
@pytest.mark.parametrize("sc", mv.SCENARIOS, ids=[s["key"] for s in mv.SCENARIOS])
def test_plan_is_ready_and_signs_mean_what_the_controls_say(sc):
    import build_movables as bm
    d = mv.OUT / sc["key"]
    plan = contract.load(d / "plan.json")
    contract.validate(plan)
    assert plan["status"] == "ready"
    assert set(plan["controls"]) == set(sc["controls"])
    for name, c in sc["controls"].items():
        assert (plan["controls"][name]["min"], plan["controls"][name]["max"]) == (c["min"], c["max"])
    b = bm.assemble(sc)
    for name, spec in b.bodies.items():
        if spec["test"]:
            ok, detail = bm.semantic_check(plan, b, name, spec)
            assert ok, (name, detail)
    result = contract.evaluate(plan, bm.asymmetric(sc))
    assert set(result["transforms"]) == set(plan["bodies"])
    views = plan["mechanisms"]
    assert views["context"]["disposition"] == "static"
    covered = {p for v in views.values() for p in v["parts"]}
    assert covered == {n["id"] for n in plan["source"]["nodes"]}


@needs_output
def test_crane_hook_stays_plumb_and_spring_seat_follows_the_forks():
    crane = contract.load(mv.OUT / "S16_crane/plan.json")
    for values in (dict(luff=0.9), dict(luff=0.5, slew=-1.0)):
        t = contract.evaluate(crane, values)["transforms"]
        hook = [row[:3] for row in t["hook"][:3]]
        sup = [row[:3] for row in t["superstructure"][:3]]
        assert max(abs(hook[i][j] - sup[i][j]) for i in range(3) for j in range(3)) < 1e-9
    kin = json.loads((mv.OUT / "S13_forklift/kinematics.json").read_text())
    seats = [v for k, v in kin["semantics"].items() if k.startswith("spring_seat")]
    assert seats and all(v["follows_forks_error"] < 1e-6 for v in seats)
    fork = contract.load(mv.OUT / "S13_forklift/plan.json")
    assert fork["bodies"]["spring"]["kind"] == "stretch"
    assert fork["signals"]["spring_scale"]["expression"] == "(136 - a) / 136"


@needs_output
def test_exported_clip_files_match_the_library():
    files = sorted((mv.OUT / "clips").glob("*.json"))
    assert len(files) == 60
    for clip in CLIPS[::7]:
        doc = json.loads((mv.OUT / "clips" / f"{clip.id}.json").read_text())
        for ch in clip.channels:
            assert doc["baked"][ch] == [round(clip.value(ch, f), 6) for f in range(1, clip.frames + 1)]
