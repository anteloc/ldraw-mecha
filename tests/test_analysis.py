from pathlib import Path

import pytest

from ldraw_mechanisms.source import Document
from ldraw_mechanisms.analysis import inspect
from ldraw_mechanisms.math3d import point

ROOT = Path(__file__).resolve().parents[1]


def test_repeated_submodels_and_embedded_dat(tmp_path):
    p = tmp_path / "fixture.mpd"
    p.write_text("""0 FILE main.ldr
0 Example
1 4 10 0 0 1 0 0 0 1 0 0 0 1 child.ldr
1 2 30 0 0 1 0 0 0 1 0 0 0 1 child.ldr
0 FILE child.ldr
0 Child
1 16 0 5 0 1 0 0 0 1 0 0 0 1 custom.dat
0 FILE custom.dat
0 Custom physical piece
1 16 0 0 0 1 0 0 0 1 0 0 0 1 stud.dat
""")
    m = Document(p).manifest()
    assert [n["id"] for n in m["nodes"]] == ["0", "0/0", "1", "1/0"]
    assert [n["effective_colour"] for n in m["nodes"]] == ["4", "4", "2", "2"]
    assert point(m["nodes"][3]["world"], [0, 0, 0]) == [30, 5, 0]
    assert m["nodes"][3]["ref"] == "custom.dat"


def test_plain_ldr_and_external_assembly(tmp_path):
    (tmp_path / "child.ldr").write_text(
        "0 External\n1 16 0 0 0 1 0 0 0 1 0 0 0 1 3001.dat\n"
    )
    p = tmp_path / "main.ldr"
    p.write_text("0 Main\n1 4 0 0 0 1 0 0 0 1 0 0 0 1 child.ldr\n")
    m = Document(p).manifest()
    assert len(m["dependencies"]) == 2
    assert m["nodes"][1]["id"] == "0/0"


def test_cycle_and_missing_assembly_fail(tmp_path):
    p = tmp_path / "cycle.mpd"
    p.write_text("0 FILE main.ldr\n1 16 0 0 0 1 0 0 0 1 0 0 0 1 main.ldr\n")
    with pytest.raises(ValueError):
        Document(p).manifest()
    p.write_text("0 Example\n1 16 0 0 0 1 0 0 0 1 0 0 0 1 absent.ldr\n")
    with pytest.raises(ValueError, match="Unresolved"):
        Document(p).manifest()


def test_real_model_instances_and_candidates():
    report = inspect(ROOT / "data/models-annotated/106-1.mpd")
    assert report["counts"] == {"assembly": 7, "part": 65}
    assert len([c for c in report["candidates"] if c["ref"] == "4213.dat"]) == 1
    assert report["coverage"]["connectivity"] == "not inferred"
    assert len({n["id"] for n in report["source"]["nodes"]}) == 72


def test_section_export_preserves_author_and_physical_count(tmp_path):
    d = Document(ROOT / "data/models-annotated/928-1.mpd")
    section = "928 - Space Ship - Cargo Hatchway.ldr"
    p = tmp_path / "hatch.mpd"
    d.export_section(section, p)
    m = Document(p).manifest()
    assert len(m["nodes"]) == 2
    assert m["author"] == d.section(section).author
    assert "!LICENSE" in p.read_text()
