"""The short workflow must preserve evidence and fail on meaningful bad motion."""

from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from ldraw_mechanisms import mechanisms, plan, workflow
from ldraw_mechanisms.cli import main
from ldraw_mechanisms.prepare import adopt_motion, prepare
from ldraw_mechanisms.recipes import create
from ldraw_mechanisms.source import Document

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def coupled(tmp_path):
    source = tmp_path / "source.ldr"
    source.write_text(
        "0 Coupled test\n"
        "1 4 0 0 0 1 0 0 0 1 0 0 0 1 3001.dat\n"
        "1 1 10 0 0 1 0 0 0 1 0 0 0 1 3001.dat\n"
    )
    p = plan.draft(Document(source).manifest())
    p.update(
        status="ready",
        controls={
            name: dict(min=-1, max=1, default=0, unit="ldu", description=name)
            for name in ("a", "b")
        },
        signals={
            "slide": dict(
                expression="a*b", variables={"a": "control:a", "b": "control:b"}
            )
        },
        bodies={
            "moving": dict(
                kind="prismatic",
                instances=["0"],
                origin=[0, 0, 0],
                axis=[1, 0, 0],
                signal="slide",
            ),
            "support": dict(
                kind="fixed", instances=["1"], origin=[10, 0, 0], axis=[1, 0, 0]
            ),
        },
        anchors={
            "start": dict(body="moving", point=[0, 0, 0]),
            "end": dict(body="support", point=[10, 0, 0]),
        },
        checks=[
            dict(
                kind="distance",
                name="link",
                a="start",
                b="end",
                length=10,
                tolerance=0.01,
            )
        ],
    )
    p["mechanisms"] = mechanisms.motion_views(p)
    p["connections"] = {}
    return p


def test_check_catches_coupling_that_independent_sweeps_miss(coupled):
    before = deepcopy(coupled)
    result = workflow.check(coupled)
    assert result["validation"]["valid"]
    assert result["sweep"]["passed"]
    assert result["poses"]["defaults"]["passed"]
    mixed = result["poses"]["mixed"]
    assert mixed["controls"] == pytest.approx(dict(a=0.37, b=-0.61))
    assert mixed["signals"]["slide"] == pytest.approx(-0.2257)
    assert mixed["checks"][0]["length"] == pytest.approx(10.2257)
    assert not result["passed"]
    assert result["plan_digest"] == plan.digest(coupled)
    assert coupled == before


def test_strict_constraints_reject_zero_check_animation_before_blender(
    coupled, tmp_path
):
    coupled["checks"] = []
    assert workflow.check(coupled)["passed"]  # Compatible legacy behaviour.
    strict = workflow.check(coupled, require_constrained=True)
    assert not strict["passed"]
    assert strict["audit"]["constraints"]["unchecked_bodies"] == ["moving"]
    path = tmp_path / "plan.json"
    plan.save(path, coupled)
    # No GLB or Blender is needed: strict preflight must reject this first.
    assert not workflow.rig(path, require_constrained=True)["passed"]


def test_check_reports_domain_failure_at_nonzero_pose(coupled):
    coupled["checks"] = []
    coupled["signals"]["slide"]["expression"] = "sqrt(1-100*a*a*b*b)"
    report = workflow.check(coupled)
    assert report["sweep"]["passed"]
    assert not report["passed"]
    assert "Signal slide" in report["poses"]["mixed"]["error"]
    coupled["signals"]["slide"]["expression"] = "sqrt(0.2-a)"
    report = workflow.check(coupled)
    assert not report["sweep"]["passed"]
    assert "Signal slide" in report["sweep"]["error"]


