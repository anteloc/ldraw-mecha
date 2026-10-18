import json
from pathlib import Path
import sqlite3

import pytest

from ldraw_mechanisms.annotate import annotate
from ldraw_mechanisms.cli import main
from ldraw_mechanisms.source import Document


@pytest.fixture
def metadata(tmp_path):
    database = tmp_path / "catalog.db"
    with sqlite3.connect(database) as db:
        db.execute("CREATE TABLE PARTS_DESCRIPTIONS(part, description)")
        db.executemany(
            "INSERT INTO PARTS_DESCRIPTIONS VALUES (?, ?)",
            [
                ("3022.dat", "Plate  2 x  2"),
                ("3710.DAT", "Plate  1 x  4"),
                ("3788.dat", "Car Mudguard  2 x  4"),
                ("4211.dat", "Car Base  4 x  5"),
                ("s\\part with spaces.dat", "Named subpart"),
            ],
        )
    ldconfig = tmp_path / "LDConfig.ldr"
    ldconfig.write_text(
        "0 Palette\n0 !COLOUR Black CODE 0 VALUE #000000 EDGE #333333\n"
        "0 !COLOUR Trans_Red CODE 36 VALUE #C91A09 EDGE #333333 ALPHA 128\n"
        "0 !COLOUR Main_Colour CODE 16 VALUE #FFFF80 EDGE #333333\n"
    )
    return dict(database=database, ldconfig=ldconfig)


def reference(name="3022.dat", colour="0"):
    return f"1 {colour} 80 8 0 1 0 0 0 1 0 0 0 1 {name}\n"


def test_exact_comments_preserve_source_bytes_and_repeat_safely(tmp_path, metadata):
    source = tmp_path / "original.mpd"
    lines = [
        "0 FILE car.ldr\n",
        "0 Car\n",
        "0 Author: Original Author\n",
        "0 !LICENSE Original license\n",
        "0 // Preserve this unrelated note\n",
        reference(),
        "0 STEP\n",
        reference("3710.dat"),
        reference("3788.dat"),
        reference("4211.dat"),
        "2 24 0 0 0 1 1 1\n",
        "0 NOFILE",
    ]
    original = b"\xef\xbb\xbf" + "".join(lines).replace("\n", "\r\n").encode()
    source.write_bytes(original)
    destination = tmp_path / "annotated" / "car.mpd"
    before_db = metadata["database"].read_bytes()
    report = annotate(source, destination, **metadata)
    expected = original
    for name, description in [
        ("3022.dat", "Plate  2 x  2"),
        ("3710.dat", "Plate  1 x  4"),
        ("3788.dat", "Car Mudguard  2 x  4"),
        ("4211.dat", "Car Base  4 x  5"),
    ]:
        part = reference(name).replace("\n", "\r\n").encode()
        expected = expected.replace(
            part, f"0 // {description} (black)\r\n".encode() + part
        )
    assert destination.read_bytes() == expected
    assert source.read_bytes() == original
    assert metadata["database"].read_bytes() == before_db
    assert report["summary"] == dict(files=1, references=4, added=4, existing=0)
    second = tmp_path / "second.mpd"
    report = annotate(destination, second, **metadata)
    assert second.read_bytes() == expected
    assert report["summary"] == dict(files=1, references=4, added=0, existing=4)


def test_mpd_sections_names_colours_and_identity(tmp_path, metadata):
    source = tmp_path / "original.mpd"
    source.write_text(
        "0 FILE main.ldr\n0 Main\n0 Author: Original\n"
        + reference("child assembly.ldr", "36")
        + "0 FILE child assembly.ldr\n0 Child\n"
        + reference("3022.DAT", "16")
        + reference("S/part with spaces.dat", "36")
        + reference("missing.dat")
        + reference("3710.dat", "999")
        + reference("4211.dat", "0x2ABCDEF").rstrip("\n")
    )
    destination = tmp_path / "annotated.mpd"
    report = annotate(source, destination, **metadata)
    text = destination.read_text()
    assert "0 // Plate  2 x  2 (main_colour)\n" in text
    assert "0 // Named subpart (trans_red)\n" in text
    assert "0 // Plate  1 x  4 (999)\n" in text
    assert "0 // Car Base  4 x  5 (0x2ABCDEF)\n" in text
    assert not text.endswith("\n")
    assert report["files"][0]["unknown_references"] == [
        "child assembly.ldr",
        "missing.dat",
    ]
    assert report["files"][0]["unknown_colours"] == ["0x2ABCDEF", "999"]
    before, after = Document(source).manifest(), Document(destination).manifest()
    assert before["author"] == after["author"] == "Original"
    assert [dict(n, line=None) for n in before["nodes"]] == [
        dict(n, line=None) for n in after["nodes"]
    ]


