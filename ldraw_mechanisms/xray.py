"""Render look boards with the globally installed ldraw-xray CLI.

ldraw-xray is never imported or installed: each board is a recipe run as
`ldraw-xray board run`. Renders use a flat copy of the selected section, one
type-1 line per physical occurrence with its world matrix in the section frame,
so every occurrence is exactly one `line:` term and plan origins and axes pass
through unchanged; only radians become degrees.
"""

from concurrent.futures import ThreadPoolExecutor
import json
import math
from pathlib import Path
import re
import shutil
import subprocess

from . import plan as contract
from .audit import boundary
from .constraints import KINDS, instances
from .math3d import unit
from .source import Document, flatten, verify_source

MAX_POSES = 8
WORKERS = 4
CHECK = [
    "Coloured = exactly what moves: mirror twins alike; nothing coloured sits on a grey axle or pin off the rod",
    "The green rod passes through the hinge barrel, axle, pin or turntable centre",
    "Positive poses turn the intended way (compare each pose with rest)",
    "Limit poses do not cut through grey neighbours",
]
CHECK_SELECTION = [
    "Coloured = exactly the parts you meant: mirror twins alike, nothing missing behind the grey"
]


def _slug(name):
    return re.sub(r"[^a-z0-9]+", "-", re.sub(r"\.ldr$", "", name.lower())).strip("-")


def executable():
    found = shutil.which("ldraw-xray")
    if not found:
        raise ValueError(
            "ldraw-xray is not on PATH: run `ldraw-xray doctor` after installing it, "
            "or record that xray evidence is unavailable and continue numerically"
        )
    return found


def selector(lines):
    """Compressed `line:` selector, e.g. line:12-15,20."""
    out, span = [], []
    for n in sorted(set(lines)):
        if span and n != span[-1] + 1:
            out.append(span)
            span = []
        span.append(n)
    out.append(span)
    return "line:" + ",".join(
        str(s[0]) if len(s) == 1 else f"{s[0]}-{s[-1]}" for s in out if s
    )


def render_source(model, section, xray_dir):
    """Flat render copy of every physical occurrence; returns its path and line map."""
    manifest = Document(model).manifest(section)
    parts = [n["id"] for n in manifest["nodes"] if n["kind"] == "part"]
    path = (Path(xray_dir) / f"{_slug(manifest['section'])}.flat.mpd").resolve()
    _, lines, _ = flatten(
        model,
        parts,
        path,
        section=section,
        name=path.with_suffix(".ldr").name,
        title=f"{manifest['description']} - xray render copy",
        note="Derived by ldraw-mecha xray for rendering only: one line per occurrence "
        "with its world matrix in the selected section frame; original IDs precede each line.",
    )
    return manifest, path, lines


def along(axis):
    """The axis-aligned view whose line of sight is closest to the axis."""
    return ("right", "top", "front")[max(range(3), key=lambda i: abs(axis[i]))]


def recipe(source, title, select, axis=None, degrees=(), closeup=True):
    """Moving set coloured and edged, everything else ghosted; poses in close-up.

    Without close-up (no measurable bounds), poses share one whole-block camera.
    """
    rod = [dict(layer="axis", **axis)] if axis else []
    marks = [dict(layer="highlight", select=select), dict(layer="ghost")]
    second = along(axis["direction"]) if axis else "front"
    panels = [
        dict(label="Moving set coloured, rest ghosted", view="home", layers=marks + rod),
        dict(
            label=f"Same, {second} view" + (" (along the axis)" if axis else ""),
            view=second,
            layers=marks + rod,
        ),
    ]
    for a in degrees:
        pose = [dict(layer="pose", select=select, angle=a, **axis), *rod, *marks]
        panels.append(
            dict(
                label=f"Pose {a:g} degrees",
                view="home",
                layers=[dict(layer="closeup", select=select, margin=2.0), *pose],
            )
            if closeup
            else dict(label=f"Pose {a:g} degrees", camera=dict(fixed="home"), layers=pose)
        )
    return dict(source=str(source), title=title[:120], panels=panels)


