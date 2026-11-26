# Research: Getnet Multi-Agent Merchant Support

All items are decisions with verified facts. Source: real calls by the user on 2026-11-25, the
committed snapshot in `data/crawl_cache/`, and `gh api` checks on 2026-11-26. No open questions.

## Stack (pinned)

- Decision: Python 3.12, uv with `uv.lock` installed `--frozen`; `fastapi==0.162.0`, `uvicorn`,
  `pydantic`, `pydantic-settings`, `google-genai==2.34.0` (stay on 2.x), `chromadb==1.5.9`,
  `beautifulsoup4` + `lxml`, `httpx`, `pyjwt==2.15.1`, `prometheus-client==0.26.0`; dev: `pytest`,
  `ruff`. SQLite from the standard library in WAL mode.
- Rationale: the set resolves with wheels for linux amd64 and arm64 (verified).
- Alternatives: agent frameworks (forbidden by constitution I); Postgres (single node is enough).

## Images (multi-arch indexes, amd64 + arm64)

- `python:3.12-slim@sha256:191083cdf6c7bda8c76158983163ead5d5cf7b77cf3033e805bb0f5296f51b4b`
- `prom/prometheus:v3.16.0@sha256:e04987641b57704f408e31f6373ba4138ecf27cb4a165d24aabb6c38fddd0f06`
  (also `promtool` via `--entrypoint promtool`)
- `grafana/grafana:13.3.1@sha256:0615ec4fbd4072004b7d86b46ded63013a74b7d6eb1119273dd89e8fa25c13cf`

## Environment

- Decision: Settings (pydantic-settings, reads `.env`) uses exactly: `GEMINI_API_KEY`,
  `GEMINI_MODEL=gemini-3.8-flash`, `GEMINI_MODEL_THINKING=low`,
  `GEMINI_ROUTER_MODEL=gemini-3.5-flash-lite`, `GEMINI_ROUTER_THINKING=minimal`,
  `GEMINI_EMBEDDING_MODEL=gemini-embedding-2`, `GEMINI_JUDGE_MODEL=gemini-3.8-flash`,
  `GEMINI_JUDGE_THINKING=high`, `PRICE_FLASH_INPUT_PER_M=0.75`, `PRICE_FLASH_OUTPUT_PER_M=3.75`,
  `PRICE_LITE_INPUT_PER_M=0.30`, `PRICE_LITE_OUTPUT_PER_M=2.50`, `PRICE_EMBEDDING_PER_M=0.20`,
  `PRICE_SEARCH_PER_1K=14`, `JWT_SECRET`, `JWT_ISSUER=getnet-multi-agent`,
  `JWT_AUDIENCE=getnet-multi-agent-api`, `PSEUDONYM_KEY`, `MAX_MESSAGE_CHARS=2000`, `RAG_TOP_K=6`,
  `RAG_MAX_PAGES=80`, `RAG_MIN_SIMILARITY=0.62`, `MAX_TOOL_ITERATIONS=3`,
  `MAX_SUPERVISOR_ITERATIONS=3`, `REQUEST_TOKEN_BUDGET=30000`, plus `LLM_MODE=live|stub`
  (default `live`). `.env.example` lists all of them with the same values and empty secrets.
- These env values supersede the spec's earlier defaults (spec updated in the same commit).
- Price mapping: `GEMINI_MODEL` and `GEMINI_JUDGE_MODEL` use FLASH prices, `GEMINI_ROUTER_MODEL`
  uses LITE, `GEMINI_EMBEDDING_MODEL` uses EMBEDDING; Search queries use `PRICE_SEARCH_PER_1K`.
- `.env` is never printed, opened or edited by the agent; the session shell has no API key, so
  local verification uses `LLM_MODE=stub`; live calls happen only in the container with `.env`.
- Constants (not env): LLM timeout 30 s, last turns 6, summary refresh after 6 turns, token
  expiry 12 h default (CLI flag), `TZ=America/Sao_Paulo`.

## Gemini contracts (google-genai 2.34.0)

- Structured output: `types.GenerateContentConfig(response_mime_type="application/json",
  response_schema=<Pydantic model>, thinking_config=types.ThinkingConfig(thinking_level=...))`
  returns `response.parsed`.
