"""Translate occurrence IDs and plan joints into ldraw-xray CLI arguments.

ldraw-xray is an external, globally installed CLI. This module only prints
commands (and writes recipe files for `ldraw-xray board run`) for agents to
run; it never imports or executes the renderer. Both
tools number source lines from 1 across the whole file. An xray `line:` term
selects direct placements of the rendered block, so nested occurrences are
expressed through the lowest block that places all of them.
"""

import json
import math
import os
from pathlib import Path
import re
import shlex

from . import plan as contract
from .math3d import cross, direction, dot, inverse, point, unit
from .source import Document, normalized, verify_source

MOSAIC_LIMIT = 12


def _number(value, digits=4):
    return str(round(value, digits) + 0.0)


def _slug(name):
    return re.sub(r"[^a-z0-9]+", "-", re.sub(r"\.ldr$", "", name.lower())).strip("-")


def _warn(warnings, code, message):
    warnings.append(dict(code=code, message=message))


def _leaves(nodes):
    """Physical leaves owned by every placement, including the leaf itself."""
    owned = {i: set() for i in nodes}
    for i, n in nodes.items():
        if n["kind"] == "part":
            parts = i.split("/")
            for depth in range(1, len(parts) + 1):
                owned["/".join(parts[:depth])].add(i)
    return owned


def _cover(nodes, owned, ids):
    """Topmost placements whose subtrees contain only requested leaves."""
    unknown = [i for i in ids if i not in nodes]
    if unknown:
        raise ValueError(f"Unknown occurrence IDs: {unknown[:10]}")
    wanted = set().union(*(owned[i] for i in ids))
    if not wanted:
        raise ValueError("Selection contains no physical parts")
    cover = set()
    for leaf in wanted:
        top, parts = leaf, leaf.split("/")
        for depth in range(len(parts) - 1, 0, -1):
            ancestor = "/".join(parts[:depth])
            if not owned[ancestor] <= wanted:
                break
            top = ancestor
        cover.add(top)
    return wanted, cover


def _parents(doc, block):
    key = normalized(block)
    return [
        (m.name, sum(normalized(p.reference) == key for p in m.pieces))
        for m in doc.sections.values()
        if any(normalized(p.reference) == key for p in m.pieces)
    ]


def _block_file(doc, block):
    """xray reads one file; adjacent .ldr assemblies are rendered from their own file."""
    local = {normalized(m.name) for m in [doc.root, *doc.root.submodels.values()]}
    if normalized(block) in local:
        return doc.path, False
    external = doc.path.parent / block.replace("\\", "/")
    if not external.is_file():
        raise ValueError(f"Cannot locate the file that defines {block!r}")
    return external.resolve(), True


def _subject(doc, nodes, instance, block, selector, warnings):
    """One rendered block: its file, parent context and selected-section placement."""
    model, external = _block_file(doc, block)
    parents = _parents(doc, block)
    if external:
        parent = None
        _warn(
            warnings,
            "external_file",
            f"{block!r} is a separate file; xray renders it alone without parent context",
        )
    elif instance:
        parent = nodes[instance]["section"]
    else:
        # The selected section is the frame; show it in its first parent, if any.
        parent = parents[0][0] if parents else None
        if len(parents) > 1:
            _warn(
                warnings,
                "several_parents",
                f"{block!r} has parents {[p for p, _ in parents]}; context uses {parent!r}",
            )
    if parent is None and not external:
        _warn(
            warnings,
            "no_parent",
            f"{block!r} has no parent; context panels are omitted",
        )
    count = dict(parents).get(parent, 0)
    if count > 1:
        _warn(
            warnings,
            "shared_definition",
            f"{parent!r} places {block!r} {count} times. Context highlights every "
            "placement and poses edit the definition, so parent panels move every "
            "instance; trust the isolated panels.",
        )
    return dict(
        model=str(model),
        block=block,
        parent=parent,
        selector=selector,
        frame_instance=instance or None,
        nonempty_steps=sum(1 for s in doc.section(block).steps if s),
        world=nodes[instance]["world"] if instance else None,
    )


