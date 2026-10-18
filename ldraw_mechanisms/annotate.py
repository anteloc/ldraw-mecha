"""Add part/colour comments to copies of LDraw sources, without reserializing them.

Implements the annotation workflow of ldraw-lib/scripts/add_parts_descriptions.py
using this repository's catalog and pyldraw3 record parser.
"""

from pathlib import Path
import sqlite3
import tempfile

from ldraw.errors import PartError
from ldraw.part import parse_ldraw_line

from .source import ROOT, library_path, normalized


def _descriptions(path):
    if not path.is_file():
        raise ValueError(f"Missing description database: {path}")
    try:
        connection = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)
        try:
            return {
                normalized(part): description
                for part, description in connection.execute(
                    "SELECT part, description FROM PARTS_DESCRIPTIONS"
                )
                if description
            }
        finally:
            connection.close()
    except sqlite3.Error as exc:
        raise ValueError(f"Cannot read part descriptions from {path}: {exc}") from exc


def _colours(path):
    colours = {}
    for number, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
        if line.split()[:2] != ["0", "!COLOUR"]:
            continue
        fields = parse_ldraw_line(line).text.split()
        try:
            code = str(int(fields[fields.index("CODE") + 1]))
            colours[code] = fields[0].lower()
        except (ValueError, IndexError) as exc:
            raise ValueError(f"Invalid !COLOUR definition in {path}:{number}") from exc
    if not colours:
        raise ValueError(f"No !COLOUR definitions in {path}")
    return colours


def _annotated_bytes(source, descriptions, colours):
    data = source.read_bytes()
    bom = b"\xef\xbb\xbf" if data.startswith(b"\xef\xbb\xbf") else b""
    lines = data.decode("utf-8-sig").splitlines(keepends=True)
    default_ending = next(
        (
            line[len(line.rstrip("\r\n")) :]
            for line in lines
            if line.endswith(("\r", "\n"))
        ),
        "\n",
    )
    output = []
    references = added = existing = 0
    unknown = set()
    unknown_colours = set()
    for index, line in enumerate(lines):
        fields = line.split(maxsplit=2)
        if fields and fields[0] == "1":
            try:
                piece = parse_ldraw_line(line)
            except (PartError, ValueError) as exc:
                raise ValueError(
                    f"Invalid type-1 line in {source}:{index + 1}: {exc}"
                ) from exc
            references += 1
            reference = normalized(piece.reference)
            description = descriptions.get(reference)
            if description is None:
                unknown.add(reference)
            else:
                # Keep the literal token for unknown/direct colours, as the
                # original annotator does; colour 16 remains inherited colour.
                colour = colours.get(str(piece.colour.code), fields[1])
                if str(piece.colour.code) not in colours:
                    unknown_colours.add(fields[1])
                comment = f"0 // {description} ({colour})"
                if index and lines[index - 1].rstrip("\r\n") == comment:
                    existing += 1
                else:
                    ending = line[len(line.rstrip("\r\n")) :] or default_ending
                    output.append(comment + ending)
                    added += 1
        output.append(line)
    return bom + "".join(output).encode("utf-8"), dict(
        source=str(source),
        references=references,
        added=added,
        existing=existing,
        unknown_references=sorted(unknown),
        unknown_colours=sorted(unknown_colours),
    )


def annotate(source, output, *, database=None, ldconfig=None, library=None):
    """Annotate one file or a recursive .ldr/.mpd/.dat tree into separate copies.

    An existing output directory receives a single file under its original name.
    Directory trees must not overlap. Matching comments are kept on repeat runs;
    unknown references (including assemblies) are unchanged and reported.
    """
    source = Path(source).expanduser().resolve()
    output = Path(output).expanduser().resolve()
    if source.is_dir():
        if source.is_relative_to(output) or output.is_relative_to(source):
            raise ValueError(
                "Annotation input and output directory trees must not overlap"
            )
        if output.exists() and not output.is_dir():
            raise ValueError("Directory input requires a directory output")
        files = sorted(
            path
            for path in source.rglob("*")
            if path.is_file() and path.suffix.lower() in {".ldr", ".mpd", ".dat"}
        )
        pairs = [
            (path, (output / path.relative_to(source)).resolve()) for path in files
        ]
    elif source.is_file():
        if output.is_dir():
            output = (output / source.name).resolve()
        pairs = [(source, output)]
    else:
        raise ValueError(f"Missing LDraw source file or directory: {source}")
    if not pairs:
        raise ValueError(f"No LDraw files in {source}")

    database = Path(database or ROOT / "data/ldraw-info.db").expanduser().resolve()
    ldconfig = (
        Path(ldconfig).expanduser().resolve()
        if ldconfig
        else library_path(library) / "LDConfig.ldr"
    )
    # Check the whole batch before writing, including symlink/hardlink aliases
    # and metadata inputs. Never truncate a source while producing a copy.
    protected = {path.resolve() for path, _ in pairs} | {database, ldconfig}
    identities = {(p.stat().st_dev, p.stat().st_ino) for p in protected if p.exists()}
    targets = set()
    for _, target in pairs:
        if target in protected or (
            target.exists()
            and (target.stat().st_dev, target.stat().st_ino) in identities
        ):
            raise ValueError(
                f"Annotation must not overwrite source or metadata inputs: {target}"
            )
        if target in targets:
            raise ValueError(f"Multiple inputs map to the same output: {target}")
        if target.exists() and not target.is_file():
            raise ValueError(f"Output must be a file: {target}")
        targets.add(target)

    descriptions = _descriptions(database)
    colours = _colours(ldconfig)
    reports = []
    for path, target in pairs:
        data, report = _annotated_bytes(path, descriptions, colours)
        target.parent.mkdir(parents=True, exist_ok=True)
        # A parse/write error must not leave a truncated destination file.
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as stream:
                temporary = Path(stream.name)
                stream.write(data)
            temporary.replace(target)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
        reports.append(dict(report, output=str(target)))
    return dict(
        source=str(source),
        output=str(output),
        database=str(database),
        ldconfig=str(ldconfig),
        summary={
            "files": len(reports),
            **{
                key: sum(r[key] for r in reports)
                for key in ("references", "added", "existing")
            },
        },
        files=reports,
    )
