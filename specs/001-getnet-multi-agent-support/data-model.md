# Data Model

## Shared contracts (`src/getnet_multi_agent/contracts.py`, Pydantic)

| Model | Fields |
|---|---|
| `Principal` | `sub`, `role` (`merchant`/`operator`), `pseudonym` |
| `Step` | `agent` (`support`/`knowledge`), `source` (`rag`/`web`/None), `query`, `reason` |
| `Plan` | `steps: list[Step]`, `language` (`en`/`pt`), `standalone`, `refusal_reason` (None or `out_of_scope`/`unsafe`/`other_merchant`/`prompt_injection`), `escalate: bool` |
| `PlanRevision` | `iteration`, `action` (`initial`/`add`/`retry`/`drop`), `step`, `reason` |
| `Evidence` | `kind` (`rag`/`tool`/`web`), `url`, `title`, `score`, `excerpt` (≈300 chars) |
| `Observation` | `step`, `status` (`answered`/`ungrounded`/`failed`/`not_found`), `answer`, `evidence: list[Evidence]`, `unanswered: list[str]`, `facts` (terminal flags for critic rules), `model`, `latency_ms`, `tokens`, `cost_usd` |
| `CriticVerdict` | `complete: bool`, `unanswered: list[str]`, `add/retry/drop: list[Step]`, `notes` |
| `AgentResult` | `observation`, `content` (raw model contents kept for tool turns) |
| `Source` | `title`, `url` |
| `TraceCall` | `purpose`, `model`, `latency_ms`, `prompt_tokens`, `output_tokens`, `thinking_tokens`, `search_queries`, `cost_usd` |
| `Trace` | `plan_revisions`, `critic_notes`, `observations`, `calls: list[TraceCall]`, `total_tokens`, `total_cost_usd`, `quality_violations` |
| `ChatRequest` | `message` (1..`MAX_MESSAGE_CHARS`), `user_id`, `conversation_id` (optional) |
| `ChatResponse` | `answer`, `status` (`answered`/`awaiting_human`/`refused`), `refusal_reason`, `route`, `sources: list[Source]`, `ticket_id`, `conversation_id`, `request_id`, `trace` |
| `Ticket` | `id`, `conversation_id`, `status`, `reason`, `question`, `draft`, `claimed_by`, timestamps, `resolution_action`, `resolution_text` |
| `RunCheckpoint` | `plan`, `revisions`, `observations`, `draft`, `language`, `pending_parts` |

## SQLite (`data/state/app.db`, WAL)

```text
conversations(id TEXT PK, owner TEXT  -- HMAC pseudonym, created_at)
turns(id INTEGER PK, conversation_id FK, seq INT, role TEXT  -- user|assistant|operator,
      text TEXT  -- masked, request_id, status, created_at; UNIQUE(conversation_id, seq))
summaries(conversation_id PK FK, text, upto_seq INT, updated_at)
checkpoints(id TEXT PK, conversation_id FK, request_id, state_json, created_at)
tickets(id TEXT PK, conversation_id FK, checkpoint_id FK, reason, status, claimed_by,
        draft, resolution_action, resolution_text, created_at, claimed_at, resolved_at)
audit(id INTEGER PK, ts, actor TEXT  -- pseudonym or "system", action, ticket_id, detail)
```

Rules
- Every text column is masked (card, CPF) before insert.
- Ticket states: `open` → `claimed` → `resolved` (approve/edit) or `rejected` (reject).
- Claim: `UPDATE tickets SET status='claimed', claimed_by=?, claimed_at=? WHERE id=? AND
  status='open'`; rowcount 0 → 409.
- Resolve: allowed only when `status='claimed' AND claimed_by=caller`, else 409; approve with empty
  draft → 422.
- Audit rows: `ticket_opened` (system), `ticket_claimed`, `ticket_approved`, `ticket_edited`,
  `ticket_rejected`.
- Summary refreshed by the lite model when turns exceed 6 beyond `upto_seq`.

## Vector store (`data/state/chroma`)

Collection `getnet_kb`, cosine space, 768-d. Chunk metadata: `url`, `title`, `heading`, `site`
(`br`/`global`), `kind` (`faq`/`section`/`table`), `text_hash`.

## Simulated merchant data (`data/merchants.json`, committed)

```text
{ "<merchant_id>": {
    "terminals": [{ "id", "model", "label", "status": online|offline,
                    "last_errors": [{ "type": connectivity|decline, "code", "reason",
                                      "days_ago", "hour" }],
                    "suggested_actions": [str] }],
    "sales": [{ "days_ago", "amount_cents", "method": debit|credit|pix, "installments" }] } }
```

Dates are offsets resolved against today in `America/Sao_Paulo`; settlement = 2 business days
after the sale (weekends skipped). `cliente1988`: terminal A offline (connectivity), terminal B
online with a recent decline (reason and actions), sales yesterday and earlier. `cliente2000`:
own data; one `label` holds an instruction-like string (tool-result injection case).
