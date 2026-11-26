# Session notes (2026-11-26)

60-minute session clock started at the first commit, 14:21:07 -0300.

## Phase times (commit times, -0300)

| Phase | Commit | Time | Minute |
|---|---|---|---|
| Session start | 8e1ef4a | 14:21:07 | 0 |
| Constitution v1.0.0 | 6aa895a | 14:22:39 | 2 |
| Spec | 4d47baa | 14:26:32 | 5 |
| Plan | 2087be5 | 14:29:55 | 9 |
| Tasks | d9207c4 | 14:32:56 | 12 |
| Wave 0 (T001 to T005, container healthy) | a7ab118 to 76f8ac4 | 14:34 to 14:40 | 13 to 19 |
| Wave 1 (G1, G2, G3, G4, G7 in parallel + lane M) | 55b04da to 34c6560 | 14:40 to 14:45 | 19 to 24 |
| Wave 2 (G5 evals, G6 docs, live scenario fixes, integration) | de3901c to afe9d0c | 14:49 to 15:00 | 28 to 39 |
| Feature freeze, README limits | 08e5e06 | 15:00:37 | 39 |
| README and threat model finished | 732e251 | 15:06:17 | 45 |
| Clean-clone proof and reports | 00b2c42 | 15:08:48 | 47 |

## What was built

- Router (typed plan, language, standalone rewrite), bounded supervisor loop with deterministic
  critic rules and a lite completeness check, Knowledge agent (hybrid RAG over the committed
  snapshot and Google Search grounding in separate calls), Customer Support agent with two tools
  in a function-calling loop, Human Escalation agent with an operator queue, synthesis and
  Personality with code checks on numbers, URLs and ticket id.
- Guardrails before any LLM (length, Luhn card, CPF, other merchant, injection en/pt), masking in
  logs and SQLite, DLP on the final answer, HS256 JWT with CLI-issued tokens, HMAC pseudonyms.
- SQLite memory with rolling summary and checkpoints; atomic ticket claim; audit trail.
- One LLM wrapper with cost, budget, timeout and single retry; stub mode for tests and CI.
- JSON logs, Prometheus metrics, four alert rules with promtool tests, Grafana dashboard under
  the observability profile, live and ready health.
- Evals: 40-case dataset, runner with code checks and typed judge, calibration export,
  retrieval metrics hybrid vs vector, held-out hash check.
- Docker (non-root, digest-pinned base, frozen lockfile, healthcheck on readiness, log limits),
  compose, CI on push and live eval on tags.

## What was cut

The five CUT-FIRST tasks (rate limiting, operator webhook, MCP server, image scanning,
approval-gated advance action); human labels for judge calibration; a live eval case for
injection inside retrieved pages (covered by an integration test instead). Listed in the README.

## Evidence

All commands below ran in this session; results are quoted, not summarized from memory.

- Unit and integration tests: `uv run pytest` 222 passed (main tree and the clean clone).
- Lint: `uv run ruff check .` all checks passed (clean clone).
- Alert rules: `promtool test rules /p/alerts.test.yml` SUCCESS (clean clone, pinned Prometheus image).
- CI on GitHub Actions: `ci` workflow success on the last pushes before the reports
  (lint, tests, compose smoke test with `LLM_MODE=stub`, promtool).
- Clean-clone proof: `git clone` of origin/main at 08e5e06 into a temporary directory, only `.env`
  copied, `docker compose -p gma-ci up --build --wait` healthy after ingesting 1178 chunks with
  live embeddings; the ten official scenarios: 10 of 10 pass route and expected fact.
- Live answer review (gma-dev): 16 of 16 pass, see docs/answer-review.md.
- Live eval (`evals/run.py --rerun-failures`, run once plus 3 reruns of failures, majority decides),
  evals/report.md: 40 cases, 30 passed; routing accuracy 0.947; correct refusal rate 1.000
  (includes 401 and 403 cases); citation rate 1.000; source match 0.750; must_mention pass 0.860;
  deterministic quality 0.946; judge averages correctness 4.55, groundedness 4.35, relevance 4.72,
  helpfulness 4.62, clarity 4.90; en 20/25 passed, pt 10/15 passed; latency p50 8.7 s, p95 20.1 s;
  cost USD 0.0056 per chat request, USD 0.377 total including the judge.
  The runner exits 1 because three thresholds were missed: deterministic quality 0.946 < 1.0,
  source match 0.750 < 0.80, must_mention 0.860 < 0.90.
- Retrieval (`evals/retrieval.py`, k=5), evals/retrieval_report.md: hybrid Hit 0.812, Recall 0.708,
  MRR 0.594, nDCG 0.582, context precision 0.400, context recall 0.875; vector only Hit 0.812,
  Recall 0.604, MRR 0.400, nDCG 0.404.
- Held-out set: not opened and not run in this session; `evals/heldout.sha256` is unchanged.

## Known failures from the eval (not fixed: feature freeze at minute 40)

- Amounts without cents copied from the site ("R$ 20,000") fail the unformatted-amount check
  in the machines comparison; the fix is to render thousands with cents in `localize_amounts`.
- Source match misses when the answer cites `/duvidas` or `/link-de-pagamento` instead of the
  topic page the dataset expects (`/duvidas/link-de-pagamento`, `/duvidas/pix`): the same FAQ
  text exists on both pages and retrieval keeps one copy.
- Portuguese cases pass less often (10/15) than English (20/25); the lowest clarity answer is the
  Portuguese multi-turn "e para o meu outro terminal?" case (clarity 3).
- Judge calibration against human labels was not done: the labeling sheet can be exported with
  `evals/calibrate.py export`, but no labels were collected.

## Notes on parallel work

- Subagents built G1 to G7 against `contracts.py`; only the main session committed, one commit
  per task with `git add` limited to the task's files.
- G4 edited `compose.yaml` before T005 was committed, so the Prometheus and Grafana services
  landed in the T005 commit instead of T017.
- G1 found that `/duvidas/crediario` does not contain "48"; the 48x limit is on `/crediario`.
- Two concurrency bugs found only in the container under parallel requests: concurrent Chroma
  client creation and concurrent google-genai client creation (a replaced client was garbage
  collected and closed the HTTP client in use). Both fixed with locks and startup warmup.
