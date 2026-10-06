import importlib.util
import json
from pathlib import Path

import pytest

from ldraw_mechanisms import plan

ROOT = Path(__file__).resolve().parents[1]
FULL = ROOT / "output/42110-suspension/plan.json"
STUDY = ROOT / "output/42110-suspension-standalone"
STANDALONE = STUDY / "plan.json"
IDMAP = STUDY / "source/idmap.json"
CORNERS = ("fl", "fr", "rl", "rr")
pytestmark = pytest.mark.skipif(
    not (FULL.exists() and STANDALONE.exists() and IDMAP.exists()),
    reason="42110 suspension studies not generated",
)


@pytest.fixture(scope="module")
def plans():
    return plan.load(FULL), plan.load(STANDALONE), json.loads(IDMAP.read_text())["idmap"]


def test_extraction_keeps_identity_colour_and_world_matrix(plans):
    full, standalone, idmap = plans
    old = {n["id"]: n for n in full["source"]["nodes"]}
    new = {n["id"]: n for n in standalone["source"]["nodes"]}
    parts = {i for i, n in new.items() if n["kind"] == "part"}
    assert set(idmap.values()) == parts and len(idmap) == len(parts)  # a bijection onto the leaves
    for o, n in idmap.items():
        a, b = old[o], new[n]
        assert a["ref"].lower() == b["ref"].lower() and a["effective_colour"] == b["effective_colour"]
        assert max(abs(x - y) for ra, rb in zip(a["world"], b["world"]) for x, y in zip(ra, rb)) < 1e-6
    # Nothing beyond the subsystem: every moving instance and the reviewed static frame, no more.
    keep = json.loads((STUDY / "keep.json").read_text())["parts"]
    assert set(idmap) == {r["id"] for r in keep}


def test_motion_is_the_verified_full_model_motion(plans):
    full, standalone, idmap = plans
    for field in ("controls", "signals", "anchors", "checks"):
        assert standalone[field] == full[field]
    for name, b in full["bodies"].items():
        assert sorted(standalone["bodies"][name]["instances"]) == sorted(idmap[i] for i in b["instances"])
    limits = {c: full["controls"][f"travel_{c}"]["max"] for c in CORNERS}
    for fractions in [(0, 0, 0, 0), (1, 1, 1, 1), (0.3, 1, 0, 0.7), (0.9, 0.05, 0.6, 0.25)]:
        values = {f"travel_{c}": f * limits[c] for c, f in zip(CORNERS, fractions)}
        a, b = plan.evaluate(full, values), plan.evaluate(standalone, values)
        assert a["transforms"] == b["transforms"]
        assert len(b["checks"]) == 48 and all(c["passed"] for c in b["checks"])


def test_standalone_animation_closes_every_frame(plans):
    _, standalone, _ = plans
    spec = importlib.util.spec_from_file_location(
        "animate_defender_suspension", ROOT / "scripts/blender/animate_defender_suspension.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    rows = module.timeline(standalone)
    assert all(r["checks_passed"] for r in rows)
    assert module.continuity(standalone, rows)["passed"]


def test_extract_reproduces_the_saved_model(tmp_path):
    spec = importlib.util.spec_from_file_location("extract_subsystem", ROOT / "scripts/extract_subsystem.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    source = ROOT / "output/42110-suspension/source/42110-1-shocks-split.mpd"
    saved = STUDY / "source/42110-suspension-standalone.mpd"
    idmap, report = module.extract(
        source, module.keep_ids(STUDY / "keep.json"), tmp_path / saved.name,
        title="42110 Land Rover Defender - independent suspension with its mounting frame",
    )
    assert report["max_world_matrix_error"] < 1e-6
    assert (tmp_path / saved.name).read_text() == saved.read_text()
    assert idmap == json.loads(IDMAP.read_text())["idmap"]
