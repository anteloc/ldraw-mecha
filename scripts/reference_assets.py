"""Copy selected working artifacts into examples; verify or reuse them without output/.

Snapshots retain original bytes, paths and provenance. Only an explicitly written
working plan relocates source paths; it never changes coordinates or identities.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import sys
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = Path("examples/reference")


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")


def copy_assets(root=ROOT):
    """Idempotent copy with explicit selection; refuse to replace a changed snapshot."""
    base = root / ARCHIVE
    selection = read(base / "selection.json")
    manifest_path = base / "manifest.json"
    previous = read(manifest_path).get("files", {}) if manifest_path.exists() else {}
    selected = {}
    for case, patterns in selection["bundles"].items():
        if Path(case).name != case:
            raise ValueError(f"Bundle must be a directory name: {case}")
        source = root / "output" / case
        for pattern in patterns:
            if Path(pattern).is_absolute() or ".." in Path(pattern).parts:
                raise ValueError(f"Pattern must stay within its bundle: {pattern}")
            matches = [p for p in source.glob(pattern) if p.is_file()]
            if not matches:
                raise ValueError(f"Selection matches nothing: {source / pattern}")
            for path in matches:
                if path.is_symlink() or not path.resolve().is_relative_to(source.resolve()):
                    raise ValueError(f"Refusing source outside the bundle: {path}")
                selected[str(Path(case) / path.relative_to(source))] = path
    # Preflight the entire selection before any mutation.
    for name, source in selected.items():
        target = base / name
        if target.is_symlink():
            raise ValueError(f"Refusing symlink destination: {target}")
        if target.exists():
            old = previous.get(name, {})
            if sha256(source) != old.get("source_sha256", sha256(target)) or sha256(target) != old.get("sha256", sha256(source)):
                raise ValueError(f"Snapshot differs: {target}; select a new version instead of overwriting")
    entries = dict(previous)
    for name, source in sorted(selected.items()):
        target = base / name
        if not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
        entry = dict(previous.get(name, {}))
        entry.update(source=str(source.relative_to(root)), source_sha256=sha256(source),
                     sha256=sha256(target), bytes=target.stat().st_size)
        entries[name] = entry
    write(manifest_path, dict(version=1, files=entries))
    return dict(files=len(entries), bytes=sum(e["bytes"] for e in entries.values()))


def repository_path(original, root=ROOT):
    """Map a recorded repository source path to archived output or current tracked data."""
    text = str(original).replace("\\", "/")
    for prefix in ("examples/reference/", "output/", "data/"):
        marker = "/" + prefix
        if text.startswith(prefix):
            relative = text
            break
        if marker in text:
            relative = prefix + text.split(marker, 1)[1]
            break
    else:
        raise ValueError(f"Source is outside the archived repository data: {original}")
    if relative.startswith("output/"):
        relative = str(ARCHIVE / relative[len("output/"):])
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()) or not path.is_file():
        raise ValueError(f"Missing archived source for {original}: {path}")
    return path


def load_plan(path, root=ROOT):
    """Read a snapshot and relocate only source filenames in memory, checking hashes."""
    plan = read(path)
    source = plan["source"]
    source["path"] = str(repository_path(source["path"], root))
    dependencies = {}
    for name, digest in source["dependencies"].items():
        resolved = repository_path(name, root)
        if sha256(resolved) != digest:
            raise ValueError(f"Archived source hash differs: {resolved}")
        dependencies[str(resolved)] = digest
    if sha256(source["path"]) != source["sha256"]:
        raise ValueError(f"Archived main source hash differs: {source['path']}")
    source["dependencies"] = dependencies
    return plan


def check(root=ROOT):
    """Check snapshots and published links without reading the working output tree."""
    base = root / ARCHIVE
    entries = read(base / "manifest.json")["files"]
    for name, entry in entries.items():
        path = base / name
        if not path.is_file() or sha256(path) != entry["sha256"]:
            raise ValueError(f"Missing/changed snapshot (fetch Git LFS if needed): {path}")
    links, plans = 0, 0
    pages = list((root / "docs").rglob("*.md")) + list((root / "examples").rglob("*.md"))
    pages += [root / "README.md", root / "instructions.md"]
    for page in pages:
        for target in re.findall(r"\[[^\]]*\]\(([^)]+)\)", page.read_text()):
            if "://" in target or target.startswith("#"):
                continue
            target = unquote(target.split("#", 1)[0].strip("<>"))
            path = (page.parent / target).resolve()
            if path.is_relative_to(root / "output"):
                raise ValueError(f"Published link points to disposable output: {page}: {target}")
            if not path.exists():
                raise ValueError(f"Broken local link: {page}: {target}")
            if path.is_relative_to(base) and path.is_file() and path.name not in {"README.md", "manifest.json", "selection.json"}:
                if str(path.relative_to(base)) not in entries:
                    raise ValueError(f"Linked artifact is not in the archive manifest: {path}")
            links += 1
    for name in entries:
        if Path(name).name == "plan.json":
            load_plan(base / name, root)
            plans += 1
    return dict(files=len(entries), links=links, source_plans=plans,
                bytes=sum(e["bytes"] for e in entries.values()))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="command", required=True)
    sub.add_parser("copy", help="Copy the reviewed selection from output; never replace changed snapshots")
    sub.add_parser("check", help="Check archive hashes, published links and source dependencies")
    p = sub.add_parser("plan", help="Write a working plan with source paths resolved in this checkout")
    p.add_argument("snapshot", type=Path)
    p.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    try:
        if args.command == "copy":
            result = copy_assets()
        elif args.command == "check":
            result = check()
        else:
            dest = args.output.resolve()
            if not dest.is_relative_to(ROOT / "output") or dest.exists():
                raise ValueError("Write the working plan to a new file under output/")
            plan = load_plan(args.snapshot)
            write(dest, plan)
            result = dict(plan=str(dest))
        print(json.dumps(result, indent=2))
    except (OSError, ValueError, KeyError) as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
