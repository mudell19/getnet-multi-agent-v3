# Implementation Plan: Getnet Multi-Agent Merchant Support

**Branch**: `main` (no feature branches) | **Date**: 2026-11-26 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/001-getnet-multi-agent-support/spec.md`

## Summary

A FastAPI service where a Router plans, a bounded supervisor runs Knowledge (RAG over the committed
Getnet snapshot, or Gemini Search grounding) and Support (two tools over simulated merchant data)
steps, a critic replans, synthesis merges, and Personality writes the merchant-facing answer under
code checks. Deterministic guardrails and JWT identity run before any LLM; escalations become
operator tickets resumed from checkpoints. One LLM wrapper meters cost and budget. Evals, metrics,
alerts and a dashboard ship with it. Verified contracts: [research.md](research.md).

## Technical Context

**Language/Version**: Python 3.12 (uv, `uv.lock`, frozen install)

**Primary Dependencies**: fastapi 0.162.0, uvicorn, pydantic, pydantic-settings, google-genai
2.34.0, chromadb 1.5.9, beautifulsoup4 + lxml, httpx, pyjwt 2.15.1, prometheus-client 0.26.0

**Storage**: SQLite (WAL) and embedded Chroma under `data/state` (named volume
`/app/data/state` in the container); `data/crawl_cache` and `data/merchants.json` read-only

**Testing**: pytest (unit with fake LLM; integration through the HTTP app with the LLM stubbed at
the wrapper), ruff, promtool, eval runner against the live API

**Target Platform**: Linux container, amd64 and arm64

**Project Type**: web service + CLI

**Performance Goals**: p95 ≤ 15 s single-topic, ≤ 25 s compound (SC-006)

**Constraints**: request token budget 30,000; avg cost < US$ 0.02/request; LLM timeout 30 s;
offline ingestion; no agent frameworks

**Scale/Scope**: single node, demo traffic; 2 simulated merchants; ≈ 98 cached pages

## Constitution Check

*Pre-design and post-design: PASS, no violations.*

| Principle | How the design satisfies it |
|---|---|
| I Orchestration | `supervisor.py` loop with typed `Plan`, observations, critic (rules then lite check), revisions in trace, stop at 3 iterations or budget; synthesis; Personality with number/URL/ticket check; sources and BR caveat added by code; one prompt module per agent, date injected |
| II Identity | `security/auth.py` HS256 with iss/aud/exp/sub/role; 403 on sub mismatch; tools get `Principal`; ownership by pseudonym; tokens only via CLI; HMAC pseudonym in logs |
| III Guardrails | `security/guardrails.py` length, Luhn, CPF, other merchant, injection (en/pt) before any LLM; `security/dlp.py` masks before log/DB and checks the final answer; untrusted data delimited |
| IV Grounding | knowledge answers carry evidence; ungrounded → one retry → escalate; Search and tools in separate calls |
| V Answer quality | `format/money_date.py` renders values before LLM; `format/quality.py` fixes dashes/bold, rejects ISO dates, checks language, counts violations |
| VI Memory + HITL | SQLite turns, summary, checkpoints, tickets, audit; atomic claim; resume through Personality |
| VII Models + cost | `core/llm.py` single wrapper, env-configured models/thinking, cost table, timeout, one retry, whole contents kept, budget |
| VIII Typed contracts | `contracts.py` Pydantic models; tools return typed results; budget/LLM failure → valid JSON + escalation |
| IX Observability | JSON logs with request_id and APP_REV, `/metrics`, alert rules + promtool tests, provisioned Grafana under profile, live/ready |
| X Evals | dataset, runner, typed judge, calibration, retrieval metrics, held-out hash check, non-zero exit, cost |
| XI Tests | `tests/` names carry FR IDs; fake LLM in unit; HTTP integration with wrapper stub |
| XII Simplicity | no repository/service layers; plain modules; only spec'd endpoints |
| Delivery | Dockerfile non-root, digest-pinned base, `uv sync --frozen`, healthcheck, log limits; CI per research |

## Project Structure

### Documentation (this feature)

```text
specs/001-getnet-multi-agent-support/
├── plan.md  research.md  data-model.md  quickstart.md
├── contracts/ (http-api.md, cli-and-evals.md, llm-wrapper.md)
└── tasks.md   (/speckit-tasks)
```

### Source Code (repository root)

```text
src/getnet_multi_agent/
├── contracts.py                 # shared Pydantic models (built first)
├── core/      settings.py llm.py context.py logging.py metrics.py
├── security/  auth.py guardrails.py dlp.py pseudonym.py
├── state/     db.py conversations.py tickets.py checkpoints.py audit.py
├── rag/       crawler.py extract.py chunk.py glossary.py store.py retriever.py ingest.py
├── agents/    planner.py critic.py knowledge.py support.py tools.py synthesis.py
│              escalation.py personality.py summary.py
│   └── prompts/ router.py critic.py knowledge.py support.py synthesis.py personality.py summary.py
├── format/    money_date.py quality.py
├── supervisor.py
├── api/       app.py chat.py conversations.py operator.py health.py
└── cli.py
data/merchants.json              # simulated data (relative dates)
tests/unit/  tests/integration/  tests/conftest.py
evals/  run.py judge.py calibrate.py retrieval.py dataset.jsonl retrieval.jsonl heldout.sha256
ops/prometheus/ prometheus.yml alerts.yml alerts.test.yml
ops/grafana/ provisioning/{datasources,dashboards}/ dashboards/getnet.json
docs/threat-model.md  README.md  Dockerfile  compose.yaml  .dockerignore  .env.example
.github/workflows/ ci.yml live-eval.yml
```

**Structure Decision**: single package with groups that never share files, so groups are built in
parallel against `contracts.py` and the `LLM` protocol.

## Request flow

1. `api/chat.py`: auth → `request_context` → guardrails (refuse by code) → load conversation.
2. `supervisor.run`: planner (summary + last 6 turns) → refusal or escalation short-circuit → loop:
   run steps, critic rules (offline/connectivity → add `knowledge:rag`; decline → support only;
   ungrounded → retry once, then mark part pending), lite critic, revise; stop at 3 iterations,
   complete, or budget.
3. Synthesis when ≥ 2 answered steps; escalation when parts pending (ticket + checkpoint).
4. Personality → code check (numbers, URLs, ticket id) → quality fixes → DLP → sources + caveat.
5. Persist turns (masked), metrics, JSON log; return `ChatResponse`.

## Build order

1. `contracts.py`, `core/` (settings, context, llm with stub, logging, metrics).
2. Skeleton: `/health/*`, `/metrics`, `/chat` returning a stub answer; Dockerfile and compose up
   with `--wait` and one curl in the container (container early).
3. Parallel groups: security, state, rag, format, agents + tools.
4. Supervisor and full API; integration tests per user story.
5. Ops (Prometheus, alerts tests, Grafana), CI workflows.
6. Evals datasets and scripts; README and threat model.
7. Final proof: clean `git archive` copy, `compose -p getnet-multi-agent-dev up --build --wait`,
   live eval.

## Complexity Tracking

No violations.
