"""Bounded semantic discovery with explicit offline keyword mode."""

import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import subprocess

from .source import ROOT

TABLES = {
    "parts": "PARTS_DESCRIPTIONS_JEV",
    "models": "MODELS_DESCRIPTIONS_JEV",
    "submodels": "SUBMODELS_DESCRIPTIONS_JEV",
}


def search(kind, query, engine="keyword", limit=8, candidates=40, database=None):
    if not 1 <= limit <= 100 or not 1 <= candidates <= 1000:
        raise ValueError("limit 1..100; candidates 1..1000")
    db = Path(database or ROOT / "data/ldraw-info.db").resolve()
    if not db.is_file():
        raise ValueError(f"Missing database {db}")
    table = TABLES[kind]
    if engine == "jev":
        if not shutil.which("jev-rerank") or not os.environ.get("TYPESAFE_API_KEY"):
            raise ValueError(
                "Jev requires jev-rerank and TYPESAFE_API_KEY; use --engine keyword for offline search"
            )
        command = [
            "jev-rerank",
            "--db",
            str(db),
            "--table-field",
            table + ".full_description",
            "--query",
            query,
            "--top",
            str(limit),
            "--candidates",
            str(candidates),
            "--model",
            "jev-1.13.0",
            "--timeout",
            "15",
            "--retries",
            "0",
            "--show",
            "--json",
        ]
        result = subprocess.run(command, capture_output=True, text=True, timeout=120)
        if result.returncode:
            raise ValueError(
                f"Jev unavailable: {result.stderr[-1000:]}; use --engine keyword"
            )
        report = json.loads(result.stdout)
        rows = [dict(text=r["text"], score=r["score"]) for r in report["results"]]
        stats = report["stats"]
    else:
        tokens = set(re.findall(r"\w+", query.casefold()))
        if not tokens:
            raise ValueError("Search query must contain words")
        with sqlite3.connect(db.as_uri() + "?mode=ro", uri=True) as con:
            texts = [r[0] for r in con.execute(f"SELECT full_description FROM {table}")]
        rows = [
            dict(text=t, score=sum(token in t.casefold() for token in tokens))
            for t in texts
            if t
        ]
        rows = sorted(
            (r for r in rows if r["score"]), key=lambda r: (-r["score"], r["text"])
        )[:limit]
        stats = dict(api_calls=0, documents=len(texts))
    for r in rows:
        fields = r["text"].split("|", 2)
        if kind == "parts":
            r["part"] = fields[0]
        elif kind == "models":
            r["model"] = fields[0]
        elif len(fields) == 3:
            r.update(model=fields[0], section=fields[1])
    return dict(
        engine=engine,
        ranking="semantic reranking" if engine == "jev" else "offline token hits",
        query=query,
        results=rows,
        stats=stats,
        coverage="Discovery only; inspect returned source and parent context",
    )
