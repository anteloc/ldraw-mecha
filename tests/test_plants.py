"""Plant wind catalog: wind model, response solvers, clip rules, case assembly, plan semantics and export.

Wind and clip tests are pure Python. Assembly tests need the LDraw library (LDRAW_DIR); tests of the generated
plans and clip files read output/plants and are skipped when it has not been generated.
"""

import json
import math
import os
from pathlib import Path
import sys

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from ldraw_mechanisms import plan as contract  # noqa: E402
import wind_clips as wc  # noqa: E402

LIBRARY = bool(os.getenv("LDRAW_DIR") or os.getenv("LDRAWDIR"))
needs_library = pytest.mark.skipif(not LIBRARY, reason="Needs the LDraw parts library and shadow connectors")
GENERATED = all((wc.OUT / c["key"] / "plan.json").exists() for c in wc.CASES)
needs_output = pytest.mark.skipif(not GENERATED, reason="output/plants has not been generated")
CLIPS = wc.library()


# --------------------------------------------------------------------------- roster and clips
def test_twenty_cases_three_regimes_each():
    by = {}
    for c in CLIPS:
        by.setdefault(c.case, []).append(c.window)
    assert list(by) == [c["key"] for c in wc.CASES]
    assert len(by) == 20 and all(v == ["A", "B", "C"] for v in by.values())
    assert len({c.id for c in CLIPS}) == 60


def test_slots_fill_the_grid_once():
    slots = [tuple(c["slot"]) for c in wc.CASES]
    assert sorted(slots) == [(r, c) for r in range(wc.ROWS) for c in range(wc.COLUMNS)]


def test_every_control_has_measured_geometry():
    for c in wc.CASES:
        assert set(wc.GEOMETRY[c["key"]]) == set(c["controls"]), c["key"]


@pytest.mark.parametrize("clip", CLIPS, ids=[c.id for c in CLIPS])
def test_clip_rules(clip):
    """Rest at start and end (spins on a symmetric step), ranges, step size, exact breeze loop."""
    assert wc.check(clip) == []
    assert clip.styles and set(clip.styles) <= set(wc.STYLES)
    assert clip.channels == list(wc.BY_KEY[clip.case]["controls"])
    assert len(clip.series(clip.channels[0])) == wc.CLIP_FRAMES


def test_every_style_is_used():
    used = {s for c in CLIPS for s in c.styles}
    assert used == set(wc.STYLES)


def test_flex_approx_ranges_are_small():
    for c in wc.CASES:
        for name, spec in c["controls"].items():
            if spec["joint"] == "flex_approx":
                assert max(abs(spec["min"]), abs(spec["max"])) <= wc.FLEX_LIMIT + 1e-12, (c["key"], name)


def test_windows_do_not_overlap_and_fit_the_timeline():
    spans = sorted(wc.WINDOWS.values())
    assert all(a[1] < b[0] for a, b in zip(spans, spans[1:]))
    assert spans[-1][1] <= wc.FRAMES and all(b - a + 1 == wc.CLIP_FRAMES for a, b in spans)


# --------------------------------------------------------------------------- wind field
def test_breeze_wind_is_periodic_and_gusts_travel_along_x():
    for t in (0.0, 13.5, 50.0):
        assert wc.wind("A", t, 0.0) == pytest.approx(wc.wind("A", t + wc.PERIOD, 0.0), abs=1e-12)
    # A gust front: the field at x feels at t what x - dx felt dx / GUST_SPEED frames earlier.
    dx = 120.0
    for w in "BC":
        for t in (40.0, 90.0, 140.0):
            assert wc.wind(w, t, dx) == pytest.approx(wc.wind(w, t - dx / wc.GUST_SPEED, 0.0), abs=1e-12)


