"""Live eval runner (FR-061..FR-067): drives the HTTP API, checks by code, judges by LLM, reports.

uv run python evals/run.py [--dataset evals/dataset.jsonl] [--heldout PATH]
    [--base-url http://localhost:8000] [--concurrency 4] [--runs 3 | --rerun-failures]
    [--report evals/report.md]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from evals.judge import CRITERIA, build_evidence, judge  # noqa: E402

HASH_FILE = ROOT / "evals" / "heldout.sha256"
MAX_WORDS = 160
RERUNS = 3
TIMEOUT = 120.0
THRESHOLDS = {
    "routing_accuracy": 0.90,
    "deterministic_quality": 1.0,
    "correct_refusal_rate": 1.0,
    "citation_rate": 0.95,
    "source_match_rate": 0.80,
    "must_mention_pass_rate": 0.90,
    **{f"judge_{c}": 4.0 for c in CRITERIA},
}


# ---------------------------------------------------------------- pure helpers


def load_jsonl(path: str | Path) -> list[dict[str, Any]]:
    with open(path, encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def norm_url(url: str) -> str:
    p = urlsplit(url.strip())
    return f"{p.scheme.lower()}://{p.netloc.lower()}{p.path.rstrip('/')}"


def expected_status(route: str) -> str:
    return {"refusal": "refused", "escalation": "awaiting_human"}.get(route, "answered")


def sha256_file(path: str | Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 16), b""):
            h.update(block)
    return h.hexdigest()


def heldout_ok(path: str | Path, hash_file: str | Path = HASH_FILE) -> bool:
    expected = Path(hash_file).read_text(encoding="utf-8").split()[0].strip().lower()
    return sha256_file(path) == expected


def code_checks(case: dict[str, Any], response: dict[str, Any], answer: str) -> dict[str, Any]:
    """Deterministic checks for one non-auth case. `answer` is the text judged (operator turn for
    human-in-the-loop cases)."""
    from getnet_multi_agent.format.quality import check_answer, word_count

    failures: list[str] = []
    exp_route = case["expected_route"]
    route_ok = response.get("route") == exp_route
    if not route_ok:
        failures.append(f"route {response.get('route')!r} != {exp_route!r}")
    status_ok = response.get("status") == expected_status(exp_route)
    if not status_ok:
        failures.append(f"status {response.get('status')!r} != {expected_status(exp_route)!r}")
    refusal_ok = None
    if exp_route == "refusal":
        want = case.get("expected_refusal_reason")
        refusal_ok = status_ok and (want is None or response.get("refusal_reason") == want)
        if want and response.get("refusal_reason") != want:
            failures.append(f"refusal_reason {response.get('refusal_reason')!r} != {want!r}")
    for sub in case.get("must_contain") or []:
        if sub not in answer:
            failures.append(f"missing literal {sub!r}")
    source_ok = None
    if case.get("source_url"):
        urls = {norm_url(s.get("url", "")) for s in response.get("sources") or []}
        source_ok = norm_url(case["source_url"]) in urls
        if not source_ok:
            failures.append(f"source {case['source_url']} not in sources")
    quality = check_answer(answer, case["lang"])
    words = word_count(answer)
    if words > MAX_WORDS:
        quality = [*quality, f"words>{MAX_WORDS}"]
    if quality:
        failures.append("quality: " + ",".join(quality))
    return {"route_ok": route_ok, "status_ok": status_ok, "refusal_ok": refusal_ok,
            "source_ok": source_ok, "quality": quality, "words": words,
            "has_sources": bool(response.get("sources")), "failures": failures}


def auth_checks(case: dict[str, Any], http_status: int) -> dict[str, Any]:
    want = {"wrong_user": 403, "no_token": 401}[case["auth"]]
    ok = http_status == want
    return {"route_ok": None, "status_ok": ok, "refusal_ok": ok, "source_ok": None,
            "quality": [], "words": 0, "has_sources": False,
            "failures": [] if ok else [f"http {http_status} != {want}"]}


def row_passed(row: dict[str, Any]) -> bool:
    if row.get("error") or row["checks"]["failures"]:
        return False
    verdict = row.get("verdict")
    return verdict is None or all(i["passed"] for i in verdict["items"])


def _rate(values: list[bool]) -> float | None:
    return sum(values) / len(values) if values else None


def _pct(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    return s[min(len(s) - 1, max(0, round(q * (len(s) - 1))))]


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    chat = [r for r in rows if r["case"].get("category") != "auth"]
    answered_rows = [r for r in chat if not r.get("error")]
    m: dict[str, Any] = {"cases": len(rows), "passed": sum(row_passed(r) for r in rows)}
    m["routing_accuracy"] = _rate([bool(r["checks"]["route_ok"]) for r in chat])
    m["deterministic_quality"] = _rate([not r["checks"]["quality"] for r in answered_rows])
    refusal = [r for r in rows if r["case"].get("category") == "auth"
               or r["case"]["expected_route"] == "refusal"]
    m["correct_refusal_rate"] = _rate([bool(r["checks"]["refusal_ok"]) for r in refusal])
    knowledge = [r for r in answered_rows if "knowledge" in r["case"]["expected_route"]
                 and r["response"].get("status") == "answered"]
    m["citation_rate"] = _rate([r["checks"]["has_sources"] for r in knowledge])
    m["source_match_rate"] = _rate([bool(r["checks"]["source_ok"]) for r in chat
                                    if r["case"].get("source_url")])
    items = [i for r in rows if r.get("verdict") for i in r["verdict"]["items"]]
    m["must_mention_pass_rate"] = _rate([i["passed"] for i in items
                                         if i["kind"] == "must_mention"])
    m["must_not_pass_rate"] = _rate([i["passed"] for i in items if i["kind"] == "must_not"])
    judged = [r["verdict"] for r in rows if r.get("verdict")]
    for c in CRITERIA:
        m[f"judge_{c}"] = statistics.mean(v[c] for v in judged) if judged else None
    lat = [r["latency_ms"] for r in chat if r.get("latency_ms")]
    m["latency_p50_ms"], m["latency_p95_ms"] = _pct(lat, 0.5), _pct(lat, 0.95)
    requests = sum(r.get("requests", 0) for r in rows)
    m["system_cost_usd"] = sum(r.get("system_cost_usd", 0.0) for r in rows)
    m["judge_cost_usd"] = sum(r.get("judge_cost_usd", 0.0) for r in rows)
    m["total_cost_usd"] = m["system_cost_usd"] + m["judge_cost_usd"]
    m["cost_per_request_usd"] = m["system_cost_usd"] / requests if requests else 0.0
    m["requests"] = requests
    by_lang: dict[str, dict[str, Any]] = {}
    for lang in sorted({r["case"]["lang"] for r in rows}):
        sub = [r for r in rows if r["case"]["lang"] == lang]
        sub_chat = [r for r in sub if r["case"].get("category") != "auth"]
        by_lang[lang] = {"cases": len(sub), "passed": sum(row_passed(r) for r in sub),
                         "routing_accuracy": _rate([bool(r["checks"]["route_ok"])
                                                    for r in sub_chat])}
    m["by_lang"] = by_lang
    return m


def missed_thresholds(m: dict[str, Any]) -> list[str]:
    missed = []
    for key, floor in THRESHOLDS.items():
        value = m.get(key)
        if value is not None and value < floor:
            missed.append(f"{key} {value:.3f} < {floor}")
    return missed


def adjudication(rows: list[dict[str, Any]]) -> list[tuple[str, str]]:
    out = []
    for r in rows:
        v, ch = r.get("verdict"), r["checks"]
        if not v:
            continue
        if ch["route_ok"] and not ch["failures"] and v["correctness"] <= 2:
            out.append((r["case"]["id"], f"code checks pass, judge correctness {v['correctness']}"))
        if ch["quality"] and v["clarity"] >= 4:
            out.append((r["case"]["id"], f"quality {ch['quality']}, judge clarity {v['clarity']}"))
        if ch["failures"] and not ch["quality"] and v["correctness"] >= 4:
            out.append((r["case"]["id"], f"code fails ({'; '.join(ch['failures'])}), "
                                         f"judge correctness {v['correctness']}"))
    return out


# ---------------------------------------------------------------- HTTP execution


def _hdr(token: str | None) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"} if token else {}


def run_case(client: Any, case: dict[str, Any], tokens: dict[str, str],
             judge_fn: Any = judge) -> dict[str, Any]:
    from getnet_multi_agent.security.auth import issue_token

    row: dict[str, Any] = {"case": case, "response": {}, "answer": "", "verdict": None,
                           "requests": 0, "system_cost_usd": 0.0, "judge_cost_usd": 0.0,
                           "latency_ms": 0, "error": None, "evidence": ""}
    try:
        if case.get("category") == "auth":
            token = issue_token("cliente1988", "merchant") if case["auth"] == "wrong_user" else None
            r = client.post("/chat", json={"message": case["message"], "user_id": case["user_id"]},
                            headers=_hdr(token))
            row["requests"] = 1
            row["http_status"] = r.status_code
            row["checks"] = auth_checks(case, r.status_code)
            return row
        uid = case["user_id"]
        if uid not in tokens:
            tokens[uid] = issue_token(uid, "merchant")
        mh = _hdr(tokens[uid])
        cid = None
        for turn in case.get("turns") or []:
            r = client.post("/chat", json={"message": turn, "user_id": uid,
                                           "conversation_id": cid}, headers=mh)
            r.raise_for_status()
            row["requests"] += 1
            body = r.json()
            cid = body["conversation_id"]
            row["system_cost_usd"] += (body.get("trace") or {}).get("total_cost_usd", 0.0)
        start = time.monotonic()
        r = client.post("/chat", json={"message": case["message"], "user_id": uid,
                                       "conversation_id": cid}, headers=mh)
        row["latency_ms"] = int((time.monotonic() - start) * 1000)
        r.raise_for_status()
        row["requests"] += 1
        resp = r.json()
        row["response"] = resp
        row["system_cost_usd"] += (resp.get("trace") or {}).get("total_cost_usd", 0.0)
        answer = resp.get("answer", "")
        op_failures: list[str] = []
        for action in case.get("operator_actions") or []:
            answer, err = _operate(client, resp, action, tokens, mh)
            if err:
                op_failures.append(err)
        row["answer"] = answer
        checks = code_checks(case, resp, answer)
        checks["failures"] += op_failures
        row["checks"] = checks
        if resp.get("status") in ("answered", "awaiting_human") and answer:
            row["evidence"] = build_evidence(resp)
            verdict, cost = judge_fn(case, case["message"], answer, row["evidence"])
            row["verdict"] = verdict.model_dump()
            row["judge_cost_usd"] = cost
    except Exception as exc:  # noqa: BLE001 - one broken case must not stop the run
        row["error"] = f"{type(exc).__name__}: {exc}"
        row.setdefault("checks", {"route_ok": False, "status_ok": False, "refusal_ok": False,
                                  "source_ok": False if case.get("source_url") else None,
                                  "quality": [], "words": 0, "has_sources": False,
                                  "failures": [row["error"]]})
    return row


def _operate(client: Any, resp: dict[str, Any], action: dict[str, str],
             tokens: dict[str, str], merchant_hdr: dict[str, str]) -> tuple[str, str | None]:
    tid = resp.get("ticket_id")
    if not tid:
        return resp.get("answer", ""), "no ticket_id on escalation"
    oh = _hdr(tokens["__operator__"])
    listed = client.get("/operator/tickets", params={"status": "open"}, headers=oh)
    listed.raise_for_status()
    if not any(t["id"] == tid for t in listed.json()):
        return resp.get("answer", ""), f"ticket {tid} not in open queue"
    client.post(f"/operator/tickets/{tid}/claim", headers=oh).raise_for_status()
    body = {"action": action["action"]}
    if action.get("text"):
        body["text"] = action["text"]
    client.post(f"/operator/tickets/{tid}/resolve", json=body, headers=oh).raise_for_status()
    conv = client.get(f"/conversations/{resp['conversation_id']}", headers=merchant_hdr)
    conv.raise_for_status()
    ops = [t for t in conv.json().get("turns", []) if t.get("role") == "operator"]
    if not ops:
        return "", "no operator turn in conversation"
    return ops[-1]["text"], None


def execute(cases: list[dict[str, Any]], base_url: str, concurrency: int,
            judge_fn: Any = judge) -> list[dict[str, Any]]:
    import httpx

    from getnet_multi_agent.security.auth import issue_token

    tokens = {"__operator__": issue_token("eval-operator", "operator")}
    with httpx.Client(base_url=base_url, timeout=TIMEOUT) as client, \
            ThreadPoolExecutor(max_workers=concurrency) as pool:
        return list(pool.map(lambda c: run_case(client, c, tokens, judge_fn), cases))


# ---------------------------------------------------------------- report


def _f(v: Any, digits: int = 3) -> str:
    return "n/a" if v is None else (f"{v:.{digits}f}" if isinstance(v, float) else str(v))


def render_report(rows: list[dict[str, Any]], m: dict[str, Any], mode: str,
                  missed: list[str], flaky: list[str]) -> str:
    out = ["# Eval report", "", f"Run mode: {mode}", "",
           f"Cases: {m['cases']}, passed: {m['passed']}, chat requests: {m['requests']}", "",
           "## Metrics", "", "| Metric | Value | Threshold |", "|---|---|---|"]
    keys = ["routing_accuracy", "deterministic_quality", "correct_refusal_rate", "citation_rate",
            "source_match_rate", "must_mention_pass_rate", "must_not_pass_rate",
            *[f"judge_{c}" for c in CRITERIA]]
    for k in keys:
        out.append(f"| {k} | {_f(m.get(k))} | {_f(THRESHOLDS.get(k))} |")
    out += ["", f"Latency p50 {m['latency_p50_ms']} ms, p95 {m['latency_p95_ms']} ms.", "",
            f"Cost: system USD {m['system_cost_usd']:.5f}, judge USD {m['judge_cost_usd']:.5f}, "
            f"total USD {m['total_cost_usd']:.5f}, per chat request USD "
            f"{m['cost_per_request_usd']:.5f}.", "",
            "Correct refusal rate includes the authorization cases (401 and 403).", "",
            "## By language", "", "| Lang | Cases | Passed | Routing accuracy |",
            "|---|---|---|---|"]
    for lang, s in m["by_lang"].items():
        out.append(f"| {lang} | {s['cases']} | {s['passed']} | {_f(s['routing_accuracy'])} |")
    out += ["", "## Thresholds (FR-067)", ""]
    out += [f"- MISSED: {x}" for x in missed] or ["- all thresholds met"]
    if flaky:
        out += ["", "## Flaky cases (mixed outcomes across runs)", ""]
        out += [f"- {x}" for x in flaky]
    judged = sorted((r for r in rows if r.get("verdict")), key=lambda r: r["verdict"]["clarity"])
    out += ["", "## Five lowest-clarity answers", ""]
    for r in judged[:5]:
        out += [f"### {r['case']['id']} (clarity {r['verdict']['clarity']})", "", "```text",
                r["answer"], "```", ""]
    out += ["## Failures", "", "| Case | Lang | Route | Failures |", "|---|---|---|---|"]
    for r in rows:
        if row_passed(r):
            continue
        reasons = list(r["checks"]["failures"])
        if r.get("verdict"):
            reasons += [f"judge {i['kind']}: {i['criterion']}" for i in r["verdict"]["items"]
                        if not i["passed"]]
        cell = "; ".join(reasons).replace("|", "/").replace("\n", " ")
        out.append(f"| {r['case']['id']} | {r['case']['lang']} | "
                   f"{r['response'].get('route', '')} | {cell} |")
    out += ["", "## Adjudication (judge and code disagree)", ""]
    out += [f"- {cid}: {why}" for cid, why in adjudication(rows)] or ["- none"]
    return "\n".join(out) + "\n"


def _result_record(r: dict[str, Any], run: int) -> dict[str, Any]:
    return {"id": r["case"]["id"], "lang": r["case"]["lang"], "run": run,
            "category": r["case"].get("category"), "message": r["case"]["message"],
            "route": r["response"].get("route"), "status": r["response"].get("status"),
            "answer": r["answer"], "evidence": r.get("evidence", ""), "verdict": r["verdict"],
            "checks": r["checks"], "error": r.get("error"), "passed": row_passed(r),
            "latency_ms": r.get("latency_ms", 0)}


# ---------------------------------------------------------------- CLI


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dataset", default=str(ROOT / "evals" / "dataset.jsonl"))
    ap.add_argument("--heldout", default=None)
    ap.add_argument("--hash-file", default=str(HASH_FILE), help=argparse.SUPPRESS)
    ap.add_argument("--base-url", default="http://localhost:8000")
    ap.add_argument("--concurrency", type=int, default=4)
    group = ap.add_mutually_exclusive_group()
    group.add_argument("--runs", type=int, default=None)
    group.add_argument("--rerun-failures", action="store_true")
    ap.add_argument("--report", default=str(ROOT / "evals" / "report.md"))
    args = ap.parse_args(argv)

    path = args.dataset
    if args.heldout:
        if not heldout_ok(args.heldout, args.hash_file):
            print("held-out hash mismatch: refusing to run", file=sys.stderr)
            return 2
        path = args.heldout
    cases = load_jsonl(path)

    attempts: list[tuple[int, dict[str, Any]]] = []
    flaky: list[str] = []
    if args.runs:
        mode = (f"fixed runs: every case run {args.runs} times; metrics over all "
                f"{args.runs * len(cases)} attempts")
        for i in range(args.runs):
            attempts += [(i + 1, r) for r in execute(cases, args.base_url, args.concurrency)]
        rows = [r for _, r in attempts]
    else:
        mode = (f"rerun failures: every case run once; each failing case rerun {RERUNS} more "
                f"times; final outcome is the majority of {RERUNS + 1} runs (a tie fails); "
                "each row shows one run matching the final outcome")
        first = execute(cases, args.base_url, args.concurrency)
        attempts = [(1, r) for r in first]
        rows = []
        failing = [r["case"] for r in first if not row_passed(r)]
        reruns: dict[str, list[dict[str, Any]]] = {c["id"]: [] for c in failing}
        for i in range(RERUNS):
            for r in execute(failing, args.base_url, args.concurrency):
                reruns[r["case"]["id"]].append(r)
                attempts.append((i + 2, r))
        for r in first:
            runs = [r, *reruns.get(r["case"]["id"], [])]
            passes = [x for x in runs if row_passed(x)]
            if len(runs) > 1 and passes:
                flaky.append(f"{r['case']['id']}: passed {len(passes)} of {len(runs)}")
            rows.append(passes[0] if len(passes) * 2 > len(runs) else r)

    m = summarize(rows)
    missed = missed_thresholds(m)
    report = Path(args.report)
    report.write_text(render_report(rows, m, mode, missed, flaky), encoding="utf-8")
    results = {"mode": mode, "dataset": "heldout" if args.heldout else path, "metrics": m,
               "rows": [_result_record(r, 1) for r in rows],
               "attempts": [_result_record(r, run) for run, r in attempts]}
    (report.parent / "results.json").write_text(json.dumps(results, ensure_ascii=False, indent=1),
                                                encoding="utf-8")
    print(f"cases {m['cases']} passed {m['passed']}; routing {_f(m['routing_accuracy'])}; "
          f"report {report}")
    for x in missed:
        print("MISSED", x)
    return 1 if missed else 0


if __name__ == "__main__":
    sys.exit(main())
