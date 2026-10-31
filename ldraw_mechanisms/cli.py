"""Small JSON-first entry point. Errors use exit 2; failed checks use exit 1."""

import argparse
import json
from pathlib import Path
import subprocess
import sys

from . import plan
from .workflow import control_values, plan_path


def parser():
    p = argparse.ArgumentParser(
        prog="ldraw-mecha",
        description="Prepare a study, edit its plan, check motion and rig in Blender",
        epilog="Start: prepare MODEL --output output/study. Then edit plan.json, check output/study, rig output/study --animate --reopen.",
    )
    p.add_argument("--library", help="LDraw library; otherwise LDRAW_DIR / LDRAWDIR")
    s = p.add_subparsers(dest="command", required=True)
    q = s.add_parser(
        "annotate",
        help="First annotation step: copy LDraw files with part/colour comments",
    )
    q.add_argument("model", help="Source file or directory tree")
    q.add_argument("--output", required=True, help="Annotated file or directory tree")
    q.add_argument(
        "--database", help="SQLite PARTS_DESCRIPTIONS; defaults to data/ldraw-info.db"
    )
    q.add_argument(
        "--ldconfig", help="Colour definitions; defaults to the library's LDConfig.ldr"
    )
    q = s.add_parser(
        "annotate-semantics",
        help="Apply agent-authored model/submodel descriptions after part annotation",
    )
    q.add_argument("model", help="Part-annotated source file")
    q.add_argument(
        "--descriptions",
        required=True,
        help="JSON object mapping exact section names to single-line descriptions",
    )
    q.add_argument(
        "--output", required=True, help="Separate annotated file or existing directory"
    )
    for name, help_text in {
        "inspect": "List source occurrences, positions and candidate roles",
        "connectors": "Inspect a part's local and world connector frames",
        "contacts": "Measure connector contacts in a bounded part selection",
        "coaxial": "Find candidate shared axes in a bounded part selection",
        "gear-meshes": "Find candidate gear meshes from source geometry",
        "extract": "Copy one source section into a standalone MPD",
        "plan": "Create a draft or adopt a studied recipe into an existing study",
        "convert": "Convert source geometry and bind occurrence IDs in a GLB",
    }.items():
        q = s.add_parser(name, help=help_text)
        q.add_argument("model")
        q.add_argument("--section")
        q.add_argument("--output")
        if name == "inspect":
            q.add_argument("--max-instances", type=int, default=100000)
            q.add_argument("--compact", action="store_true")
            q.add_argument("--format", choices=["json", "table"], default="json")
            q.add_argument("--ref", action="append")
            q.add_argument("--instances", nargs="+")
            q.add_argument("--mechanical-only", action="store_true")
            q.add_argument("--limit", type=int, default=100)
            q.add_argument("--offset", type=int, default=0)
        if name == "connectors":
            q.add_argument("--instance", required=True)
            q.add_argument("--shadow")
        if name in ("contacts", "coaxial"):
            q.add_argument("--instances", nargs="+", required=True)
            q.add_argument("--shadow")
        if name in ("contacts", "connectors", "coaxial", "gear-meshes"):
            q.add_argument(
                "--raw-transforms",
                action="store_true",
                help="Diagnostic comparison: disable analysis-only correction of rounded frames",
            )
        if name in ("coaxial", "gear-meshes"):
            q.add_argument("--distance-tolerance", type=float, default=0.5, help="LDU")
            q.add_argument("--angle-tolerance", type=float, default=1.0, help="Degrees")
        if name == "plan":
            from .recipes import RECIPES

            q.add_argument("--recipe", choices=sorted(RECIPES))
            q.add_argument(
                "--study",
                type=plan_path,
                help="Preserve a prepared study's evidence while adopting this recipe",
            )
        if name == "convert":
            q.add_argument(
                "--plan",
                type=plan_path,
                help="Use the exact source/section recorded in this plan",
            )
    for name, help_text in {
        "check": "Validate source, sweep motion, evaluate mixed poses and audit scope",
        "validate": "Check plan structure, source freshness and default-pose closure",
        "evaluate": "Evaluate one pose and its declared closure checks",
        "sweep": "Sweep each control independently through its limits",
        "audit": "Report reviewed, unresolved and deferred mechanisms",
    }.items():
        q = s.add_parser(name, help=help_text)
        q.add_argument("plan", type=plan_path, help="Plan JSON or study directory")
        q.add_argument(
            "--output",
            help=(
                "Defaults to check.json beside the plan"
                if name == "check"
                else "Save the full JSON report to this file"
            ),
        )
        if name in ("audit", "check"):
            q.add_argument(
                "--require-constrained",
                action="store_true",
                help="Exit 1 if any controlled body lacks a cross-body mechanical check",
            )
            q.add_argument(
                "--require-reviewed",
                action="store_true",
                help="Exit 1 for unresolved/unaccounted mechanisms; deferred items remain explicitly reported",
            )
        if name in ("evaluate", "check"):
            q.add_argument(
                "--set", action="append", default=[], metavar="CONTROL=VALUE"
            )
        if name in ("sweep", "check"):
            q.add_argument("--steps", type=int, default=17)
    q = s.add_parser(
        "search", help="Search the part/model catalog (offline by default)"
    )
    q.add_argument("kind", choices=["parts", "models", "submodels"])
    q.add_argument("query")
    q.add_argument("--engine", choices=["fts", "keyword", "jev"], default="fts")
    q.add_argument(
        "--raw-fts",
        action="store_true",
        help="Use FTS5 query syntax instead of literal OR tokens",
    )
    q.add_argument("--limit", type=int, default=8)
    q.add_argument("--candidates", type=int, default=40)
    q.add_argument("--database")
    q.add_argument("--output")
    q = s.add_parser(
        "prepare",
        help="Collect source identities and evidence, then optionally convert to GLB",
    )
    q.add_argument("model")
    q.add_argument("--section")
    q.add_argument("--output", required=True, help="New study directory")
    q.add_argument("--shadow")
    q.add_argument("--contact-limit", type=int, default=300)
    q.add_argument("--no-glb", action="store_true", help="Source-only preparation")
    motion = q.add_mutually_exclusive_group()
    motion.add_argument(
        "--plan",
        type=plan_path,
        help="Optional existing motion plan with exactly matching source identities",
    )
    from .recipes import RECIPES

    motion.add_argument(
        "--recipe",
        choices=sorted(RECIPES),
        help="Adopt studied motion while preserving all discovery evidence",
    )
    q = s.add_parser(
        "diagrams", help="Export optional diagnostic Mermaid views from the plan JSON"
    )
    q.add_argument("plan", type=plan_path, help="Plan JSON or study directory")
    q.add_argument("--output", help="Directory; defaults to diagrams beside the plan")
    q.add_argument("--view", choices=["auto", "connections", "motion"], default="auto")
    q.add_argument("--mechanism")
    q = s.add_parser(
        "jev-status", help="One small billable availability probe; no balance endpoint"
    )
    q.add_argument("--output")
    q = s.add_parser(
        "submodels", help="Compare named assemblies and their part inventories"
    )
    q.add_argument("model")
    q.add_argument("--match", help="Substring in section name or description")
    q.add_argument(
        "--sort",
        choices=["parts", "pistons", "rods", "crank_parts", "gears", "axles"],
        default="pistons",
    )
    q.add_argument("--limit", type=int, default=30)
    q.add_argument("--format", choices=["json", "table"], default="json")
    q.add_argument("--output")
    q = s.add_parser(
        "xray-args",
        help="Print ldraw-xray commands for occurrences or an authored plan body",
        description=(
            "Translate occurrence IDs and plan joints into ldraw-xray CLI arguments: "
            "block, line selectors, block-frame axis and angles in degrees. "
            "Nothing is rendered; run the printed argv with ldraw-xray."
        ),
    )
    q.add_argument("model", nargs="?", help="Source file; optional with --plan")
    q.add_argument("--section")
    q.add_argument(
        "--instances", nargs="+", help="Occurrence IDs in the selected section"
    )
    q.add_argument(
        "--point",
        nargs=3,
        type=float,
        metavar=("X", "Y", "Z"),
        help="Candidate pivot in the selected section frame (LDU)",
    )
    q.add_argument(
        "--direction",
        nargs=3,
        type=float,
        metavar=("X", "Y", "Z"),
        help="Candidate axis in the selected section frame",
    )
    q.add_argument(
        "--angles",
        nargs="+",
        type=float,
        help="Pose angles in degrees (default 0 45 90)",
    )
    q.add_argument("--plan", type=plan_path, help="Plan JSON or study directory")
    q.add_argument("--body", help="Plan body to review; requires --plan")
    q.add_argument(
        "--xray-dir",
        help="Render directory; defaults to xray beside the plan with --plan",
    )
    q.add_argument("--output", help="Save the JSON result to this file")
    q = s.add_parser("rig", help="Build and verify a ready plan in background Blender")
    q.add_argument(
        "--require-constrained",
        action="store_true",
        help="Require passing sampled mechanical checks and coverage before starting Blender",
    )
    q.add_argument("plan", type=plan_path, help="Plan JSON or study directory")
    q.add_argument("--glb", help="Defaults to model.glb beside the plan")
    q.add_argument("--save", help="Defaults to rigged.blend beside the plan")
    q.add_argument("--blender", help="Blender executable, or BLENDER_BIN")
    q.add_argument(
        "--report", help="Defaults to blender-check.json beside the saved blend"
    )
    q.add_argument("--animate", action="store_true")
    q.add_argument(
        "--reopen",
        action="store_true",
        help="Also verify the saved rig in a fresh Blender process",
    )
    q.add_argument(
        "--tolerance",
        type=float,
        default=0.002,
        help="Matrix error bound in LDU; raise only for measured float32 rounding",
    )
    return p


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        command = args.command
        if command == "annotate":
            from .annotate import annotate

            result = annotate(
                args.model,
                args.output,
                database=args.database,
                ldconfig=args.ldconfig,
                library=args.library,
            )
        elif command == "annotate-semantics":
            from .annotate import annotate_semantics

            result = annotate_semantics(
                args.model,
                args.output,
                json.loads(Path(args.descriptions).read_text(encoding="utf-8")),
            )
        elif command == "prepare":
            from .prepare import prepare

            result = prepare(
                args.model,
                args.output,
                section=args.section,
                library=args.library,
                shadow=args.shadow,
                contact_limit=args.contact_limit,
                convert_glb=not args.no_glb,
                motion=plan.load(args.plan) if args.plan else None,
                recipe=args.recipe,
            )
        elif command == "check":
            from .workflow import check, protect_inputs

            p = plan.load(args.plan)
            args.output = args.output or args.plan.with_name("check.json")
            protect_inputs(
                [args.plan, p["source"]["path"], *p["source"]["dependencies"]],
                [args.output],
            )
            result = check(
                p,
                steps=args.steps,
                values=control_values(args.set) if args.set else None,
                require_reviewed=args.require_reviewed,
                require_constrained=args.require_constrained,
            )
        elif command == "diagrams":
            from .mechanisms import write_diagrams

            result = write_diagrams(
                plan.load(args.plan),
                args.output or Path(args.plan).parent / "diagrams",
                view=args.view,
                mechanism=args.mechanism,
            )
        elif command == "audit":
            from .audit import audit

            result = audit(plan.load(args.plan))
            if args.require_reviewed:
                result["passed"] = result["review_complete"]
            if args.require_constrained:
                result["passed"] = (
                    result.get("passed", True) and result["constraints"]["complete"]
                )
        elif command == "inspect":
            from .analysis import inspect

            if (
                args.compact
                or args.format == "table"
                or args.ref
                or args.instances
                or args.mechanical_only
            ):
                from .discovery import compact_inspect
                from .source import Document

                result = compact_inspect(
                    Document(args.model).manifest(args.section, args.max_instances),
                    refs=args.ref,
                    instances=args.instances,
                    mechanical_only=args.mechanical_only,
                    limit=args.limit,
                    offset=args.offset,
                )
            else:
                result = inspect(args.model, args.section, args.max_instances)
        elif command == "submodels":
            from .discovery import submodels

            result = submodels(args.model, args.match, args.sort, args.limit)
        elif command == "xray-args":
            from . import xray

            if args.plan:
                if args.instances or args.point or args.direction or args.angles:
                    raise ValueError(
                        "--plan uses the body's instances, axis and limits; omit study flags"
                    )
                if not args.body:
                    raise ValueError("--plan requires --body NAME")
                p = plan.load(args.plan)
                if args.model and Path(args.model).resolve() != Path(
                    p["source"]["path"]
                ):
                    raise ValueError("Model does not match plan source")
                if args.section and xray.normalized(args.section) != xray.normalized(
                    p["source"]["section"]
                ):
                    raise ValueError("Section does not match plan source")
                result = xray.joint(
                    p, args.body, xray_dir=args.xray_dir, plan_file=args.plan
                )
            else:
                if not args.model or not args.instances:
                    raise ValueError(
                        "xray-args needs MODEL --instances ... or --plan --body"
                    )
                if args.body:
                    raise ValueError("--body requires --plan")
                if not args.xray_dir:
                    raise ValueError("xray-args without --plan requires --xray-dir")
                result = xray.study(
                    args.model,
                    args.instances,
                    section=args.section,
                    origin=args.point,
                    axis=args.direction,
                    angles=args.angles,
                    xray_dir=args.xray_dir,
                )
        elif command in ("gear-meshes", "coaxial"):
            from .geometry import coaxial, gear_meshes
            from .source import Document

            manifest = Document(args.model).manifest(args.section)
            options = dict(
                distance_tolerance=args.distance_tolerance,
                angle_tolerance=args.angle_tolerance,
                normalize=not args.raw_transforms,
            )
            result = (
                gear_meshes(manifest, **options)
                if command == "gear-meshes"
                else coaxial(
                    manifest, args.instances, args.library, args.shadow, **options
                )
            )
        elif command == "extract":
            from .source import Document

            if not args.section or not args.output:
                raise ValueError("extract requires --section and --output FILE.mpd")
            doc = Document(args.model)
            manifest = doc.manifest(args.section)
            target = Path(args.output).resolve()
            if target in {Path(p) for p in manifest["dependencies"]}:
                raise ValueError("Extraction must not overwrite source dependencies")
            target.parent.mkdir(parents=True, exist_ok=True)
            doc.export_section(args.section, target)
            result = dict(
                output=str(target),
                section=manifest["section"],
                parts=sum(n["kind"] == "part" for n in manifest["nodes"]),
            )
        elif command == "connectors":
            from .analysis import connectors
            from .source import Document

            result = connectors(
                Document(args.model).manifest(args.section),
                args.instance,
                args.library,
                args.shadow,
                normalize=not args.raw_transforms,
            )
        elif command == "contacts":
            from .analysis import contacts
            from .source import Document

            result = contacts(
                Document(args.model).manifest(args.section),
                args.instances,
                args.library,
                args.shadow,
                normalize=not args.raw_transforms,
            )
        elif command == "plan":
            from .recipes import create

            result = create(args.model, args.recipe, args.section)
            if args.study:
                if not args.recipe:
                    raise ValueError(
                        "--study requires --recipe; otherwise edit the prepared plan directly"
                    )
                from .prepare import adopt_motion

                result = adopt_motion(plan.load(args.study), result)
        elif command == "convert":
            from .source import Document
            from .glb import convert

            manifest = (
                plan.load(args.plan)["source"]
                if args.plan
                else Document(args.model).manifest(args.section)
            )
            if args.plan and Path(args.model).resolve() != Path(manifest["path"]):
                raise ValueError("Model does not match plan source")
            if not args.output:
                raise ValueError("convert requires --output FILE.glb")
            result = convert(manifest, args.output, args.library)
        elif command == "search":
            from .search import search

            result = search(
                args.kind,
                args.query,
                args.engine,
                args.limit,
                args.candidates,
                args.database,
                raw_fts=args.raw_fts,
            )
        elif command == "jev-status":
            from .search import jev_status

            result = jev_status()
            result["passed"] = result["available"]
        elif command in ("validate", "evaluate", "sweep"):
            p = plan.load(args.plan)
            validated = plan.validate(p, check_source=True)
            if command == "validate":
                result = validated
            elif command == "sweep":
                result = plan.sweep(p, args.steps)
            else:
                result = plan.evaluate(p, control_values(args.set))
                result["passed"] = all(c["passed"] for c in result["checks"])
        elif command == "rig":
            from .workflow import rig

            result = rig(
                args.plan,
                glb=args.glb,
                save=args.save,
                report=args.report,
                blender=args.blender,
                animate=args.animate,
                tolerance=args.tolerance,
                reopen=args.reopen,
                require_constrained=args.require_constrained,
            )
        else:
            raise ValueError("Unknown command")
        if getattr(args, "format", None) == "table":
            from .discovery import table

            rendered = table(result)
            if args.output:
                target = Path(args.output)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(rendered + "\n")
            else:
                print(rendered)
        elif getattr(args, "output", None) and command not in (
            "annotate",
            "annotate-semantics",
            "convert",
            "extract",
            "prepare",
            "diagrams",
        ):
            plan.save(args.output, result)
            print(
                json.dumps(
                    dict(
                        output=str(Path(args.output).resolve()),
                        command=command,
                        passed=result.get("passed", result.get("valid")),
                        summary=result.get("summary"),
                        warnings=result.get("warnings", []),
                    )
                )
            )
        elif command in ("prepare", "diagrams"):
            coverage = result.get("discovery", result.get("coverage", {}))
            contact_report = coverage.get("contacts", "not recorded")
            print(
                json.dumps(
                    dict(
                        plan=str(result.get("plan", getattr(args, "plan", ""))),
                        **(
                            {"diagrams": result["directory"]}
                            if command == "diagrams"
                            else {}
                        ),
                        glb=result.get("glb"),
                        contacts=contact_report.get("summary", contact_report)
                        if isinstance(contact_report, dict)
                        else contact_report,
                        audit=result["audit"]["summary"],
                        warnings=result["audit"]["warnings"],
                        details=str(Path(result["plan"]).with_name("preparation.json"))
                        if command == "prepare"
                        else str(Path(result["directory"]) / "index.json"),
                    ),
                    indent=2,
                )
            )
        else:
            print(json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False))
        return 1 if result.get("passed") is False else 0
    except (
        ValueError,
        KeyError,
        TypeError,
        OSError,
        RuntimeError,
        subprocess.SubprocessError,
    ) as exc:
        print(json.dumps(dict(error=str(exc), command=args.command)), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
