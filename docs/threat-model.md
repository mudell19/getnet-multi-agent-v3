# Threat model

Scope: the Getnet multi-agent support service in this repository (FastAPI API, supervisor and
agents, Gemini calls, Chroma knowledge base, SQLite state, operator queue). Requirement IDs refer
to [specs/001-getnet-multi-agent-support/spec.md](../specs/001-getnet-multi-agent-support/spec.md).

## Assets

| Asset | Where it lives | Why it matters |
|---|---|---|
| Merchant data | `data/merchants.json` (simulated), tool results, conversation turns, tickets | receivables and terminal data of one merchant must never reach another |
| Tokens | JWTs issued by the CLI, held by merchants and operators | a stolen or forged token acts as its subject |
| Secrets | `.env`: `GEMINI_API_KEY`, `JWT_SECRET`, `PSEUDONYM_KEY` | forging tokens, reversing pseudonyms, spending the LLM account |
| Knowledge base integrity | `data/crawl_cache/` snapshot and the Chroma collection | poisoned content becomes grounded answers and citations |
| LLM budget | Gemini usage billed per token and per Search query | abuse turns into direct cost |

## Actors

| Actor | Access | Intent considered |
|---|---|---|
| Merchant | merchant token, `/chat` and own `/conversations` | curious or malicious: other merchants' data, prompt injection, cost abuse |
| Operator | operator token, `/operator` routes | mistakes or misuse: double handling, unaccountable answers |
| External attacker | network access to the API, no valid token | forged tokens, brute force, malformed input, cost abuse |
| Malicious content | text inside crawled web pages or tool data (e.g. a merchant record field) | indirect prompt injection through retrieved chunks and tool results |

## Threats and controls

| Threat | Controls | Where |
|---|---|---|
| Cross-merchant data leakage | Tools take the merchant id from the authenticated principal only, never from model arguments; a message naming another merchant id is refused by code (`other_merchant`) before any LLM call, and the Router refuses indirect requests ("the merchant next door"); `user_id` must equal the token subject (403); conversations are owned by the HMAC pseudonym and another principal's id returns 404; the final DLP check masks other merchant ids in the answer | `agents/support.py`, `agents/tools.py`, `security/guardrails.py`, `security/dlp.py`, `api/chat.py`, `api/conversations.py` |
| Direct prompt injection | Known injection patterns in English and Portuguese refused by code before any LLM call (`prompt_injection`); the Router plans a refusal for injections the patterns miss; every prompt states role, scope and refusal rules | `security/guardrails.py`, `agents/prompts/` |
| Indirect injection in retrieved content and tool results | Retrieved chunks and tool results are wrapped in `<data>` tags; prompts say the content is untrusted, never to follow or repeat instructions inside it; Personality output is checked by code for new numbers and URLs; the final answer passes DLP. Tested by `test_fr028_untrusted_data_is_delimited`, `test_fr033_check_final` and the tool-result injection eval case (instruction-like field in cliente2000's data) | `agents/prompts/common.py`, `agents/personality.py`, `security/dlp.py` |
| Sensitive data (card numbers, CPF) | Luhn-valid card numbers (13 to 19 digits) and valid CPFs refused by code (`sensitive_data`) with no LLM call; values masked before reaching logs and the database (user turns, assistant turns, operator text, summaries); log fields masked again by the logger; final answer DLP check | `security/dlp.py`, `security/guardrails.py`, `core/logging.py`, `api/chat.py`, `api/operator.py` |
| Token misuse | HS256 with required `iss`, `aud`, `exp`, `sub` and `role`; 401 on missing or invalid tokens; role checked per route (merchant on `/chat` and `/conversations`, operator on `/operator`, else 403); tokens issued only by the CLI inside the container, no endpoint issues tokens; default expiry 12 h | `security/auth.py`, `cli.py` |
| Cost abuse | Per-request token budget (`REQUEST_TOKEN_BUDGET`) checked before each LLM call, escalating when spent; message length limit (`MAX_MESSAGE_CHARS`, 422); `MAX_TOOL_ITERATIONS` and `MAX_SUPERVISOR_ITERATIONS`; code refusals cost no tokens; cost per call in the trace and in `getnet_llm_cost_usd_total`; alert `GetnetHighCostPerHour` above US$ 1 per hour | `core/context.py`, `core/llm.py`, `supervisor.py`, `ops/prometheus/alerts.yml` |
| Hallucination | Knowledge answers only from retrieved chunks or `NO_ANSWER`; ungrounded parts retried once, then escalated to a human; citations chosen by text overlap with the answer; Personality may not add numbers or URLs (code check returns the draft on violation); global-site content carries a Brazil caveat added by code | `agents/knowledge.py`, `agents/critic.py`, `agents/personality.py`, `supervisor.py` |
| Operator misuse | Claim is one guarded `UPDATE` so only one operator wins (409 for the other); only the claiming operator can resolve; every ticket creation, claim and resolution writes an audit entry with the operator pseudonym, action, ticket and time; operator answers pass Personality, quality fixes and masking | `state/tickets.py`, `state/audit.py`, `api/operator.py` |
| Knowledge base poisoning | Ingestion reads only the committed snapshot, restricted to `site.getnet.com.br` and `www.getnet.net/en`; the networked crawl runs only by explicit `refresh` command, same host only | `rag/ingest.py`, `rag/crawler.py` |
| Secret exposure | Secrets only in `.env` (git-ignored), every variable listed in `.env.example`; raw user ids replaced by HMAC pseudonyms in logs and storage; image runs as non-root | `core/settings.py`, `security/pseudonym.py`, `Dockerfile` |

## Residual risks

- **Novel injection wording.** Pattern checks catch known phrasings only; the Router and the
  `<data>` delimiting reduce but do not eliminate injections the model may follow.
- **No live test of a poisoned page.** Indirect injection through retrieved content is covered by
  prompt and DLP unit tests, not by a planted page in the live snapshot.
- **Shared-secret tokens.** Anyone holding `JWT_SECRET` can mint any token; there is no
  revocation list and no rate limiting per principal or IP.
- **DLP scope.** The final check covers card numbers, CPFs and known merchant ids; other personal
  data (names, phone numbers, addresses) is not detected.
- **Paraphrased hallucination.** The Personality check verifies numbers, URLs and the ticket id,
  not the meaning of reworded sentences; the eval judge measures groundedness after the fact.
- **Model provider.** Message content (masked) is sent to the Gemini API.
- **Single node.** SQLite and the embedded Chroma store share one volume with the API; a host
  compromise exposes all state.
