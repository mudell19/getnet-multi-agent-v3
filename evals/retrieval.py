"""Retrieval eval (FR-066): Hit@k, Recall@k, MRR, nDCG@k, context precision and recall.

uv run python evals/retrieval.py [--dataset evals/retrieval.jsonl] [--base-url ...] [--k 5]
Report only: always exits 0.
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

MODES = ("hybrid", "vector")
METRICS = ("hit", "recall", "mrr", "ndcg", "context_precision", "context_recall")


def norm_url(url: str) -> str:
    p = urlsplit(url.strip())
    return f"{p.scheme.lower()}://{p.netloc.lower()}{p.path.rstrip('/')}"


def hit_at_k(ranked: list[str], relevant: set[str], k: int) -> float:
    return 1.0 if any(u in relevant for u in ranked[:k]) else 0.0


def recall_at_k(ranked: list[str], relevant: set[str], k: int) -> float:
    return len(relevant & set(ranked[:k])) / len(relevant) if relevant else 0.0


def mrr(ranked: list[str], relevant: set[str], k: int) -> float:
    for i, u in enumerate(ranked[:k], start=1):
        if u in relevant:
            return 1.0 / i
    return 0.0


def ndcg_at_k(ranked: list[str], relevant: set[str], k: int) -> float:
    """Binary gain, each relevant URL counted once (later chunks of the same page add nothing)."""
    seen: set[str] = set()
    dcg = 0.0
    for i, u in enumerate(ranked[:k], start=1):
        if u in relevant and u not in seen:
            seen.add(u)
            dcg += 1.0 / math.log2(i + 1)
    ideal = sum(1.0 / math.log2(i + 1) for i in range(1, min(len(relevant), k) + 1))
    return dcg / ideal if ideal else 0.0


def context_precision(ranked: list[str], relevant: set[str], k: int) -> float:
    top = ranked[:k]
    return sum(u in relevant for u in top) / len(top) if top else 0.0


def context_recall(texts: list[str], fact: str, k: int) -> float:
    f = fact.casefold()
    return 1.0 if f and any(f in t.casefold() for t in texts[:k]) else 0.0


def score_query(hits: list[dict[str, Any]], relevant_urls: list[str], fact: str,
                k: int) -> dict[str, float]:
    ranked = [norm_url(h["url"]) for h in hits]
    rel = {norm_url(u) for u in relevant_urls}
    return {"hit": hit_at_k(ranked, rel, k), "recall": recall_at_k(ranked, rel, k),
            "mrr": mrr(ranked, rel, k), "ndcg": ndcg_at_k(ranked, rel, k),
            "context_precision": context_precision(ranked, rel, k),
            "context_recall": context_recall([h.get("text", "") for h in hits], fact, k)}


def aggregate(rows: list[dict[str, Any]]) -> dict[str, float]:
    return {m: statistics.mean(r["scores"][m] for r in rows) if rows else 0.0 for m in METRICS}


def render(rows: list[dict[str, Any]], k: int) -> str:
    out = ["# Retrieval report", "", f"k = {k}; relevance by normalized URL; context recall = "
           "expected fact found in any top-k chunk.", "",
           "| Mode | Lang | N | " + " | ".join(METRICS) + " |",
           "|---" * (len(METRICS) + 3) + "|"]
    for mode in MODES:
        for lang in ("all", "en", "pt"):
            sub = [r for r in rows if r["mode"] == mode and lang in ("all", r["lang"])]
            agg = aggregate(sub)
            out.append(f"| {mode} | {lang} | {len(sub)} | "
                       + " | ".join(f"{agg[m]:.3f}" for m in METRICS) + " |")
    out += ["", "## Per query", "", "| Query | Mode | Hit | MRR | Fact | Top URLs |",
            "|---|---|---|---|---|---|"]
    for r in rows:
        s = r["scores"]
        top = ", ".join(dict.fromkeys(r["ranked"]))
        out.append(f"| {r['id']} | {r['mode']} | {s['hit']:.0f} | {s['mrr']:.2f} | "
                   f"{s['context_recall']:.0f} | {top} |")
    return "\n".join(out) + "\n"


def main(argv: list[str] | None = None) -> int:
    import httpx

    from getnet_multi_agent.security.auth import issue_token

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dataset", default=str(ROOT / "evals" / "retrieval.jsonl"))
    ap.add_argument("--base-url", default="http://localhost:8000")
    ap.add_argument("--k", type=int, default=5)
    ap.add_argument("--report", default=str(ROOT / "evals" / "retrieval_report.md"))
    args = ap.parse_args(argv)

    with open(args.dataset, encoding="utf-8") as fh:
        queries = [json.loads(line) for line in fh if line.strip()]
    headers = {"Authorization": f"Bearer {issue_token('eval-operator', 'operator')}"}
    rows = []
    with httpx.Client(base_url=args.base_url, timeout=120.0, headers=headers) as client:
        for q in queries:
            for mode in MODES:
                r = client.get("/operator/retrieval",
                               params={"q": q["query"], "mode": mode, "k": args.k})
                r.raise_for_status()
                hits = r.json()
                rows.append({"id": q["id"], "lang": q["lang"], "mode": mode,
                             "ranked": [norm_url(h["url"]) for h in hits[:args.k]],
                             "scores": score_query(hits, q["relevant_urls"],
                                                   q.get("expected_fact", ""), args.k)})
    Path(args.report).write_text(render(rows, args.k), encoding="utf-8")
    for mode in MODES:
        agg = aggregate([r for r in rows if r["mode"] == mode])
        print(mode, " ".join(f"{m}={agg[m]:.3f}" for m in METRICS))
    print(f"report {args.report}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
