"""Small JSON-first entry point. Errors use exit 2; failed checks use exit 1."""

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

from . import plan


def parser():
    p = argparse.ArgumentParser(
        description="Analyze LDraw mechanisms, plan motion, convert and rig in Blender"
    )
    p.add_argument("--library", help="LDraw library; otherwise LDRAW_DIR / LDRAWDIR")
    s = p.add_subparsers(dest="command", required=True)
    for name in (
        "inspect",
        "connectors",
        "contacts",
        "coaxial",
        "gear-meshes",
        "extract",
        "plan",
        "convert",
    ):
        q = s.add_parser(name)
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
                help="Preserve a prepared study's evidence while adopting this recipe",
            )
        if name == "convert":
            q.add_argument(
                "--plan", help="Use the exact source/section recorded in this plan"
            )
    for name in ("validate", "evaluate", "sweep", "audit"):
        q = s.add_parser(name)
        q.add_argument("plan")
        q.add_argument("--output")
        if name == "audit":
            q.add_argument(
                "--require-reviewed",
                action="store_true",
                help="Exit 1 for unresolved/unaccounted mechanisms; deferred items remain explicitly reported",
            )
        if name == "evaluate":
            q.add_argument(
                "--set", action="append", default=[], metavar="CONTROL=VALUE"
            )
        if name == "sweep":
            q.add_argument("--steps", type=int, default=17)
    q = s.add_parser("search")
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
        "prepare", help="Create candidate diagrams before optional GLB conversion"
    )
    q.add_argument("model")
    q.add_argument("--section")
    q.add_argument("--output", required=True, help="New study directory")
    q.add_argument("--shadow")
    q.add_argument("--contact-limit", type=int, default=300)
    q.add_argument("--no-glb", action="store_true", help="Source-only preparation")
    q.add_argument(
        "--plan",
        help="Optional existing motion plan with exactly matching source identities",
    )
    q = s.add_parser("diagrams", help="Regenerate Mermaid views from the plan JSON")
    q.add_argument("plan")
    q.add_argument("--output", help="Directory; defaults to diagrams beside the plan")
    q.add_argument("--view", choices=["auto", "connections", "motion"], default="auto")
    q.add_argument("--mechanism")
    q = s.add_parser(
        "jev-status", help="One small billable availability probe; no balance endpoint"
    )
    q.add_argument("--output")
    q = s.add_parser("submodels")
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
    q = s.add_parser("rig")
    q.add_argument("plan")
    q.add_argument("--glb", required=True)
    q.add_argument("--save", required=True)
    q.add_argument("--blender", help="Blender executable, or BLENDER_BIN")
    q.add_argument("--report")
    q.add_argument("--animate", action="store_true")
    return p


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        command = args.command
        if command == "prepare":
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
                values = {}
                for pair in args.set:
                    k, sep, v = pair.partition("=")
                    if not sep:
                        raise ValueError("--set needs CONTROL=VALUE")
                    values[k] = float(v)
                result = plan.evaluate(p, values)
        elif command == "rig":
            from .source import ROOT

            plan.validate(plan.load(args.plan), check_source=True)
            executable = (
                args.blender or os.environ.get("BLENDER_BIN") or shutil.which("blender")
            )
            if (
                not executable
                and Path("/Applications/Blender.app/Contents/MacOS/Blender").is_file()
            ):
                executable = "/Applications/Blender.app/Contents/MacOS/Blender"
            if not executable:
                raise ValueError("Set BLENDER_BIN or pass --blender")
            cmd = [
                executable,
                "--background",
                "--factory-startup",
                "--python-exit-code",
                "1",
                "--python",
                str(ROOT / "scripts/blender/apply_plan.py"),
                "--",
                "--new-scene",
                "--plan",
                str(Path(args.plan).resolve()),
                "--glb",
                str(Path(args.glb).resolve()),
                "--save",
                str(Path(args.save).resolve()),
            ]
            if args.report:
                cmd += ["--report", str(Path(args.report).resolve())]
            if args.animate:
                cmd += ["--animate"]
            run = subprocess.run(cmd, stdout=sys.stderr, stderr=sys.stderr)
            if run.returncode:
                return 1
            result = dict(saved=str(Path(args.save).resolve()), verified=True)
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
                        plan=result.get("plan", getattr(args, "plan", None)),
                        diagrams=result.get(
                            "directory", result.get("diagrams", {}).get("directory")
                        ),
                        glb=result.get("glb"),
                        contacts=contact_report.get("summary", contact_report)
                        if isinstance(contact_report, dict)
                        else contact_report,
                        audit=result["audit"]["summary"],
                        warnings=result["audit"]["warnings"],
                        details="Full reports in preparation.json / diagrams/index.json",
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
