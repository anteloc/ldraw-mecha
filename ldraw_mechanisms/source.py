"""pyldraw3 record parsing with explicit physical/assembly instance boundaries.

IDs are type-1 index paths, not Blender names. A source hash makes their lifetime
explicit. Embedded DAT geometry remains a physical leaf, as in ldraw-nova.
"""

from __future__ import annotations

from dataclasses import fields, is_dataclass
from functools import lru_cache
import hashlib
import os
import re
from pathlib import Path
import shutil

from ldraw import Parts, parse_model_result

from .math3d import identity, matmul, pose

ROOT = Path(__file__).resolve().parents[1]


def normalized(s):
    return s.replace("\\", "/").strip().casefold()


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def jsonable(v):
    if hasattr(v, "to_dict"):
        return jsonable(v.to_dict())
    if hasattr(v, "rows"):
        return jsonable(v.rows)
    if all(hasattr(v, a) for a in ("x", "y", "z")):
        return [v.x, v.y, v.z]
    if is_dataclass(v):
        return {f.name: jsonable(getattr(v, f.name)) for f in fields(v)}
    if isinstance(v, dict):
        return {str(k): jsonable(x) for k, x in v.items()}
    if isinstance(v, (list, tuple, set, frozenset)):
        return [jsonable(x) for x in v]
    if isinstance(v, Path):
        return str(v)
    return v


def library_path(value=None):
    value = value or os.environ.get("LDRAW_DIR") or os.environ.get("LDRAWDIR")
    if not value:
        raise ValueError("Pass --library or set LDRAW_DIR / LDRAWDIR")
    path = Path(value).expanduser().resolve()
    if not (path / "parts").is_dir():
        raise ValueError(f"Not an LDraw library: {path}")
    return path


def find_tool(name, value=None, bundled=None):
    """External tool: explicit value, else bin/ (bundled or bin/<name>), else PATH."""
    local = ROOT / "bin" / (bundled or name)
    found = value or (str(local) if os.access(local, os.X_OK) else shutil.which(name))
    if not found:
        raise ValueError(f"{name} not found in bin/ or on PATH: run ./setup-macos.sh (docs/setup.md)")
    return found


def parts_library(value=None, shadow=None):
    lib = library_path(value)
    # Read-through index pattern adapted from ldraw-nova/common.py. Never write
    # parts.lst into the user's official library (also works with read-only mounts).
    cache = Path(os.environ.get("LDRAW_MECHA_CACHE", ROOT / ".cache"))
    target = cache / ("library-" + hashlib.sha256(str(lib).encode()).hexdigest()[:12])
    target.mkdir(parents=True, exist_ok=True)
    for entry in lib.iterdir():
        if entry.name.lower() in {"parts", "p", "ldconfig.ldr"}:
            link = target / entry.name
            if not link.exists():
                link.symlink_to(entry, target_is_directory=entry.is_dir())
    files = sorted((lib / "parts").glob("*.dat"))
    signature = hashlib.sha256(
        "\n".join(
            f"{p.name}:{p.stat().st_size}:{p.stat().st_mtime_ns}" for p in files
        ).encode()
    ).hexdigest()
    index, stamp = target / "parts.lst", target / "signature"
    if not index.exists() or not stamp.exists() or stamp.read_text() != signature:
        rows = []
        for p in files:
            with p.open(encoding="utf-8-sig", errors="replace") as f:
                rows.append(
                    p.name + " " + next(f, "0").strip().removeprefix("0").strip()
                )
        index.write_text("\n".join(rows) + "\n")
        stamp.write_text(signature)
    parts = Parts(index)
    shadows = [Path(shadow)] if shadow else [ROOT / "data/offLibShadow"]
    for path in shadows:
        if path.exists():
            parts.add_connection_shadow(path)
    return parts


@lru_cache(maxsize=4)
def descriptions(path=None):
    path = Path(path or ROOT / "data/part-descriptions-full.tsv")
    if not path.exists():
        return {}
    return {
        normalized(k): v
        for line in path.read_text().splitlines()
        if "\t" in line
        for k, v in [line.split("\t", 1)]
    }


def embedded_alias(title, desc):
    """Library part named by an embedded DAT whose own title is just its number.

    Converted models often embed pre-release parts titled e.g. `18575`; without
    a label they escape role and gear discovery. Annotated titles are kept.
    """
    token = (title or "").strip()
    key = normalized(token + ".dat")
    if re.fullmatch(r"[0-9]+[a-z]?[0-9]*", token, re.I) and key in desc:
        return key
    return None