def test_recursive_directory_and_existing_file_destination_directory(
    tmp_path, metadata
):
    source = tmp_path / "models"
    (source / "nested").mkdir(parents=True)
    for name in ("car.MPD", "nested/child.LDR", "nested/piece.DAT"):
        (source / name).write_text(reference())
    (source / "readme.txt").write_text("untouched")
    output = tmp_path / "copies"
    report = annotate(source, output, **metadata)
    assert report["summary"]["files"] == 3
    assert sorted(
        p.relative_to(output).as_posix() for p in output.rglob("*") if p.is_file()
    ) == [
        "car.MPD",
        "nested/child.LDR",
        "nested/piece.DAT",
    ]
    # Existing output artifacts can be regenerated without accumulating comments.
    annotate(source, output, **metadata)
    assert (output / "car.MPD").read_text().count("0 // ") == 1
    assert (source / "car.MPD").read_text() == reference()
    report = annotate(source / "car.MPD", output, **metadata)
    assert Path(report["output"]) == output / "car.MPD"


@pytest.mark.parametrize("alias", ["same", "symlink", "hardlink", "directory"])
def test_refuse_source_overwrite(tmp_path, metadata, alias):
    source = tmp_path / "model.ldr"
    source.write_text(reference())
    destination = tmp_path / "alias.ldr"
    if alias == "same":
        destination = source
    elif alias == "symlink":
        destination.symlink_to(source)
    elif alias == "hardlink":
        destination.hardlink_to(source)
    else:
        destination = source.parent
    with pytest.raises(ValueError, match="must not overwrite"):
        annotate(source, destination, **metadata)
    assert source.read_text() == reference()


@pytest.mark.parametrize("destination", ["models", "models/annotated"])
def test_refuse_overlapping_trees(tmp_path, metadata, destination):
    source = tmp_path / "models"
    source.mkdir()
    (source / "car.ldr").write_text(reference())
    with pytest.raises(ValueError, match="must not overlap"):
        annotate(source, tmp_path / destination, **metadata)
    assert not (source / "annotated").exists()


def test_invalid_record_keeps_existing_output(tmp_path, metadata, capsys):
    source = tmp_path / "broken.ldr"
    source.write_text(reference() + "1 0 invalid.dat\n")
    output = tmp_path / "annotated.ldr"
    output.write_text("Existing artifact\n")
    assert (
        main(
            [
                "annotate",
                str(source),
                "--output",
                str(output),
                "--database",
                str(metadata["database"]),
                "--ldconfig",
                str(metadata["ldconfig"]),
            ]
        )
        == 2
    )
    assert "Invalid type-1 line" in json.loads(capsys.readouterr().err)["error"]
    assert output.read_text() == "Existing artifact\n"


def test_cli_uses_library_palette_and_emits_json_without_overwriting_model(
    tmp_path, metadata, capsys
):
    library = tmp_path / "library"
    (library / "parts").mkdir(parents=True)
    (library / "LDConfig.ldr").write_bytes(metadata["ldconfig"].read_bytes())
    source = tmp_path / "input.ldr"
    source.write_text(reference())
    output = tmp_path / "annotated.ldr"
    assert (
        main(
            [
                "--library",
                str(library),
                "annotate",
                str(source),
                "--output",
                str(output),
                "--database",
                str(metadata["database"]),
            ]
        )
        == 0
    )
    report = json.loads(capsys.readouterr().out)
    assert report["summary"]["added"] == 1
    assert output.read_text() == "0 // Plate  2 x  2 (black)\n" + reference()


@pytest.mark.parametrize("missing", ["database", "ldconfig"])
def test_missing_metadata_fails_without_creating_files(tmp_path, metadata, missing):
    source = tmp_path / "model.ldr"
    source.write_text(reference())
    metadata[missing] = tmp_path / "missing"
    output = tmp_path / "annotated.ldr"
    with pytest.raises((ValueError, OSError)):
        annotate(source, output, **metadata)
    assert not output.exists()
    assert not metadata[missing].exists()
