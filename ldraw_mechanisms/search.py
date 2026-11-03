"""Read-only FTS5 discovery and bounded, optional semantic reranking."""

import json
import os
from pathlib import Path
import re
import sqlite3
import subprocess
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .source import ROOT, find_tool

TABLES = {
    "parts": "PARTS_DESCRIPTIONS",
    "models": "MODELS_DESCRIPTIONS",
    "submodels": "SUBMODELS_DESCRIPTIONS",
}
MODEL = "jev-1.13.0"


def jev_status():
    """One tiny uncached inference, no retries. This is NOT a balance query.

    TypeSafe documents evaluation but no read-only credit endpoint. A successful
    probe consumes tokens and cannot guarantee credit for a subsequent batch.
    Never return HTTP bodies or credentials in diagnostics.
    """
    key = os.environ.get("TYPESAFE_API_KEY")
    result = dict(
        available=False,
        api_calls=0,
        balance=None,
        coverage="Availability probe, not a credit balance; one billable inference on success",
    )
    if not key:
        return dict(result, reason="TYPESAFE_API_KEY is missing")
    base = os.environ.get("TYPESAFE_BASE_URL", "https://api.typesafe.ai").rstrip("/")
    request = Request(
        base + "/v1/systemone",
        data=json.dumps(
            {
                "model": MODEL,
                "state": "LEGO engine",
                "questions": {
                    "check": {"type": "noul", "instructions": "Is this about LEGO?"}
                },
            }
        ).encode(),
        headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"},
    )
    result["api_calls"] = 1
    try:
        with urlopen(request, timeout=15) as response:
            payload = json.load(response)
        if "check" not in payload.get("answers", {}):
            return dict(result, reason="Unexpected Jev response")
        return dict(
            result,
            available=True,
            reason="Evaluation succeeded",
            usage=payload.get("usage"),
        )
    except HTTPError as exc:
        reasons = {
            402: "Insufficient credits",
            401: "Invalid API credentials",
            403: "Access denied",
            429: "Rate limited",
        }
        return dict(
            result, http_status=exc.code, reason=reasons.get(exc.code, "Jev HTTP error")
        )
    except (URLError, TimeoutError, ValueError, OSError):
        return dict(result, reason="Jev unreachable or invalid response")


def search(
    kind, query, engine="fts", limit=8, candidates=40, database=None, *, raw_fts=False
):
    if not 1 <= limit <= 100 or not 1 <= candidates <= 1000:
        raise ValueError("limit 1..100; candidates 1..1000")
    if kind not in TABLES or engine not in {"fts", "keyword", "jev"}:
        raise ValueError("Unknown search kind or engine")
    if raw_fts and engine != "fts":
        raise ValueError("--raw-fts requires --engine fts")
    if not query.strip():
        raise ValueError("Search query must not be empty")
    db = Path(database or ROOT / "data/ldraw-info.db").resolve()
    if not db.is_file():
        raise ValueError(f"Missing database {db}")
    table = TABLES[kind]
    if engine == "jev":
        jev = find_tool("jev-rerank")
        status = jev_status()
        if not status["available"]:
            raise ValueError(f"Jev preflight: {status['reason']}; use --engine fts")
        command = [
            jev,
            "--db",
            str(db),
            "--table-field",
            table + "_JEV.full_description",
            "--query",
            query,
            "--top",
            str(limit),
            "--candidates",
            str(candidates),
            "--model",
            MODEL,
            "--timeout",
            "15",
            "--retries",
            "0",
            "--show",
            "--json",
        ]
        result = subprocess.run(command, capture_output=True, text=True, timeout=120)
        if result.returncode:
            # Do not echo arbitrary CLI diagnostics, which may contain auth headers.
            reason = (
                "Insufficient credits (402)"
                if "402" in result.stderr
                else "reranker failed"
            )
            raise ValueError(f"Jev unavailable: {reason}; use --engine fts")
        report = json.loads(result.stdout)
        rows = [dict(text=r["text"], score=r["score"]) for r in report["results"]]
        stats = dict(report["stats"], preflight=status)
    else:
        tokens = sorted(set(re.findall(r"\w+", query.casefold())))
        if not tokens and not raw_fts:
            raise ValueError("Search query must contain words")
        try:
            with sqlite3.connect(db.as_uri() + "?mode=ro", uri=True) as con:
                if engine == "fts":
                    fts = table + "_FTS"
                    # Natural language is data, not FTS syntax. Advanced callers can opt in.
                    match = (
                        query if raw_fts else " OR ".join('"' + t + '"' for t in tokens)
                    )
                    hits = con.execute(
                        f"SELECT *, bm25({fts}) FROM {fts} WHERE {fts} MATCH ? ORDER BY bm25({fts}), rowid LIMIT ?",
                        (match, limit),
                    ).fetchall()
                    rows = [
                        dict(
                            text="|".join(str(v or "") for v in r[:-1]),
                            score=-r[-1],
                            bm25=r[-1],
                        )
                        for r in hits
                    ]
                    stats = dict(api_calls=0, match=match)
                else:
                    texts = [
                        r[0]
                        for r in con.execute(
                            f"SELECT full_description FROM {table}_JEV"
                        )
                    ]
                    rows = [
                        dict(
                            text=t, score=sum(token in t.casefold() for token in tokens)
                        )
                        for t in texts
                        if t
                    ]
                    rows = sorted(
                        (r for r in rows if r["score"]),
                        key=lambda r: (-r["score"], r["text"]),
                    )[:limit]
                    stats = dict(api_calls=0, documents=len(texts))
        except sqlite3.Error as exc:
            raise ValueError(f"{engine} search failed: {exc}") from exc
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
        ranking={
            "jev": "semantic reranking",
            "fts": "FTS5 BM25 (score higher is better)",
            "keyword": "offline token hits",
        }[engine],
        query=query,
        results=rows,
        stats=stats,
        coverage="Discovery only; inspect returned source and parent context",
    )
