"""Preparation and optional diagnostic views share source identities and motion."""

from copy import deepcopy
import json
from pathlib import Path

import pytest

from ldraw_mechanisms import mechanisms as graph, plan
from ldraw_mechanisms.cli import main
from ldraw_mechanisms.prepare import adopt_motion, discover, prepare
from ldraw_mechanisms import recipes
from ldraw_mechanisms.recipes import create
from ldraw_mechanisms.source import Document

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def source(tmp_path):
    path = tmp_path / "simple.ldr"
    path.write_text("""0 Simple mechanism
0 Author: Test Author
1 16 0 0 0 1 0 0 0 1 0 0 0 1 4214.dat
1 4 0 -8 -30 1 0 0 0 1 0 0 0 1 4213.dat
1 4 20 0 0 1 0 0 0 1 0 0 0 1 3001.dat
""")
    return path


@pytest.fixture
def study(source):
    p = plan.draft(Document(source).manifest())
    p["mechanisms"] = {
        "roof": dict(
            label="Roof", parts=["0", "1"], bodies=[], inputs=[], outputs=[], notes=[]
        ),
        "other": dict(
            label="Other mechanism",
            parts=["0", "2"],
            bodies=[],
            inputs=[],
            outputs=[],
            notes=[],
        ),
    }
    p["connections"] = {
        "hinge": dict(
            a="0",
            b="1",
            kind="revolute",
            status="candidate",
            evidence="Measured hinge frames",
        )
    }
    return p


def joint(study):
    return graph.add_joint(
        study,
        mechanism="roof",
        name="roof_angle",
        instances=["1"],
        origin=[0, -4, 6],
        axis=[1, 0, 0],
        minimum=0,
        maximum=1.2,
    )


def test_shared_identity_and_typed_candidate(study, tmp_path):
    assert plan.validate(study)["valid"]
    result = graph.write_diagrams(study, tmp_path / "diagrams")
    assert result["shared_parts"] == {"0": ["other", "roof"]}
    a = graph.diagram(study, "roof")
    b = graph.diagram(study, "other")
    assert graph._id("part:0") in a and graph._id("part:0") in b
    assert "revolute (candidate)" in a and "-.->" in a
    assert "Input not yet identified" in a
    # Edge reaching beyond view membership stays present with a boundary node.
    assert graph._id("part:1") in b and ":::boundary" in b
    assert a == graph.diagram(deepcopy(study), "roof")


@pytest.mark.parametrize(
    "change", ["assembly", "missing", "review", "status", "body", "empty", "io"]
)
def test_invalid_graph_rejected(study, change):
    if change == "assembly":
        study["connections"]["hinge"]["a"] = "root"
    elif change == "missing":
        study["mechanisms"]["roof"]["parts"].append("absent")
    elif change == "review":
        study["connections"]["hinge"]["status"] = "reviewed"
    elif change == "status":
        study["connections"]["hinge"]["status"] = "proven"
    elif change == "body":
        study["mechanisms"]["roof"]["bodies"].append("absent")
    elif change == "empty":
        study["mechanisms"]["roof"]["parts"] = []
    else:
        study["mechanisms"]["roof"]["inputs"] = ["control:absent"]
    with pytest.raises(ValueError):
        plan.validate(study)


def test_joint_is_canonical_motion_and_draft(study):
    p = joint(study)
    assert not study["bodies"] and p["status"] == "draft"
    assert (
        plan.evaluate(p, {"roof_angle": 0.6})["transforms"]["roof_angle"]
        != plan.evaluate(p)["transforms"]["roof_angle"]
    )
    text = graph.diagram(p, "roof")
    assert "revolute axis (1,0,0)" in text
    assert "INPUT roof_angle" in text
    p["bodies"]["roof_angle"]["axis"] = [0, 1, 0]
    assert "revolute axis (0,1,0)" in graph.diagram(p, "roof")
    assert "revolute axis (1,0,0)" not in graph.diagram(p, "roof")
    with pytest.raises(ValueError, match="already in use"):
        joint(p)


