"""Reference snapshots remain usable after moving the checkout or deleting output/."""
import importlib.util
import json
from pathlib import Path
import shutil

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/reference_assets.py"
spec = importlib.util.spec_from_file_location("reference_assets", SCRIPT)
assets = importlib.util.module_from_spec(spec)
spec.loader.exec_module(assets)


def setup_bundle(root):
    source = root / "output/demo/source/demo.mpd"
    source.parent.mkdir(parents=True)
    source.write_text("0 FILE demo.ldr\n0 Test attribution\n")
    plan = dict(source=dict(path=str(source), sha256=assets.sha256(source),
                            dependencies={str(source): assets.sha256(source)}),
                controls={"angle": {"min": 0, "max": 1}}, bodies={"hinge": {"origin": [1, 2, 3]}})
    assets.write(root / "output/demo/plan.json", plan)
    assets.write(root / assets.ARCHIVE / "selection.json", dict(bundles={"demo": ["*.json", "source/*.mpd"]}))
    return plan


def test_copy_preserves_originals_and_rebases_in_another_checkout(tmp_path):
    original = tmp_path / "old"
    plan = setup_bundle(original)
    before = assets.sha256(original / "output/demo/plan.json")
    assert assets.copy_assets(original)["files"] == 2
    assert assets.copy_assets(original)["files"] == 2
    assert assets.sha256(original / "output/demo/plan.json") == before
    clone = tmp_path / "elsewhere"
    shutil.copytree(original / "examples", clone / "examples")
    shutil.rmtree(original)
    snapshot = clone / assets.ARCHIVE / "demo/plan.json"
    loaded = assets.load_plan(snapshot, clone)
    assert loaded["source"]["path"] == str(clone / assets.ARCHIVE / "demo/source/demo.mpd")
    assert loaded["bodies"] == plan["bodies"] and loaded["controls"] == plan["controls"]
    assert assets.read(snapshot) == plan  # relocating is only in memory


def test_copy_refuses_changed_original_before_writing_any_new_file(tmp_path):
    setup_bundle(tmp_path)
    assets.copy_assets(tmp_path)
    (tmp_path / "output/demo/source/demo.mpd").write_text("changed")
    assets.write(tmp_path / "output/demo/new.json", {})
    with pytest.raises(ValueError, match="Snapshot differs"):
        assets.copy_assets(tmp_path)
    assert not (tmp_path / assets.ARCHIVE / "demo/new.json").exists()


def test_new_bundle_can_be_archived_after_earlier_working_files_are_deleted(tmp_path):
    setup_bundle(tmp_path)
    assets.copy_assets(tmp_path)
    shutil.rmtree(tmp_path / "output")
    assets.write(tmp_path / "output/second/evidence.json", {"passed": True})
    selection = tmp_path / assets.ARCHIVE / "selection.json"
    data = assets.read(selection)
    data["bundles"]["second"] = ["*.json"]
    assets.write(selection, data)
    assert assets.copy_assets(tmp_path, cases=["second"])["files"] == 3
    with pytest.raises(ValueError, match="Unknown bundles"):
        assets.copy_assets(tmp_path, cases=["missing"])


def test_missing_and_stale_sources_fail_without_falling_back_to_output(tmp_path):
    setup_bundle(tmp_path)
    assets.copy_assets(tmp_path)
    archived = tmp_path / assets.ARCHIVE / "demo/source/demo.mpd"
    archived.write_text("tampered")
    with pytest.raises(ValueError, match="hash differs"):
        assets.load_plan(tmp_path / assets.ARCHIVE / "demo/plan.json", tmp_path)
    archived.unlink()
    with pytest.raises(ValueError, match="Missing archived source"):
        assets.load_plan(tmp_path / assets.ARCHIVE / "demo/plan.json", tmp_path)


def test_check_rejects_output_links_and_missing_archive_files(tmp_path):
    setup_bundle(tmp_path)
    assets.copy_assets(tmp_path)
    (tmp_path / "README.md").write_text("[Plan](output/demo/plan.json)\n")
    (tmp_path / "instructions.md").write_text("")
    with pytest.raises(ValueError, match="disposable output"):
        assets.check(tmp_path)
    (tmp_path / "README.md").write_text("[Plan](examples/reference/demo/plan.json)\n")
    assert assets.check(tmp_path)["source_plans"] == 1
    (tmp_path / assets.ARCHIVE / "demo/plan.json").unlink()
    with pytest.raises(ValueError, match="Missing/changed snapshot"):
        assets.check(tmp_path)