def run(spec, output):
    """Render one recipe; return its mosaic and passed-through notes, or an error."""
    output = Path(output)
    path = output.with_name(output.name + ".recipe.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(spec, indent=2) + "\n")
    done = subprocess.run(
        [executable(), "board", "run", str(path), "--output", str(output), "--force"],
        capture_output=True,
        text=True,
    )
    if done.returncode:
        try:
            error = json.loads(done.stderr)["error"]
        except (ValueError, KeyError, TypeError):
            error = done.stderr.strip() or f"exit {done.returncode}"
        return dict(error=error)
    result = json.loads(done.stdout)
    notes = []
    for image in result["images"]:
        for n in image.get("notes", []) + image.get("warnings", []):
            if n not in notes:
                notes.append(n)
    return dict(image=result.get("mosaic"), panels=len(result["images"]), notes=notes)


def look(source, name, title, ids, lines, base, axis=None, degrees=(), notes=(), embedded=()):
    select = selector(lines[i] for i in ids)
    board = dict(
        board=name,
        select=select,
        degrees=[round(a, 3) for a in degrees],
        check=CHECK if axis else CHECK_SELECTION,
        notes=list(notes),
    )
    # xray measures library geometry only; embedded parts cannot frame a close-up.
    closeup = not set(ids) <= set(embedded)
    rendered = run(recipe(source, title, select, axis, degrees, closeup), Path(base) / name)
    if closeup and "No measurable geometry" in rendered.get("error", ""):
        closeup = False
        rendered = run(recipe(source, title, select, axis, degrees, False), Path(base) / name)
    if degrees and not closeup:
        board["notes"].append(
            "The moving set has no measurable bounds (embedded or unknown parts): "
            "poses use one whole-block camera instead of a close-up"
        )
    rendered["notes"] = board["notes"] + rendered.get("notes", [])
    board.update(rendered)
    return board


def _controls(plan, signal):
    out = set()
    for ref in plan["signals"][signal]["variables"].values():
        kind, name = ref.split(":", 1)
        out |= {name} if kind == "control" else _controls(plan, name)
    return out


def body_values(plan, name):
    """Body signal at rest and at each driving control's min/default/max."""
    signal = plan["bodies"][name]["signal"]
    values = {0.0}
    for control in sorted(_controls(plan, signal)):
        c = plan["controls"][control]
        for v in (c["min"], c["default"], c["max"]):
            values.add(contract.evaluate(plan, {control: v})["signals"][signal])
    return sorted(values)


def poses(values):
    """Degrees to show: full turns as 0/45/90, otherwise at most MAX_POSES values.

    Angles wrap into [-180, 180) so a signal near 2*pi reads as a small turn.
    """
    if values[-1] - values[0] >= 2 * math.pi - 1e-9:
        return [0.0, 45.0, 90.0]
    if len(values) > MAX_POSES:
        step = (len(values) - 1) / (MAX_POSES - 1)
        values = [values[round(i * step)] for i in range(MAX_POSES)]
    return sorted({(math.degrees(v) + 180) % 360 - 180 for v in values})


def descendants(plan, name):
    out = [name]
    for child, b in plan["bodies"].items():
        if b.get("parent") == name:
            out += descendants(plan, child)
    return out


def _result(manifest, path, boards, **extra):
    errors = [dict(board=b["board"], error=b.pop("error")) for b in boards if "error" in b]
    return dict(
        source=manifest["path"],
        section=manifest["section"],
        render_source=str(path),
        boards=boards,
        **extra,
        errors=errors,
        passed=not errors,
        notes=[
            "Open each board's image and answer its check list; cite xray/<board>/mosaic.png with what it showed",
            "Renders are static evidence, not proof of clearance or engagement",
        ],
    )


def study(
    model,
    ids,
    *,
    section=None,
    origin=None,
    axis=None,
    angles=None,
    xray_dir,
    name=None,
    plan=None,
):
    """Look at candidate occurrences, optionally posed about a section-frame axis.

    With a plan, the candidate is also audited as one body on that axis against
    the study's contacts, so a wrong grouping shows before it is authored.
    """
    if (origin is None) != (axis is None):
        raise ValueError("--point and --direction must be given together")
    if angles and origin is None:
        raise ValueError("--angles needs --point and --direction")
    if angles and len(angles) > MAX_POSES:
        raise ValueError(f"At most {MAX_POSES} angles fit one board")
    executable()
    manifest, path, lines = render_source(model, section, xray_dir)
    unknown = [i for i in ids if i not in lines]
    if unknown:
        raise ValueError(
            f"Not physical occurrences of {manifest['section']!r}: {unknown[:10]}"
        )
    line = None if origin is None else dict(point=list(origin), direction=unit(axis))
    degrees = list(angles or [0, 45, 90]) if line else []
    name = name or "look-" + _slug(ids[0].replace("/", "-"))
    extra = {}
    if plan is not None and line:
        chosen = set(ids)
        bodies = {
            n: dict(b, instances=[i for i in b["instances"] if i not in chosen])
            for n, b in plan["bodies"].items()
        }
        bodies["candidate"] = dict(
            kind="revolute", instances=sorted(chosen), origin=line["point"], axis=line["direction"]
        )
        declared = [instances(c) for c in plan["checks"] if c["kind"] in KINDS]
        edges = boundary(bodies, plan.get("connections", {}), declared)
        extra["boundary"] = [g for g in edges["flagged"] if "candidate" in g["bodies"]]
    embedded = {n["id"] for n in manifest["nodes"] if n.get("embedded")}
    title = f"{manifest['section']}: {name}"
    board = look(path, name, title, ids, lines, xray_dir, line, degrees, (), embedded)
    return _result(manifest, path, [board], **extra)


def review(plan, bodies=None, *, xray_dir):
    """Look boards for authored bodies: each body posed with its descendants."""
    source = plan["source"]
    verify_source(source)
    unknown = sorted(set(bodies or ()) - set(plan["bodies"]))
    if unknown:
        raise ValueError(f"Unknown bodies {unknown}; bodies: {sorted(plan['bodies'])}")
    executable()
    manifest, path, lines = render_source(source["path"], source["section"], xray_dir)
    embedded = {n["id"] for n in manifest["nodes"] if n.get("embedded")}
    jobs = []
    for name in bodies or [n for n, b in plan["bodies"].items() if b["kind"] != "fixed"]:
        b = plan["bodies"][name]
        moving = [i for d in descendants(plan, name) for i in plan["bodies"][d]["instances"]]
        notes = []
        if len(moving) > len(b["instances"]):
            notes.append("Descendant bodies ride along at their rest pose")
        if b.get("parent"):
            notes.append(f"Posed about its rest-frame axis; parent {b['parent']!r} stays at rest")
        axis, degrees = None, []
        if b["kind"] in ("revolute", "prismatic", "stretch"):
            axis = dict(point=b["origin"], direction=unit(b["axis"]))
        if b["kind"] == "revolute":
            degrees = poses(body_values(plan, name))
        elif axis:
            notes.append("xray cannot translate or scale parts: axis and selection only")
        title = f"{name} ({b['kind']})"
        jobs.append(
            (path, _slug(name), title, moving, lines, xray_dir, axis, degrees, notes, embedded)
        )
    # Each board is its own LeoCAD process; a few in parallel cut wall time.
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        boards = list(pool.map(lambda job: look(*job), jobs))
    return _result(manifest, path, boards)
