# Quickstart validation

Prerequisites: Docker with compose, `uv`, a `.env` (copy `.env.example`, fill `GEMINI_API_KEY`,
`JWT_SECRET`, `PSEUDONYM_KEY`). Contracts: [http-api](contracts/http-api.md),
[cli-and-evals](contracts/cli-and-evals.md).

## 1. Local checks (no key needed)

```bash
uv sync --frozen
uv run ruff check .
uv run pytest -q                      # every FR-NNN has a test with the ID in its name
docker run --rm -v "$PWD/ops/prometheus:/p" --entrypoint promtool \
  prom/prometheus:v3.16.0@sha256:e04987641b57704f408e31f6373ba4138ecf27cb4a165d24aabb6c38fddd0f06 \
  test rules /p/alerts.test.yml
```
Expected: all pass, exit 0.

## 2. Container smoke test (stub LLM)

```bash
LLM_MODE=stub docker compose up --build --wait
curl -s localhost:8000/health/ready          # {"status":"ready",...}
TOKEN=$(docker compose exec -T api getnet-multi-agent token --sub cliente1988 --role merchant)
curl -s localhost:8000/chat -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"message":"When will the money from yesterday'\''s sales be deposited?","user_id":"cliente1988"}'
```
Expected: JSON with `status` `answered`, `route` `support`, a `request_id`.

## 3. Live acceptance (real key, in the container)

```bash
docker compose up --build --wait
uv run python evals/run.py --dataset evals/dataset.jsonl
uv run python evals/retrieval.py
```
Expected: `evals/report.md` and `evals/retrieval_report.md` written; exit 0 means every FR-067
threshold met. The ten official scenarios pass route, facts and quality checks (SC-001).

## 4. Spot checks

- No token → 401; token for cliente1988 with `user_id` cliente2000 → 403.
- Message with a Luhn-valid card number → `refused`, `sensitive_data`, no LLM call in the trace.
- "I want to talk to a person" → `awaiting_human` + `ticket_id`; operator token: list, claim
  (second claim 409), resolve `edit`; `GET /conversations/{id}` shows the operator answer.
- `docker compose restart api`, then a follow-up with the same `conversation_id` answers in
  context.
- `docker compose --profile observability up -d`; Grafana on :3000 shows the provisioned
  dashboard.

## 5. Final proof

From a clean copy of the commit (`git archive HEAD | tar -x -C "$(mktemp -d)"`, plus `.env`):
`docker compose -p getnet-multi-agent-dev up --build --wait`, then step 3 against it.