def test_wind_starts_calm_and_regimes_get_stronger():
    for w in "BC":
        assert wc.wind(w, 0.0, wc.X0) == (0.0, 0.0)
    mean = {w: np.mean([math.hypot(*wc.wind(w, t, 0.0)) for t in range(40, 170)]) for w in "ABC"}
    assert mean["A"] < mean["B"] < mean["C"]
    assert max(math.hypot(*wc.wind("C", t, 0.0)) for t in range(0, 240)) > 1.0


def test_case_delay_follows_its_column():
    delays = {c["key"]: wc.delay(wc.case_slot(c)[0]) for c in wc.CASES}
    for c in wc.CASES:
        assert delays[c["key"]] == pytest.approx((wc.case_slot(c)[0] - wc.X0) / wc.GUST_SPEED)
    assert delays["P01_palm_tree"] < delays["P02_swordleaf_palm"] < delays["P03_bamboo"]


# --------------------------------------------------------------------------- solvers
def test_periodic_steady_state_equals_a_long_integration():
    """The breeze solution (spectrum x transfer function) is the state a long RK4 run settles into."""
    spec = wc.BY_KEY["P11_hinged_oak"]["controls"]["branch_upwind"]
    r = spec["recipe"]
    n = wc.PERIOD * wc.SUB
    g = [wc._drive(r, "A", j / wc.SUB, r["x"]) for j in range(n)]
    steady = wc._periodic_linear(g, wc._osc_transfer(r))
    periods = 40  # light damping (zeta 0.05): long settling
    states = wc._rk4(wc._osc_ode(r, "A", r["x"]), [0.0, 0.0], 0.0, periods * n, 1.0 / wc.SUB)
    last = np.array([s[0] for s in states[(periods - 1) * n:periods * n]])
    assert np.max(np.abs(last - steady)) < 1e-5 * max(1.0, np.max(np.abs(steady)))


def test_soft_limit_keeps_values_inside_and_is_odd_symmetric_for_symmetric_ranges():
    for v in (-5.0, -0.1, 0.0, 0.07, 3.0):
        out = wc.soft_limit(v, -0.3, 0.3)
        assert -0.3 < out < 0.3 or out == 0.0
        assert wc.soft_limit(-v, -0.3, 0.3) == pytest.approx(-out)


def test_spins_follow_the_wind_and_end_on_symmetric_steps():
    case = wc.BY_KEY["P06_pinwheel_daisies"]
    for clip in (c for c in CLIPS if c.case == case["key"]):
        for name, spec in case["controls"].items():
            v = clip.series(name)
            step = wc.TAU / spec["symmetry"]
            assert v[-1] / step == pytest.approx(round(v[-1] / step), abs=1e-6)
            speed = np.diff(v) * spec["recipe"]["sign"]
            assert np.min(speed) > -1e-9  # never turns backwards
    storm = next(c for c in CLIPS if c.id == "P06_pinwheel_daisies.storm")
    breeze = next(c for c in CLIPS if c.id == "P06_pinwheel_daisies.breeze")
    assert abs(storm.series("spin_1")[-1]) > abs(breeze.series("spin_1")[-1])


def test_shared_wind_direction_leans_every_downwind_joint_the_same_way():
    """Storm mean of every drag-driven joint has the sign of its swing x: the wind pushes everything toward +X."""
    storm = {c.case: c for c in CLIPS if c.window == "C"}
    checked = 0
    for case in wc.CASES:
        for name, spec in case["controls"].items():
            r = spec["recipe"]
            if r["kind"] != "osc" or r["drive"] != "drag" or abs(r["swing"][0]) < 0.5 or r.get("lift"):
                continue
            mean = np.mean(storm[case["key"]].series(name)[40:200])
            assert mean * r["swing"][0] > 0, (case["key"], name, mean)
            checked += 1
    assert checked >= 40


def test_directional_fronds_upwind_lifts_downwind_flattens():
    storm = next(c for c in CLIPS if c.id == "P13_fern.storm")
    assert np.mean(storm.series("frond_upwind")[40:200]) > 0
    assert np.mean(storm.series("frond_downwind")[40:200]) < 0