def locate(manifest, ids, doc=None):
    """Choose the rendered blocks, line selectors and frames for occurrences.

    The subject is the lowest block placing every occurrence. When the
    occurrences are exactly one assembly, the subject is that assembly's own
    block (moving `all`) and the containing block becomes `surroundings`.
    """
    doc = doc or Document(manifest["path"])
    nodes = {n["id"]: n for n in manifest["nodes"]}
    owned = _leaves(nodes)
    wanted, cover = _cover(nodes, owned, ids)
    prefix = os.path.commonprefix([c.split("/")[:-1] for c in cover])
    instance = "/".join(prefix)
    placements = sorted(
        {"/".join(c.split("/")[: len(prefix) + 1]) for c in cover},
        key=lambda i: nodes[i]["line"],
    )
    block = nodes[placements[0]]["section"]
    selector = "line:" + ",".join(str(nodes[p]["line"]) for p in placements)
    warnings = []
    extra = sorted(set().union(*(owned[p] for p in placements)) - wanted)
    if extra:
        _warn(
            warnings,
            "over_selects",
            f"Selecting whole placements in {block!r} also moves {len(extra)} "
            f"unrequested parts: {extra[:20]}",
        )
    subject = _subject(doc, nodes, instance, block, selector, warnings)
    surroundings = None
    whole = placements[0]
    if len(placements) == 1 and whole in cover and nodes[whole]["kind"] == "assembly":
        surroundings = subject
        own = doc.section(nodes[whole]["ref"]).name
        subject = _subject(doc, nodes, whole, own, "all", warnings)
    occurrences = []
    for i in ids:
        parts = i.split("/")
        chain = ["/".join(parts[:d]) for d in range(1, len(parts) + 1)]
        occurrences.append(
            dict(
                id=i,
                ref=nodes[i]["ref"],
                block=nodes[i]["section"],
                line=nodes[i]["line"],
                chain=[
                    dict(block=nodes[c]["section"], line=nodes[c]["line"])
                    for c in chain
                ],
            )
        )
    return dict(
        subject=subject,
        surroundings=surroundings,
        moving=sorted(wanted),
        extra=extra,
        occurrences=occurrences,
        warnings=warnings,
    )


def to_block(world, origin, axis, warnings):
    """Express a selected-section point/axis in a rendered block's frame."""
    if world is None:
        return list(origin), unit(axis), False
    r = [row[:3] for row in world[:3]]
    gram = [[dot(a, b) for b in r] for a in r]
    if max(abs(gram[i][j] - (i == j)) for i in range(3) for j in range(3)) > 1e-3:
        _warn(
            warnings,
            "non_orthonormal",
            "A block placement has scale or shear; check the axis visually",
        )
    inv = inverse(world)
    mirrored = dot(r[0], cross(r[1], r[2])) < 0
    clean = lambda v: [c + 0.0 for c in v]  # noqa: E731 - avoid printing -0.0
    return clean(point(inv, origin)), clean(unit(direction(inv, axis))), mirrored


def _pose(subject, origin, axis, degrees, warnings):
    """Attach a block-frame pivot; mirrored placements reverse the angle sign."""
    block_point, block_direction, mirrored = to_block(
        subject["world"], origin, axis, warnings
    )
    if mirrored:
        _warn(
            warnings,
            "mirrored",
            f"{subject['block']!r} is placed mirrored; angles are negated to keep the same motion",
        )
    subject["pivot"] = dict(
        point=block_point,
        direction=block_direction,
        mirrored=mirrored,
        angles_degrees=[-a if mirrored else a for a in degrees],
    )


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


def _command(name, purpose, argv, stdout=None):
    shell = shlex.join(argv) + (f" > {shlex.quote(stdout)}" if stdout else "")
    extra = {"stdout": stdout} if stdout else {}
    return dict(name=name, purpose=purpose, argv=argv, shell=shell, **extra)


