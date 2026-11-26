"""Judge calibration (FR-068): export judged answers for human labels, then score agreement.

uv run python evals/calibrate.py export   # evals/results.json -> evals/labels.csv
uv run python evals/calibrate.py score    # labels.csv with human_* columns filled -> agreement
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CRITERIA = ("correctness", "groundedness", "relevance", "helpfulness", "clarity")
TARGET = 0.80


def export(results: Path, labels: Path) -> int:
    rows = json.loads(results.read_text(encoding="utf-8"))["rows"]
    fields = ["id", "lang", "answer", *[f"judge_{c}" for c in CRITERIA],
              *[f"human_{c}" for c in CRITERIA]]
    n = 0
    with labels.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        for r in rows:
            if not r.get("verdict"):
                continue
            rec: dict[str, Any] = {"id": r["id"], "lang": r["lang"], "answer": r["answer"]}
            rec.update({f"judge_{c}": r["verdict"][c] for c in CRITERIA})
            rec.update({f"human_{c}": "" for c in CRITERIA})
            w.writerow(rec)
            n += 1
    print(f"wrote {n} rows to {labels}")
    return 0


def agreement(rows: list[dict[str, str]]) -> dict[str, float | None]:
    """Per criterion: fraction of labelled rows where |judge - human| <= 1."""
    out: dict[str, float | None] = {}
    for c in CRITERIA:
        pairs = [(int(r[f"judge_{c}"]), int(r[f"human_{c}"])) for r in rows
                 if (r.get(f"human_{c}") or "").strip() and (r.get(f"judge_{c}") or "").strip()]
        out[c] = sum(abs(j - h) <= 1 for j, h in pairs) / len(pairs) if pairs else None
    return out


def score(labels: Path) -> int:
    with labels.open(encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    agr = agreement(rows)
    ok = True
    for c, v in agr.items():
        status = "n/a" if v is None else f"{v:.2f}"
        if v is not None and v < TARGET:
            ok = False
        print(f"{c}: agreement within one point {status} (target {TARGET})")
    return 0 if ok else 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("command", choices=["export", "score"])
    ap.add_argument("--results", default=str(ROOT / "evals" / "results.json"))
    ap.add_argument("--labels", default=str(ROOT / "evals" / "labels.csv"))
    args = ap.parse_args(argv)
    if args.command == "export":
        return export(Path(args.results), Path(args.labels))
    return score(Path(args.labels))


if __name__ == "__main__":
    sys.exit(main())