def test_rejected_connections_hidden_but_retained(study):
    study["connections"]["hinge"].update(
        status="rejected", review="Inspected: wrong hinge mate"
    )
    assert "revolute (rejected)" not in graph.diagram(study, "roof")
    assert "hinge" in study["connections"]


def test_reviewed_support_remains_in_motion_view(study):
    p = joint(study)
    p["connections"]["hinge"].update(
        status="reviewed", review="Holder stays fixed; roof rotates"
    )
    text = graph.diagram(p, "roof")
    assert (
        f'{graph._id("part:0")} ---|"revolute (reviewed)"| {graph._id("body:roof_angle")}'
        in text
    )


def test_regeneration_digest_and_stale_files(study, tmp_path):
    d = tmp_path / "diagrams"
    a = graph.write_diagrams(study, d)
    (d / "handwritten.txt").write_text("keep")
    del study["mechanisms"]["other"]
    study["mechanisms"]["roof"]["label"] = "Reviewed roof"
    b = graph.write_diagrams(study, d)
    assert a["plan_digest"] != b["plan_digest"]
    assert not (d / "other.mmd").exists()
    assert (d / "handwritten.txt").read_text() == "keep"
    assert (d / "roof.mmd").read_text() == graph.diagram(study, "roof")


def test_source_text_cannot_inject_mermaid(study):
    study["source"]["nodes"][0]["description"] = (
        '"]\nclick N1 call bad()\n<script>bad</script> ```'
    )
    text = graph.diagram(study, "roof")
    assert "\nclick" not in text and "<script>" not in text and "```" not in text
    assert "#34;" in text and "#60;" in text


def test_prepare_persists_evidence_without_diagrams_before_converter_failure(
    source, tmp_path, monkeypatch
):
    from ldraw_mechanisms import glb

    monkeypatch.delenv("LDRAW_DIR", raising=False)
    monkeypatch.delenv("LDRAWDIR", raising=False)
    out = tmp_path / "prepared"

    def fail(manifest, target, library):
        assert (out / "plan.json").is_file()
        assert not (out / "diagrams").exists()
        report = json.loads((out / "preparation.json").read_text())
        saved = json.loads((out / "plan.json").read_text())
        assert report["glb"] is None
        assert report["discovery"] == saved["discovery"]
        assert saved["mechanisms"]  # Candidate evidence survives conversion failure.
        raise ValueError("converter unavailable")

    monkeypatch.setattr(glb, "convert", fail)
    with pytest.raises(ValueError, match="converter unavailable"):
        prepare(source, out)
    original = (out / "plan.json").read_bytes()
    with pytest.raises(ValueError, match="not empty"):
        prepare(source, out)
    assert (out / "plan.json").read_bytes() == original


