"""pyldraw3 record parsing with explicit physical/assembly instance boundaries.

IDs are type-1 index paths, not Blender names. A source hash makes their lifetime
explicit. Embedded DAT geometry remains a physical leaf, as in ldraw-nova.
"""

from __future__ import annotations

from dataclasses import fields, is_dataclass
from functools import lru_cache
import hashlib
import os
from pathlib import Path

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
                if ref.endswith(".ldr") and ref not in self.sections:
                    # Standalone LDRs may reference adjacent LDR assemblies.
                    external = self.path.parent / p.reference.replace("\\", "/")
                    if external.is_file():
                        loaded = self._load(external.resolve())
                        self.sections[ref] = loaded
                    else:
                        raise ValueError(
                            f"Unresolved external assembly {p.reference!r}"
                        )
                child = self.sections.get(ref)
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
