# CLI and eval contracts

## CLI (`getnet-multi-agent`, entry `getnet_multi_agent.cli:main`)

| Command | Behavior |
|---|---|
| `token --sub <id> --role merchant\|operator [--hours 12]` | prints a JWT signed with `JWT_SECRET` |
| `refresh` | crawls per FR-014 and rewrites `data/crawl_cache/`; the only networked crawl |
| `ingest [--rebuild]` | builds the collection from the cache, offline |

In the container: `docker compose exec api getnet-multi-agent token --sub cliente1988 --role merchant`.

## Eval dataset JSONL (dataset, held-out, any `--dataset`)

```json
{"id": "rag-machines-en", "lang": "en", "category": "rag",
 "user_id": "cliente1988", "message": "...", "expected_route": "knowledge:rag",
 "must_mention": ["what Get Classic is for", "..."], "must_not": ["..."],
 "source_url": "https://site.getnet.com.br/todas-as-maquininhas",
 "must_contain": ["R$"], "turns": ["earlier message"],
 "operator_actions": [{"action": "edit", "text": "..."}]}
```

`expected_route` uses the response route vocabulary; `expected_status` is derived (`refusal` →
`refused`, `escalation` → `awaiting_human`, else `answered`). Optional keys may be absent.

## Retrieval set JSONL (`evals/retrieval.jsonl`)

```json
{"id": "r-pix-pt", "lang": "pt", "query": "...", "relevant_urls": ["..."], "expected_fact": "..."}
```

## Runner

`uv run python evals/run.py [--dataset evals/dataset.jsonl] [--heldout PATH] [--base-url
http://localhost:8000] [--concurrency 4] [--runs 3|--rerun-failures]` → `evals/report.md`, exit 1
below thresholds (FR-067) or on held-out hash mismatch.

`evals/retrieval.py [--k 5]` → `evals/retrieval_report.md`. `evals/calibrate.py export|score` →
`evals/labels.csv` and agreement report.

## Judge output (typed)

```text
JudgeVerdict { correctness, groundedness, relevance, helpfulness, clarity: int 1..5,
               items: [{criterion, kind: must_mention|must_not, passed: bool, rationale}] }
```