def test_source_only_cli_and_no_library(source, tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("LDRAW_DIR", raising=False)
    monkeypatch.delenv("LDRAWDIR", raising=False)
    out = tmp_path / "prepared"
    assert main(["prepare", str(source), "--output", str(out), "--no-glb"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["glb"] is None
    assert "diagrams" not in report
    assert not (out / "diagrams").exists()
    assert not (out / "model.glb").exists()
    assert "not run" in report["contacts"]
    assert "contacts_not_run" in {w["code"] for w in report["warnings"]}
    assert (
        "not run"
        in json.loads((out / "preparation.json").read_text())["discovery"]["contacts"]
    )
    assert main(["diagrams", str(out / "plan.json")]) == 0
    exported = json.loads(capsys.readouterr().out)
    assert exported["diagrams"] == str(out / "diagrams")
    assert list((out / "diagrams").glob("*.mmd"))


def test_contact_budget_is_explicit(source):
    import os

    if not os.getenv("LDRAW_DIR"):
        pytest.skip("Needs parts library")
    result = discover(Document(source).manifest(), contact_limit=2)
    assert "outside 2..2" in result["discovery"]["contacts"]
    assert not result["connections"]


def test_adopt_preserves_evidence_and_nonzero_motion(study):
    motion = joint(study)
    motion["status"] = "ready"
    adopted = adopt_motion(study, motion)
    assert adopted["connections"] == study["connections"]
    assert set(adopted["mechanisms"]) == {"roof", "other", "roof_angle"}
    assert adopted["mechanisms"]["other"] == study["mechanisms"]["other"]
    assert plan.evaluate(adopted, {"roof_angle": 0.731}) == plan.evaluate(
        motion, {"roof_angle": 0.731}
    )
    changed = deepcopy(motion)
    changed["source"]["sha256"] = "wrong"
    with pytest.raises(ValueError, match="same source"):
        adopt_motion(study, changed)


def test_real_technic_shared_views_and_asymmetric_evaluation():
    p = create(ROOT / "data/models-annotated/42000-1.mpd", "42000")
    p["mechanisms"] = graph.motion_views(p)
    p["connections"] = {}
    assert plan.validate(p)["valid"]
    deps = graph.control_dependencies(p)
    shared = [b for b, v in deps.items() if "spin_rl" in v and "spin_rr" in v]
    assert shared
    for b in shared:
        assert b in p["mechanisms"]["spin_rl"]["bodies"]
        assert b in p["mechanisms"]["spin_rr"]["bodies"]
    assert plan.evaluate(p, dict(spin_rl=0.7, spin_rr=-0.2, steering=0.4))["checks"]
    text = graph.diagram(p, "spin_rl")
    assert "anchor crank_pin" in text
    assert "prismatic axis" in text


def test_10265_steering_closes_under_asymmetric_input():
    """The pitman linkage must propagate, not just exist.

    The earlier study left the steering links static and declared no closure
    check at all, so a sweep passed while nothing moved. Assert the knuckles
    follow the wheel, that the two sides differ (the linkage is Ackermann),
    and that both 100 LDU tie-rod closures are actually measured.
    """
    p = create(ROOT / "data/models-annotated/10265-1_B-Model.mpd", "10265")
    assert plan.validate(p)["valid"]
    for side in ("l", "r"):
        rod = p["bodies"]["tierod_" + side]
        assert rod["kind"] == "rod"
        assert rod["start"] == "crank_ball_" + side
    assert {c["name"] for c in p["checks"]} == {"link_l", "link_r"}

    rest = plan.evaluate(p, {})
    assert all(abs(c["error"]) < 1e-6 for c in rest["checks"])
    assert rest["signals"]["knuckle_l"] == pytest.approx(0.0, abs=1e-9)

    steered = plan.evaluate(
        p, dict(steering=0.18, spin_rl=0.7, spin_rr=-0.2, spin_fl=1.4)
    )
    assert steered["checks"]
    for check in steered["checks"]:
        assert check["passed"], check
        assert check["length"] == pytest.approx(100.0, abs=0.02)
    left, right = (steered["signals"]["knuckle_" + s] for s in ("l", "r"))
    # Both knuckles turn the same way, and the inner one turns further.
    assert left > 0 and right > 0
    assert left > right
    assert steered["signals"]["crank"] == pytest.approx(0.4 * 0.18)
    # Rear wheels stay independent: no differential is declared.
    assert steered["signals"]["wheel_rl"] == pytest.approx(0.7)
    assert steered["signals"]["wheel_rr"] == pytest.approx(-0.2)

    mirrored = plan.evaluate(p, dict(steering=-0.18))
    assert mirrored["signals"]["knuckle_l"] == pytest.approx(
        -steered["signals"]["knuckle_r"], abs=1e-9
    )
    # Every Blender driver expression must stay inside the 255 byte limit.
    assert max(len(s["expression"]) for s in p["signals"].values()) < 255


def test_10265_recipe_rejects_a_changed_source():
    p = create(ROOT / "data/models-annotated/10265-1_B-Model.mpd", "10265")
    owned = [i for b in p["bodies"].values() for i in b["instances"]]
    assert len(owned) == len(set(owned))
    manifest = Document(ROOT / "data/models-annotated/10265-1_B-Model.mpd").manifest()
    for node in manifest["nodes"]:
        if node["id"] == "0/91/7":
            node["ref"] = "3648.dat"
    with pytest.raises(ValueError, match="Expected 3649.dat at 0/91/7"):
        recipes.RECIPES["10265"](manifest)
