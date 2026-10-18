import json

import pytest

from ldraw_mechanisms.annotate import annotate_semantics
from ldraw_mechanisms.cli import main
from ldraw_mechanisms.source import Document


PART = "1 0 80 8 0 1 0 0 0 1 0 0 0 1 3022.dat\n"


def test_semantics_change_only_selected_titles_and_preserve_occurrences(tmp_path):
    source = tmp_path / "parts.mpd"
    raw = (
        "0 FILE main.ldr\n0 main\n0 Name: main.ldr\n0 Author: Original Author\n"
        "0 !LICENSE Original license\n"
        "1 16 0 0 0 1 0 0 0 1 0 0 0 1 child assembly.ldr\n"
        "0 STEP\n0 FILE child assembly.ldr\n0 child\n"
        "0 // Plate  2 x  2 (black)\n"
        + PART
        + "0 FILE unused.ldr\n0 Already rich description of a spare black plate\n"
        + PART.rstrip("\n")
    )
    original = b"\xef\xbb\xbf" + raw.replace("\n", "\r\n").encode()
    source.write_bytes(original)
    output = tmp_path / "finished.mpd"
    descriptions = {
        "main.ldr": "Small display model containing a black plate assembly",
        "child assembly.ldr": "Base assembly: one black 2 x 2 plate",
    }
    report = annotate_semantics(source, output, descriptions)
    expected = original.replace(
        b"0 main\r\n", ("0 " + descriptions["main.ldr"] + "\r\n").encode()
    ).replace(
        b"0 child\r\n", ("0 " + descriptions["child assembly.ldr"] + "\r\n").encode()
    )
    assert output.read_bytes() == expected
    assert source.read_bytes() == original
    assert report["updated_sections"] == ["child assembly.ldr", "main.ldr"]
    assert report["preserved_sections"] == ["unused.ldr"]
    before, after = Document(source).manifest(), Document(output).manifest()
    assert before["author"] == after["author"] == "Original Author"
    assert after["description"] == descriptions["main.ldr"]
    assert [dict(n, line=None, description=None) for n in before["nodes"]] == [
        dict(n, line=None, description=None) for n in after["nodes"]
    ]
    repeated = tmp_path / "repeated.mpd"
    assert annotate_semantics(output, repeated, descriptions)["updated_sections"] == []
    assert repeated.read_bytes() == expected


@pytest.mark.parametrize(
    "prefix",
    [
        "0 Name:plain.ldr\n0 Author:Test\n",
        "0 !LICENSE Keep this\n",
        "0 // Plate  2 x  2 (black)\n",
        "0 STEP\n",
        "0 BFC CERTIFY CCW\n",
        "",
        "\n",
    ],
)
def test_missing_plain_header_is_inserted_without_erasing_metadata_or_parts(
    tmp_path, prefix
):
    source = tmp_path / "plain.ldr"
    original = prefix + PART
    source.write_text(original)
    output = tmp_path / "output.ldr"
    annotate_semantics(
        source, output, {"plain.ldr": "Black plate forming a small base"}
    )
    assert output.read_text() == "0 Black plate forming a small base\n" + original
    assert source.read_text() == original


def test_mpd_preamble_and_adjacent_empty_sections_are_preserved(tmp_path):
    source = tmp_path / "source.mpd"
    original = "0 Keep this preamble\n0 FILE empty.ldr\n0 FILE last.ldr"
    source.write_text(original)
    output = tmp_path / "out.mpd"
    annotate_semantics(
        source,
        output,
        {
            "empty.ldr": "Empty placeholder assembly with no parts",
            "last.ldr": "Second empty placeholder assembly",
        },
    )
    assert output.read_text() == (
        "0 Keep this preamble\n0 FILE empty.ldr\n"
        "0 Empty placeholder assembly with no parts\n0 FILE last.ldr\n"
        "0 Second empty placeholder assembly\n"
    )


@pytest.mark.parametrize(
    "descriptions",
    [
        {},
        [],
        {"plain.ldr": ""},
        {"plain.ldr": None},
        {"plain.ldr": "Two\nlines"},
        {"plain.ldr": "Two\r lines"},
        {"plain.ldr": "Two\u2028lines"},
        {"plain.ldr": "!LICENSE changed"},
        {"plain.ldr": "// A part annotation"},
        {"plain.ldr": "0 Already prefixed"},
        {"plain.ldr": "Author: Someone else"},
        {"wrong.ldr": "A descriptive title"},
    ],
)
def test_invalid_semantic_input_leaves_destination_untouched(tmp_path, descriptions):
    source = tmp_path / "plain.ldr"
    source.write_text("0 Original title\n" + PART)
    output = tmp_path / "out.ldr"
    output.write_text("Existing artifact\n")
    with pytest.raises(ValueError):
        annotate_semantics(source, output, descriptions)
    assert output.read_text() == "Existing artifact\n"


@pytest.mark.parametrize("alias", ["same", "symlink", "hardlink"])
def test_semantics_never_overwrite_the_input(tmp_path, alias):
    source = tmp_path / "plain.ldr"
    original = "0 Original title\n" + PART
    source.write_text(original)
    output = tmp_path / "alias.ldr"
    if alias == "same":
        output = source
    elif alias == "symlink":
        output.symlink_to(source)
    else:
        output.hardlink_to(source)
    with pytest.raises(ValueError, match="must not overwrite"):
        annotate_semantics(source, output, {"plain.ldr": "Black plate base"})
    assert source.read_text() == original


def test_cli_applies_authored_descriptions_without_library_or_catalog(tmp_path, capsys):
    source = tmp_path / "model.mpd"
    source.write_text("0 FILE main.ldr\n0 main\n0 // Plate  2 x  2 (black)\n" + PART)
    mapping = tmp_path / "descriptions.json"
    mapping.write_text(json.dumps({"main.ldr": "Black plate forming a small base"}))
    output = tmp_path / "finished.mpd"
    assert (
        main(
            [
                "annotate-semantics",
                str(source),
                "--descriptions",
                str(mapping),
                "--output",
                str(output),
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)["updated_sections"] == ["main.ldr"]
    assert output.read_text() == (
        "0 FILE main.ldr\n0 Black plate forming a small base\n"
        "0 // Plate  2 x  2 (black)\n" + PART
    )
