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
    for name in ("inspect", "connectors", "contacts", "plan", "convert"):
        q = s.add_parser(name)
        q.add_argument("model")
        q.add_argument("--section")
        q.add_argument("--output")
        if name == "inspect":
            q.add_argument("--max-instances", type=int, default=100000)
        if name == "connectors":
            q.add_argument("--instance", required=True)
            q.add_argument("--shadow")
        if name == "contacts":
            q.add_argument("--instances", nargs="+", required=True)
            q.add_argument("--shadow")
        if name == "plan":
            q.add_argument("--recipe", choices=["106", "928", "42000"])
        if name == "convert":
            q.add_argument(
                "--plan", help="Use the exact source/section recorded in this plan"
            )
    for name in ("validate", "evaluate", "sweep"):
        q = s.add_parser(name)
        q.add_argument("plan")
        q.add_argument("--output")
        if name == "evaluate":
            q.add_argument(
                "--set", action="append", default=[], metavar="CONTROL=VALUE"
            )
        if name == "sweep":
            q.add_argument("--steps", type=int, default=17)
    q = s.add_parser("search")
    q.add_argument("kind", choices=["parts", "models", "submodels"])
    q.add_argument("query")
    q.add_argument("--engine", choices=["keyword", "jev"], default="keyword")
    q.add_argument("--limit", type=int, default=8)
    q.add_argument("--candidates", type=int, default=40)
    q.add_argument("--database")
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
        if command == "inspect":
            from .analysis import inspect

            result = inspect(args.model, args.section, args.max_instances)
        elif command == "connectors":
            from .analysis import connectors
            from .source import Document

            result = connectors(
                Document(args.model).manifest(args.section),
                args.instance,
                args.library,
                args.shadow,
            )
        elif command == "contacts":
            from .analysis import contacts
            from .source import Document

            result = contacts(
                Document(args.model).manifest(args.section),
                args.instances,
                args.library,
                args.shadow,
            )
        elif command == "plan":
            from .recipes import create

            result = create(args.model, args.recipe, args.section)
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
            )
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
        if getattr(args, "output", None) and command != "convert":
            plan.save(args.output, result)
            print(
                json.dumps(
                    dict(
                        output=str(Path(args.output).resolve()),
                        command=command,
                        passed=result.get("passed", result.get("valid")),
                    )
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