- `gemini-3.8-flash` rejects `thinking_level="minimal"`; minimal is used only with the lite
  router model. Judge: `gemini-3.8-flash` with `high` (2.5-pro is 404 for new users; previews not
  allowed).
- Usage: `usage_metadata.prompt_token_count`, `candidates_token_count`, `thoughts_token_count`,
  each possibly `None` (treated as 0). Cost = prompt × input price + (candidates + thoughts) ×
  output price, per million.
- Search grounding: `types.Tool(google_search=types.GoogleSearch())`; queries counted from
  `candidates[0].grounding_metadata.web_search_queries` and priced per 1K. Grounding chunk URIs are
  vertexaisearch redirect links, so sources carry the chunk title with the URI.
- Grounding + function calling in one request returns 400: web steps and tool steps are separate
  calls.
- Function-calling loop: the model `Content` is appended back whole each turn; otherwise the next
  turn returns 400 (missing `thought_signature`).
- Embeddings: `output_dimensionality=768`, `task_type` `RETRIEVAL_DOCUMENT` for chunks and
  `RETRIEVAL_QUERY` for queries. Passing a list of strings returns ONE embedding; pass one
  `types.Content` per text and assert vector count equals text count.

## Other library contracts

- Chroma defaults to l2: collection created with `configuration={"hnsw": {"space": "cosine"}}`;
  similarity = 1 - distance, threshold 0.62.
- PyJWT: `jwt.encode(..., algorithm="HS256")`; `jwt.decode(token, secret, algorithms=["HS256"],
  audience=..., issuer=...)`, `exp` required.
- Prometheus: `generate_latest()` served with `CONTENT_TYPE_LATEST`.
- Budget in a `ContextVar` accumulates per worker thread if no request context is opened: every
  HTTP request and every eval judgment opens a fresh request context.

## CI

- `actions/checkout@v7` → `3d3c42e5aac5ba805825da76410c181273ba90b1`, node24 (verified).
- `actions/upload-artifact@v7` → `cf430e030ddbb5b0abf93d22962f4752f3646cd9`, node24 (verified).
- uv via `pip install uv==0.13.6` (setup-uv has no v10 tag); uv provisions Python 3.12.
- `ci.yml` on push: ruff, pytest, `.env` from `.env.example` with generated secrets, compose smoke
  test with `LLM_MODE=stub`, `promtool test rules`.
- `live-eval.yml` on tags `sessao-*`: `.env` from `.env.example` + `GEMINI_API_KEY` secret +
  generated `JWT_SECRET`/`PSEUDONYM_KEY`; compose up; `evals/run.py`, then `evals/retrieval.py`
  with `if: always() && steps.up.outcome == 'success'`; reports uploaded; job fails if either fails.

## Snapshot facts (checked 2026-11-26)

- 99 entries, file names match sha256 of the normalized URL; one 404 (`/fale-conosco`) dropped.
- Required pages present, including all `/duvidas/<topic>` pages and
  `/en/our-solutions/in-person-payments`. Expected facts per scenario are listed in spec
  Assumptions. Connectivity steps live on `/duvidas/algar`; no page covers declines.

## Design decisions

- Orchestration: plain functions; supervisor loop in one module; contracts in one shared module
  so groups build in parallel.
- Retrieval: Chroma vector top-k merged with lexical glossary hits; rule boost for chunks with
  requirement markers (`precisa`, `é necessário`, `deve`, `até`, `required`, `must`); per-product
  sub-queries when more than one glossary product is named.
- Ingestion runs in a background thread at startup when the collection is empty; readiness =
  collection count > 0.
- Conversation ownership stored as the HMAC pseudonym, so no raw id is in the database.
- Stub mode: keyword-rule planner and canned agent outputs, 768-d hash embeddings; integration
  tests inject a scripted fake at the same wrapper interface.

## Cost and budget estimate

- Single-topic RAG request ≈ US$ 0.010 (router lite 2k/0.3k, knowledge flash 5k/0.9k,
  personality flash 1.5k/0.2k, critic lite 1.5k/0.1k). Compound ≈ US$ 0.018. Web requests add
  US$ 0.014 per Search query, ≈ US$ 0.02 to 0.03 each. Dataset average stays under US$ 0.02
  (SC-007).
- Compound request ≈ 21k tokens including thinking, under the 30k budget; a third supervisor
  iteration may exhaust it, which escalates by design (FR-051) and shows in the eval report.
