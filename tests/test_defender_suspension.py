import importlib.util
import json
from pathlib import Path

import pytest

from ldraw_mechanisms import plan
from ldraw_mechanisms.math3d import add, length, mul, point, sub, unit

ROOT = Path(__file__).resolve().parents[1]
STUDY = ROOT / "output/42110-suspension"
PLAN = STUDY / "plan.json"
CORNERS = ("fl", "fr", "rl", "rr")
needs_plan = pytest.mark.skipif(not PLAN.exists(), reason="42110 suspension study not generated")


def load_script(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_split_shortcuts_keeps_every_other_identity(tmp_path):
    split = load_script("split_shortcuts")
    source = ROOT / "data/models-annotated/42110-1.mpd"
    before = source.read_bytes()
    report = split.split(source, ["76537.dat", "41838.dat"], tmp_path / "split.mpd")
    assert source.read_bytes() == before
    assert len(report["split_occurrences"]) == 8
    assert report["max_subpart_matrix_error"] == 0
    for occurrence in report["split_occurrences"].values():
        refs = [c["ref"].lower() for c in occurrence["children"]]
        assert refs[:2] == ["4254.dat", "4255.dat"] and refs[2] in ("22977.dat", "41837.dat")


@pytest.fixture(scope="module")
def p():
    return plan.load(PLAN)


def limit(p, c="fl"):
    return p["controls"][f"travel_{c}"]["max"]


def wheel_centre(p, e, c):
    return point(e["transforms"][f"knuckle_{c}"], p["bodies"][f"knuckle_{c}"]["origin"])


@needs_plan
@pytest.mark.parametrize(
    "fractions",
    [(0, 0, 0, 0), (1, 1, 1, 1), (0.3, 1, 0, 0.7), (1, 0, 0.55, 0.2), (0.12, 0.88, 0.47, 0.03)],
)
def test_closures_hold_for_asymmetric_travel(p, fractions):
    values = {f"travel_{c}": f * limit(p, c) for c, f in zip(CORNERS, fractions)}
    e = plan.evaluate(p, values)
    assert len(e["checks"]) == 48
    assert all(c["passed"] for c in e["checks"]), [c for c in e["checks"] if not c["passed"]]
    for c in CORNERS:
        m = e["transforms"][f"knuckle_{c}"]
        # Parallelogram: knuckle, hub and wheel translate without camber or toe change.
        assert max(abs(m[i][j] - (i == j)) for i in range(3) for j in range(3)) < 1e-12
        rest = p["bodies"][f"knuckle_{c}"]["origin"]
        # Positive travel raises the wheel centre by the control value, measured along chassis-up
        # (perpendicular to the wishbone axis); world -Y differs by the 0.003 rad chassis tilt.
        assert rest[1] - wheel_centre(p, e, c)[1] == pytest.approx(values[f"travel_{c}"], rel=1e-5, abs=1e-9)


@needs_plan
def test_corners_are_independent(p):
    e = plan.evaluate(p, dict(travel_rr=limit(p, "rr")))
    for c in ("fl", "fr", "rl"):
        assert e["signals"][f"th_{c}"] == 0
    assert e["signals"]["th_rr"] > 0.3


@needs_plan
@pytest.mark.parametrize("c", CORNERS)
def test_shocks_compress_monotonically_within_the_stroke(p, c):
    lengths = []
    for i in range(21):
        e = plan.evaluate(p, {f"travel_{c}": limit(p, c) * i / 20})
        lengths.append(e["signals"][f"ext_{c}0"])
        assert e["signals"][f"ext_{c}1"] == pytest.approx(e["signals"][f"ext_{c}0"], abs=1e-6)
    assert lengths[0] == pytest.approx(0, abs=1e-9)
    assert all(b < a for a, b in zip(lengths, lengths[1:]))
    # 16 LDU design limit, inside the 20 LDU piston-to-bore-floor stroke; the front stops earlier.
    assert -16.0 <= lengths[-1] < (-15.0 if c in ("rl", "rr") else -10.0)


@needs_plan
@pytest.mark.parametrize("c", CORNERS)
def test_spring_free_end_stays_on_the_rod(p, c):
    e = plan.evaluate(p, {f"travel_{c}": 0.8 * limit(p, c)})
    for j in range(2):
        spring = p["bodies"][f"spring_{c}{j}"]
        free_end = add(spring["origin"], mul(unit(spring["axis"]), 44.0))
        carried_by_spring = point(e["transforms"][f"spring_{c}{j}"], free_end)
        carried_by_rod = point(e["transforms"][f"rod_{c}{j}"], free_end)
        assert length(sub(carried_by_spring, carried_by_rod)) < 1e-6
        # The fixed seat stays on the cylinder.
        seat = spring["origin"]
        assert length(sub(point(e["transforms"][f"spring_{c}{j}"], seat),
                          point(e["transforms"][f"cyl_{c}{j}"], seat))) < 1e-9


@needs_plan
def test_rebuild_reproduces_saved_motion(p):
    study = STUDY / "study/plan.json"
    evidence = STUDY / "evidence/contacts-suspension.json"
    if not (study.exists() and evidence.exists()):
        pytest.skip("study inputs not generated")
    builder = load_script("build_defender_suspension")
    stops = {c: limit(p, c) for c in ("fl", "fr")}
    out = builder.build(plan.load(study), json.loads(evidence.read_text()), stops=stops)
    for field in ("controls", "signals", "bodies", "anchors", "checks"):
        assert out[field] == p[field], field


@needs_plan
def test_animation_timeline_is_continuous_and_closed(p):
    anim = importlib.util.spec_from_file_location(
        "animate_defender_suspension", ROOT / "scripts/blender/animate_defender_suspension.py"
    )
    module = importlib.util.module_from_spec(anim)
    anim.loader.exec_module(module)
    rows = module.timeline(p)
    assert all(r["checks_passed"] for r in rows)
    for c in CORNERS:
        values = [r["controls"][f"travel_{c}"] for r in rows]
        assert min(values) >= 0 and max(values) <= limit(p, c)
        assert max(values) > 0.95 * limit(p, c)  # the articulation reaches near full bump
    assert rows[0]["controls"] == rows[-1]["controls"] == {f"travel_{c}": 0.0 for c in CORNERS}
    assert module.continuity(p, rows)["passed"]
