"""Section-relative extraction must retain its frame as well as its identities."""

import importlib.util
from pathlib import Path

from ldraw_mechanisms.source import Document, sha256


def test_selected_section_preserves_frame_attribution_and_embedded_geometry(tmp_path):
    spec = importlib.util.spec_from_file_location(
        "extract_subsystem", Path(__file__).resolve().parents[1] / "scripts/extract_subsystem.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    source = tmp_path / "model.mpd"
    source.write_text("""0 FILE main.ldr
0 Example
0 Author: Fixture author
0 !LICENSE Redistributable under CCAL version 2.0 : see CAreadme.txt
1 2 100 200 300 0 -1 0 1 0 0 0 0 1 mechanism.ldr
0 FILE mechanism.ldr
0 Mechanism
1 4 3 7 11 0 0 1 0 1 0 -1 0 0 custom.dat
1 14 8 9 10 1 0 0 0 1 0 0 0 1 custom.dat
0 FILE custom.dat
0 Embedded part
3 16 0 0 0 4 0 0 0 4 0
""")
    original = source.read_bytes()
    output = tmp_path / "extract.mpd"
    idmap, report = module.extract(source, ["0"], output, section="mechanism.ldr")
    assert idmap == {"0": "0"}
    assert report["source_section"] == "mechanism.ldr"
    assert report["source_sha256"] == sha256(source)
    assert source.read_bytes() == original
    manifest = Document(output).manifest()
    assert manifest["author"] == "Fixture author"
    assert len(manifest["nodes"]) == 1
    part = manifest["nodes"][0]
    assert part["world"] == [[0, 0, 1, 3], [0, 1, 0, 7], [-1, 0, 0, 11], [0, 0, 0, 1]]
    assert part["effective_colour"] == "4" and part["embedded"]
    assert "3 16 0 0 0 4 0 0 0 4 0" in output.read_text()
    assert "!LICENSE" in output.read_text()