def test_whip_chain_lags_toward_the_tip():
    gusty = next(c for c in CLIPS if c.id == "P01_palm_tree.gusty")
    peaks = [int(np.argmax(gusty.series(f"bend_{k}")[:80])) for k in (1, 6)]
    assert peaks[1] > peaks[0]


def test_sheltered_plants_ignore_the_breeze():
    breeze = next(c for c in CLIPS if c.id == "P18_ground_cover.breeze")
    storm = next(c for c in CLIPS if c.id == "P18_ground_cover.storm")
    assert max(abs(v) for ch in breeze.channels for v in breeze.series(ch)) < 1e-9
    assert max(abs(v) for ch in storm.channels for v in storm.series(ch)) > 0.2


def test_vanes_turn_downwind():
    case = wc.BY_KEY["P19_leaf_vanes"]
    storm = next(c for c in CLIPS if c.id == "P19_leaf_vanes.storm")
    for name, spec in case["controls"].items():
        h = spec["recipe"]["heading"]
        heading = h + np.mean(storm.series(name)[80:180])
        assert abs(math.remainder(heading, wc.TAU)) < 0.5, (name, heading)


def test_clip_document_bakes_the_values(tmp_path):
    clip = CLIPS[3]
    doc = wc.clip_document(clip)
    assert doc["baked"][clip.channels[0]] == [round(v, 6) for v in clip.series(clip.channels[0])]
    assert doc["blender"]["action_slot"] == "OBplant_controller"
    assert set(doc["channels"]) == set(clip.channels)
    json.dumps(doc)


# --------------------------------------------------------------------------- assembly (needs the library)
@needs_library
def test_cases_assemble_and_reference_checks_hold():
    import build_plants as bp
    for case in wc.CASES:
        b = bp.assemble(case)
        assert b.parts and b.bodies
        for r in b.references:
            assert r["position_offset_ldu"] <= 0.05, (case["key"], r)
        assert all(c["passed"] for c in b.checks), case["key"]


@needs_library
def test_palm_ball_chain_matches_the_official_shortcut():
    import build_plants as bp
    b = bp.assemble(wc.BY_KEY["P01_palm_tree"])
    gaps = [c["value"] for c in b.checks if c["name"].startswith("ball_socket_gap")]
    assert len(gaps) == 6 and max(gaps) < 0.5


@needs_library
def test_swordleaf_clip_centre_is_on_the_official_handle_bars():
    import build_plants as bp
    b = bp.assemble(wc.BY_KEY["P02_swordleaf_palm"])
    check = next(c for c in b.checks if c["name"] == "clip5_grip_vs_10297_handles")
    assert check["value"] < 0.1


# --------------------------------------------------------------------------- generated output
@needs_output
@pytest.mark.parametrize("case", wc.CASES, ids=[c["key"] for c in wc.CASES])
def test_plan_is_ready_and_matches_the_roster(case):
    d = wc.OUT / case["key"]
    plan = contract.load(d / "plan.json")
    assert plan["status"] == "ready"
    assert set(plan["controls"]) == set(case["controls"])
    for name, c in plan["controls"].items():
        assert (c["min"], c["max"]) == (case["controls"][name]["min"], case["controls"][name]["max"])
    kin = json.loads((d / "kinematics.json").read_text())
    assert kin["roster_problems"] == []
    for body, sem in kin["semantics"].items():
        assert sem["displacement"] != [0.0, 0.0, 0.0]
    # Joint names equal control names; the roster's joint kind must be the builder's.
    assert kin["joints"] == {k: s["joint"] for k, s in case["controls"].items()}


@needs_output
def test_exported_clip_files_match_the_library():
    if not (wc.OUT / "clips").exists():
        pytest.skip("catalog not exported")
    for clip in CLIPS:
        doc = json.loads((wc.OUT / "clips" / f"{clip.id}.json").read_text())
        for ch in clip.channels:
            assert doc["baked"][ch] == [round(v, 6) for v in clip.series(ch)]
