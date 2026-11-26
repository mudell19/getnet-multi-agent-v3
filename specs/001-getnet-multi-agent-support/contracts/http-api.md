# HTTP API contract

Auth: `Authorization: Bearer <JWT HS256>` with `iss`, `aud`, `exp`, `sub`, `role`. Missing or
invalid → 401. Wrong role → 403. All errors are JSON `{"detail": ...}`; validation errors 422.

| Method | Path | Role | Success | Errors |
|---|---|---|---|---|
| POST | `/chat` | merchant | 200 `ChatResponse` | 401, 403 (`user_id` ≠ `sub`), 404 (conversation not owned), 422 |
| GET | `/conversations/{id}` | merchant (owner) | 200 `{id, turns:[{seq, role, text, status, created_at}]}` | 401, 403, 404 |
| GET | `/operator/tickets?status=open\|claimed\|resolved\|rejected` | operator | 200 `[Ticket]` | 401, 403, 422 |
| POST | `/operator/tickets/{id}/claim` | operator | 200 `Ticket` | 401, 403, 404, 409 |
| POST | `/operator/tickets/{id}/resolve` | operator (claimer) | 200 `{ticket: Ticket, answer, conversation_id}` | 401, 403, 404, 409, 422 |
| GET | `/operator/retrieval?q=&mode=hybrid\|vector&k=` | operator | 200 `[{rank, url, title, score, text}]` | 401, 403, 422 |
| GET | `/health/live` | none | 200 `{"status":"ok"}` | |
| GET | `/health/ready` | none | 200 `{"status":"ready","chunks":n}` | 503 `{"status":"not_ready"}` |
| GET | `/metrics` | none | 200 Prometheus text | |

## POST /chat

Request:
```json
{"message": "When will the money from yesterday's sales be deposited?",
 "user_id": "cliente1988", "conversation_id": null}
```

Response:
```json
{"answer": "...", "status": "answered", "refusal_reason": null,
 "route": "support", "sources": [{"title": "...", "url": "..."}],
 "ticket_id": null, "conversation_id": "c_...", "request_id": "r_...",
 "trace": {"plan_revisions": [], "critic_notes": [], "observations": [],
           "calls": [], "total_tokens": 0, "total_cost_usd": 0.0,
           "quality_violations": []}}
```

`route`: `refusal` | `escalation` | executed answering steps joined by `>` from `support`,
`knowledge:rag`, `knowledge:web`. `refusal_reason`: `sensitive_data`, `other_merchant`,
`prompt_injection`, `unsafe`, `out_of_scope`.

## POST /operator/tickets/{id}/resolve

```json
{"action": "approve|edit|reject", "text": "operator text (required for edit and reject)"}
```