class Document:
    def __init__(self, path):
        self.path = Path(path).resolve()
        self.dependencies = {}
        self.diagnostics = []
        self.sections = {}
        self.root = self._load(self.path)

    def _load(self, path):
        data = path.read_bytes()
        self.dependencies[str(path)] = hashlib.sha256(data).hexdigest()
        parsed = parse_model_result(
            data.decode("utf-8-sig"), name=path.name, source=path
        )
        diagnostics = [d.to_dict() for d in parsed.diagnostics]
        self.diagnostics.extend(diagnostics)
        if parsed.model is None or any(d["severity"] == "error" for d in diagnostics):
            raise ValueError(f"Invalid LDraw source {path}: {diagnostics[:5]}")
        for model in [parsed.model, *parsed.model.submodels.values()]:
            key = normalized(model.name)
            if key in self.sections and self.sections[key] is not model:
                raise ValueError(f"Duplicate section identity: {model.name}")
            self.sections[key] = model
        return parsed.model

    def section(self, name=None):
        if name is None:
            return self.root
        key = normalized(name)
        if key not in self.sections:
            raise ValueError(f"Unknown section {name!r}")
        return self.sections[key]

    def resolve(self, reference):
        """Load adjacent assemblies once; share resolution with inventory tools."""
        ref = normalized(reference)
        if ref.endswith(".ldr") and ref not in self.sections:
            external = self.path.parent / reference.replace("\\", "/")
            if not external.is_file():
                raise ValueError(f"Unresolved external assembly {reference!r}")
            self.sections[ref] = self._load(external.resolve())
        return self.sections.get(ref)

    def manifest(self, section=None, max_instances=100000):
        selected = self.section(section)
        nodes = []
        desc = descriptions()

        def visit(model, parent_id, world, colour, ancestors):
            key = normalized(model.name)
            if key in ancestors:
                raise ValueError(f"Assembly cycle: {ancestors + [key]}")
            for index, p in enumerate(model.pieces):
                if len(nodes) >= max_instances:
                    raise ValueError(
                        f"Instance budget {max_instances} exceeded; select a section"
                    )
                ref = normalized(p.reference)
                child = self.resolve(p.reference)
                assembly = child is not None and not ref.endswith(".dat")
                local = pose(jsonable(p.position), p.matrix.rows)
                node_id = f"{parent_id}/{index}" if parent_id != "root" else str(index)
                c = str(p.colour.code)
                effective = colour if c == "16" else c
                node = dict(
                    id=node_id,
                    parent=parent_id,
                    ref=p.reference,
                    kind="assembly" if assembly else "part",
                    embedded=child is not None and not assembly,
                    section=model.name,
                    index=index,
                    line=model.source_line_for(p),
                    colour=c,
                    effective_colour=effective,
                    local=local,
                    world=matmul(world, local),
                    description=child.description
                    if child
                    else desc.get(ref, p.reference),
                )
                if node["embedded"]:
                    alias = embedded_alias(child.description, desc)
                    if alias:
                        # Label only: embedded geometry is never substituted.
                        node["library_alias"] = alias
                        node["description"] = desc[alias]
                nodes.append(node)
                if assembly:
                    visit(child, node_id, node["world"], effective, ancestors + [key])

        visit(selected, "root", identity(), "16", [])
        return dict(
            version=1,
            path=str(self.path),
            sha256=sha256(self.path),
            section=selected.name,
            description=selected.description,
            author=selected.author,
            dependencies=self.dependencies.copy(),
            nodes=nodes,
            diagnostics=self.diagnostics,
            coordinate_space="selected section, LDU, -Y up",
        )

    def export_section(self, section, output):
        """Dependency-closed MPD copy; pyldraw3 serializes records and attribution."""
        selected = self.section(section)
        pending, ordered, seen = [selected], [], set()
        while pending:
            m = pending.pop(0)
            if normalized(m.name) in seen:
                continue
            seen.add(normalized(m.name))
            ordered.append(m)
            pending.extend(
                self.sections[normalized(p.reference)]
                for p in m.pieces
                if normalized(p.reference) in self.sections
            )
        from dataclasses import replace

        copy = replace(
            selected, submodels={m.name: replace(m, submodels={}) for m in ordered[1:]}
        )
        Path(output).write_text(copy.to_ldraw() + "\n")


def verify_source(manifest):
    for name, expected in manifest["dependencies"].items():
        if sha256(name) != expected:
            raise ValueError(f"Stale source: {name}; inspect and regenerate the plan")