def test_scope_is_reported_and_strict_review_retains_deferrals(coupled):
    coupled["checks"] = []
    view = next(iter(coupled["mechanisms"].values()))
    view.pop("disposition", None)
    view.pop("review", None)
    assert workflow.check(coupled)["passed"]
    assert not workflow.check(coupled, require_reviewed=True)["passed"]
    for view in coupled["mechanisms"].values():
        view.update(disposition="deferred", review="Coupling awaits measurement")
    result = workflow.check(coupled, require_reviewed=True)
    assert result["passed"]
    assert result["audit"]["deferred"]
    assert result["summary"]["deferred"] == len(result["audit"]["deferred"])


def test_check_records_requested_and_clamped_values(coupled):
    report = workflow.check(coupled, values=dict(a=4, b=-0.25))
    pose = report["poses"]["requested"]
    assert pose["requested"] == dict(a=4, b=-0.25)
    assert pose["controls"] == dict(a=1, b=-0.25)
    assert pose["signals"]["slide"] == -0.25
    assert not pose["passed"]


@pytest.mark.parametrize(
    "options,match",
    [
        ({"values": {"missing": 1}}, "Unknown controls"),
        ({"values": {"a": float("nan")}}, "Nonfinite"),
        ({"steps": 1}, "Sweep steps"),
    ],
)
def test_bad_check_input_is_an_error(coupled, options, match):
    with pytest.raises(ValueError, match=match):
        workflow.check(coupled, **options)


def test_check_cli_saves_report_and_preserves_plan(coupled, tmp_path, capsys):
    path = tmp_path / "plan.json"
    plan.save(path, coupled)
    original = path.read_bytes()
    assert main(["check", str(tmp_path), "--set", "a=0.5", "--set", "b=-0.25"]) == 1
    result = json.loads(capsys.readouterr().out)
    assert result["passed"] is False
    assert result["summary"]["status"] == "ready"
    saved = json.loads((tmp_path / "check.json").read_text())
    assert saved["poses"]["requested"]["signals"]["slide"] == -0.125
    assert path.read_bytes() == original
    # Explicit output uses exactly that path; a plan file works as well as a directory.
    assert main(["check", str(path), "--output", str(tmp_path / "custom.json")]) == 1
    assert (tmp_path / "custom.json").is_file()


def test_check_refuses_stale_source_and_output_aliases(coupled, tmp_path, capsys):
    path = tmp_path / "plan.json"
    plan.save(path, coupled)
    original = path.read_bytes()
    alias = tmp_path / "alias.json"
    alias.symlink_to(path)
    for output in (path, alias, coupled["source"]["path"]):
        assert main(["check", str(path), "--output", str(output)]) == 2
        assert "overwrite" in json.loads(capsys.readouterr().err)["error"]
    assert path.read_bytes() == original
    Path(coupled["source"]["path"]).write_text("0 Changed source\n")
    assert main(["check", str(tmp_path)]) == 2
    assert not (tmp_path / "check.json").exists()


def test_evaluate_exit_code_reflects_failed_closure(coupled, tmp_path, capsys):
    plan.save(tmp_path / "plan.json", coupled)
    assert main(["evaluate", str(tmp_path), "--set", "a=0.5", "--set", "b=-0.25"]) == 1
    assert json.loads(capsys.readouterr().out)["passed"] is False
    assert main(["evaluate", str(tmp_path)]) == 0
    assert json.loads(capsys.readouterr().out)["passed"] is True
    # Preserve the established CLI convention: the last assignment wins.
    assert main(["evaluate", str(tmp_path), "--set", "a=1", "--set", "a=0"]) == 0
    assert json.loads(capsys.readouterr().out)["controls"]["a"] == 0


