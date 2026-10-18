"""Add part comments and agent-authored semantics without reserializing sources.

Implements the annotation workflow of ldraw-lib/scripts/add_parts_descriptions.py
using this repository's catalog and pyldraw3 record parser.
"""

from pathlib import Path
import sqlite3
import tempfile

from ldraw import parse_model_result
from ldraw.errors import PartError
from ldraw.lines import Comment
from ldraw.part import parse_ldraw_line
from ldraw.utils import ldraw_file_name

from .source import ROOT, library_path, normalized


def _write_copy(target, data):
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(data)
        temporary.replace(target)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


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
        # A parse/write error must not leave a truncated destination file.
        _write_copy(target, data)
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
        next_step=(
            "For an unannotated-model pipeline, the agent must now inspect this copy "
            "and author rich single-line descriptions for the model and its existing "
            "submodels, then apply them with annotate-semantics. Next, review hierarchy "
            "coverage and create/describe missing submodels or nested submodels when "
            "supported, verifying physical occurrence preservation before prepare. "
            "Preserve existing rich descriptions; do not enrich previously annotated "
            "models unless requested. Part annotation alone does not complete semantics."
        ),
    )


def _is_description(line):
    """Distinguish an ordinary title from attribution, part comments and commands."""
    record = parse_ldraw_line(line)
    if not isinstance(record, Comment) or not record.text:
        return False
    first = record.text.split()[0].upper()
    return not record.text.upper().startswith(
        ("//", "NAME:", "AUTHOR:")
    ) and first not in {
        "0",
        "NAME:",
        "AUTHOR:",
        "BFC",
        "FILE",
        "NOFILE",
        "STEP",
        "ROTSTEP",
        "WRITE",
        "PRINT",
        "SAVE",
        "CLEAR",
        "PAUSE",
    }


def annotate_semantics(source, output, descriptions):
    """Apply explicitly authored section descriptions to a separate source copy.

    Keys are exact FILE names (the input basename for a plain LDR/DAT).
    Unlisted sections are preserved. This validates placement and single-line
    syntax, not semantic richness, factual accuracy or completeness.
    """
    source = Path(source).expanduser().resolve()
    target = Path(output).expanduser().resolve()
    if target.is_dir():
        target = (target / source.name).resolve()
    if target == source or (target.exists() and target.samefile(source)):
        raise ValueError("Semantic annotation must not overwrite its source input")
    if not isinstance(descriptions, dict) or not descriptions:
        raise ValueError(
            "Descriptions must be a nonempty object mapping section names to text"
        )
    for name, description in descriptions.items():
        if (
            not isinstance(name, str)
            or not isinstance(description, str)
            or not description.strip()
            or len(description.splitlines()) != 1
            or any(ord(char) < 32 for char in description)
            or not _is_description("0 " + description.strip())
        ):
            raise ValueError(
                f"Description for {name!r} must be one nonempty line of plain text"
            )

    data = source.read_bytes()
    text = data.decode("utf-8-sig")
    parsed = parse_model_result(text, name=source.name, source=source)
    if parsed.model is None or not parsed.valid:
        raise ValueError(
            f"Invalid LDraw source {source}: {[d.to_dict() for d in parsed.diagnostics][:5]}"
        )
    lines = text.splitlines(keepends=True)
    # pyldraw3 supplies section identity; offsets allow surgical header edits
    # without serializing transforms, comments or MPD metadata again.
    starts = {
        name: index + 1
        for index, line in enumerate(lines)
        if (name := ldraw_file_name(line)) is not None
    }
    if not starts:
        starts = {parsed.model.name: 0}
    unknown = descriptions.keys() - starts.keys()
    if unknown:
        raise ValueError(f"Unknown section names: {sorted(unknown)}")
    default_ending = next(
        (
            line[len(line.rstrip("\r\n")) :]
            for line in lines
            if line.endswith(("\r", "\n"))
        ),
        "\n",
    )
    changes = []
    # Work from the end so insertions cannot move a later section's offset.
    for name, index in sorted(starts.items(), key=lambda item: item[1], reverse=True):
        if name not in descriptions:
            continue
        description = descriptions[name].strip()
        old = lines[index] if index < len(lines) else ""
        replace = bool(old) and _is_description(old)
        ending = old[len(old.rstrip("\r\n")) :] if replace else default_ending
        new = "0 " + description + ending
        if replace and old == new:
            continue
        if index and not lines[index - 1].endswith(("\r", "\n")):
            lines[index - 1] += default_ending
        lines[index : index + int(replace)] = [new]
        changes.append(name)
    bom = b"\xef\xbb\xbf" if data.startswith(b"\xef\xbb\xbf") else b""
    _write_copy(target, bom + "".join(lines).encode("utf-8"))
    return dict(
        source=str(source),
        output=str(target),
        updated_sections=sorted(changes),
        preserved_sections=sorted(starts.keys() - set(changes)),
        coverage="Applied agent-authored text; the agent must review semantic accuracy and coverage",
        next_step=(
            "For an originally unannotated model, the agent must now review whether "
            "the root and submodel hierarchy adequately express its semantic assemblies, "
            "including flat models. Infer, create and richly describe missing submodels "
            "and nested submodels where supported; otherwise record why the hierarchy "
            "is sufficient. Record grouping evidence and an old-to-new occurrence map "
            "for any regrouping; verify every physical part's reference, effective colour "
            "and world transform before prepare. See docs/workflow.md#review-and-enrich-the-hierarchy. "
            "Do not regroup previously annotated models unless requested."
        ),
    )