def _pivot_argv(subject, base):
    s, p = subject, subject["pivot"]
    return (
        ["ldraw-xray", "board", "pivot", s["model"], "--section", s["block"]]
        + (["--parent", s["parent"]] if s["parent"] else [])
        + ["--point", *map(_number, p["point"])]
        + ["--direction", *map(_number, p["direction"])]
        + ["--moving", s["selector"], "--angles"]
        + [_number(a, 3) for a in p["angles_degrees"]]
        + ["--output", str(base)]
    )


def focus_recipe(subject, title):
    """Pose panels framed on the moving parts' rest bounds, others ghosted.

    `board pivot` frames the whole block, so buried or small moving parts can
    look identical at every angle; this recipe is for `ldraw-xray board run`.
    """
    sel, p = subject["selector"], subject["pivot"]
    line = dict(point=p["point"], direction=p["direction"])
    panels = [
        dict(
            label=f"Pose {_number(a, 3)} degrees: moving parts edged, others ghosted",
            view="home",
            layers=[
                dict(layer="closeup", select=sel, margin=2.0),
                dict(layer="pose", select=sel, angle=a, **line),
                dict(layer="axis", **line),
                dict(layer="highlight", select=sel),
                dict(layer="ghost"),
            ],
        )
        for a in p["angles_degrees"]
    ]
    return dict(
        source=subject["model"],
        section=subject["block"],
        title=title[:120],
        panels=panels,
    )


def commands(located, base):
    """Ordered CLI calls plus recipe files to write before running them."""
    s = located["subject"]
    subject = [s["model"], "--section", s["block"]]
    context = ["--parent", s["parent"]] if s["parent"] else []
    base = Path(base).resolve()
    # Overview: parent context, isolated home view, one image per step, front view if short.
    images = bool(s["parent"]) + 1 + s["nonempty_steps"]
    images += images < 4
    out = [
        _command(
            "overview",
            "Build steps (cumulative, new parts edged) and the block in its parent",
            ["ldraw-xray", "board", "overview", *subject, *context, "--steps"]
            + (["--no-mosaic"] if images > MOSAIC_LIMIT else [])
            + ["--output", str(base / "overview")],
        )
    ]
    if s["parent"]:
        out.append(
            _command(
                "context",
                "Highlighted block inside its parent, surroundings ghosted",
                [
                    "ldraw-xray",
                    "render",
                    *subject,
                    *context,
                    "--highlight",
                    "section",
                    "--ghost",
                ]
                + [
                    "--view",
                    "home",
                    "--view",
                    "front",
                    "--output",
                    str(base / "context"),
                ],
            )
        )
    if s["selector"] != "all":
        out.append(
            _command(
                "selection",
                "Selected placements edged in the isolated block",
                [
                    "ldraw-xray",
                    "render",
                    *subject,
                    "--highlight",
                    s["selector"],
                    "--ghost",
                ]
                + [
                    "--view",
                    "home",
                    "--view",
                    "front",
                    "--output",
                    str(base / "selection"),
                ],
            )
        )
    if "pivot" in s:
        out.append(
            _command(
                "pivot",
                "Axis rod and the moving selection posed at each angle (degrees)",
                _pivot_argv(s, base / "pivot"),
            )
        )
    around = located["surroundings"]
    if around and "pivot" in around:
        out.append(
            _command(
                "pivot-in-parent",
                f"The same motion inside {around['block']!r}, to judge neighbours",
                _pivot_argv(around, base / "pivot-in-parent"),
            )
        )
    recipes = {}
    focus = next(
        (x for x in (s, around) if x and "pivot" in x and x["selector"] != "all"), None
    )
    if focus:
        path = base / "pivot-focus.recipe.json"
        recipes[str(path)] = focus_recipe(focus, f"{focus['block']}: focused pivot")
        out.append(
            _command(
                "pivot-focus",
                "Close-up poses: moving parts edged, everything else ghosted",
                [
                    "ldraw-xray",
                    "board",
                    "run",
                    str(path),
                    "--output",
                    str(base / "pivot-focus"),
                ],
            )
        )
    for name, purpose in (
        (
            "connections",
            "Contacts, connected groups and overlap candidates (block frame)",
        ),
        ("axes", "Coaxial connector axis candidates (block frame; sign-normalised)"),
    ):
        out.append(
            _command(
                name,
                purpose,
                ["ldraw-xray", name, *subject],
                str(base / f"{name}.json"),
            )
        )
    return out, recipes