def _file_blocks(text):
    """Map normalized FILE names to their raw lines (header to the line before the next FILE)."""
    blocks, name, lines = {}, None, []
    for line in text.splitlines():
        m = re.match(r"^0\s+FILE\s+(.+?)\s*$", line)
        if m:
            if name is not None:
                blocks[normalized(name)] = (name, lines)
            name, lines = m.group(1), [line]
        elif name is not None:
            lines.append(line)
    if name is not None:
        blocks[normalized(name)] = (name, lines)
    return blocks


def _references(lines):
    for line in lines:
        tokens = line.split()
        if len(tokens) >= 15 and tokens[0] == "1":
            yield " ".join(tokens[14:])


def _number(v):
    s = f"{v:.10g}"
    return "0" if s in ("-0", "0") else s


def flatten(model, ids, output, *, section=None, name=None, title=None, note=""):
    """Write chosen physical occurrences as one flat FILE in the selection's frame.

    Each occurrence becomes one type-1 line with its composed world matrix and
    effective colour, preceded by a comment naming its original ID. Embedded
    FILE blocks those parts use (and their own sub-files) are copied verbatim.
    The output is re-read: references, colours and matrices must be unchanged.
    Returns the old-to-new ID map, each old ID's 1-based line in the output and
    the verification report.
    """
    model, output = Path(model).resolve(), Path(output).resolve()
    if output == model:
        raise ValueError("Refusing to overwrite the source model")
    manifest = Document(model).manifest(section)
    nodes = {n["id"]: n for n in manifest["nodes"]}
    order = sorted(dict.fromkeys(ids), key=lambda s: [int(x) for x in s.split("/")])
    missing = [i for i in order if i not in nodes]
    if missing:
        raise ValueError(f"Unknown occurrences: {missing[:5]}")
    non_parts = [i for i in order if nodes[i]["kind"] != "part"]
    if non_parts:
        raise ValueError(f"Keep physical leaves only: {non_parts[:5]}")
    blocks = _file_blocks(model.read_text(encoding="utf-8-sig"))
    first = next(iter(blocks.values()), (None, []))[1]
    header = [
        next((ln for ln in first if ln.startswith(p)), None)
        for p in ("0 Author:", "0 !LDRAW_ORG", "0 !LICENSE")
    ]
    name = name or f"{output.stem}.ldr"
    out = [
        f"0 FILE {name}",
        f"0 {title or manifest['description'] + ' - standalone extract'} ({len(order)} parts)",
        f"0 Name: {name}",
        *(v for v in header if v),
        *([f"0 // {note}"] if note else []),
        "",
    ]
    idmap, lines = {}, {}
    for new, old in enumerate(order):
        w = nodes[old]["world"]
        values = [w[0][3], w[1][3], w[2][3], *w[0][:3], *w[1][:3], *w[2][:3]]
        out.append(f"0 // from {old}")
        out.append(
            f"1 {nodes[old]['effective_colour']} "
            + " ".join(_number(v) for v in values)
            + f" {nodes[old]['ref']}"
        )
        idmap[old], lines[old] = str(new), len(out)
    # Embedded FILE closure: blocks referenced by kept parts, then by those blocks.
    pending = [normalized(nodes[i]["ref"]) for i in order if nodes[i]["embedded"]]
    copied = []
    while pending:
        key = pending.pop(0)
        if key in copied or key not in blocks:
            continue
        copied.append(key)
        pending += [normalized(r) for r in _references(blocks[key][1])]
    for key in copied:
        block = blocks[key][1]
        while block and not block[-1].strip():
            block = block[:-1]
        out += ["", *block]
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(out) + "\n")
    new = {n["id"]: n for n in Document(output).manifest()["nodes"]}
    if set(new) != set(idmap.values()):
        raise ValueError("Flattened occurrences differ from the ID map")
    worst = 0.0
    for old, i in idmap.items():
        a, b = nodes[old], new[i]
        if (
            normalized(a["ref"]) != normalized(b["ref"])
            or a["effective_colour"] != b["effective_colour"]
        ):
            raise ValueError(f"{old} -> {i}: reference or colour changed")
        if b["kind"] != "part":
            raise ValueError(f"{old} -> {i}: not a physical leaf")
        worst = max(
            worst,
            max(abs(x - y) for ra, rb in zip(a["world"], b["world"]) for x, y in zip(ra, rb)),
        )
    if worst > 1e-6:
        raise ValueError(f"World matrix changed by {worst}")
    report = dict(
        kept=len(idmap),
        max_world_matrix_error=worst,
        coverage="Every kept leaf re-read from the written file: same reference, effective colour and "
        "world matrix (max error reported)",
        source=str(model),
        source_section=manifest["section"],
        source_sha256=sha256(model),
        output=str(output),
        output_sha256=sha256(output),
        embedded_files=[blocks[k][0] for k in copied],
    )
    return idmap, lines, report