def test_prepare_recipe_matches_explicit_adoption(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("LDRAW_DIR", raising=False)
    monkeypatch.delenv("LDRAWDIR", raising=False)
    source = ROOT / "data/models-annotated/106-1.mpd"
    plain, short = tmp_path / "plain", tmp_path / "short"
    prepare(source, plain, convert_glb=False)
    expected = adopt_motion(plan.load(plain / "plan.json"), create(source, "106"))
    assert (
        main(
            [
                "prepare",
                str(source),
                "--recipe",
                "106",
                "--no-glb",
                "--output",
                str(short),
            ]
        )
        == 0
    )
    assert plan.load(short / "plan.json") == expected
    assert json.loads(capsys.readouterr().out)["audit"]["unresolved"] > 0
    assert not (short / "model.glb").exists()
    before = (short / "plan.json").read_bytes()
    assert (
        main(
            [
                "prepare",
                str(source),
                "--recipe",
                "106",
                "--no-glb",
                "--output",
                str(short),
            ]
        )
        == 2
    )
    assert (short / "plan.json").read_bytes() == before
    with pytest.raises(ValueError, match="not both"):
        prepare(source, tmp_path / "conflict", motion=expected, recipe="106")


@pytest.fixture
def rig_files(coupled, tmp_path):
    plan.save(tmp_path / "plan.json", coupled)
    (tmp_path / "model.glb").write_bytes(b"Test placeholder; subprocess mocked")
    return tmp_path


def test_rig_defaults_and_reopening_keep_stdout_for_json(rig_files, monkeypatch):
    calls = []

    def run(command, **kwargs):
        calls.append(command)
        assert kwargs == dict(stdout=workflow.sys.stderr, stderr=workflow.sys.stderr)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(workflow.subprocess, "run", run)
    result = workflow.rig(
        rig_files,
        blender="/path with spaces/Blender",
        animate=True,
        reopen=True,
        tolerance=0.004,
    )
    assert result["passed"] and result["verified"] and result["reopened"]
    assert result["saved"] == str(rig_files / "rigged.blend")
    assert result["report"] == str(rig_files / "blender-check.json")
    assert result["reopen_report"] == str(rig_files / "blender-check-reopen.json")
    assert calls[0][0] == "/path with spaces/Blender"
    assert "--new-scene" in calls[0] and "--animate" in calls[0]
    assert "--disable-autoexec" in calls[1] and "--verify-existing" in calls[1]
    assert "--new-scene" not in calls[1] and "--animate" not in calls[1]
    assert all(c[c.index("--tolerance") + 1] == "0.004" for c in calls)


@pytest.mark.parametrize("fail_stage", [0, 1])
def test_rig_subprocess_failure_is_not_success(
    rig_files, monkeypatch, capsys, fail_stage
):
    calls = []

    def run(command, **kwargs):
        calls.append(command)
        return SimpleNamespace(returncode=int(len(calls) - 1 == fail_stage))

    monkeypatch.setattr(workflow.subprocess, "run", run)
    assert main(["rig", str(rig_files), "--blender", "Blender", "--reopen"]) == 1
    assert json.loads(capsys.readouterr().out)["passed"] is False
    assert len(calls) == fail_stage + 1


def test_explicit_rig_paths_still_work(rig_files, monkeypatch):
    calls = []
    monkeypatch.setattr(
        workflow.subprocess,
        "run",
        lambda cmd, **kw: calls.append(cmd) or SimpleNamespace(returncode=0),
    )
    result = workflow.rig(
        rig_files / "plan.json",
        blender="Blender",
        glb=rig_files / "model.glb",
        save=rig_files / "custom.blend",
        report=rig_files / "custom.json",
    )
    assert result["passed"]
    assert result["saved"] == str(rig_files / "custom.blend")
    assert result["report"] == str(rig_files / "custom.json")
    assert len(calls) == 1


def test_rig_rejects_missing_geometry_and_output_aliases(rig_files):
    for options in (
        dict(save=rig_files / "plan.json"),
        dict(report=rig_files / "model.glb"),
        dict(save=rig_files / "same", report=rig_files / "same"),
    ):
        with pytest.raises(ValueError, match="overwrite"):
            workflow.rig(rig_files, blender="Blender", **options)
    (rig_files / "model.glb").unlink()
    with pytest.raises(ValueError, match="Bound GLB not found"):
        workflow.rig(rig_files, blender="Blender")