def _result(manifest, located, axis, base, notes):
    warnings = located.pop("warnings")
    cmds, recipes = commands(located, base)
    for path, recipe in recipes.items():
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(json.dumps(recipe, indent=2) + "\n")
    for s in (located["subject"], located["surroundings"]):
        if s:
            s.pop("world")
    return dict(
        source=manifest["path"],
        section=manifest["section"],
        **located,
        axis=axis,
        commands=cmds,
        recipes=sorted(recipes),
        warnings=warnings,
        notes=notes
        + [
            "Run each argv with the globally installed ldraw-xray; add --force to replace earlier output",
            "Renders are static evidence, not proof of clearance or mechanical engagement",
        ],
    )


def _posed(located, origin, axis, degrees):
    for s in (located["subject"], located["surroundings"]):
        if s:
            _pose(s, origin, axis, degrees, located["warnings"])


def study(
    model, instances, *, section=None, origin=None, axis=None, angles=None, xray_dir
):
    """Commands for candidate occurrences, with an optional axis in the section frame."""
    if (origin is None) != (axis is None):
        raise ValueError("--point and --direction must be given together")
    if angles and origin is None:
        raise ValueError("--angles needs --point and --direction")
    doc = Document(model)
    manifest = doc.manifest(section)
    located = locate(manifest, instances, doc)
    frame = None
    if origin is not None:
        degrees = list(angles or [0, 45, 90])
        _posed(located, origin, axis, degrees)
        frame = dict(point=list(origin), direction=unit(axis), degrees=degrees)
    base = Path(xray_dir) / _slug(located["subject"]["block"])
    return _result(manifest, located, frame, base, [])


def joint(plan, body, *, xray_dir=None, plan_file=None):
    """Commands to review one authored body: pivot, axis, sign and limit poses."""
    manifest = plan["source"]
    verify_source(manifest)
    if body not in plan["bodies"]:
        raise ValueError(f"Unknown body {body!r}; bodies: {sorted(plan['bodies'])}")
    b = plan["bodies"][body]
    located = locate(manifest, b["instances"])
    notes = []
    if b.get("parent"):
        notes.append(
            f"Body moves relative to {b['parent']!r}; poses show it at the parent's rest pose"
        )
    frame = dict(point=b["origin"], direction=unit(b["axis"]), kind=b["kind"])
    if b["kind"] == "revolute":
        values = body_values(plan, body)
        if values[-1] - values[0] >= 2 * math.pi - 1e-9:
            notes.append("Full-turn range; showing 0, 45 and 90 degrees")
            degrees = [0.0, 45.0, 90.0]
        else:
            degrees = [math.degrees(v) for v in values]
        frame.update(radians=values, degrees=degrees)
        _posed(located, b["origin"], b["axis"], degrees)
    elif b["kind"] in ("prismatic", "stretch"):
        frame.update(values=body_values(plan, body), degrees=[0.0])
        _posed(located, b["origin"], b["axis"], [0.0])
        notes.append(
            "xray cannot translate or scale parts; the board shows the axis and selection only"
        )
    else:
        notes.append(
            f"{b['kind']} body: no pivot board; review the selection and context"
        )
    base = Path(xray_dir or Path(plan_file).parent / "xray") / _slug(body)
    result = _result(manifest, located, frame, base, notes)
    result.update(body=body, kind=b["kind"])
    return result
