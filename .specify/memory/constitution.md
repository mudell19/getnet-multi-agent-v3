# Getnet Multi-Agent Constitution

## Core Principles

### I. Bounded Supervisor Orchestration

- Orchestration MUST be plain Python with direct function calls. Agent frameworks are forbidden.
- Orchestration MUST be a bounded supervisor loop, not a fixed pipeline.
- A Router MUST return a typed plan containing: ordered steps (each naming an agent and, for
  Knowledge, the source `rag` or `web`), the user language (`en` or `pt`), and a standalone
  rewrite of the message that resolves references to earlier turns.
- The supervisor MUST execute each step and record a structured observation with status,
  evidence and unanswered parts.
- A critic MUST review observations with deterministic rules first, then a lite-model check that
  every part of the user message was answered. The critic MAY replan by adding, retrying or
  dropping steps. Every plan revision and its reason MUST be kept in the trace.
- The loop MUST stop when the answer is complete, at `MAX_SUPERVISOR_ITERATIONS`, or when the
  per-request budget is spent, whichever comes first.
- When more than one step answered, a synthesis step MUST merge their answers into one draft that
  keeps every part.
- A final Personality step MUST turn the draft into the merchant-facing answer in the planned
  language and brand voice. It MAY shorten, merge repeated parts and drop details the user did
  not ask for. It MUST NOT add any fact, number or URL, and MUST keep the ticket id and the facts
  that answer the question.
- Code MUST verify that every number and URL in the Personality output appears in the draft and
  that the ticket id is kept. On violation or Personality failure the draft MUST be returned.
  Deterministic refusals skip Personality.
- Source URLs MUST be attached by code after Personality. When a cited source is on
  `www.getnet.net`, code MUST append one short sentence in the answer language stating that the
  global site may differ for Brazil.
- Each agent prompt MUST live in its own module and state role, scope, output format and refusal
  rules. The current date MUST be injected by code.

Rationale: a bounded, traceable loop handles compound questions without unbounded cost, and
code-checked Personality keeps tone improvements from introducing ungrounded content.

### II. Identity Enforced by Code

- Every endpoint except health and metrics MUST require a Bearer JWT (HS256, claims `iss`, `aud`,
  `exp`, `sub`, and `role` in `merchant` or `operator`), verified by code.
- The chat `user_id` MUST equal the token subject; otherwise the request MUST get HTTP 403.
- Tools MUST receive the merchant id from the authenticated principal, never from LLM output.
- Conversations and tickets MUST belong to their principal and MUST NOT be readable or writable
  by another principal outside the operator role's ticket permissions.
- Tokens MUST be issued only by a CLI command. No endpoint issues tokens.
- Raw user ids MUST NOT reach logs or prompts. Logs MUST carry an HMAC pseudonym instead.

Rationale: authorization decided by an LLM is not authorization.

### III. Deterministic Guardrails and Untrusted Data

- Input guardrails MUST be deterministic and MUST run before any LLM call:
  - a configurable message length limit;
  - refusal of any message carrying a full Luhn-valid card number or a valid CPF;
  - refusal of any message that names another merchant;
  - prompt-injection heuristics in English and Portuguese.
- Card numbers and CPFs MUST be masked in every field before reaching a log or the database.
- The final answer MUST pass a DLP check before it is returned.
- Retrieved content and tool results are untrusted data: they MUST be delimited in prompts and
  MUST NEVER be followed or repeated as instructions.
- Unsafe or out-of-scope requests MUST receive a polite refusal that says what happens next.

Rationale: deterministic checks are testable, cheap and cannot be talked out of their rules.

### IV. Grounded Answers or Escalation

- Domain answers MUST be grounded in retrieved context or tool results and MUST cite source URLs.
- When grounding fails the system MUST NOT guess; it MUST escalate to a human.
- Google Search grounding and function calling MUST NOT share a single model request.

Rationale: a wrong confident answer to a merchant costs more than an escalation.

### V. Answer Quality for the Merchant (NON-NEGOTIABLE)

Answer quality is a requirement, not polish. Correct facts in a hard-to-read answer count as a
failure. Every answer is written for a Brazilian merchant reading on a phone:

- The first sentence answers the question.
- At most about 120 words unless the user asked for steps; numbered steps only for procedures.
- No markdown bold, headers or tables. No em dash or en dash.
- One language only: the planned one.
- No talk about documents, retrieved context or the system (never "the documents do not
  contain"). Naming where a live value comes from, such as an exchange rate, is allowed.
- Nothing the user did not ask for.
- A comparison explains what each option is for, not only prices.
- Portuguese uses the merchant's words (maquininha, vendas, recebíveis, Pix). English keeps the
  Getnet product names.
- Support answers explain in plain words what happened and what to do next, never a
  field-by-field status dump. Escalation and refusal messages say what happens next.
- Tools MUST return raw values. A code formatter MUST render amounts and dates in the answer
  language before any LLM sees them: `pt` R$ 1.250,00 and 25/11/2026; `en` R$ 1,250.00 and
  25 Nov 2026. No answer may show an ISO date or an unformatted amount.
- Code MUST enforce what is checkable: dashes replaced, markdown bold removed, no ISO date, answer
  language matching the plan. Every violation MUST be logged and counted in a metric.

Rationale: the merchant judges the product by the text on the screen.

### VI. Durable Memory and Human in the Loop

- Conversations MUST persist in SQLite on a Docker volume with turns, a rolling summary written by
  the lite model, and run checkpoints. A conversation MUST survive a restart.
- Follow-ups MUST be resolved through the Router's standalone rewrite.
- Escalation MUST store a checkpoint of the pending run, open a ticket and return status
  `awaiting_human`.
- Operators MUST be able to list tickets, claim one atomically, and resolve it by approve, edit or
  reject.
- Resolving a ticket MUST resume the run from its checkpoint, pass the operator answer through
  Personality, append it to the same conversation, and write an audit entry. Every operator
  action MUST write an audit entry.

Rationale: escalation is only useful if the merchant receives the human answer in context.

### VII. Right Model per Task, Metered and Bounded

- Gemini through the `google-genai` SDK is the only LLM provider at runtime and in evals.
- All model names and thinking levels MUST come from environment variables:
  - planning, critic and memory summary: `GEMINI_ROUTER_MODEL`, thinking minimal;
  - answering agents, synthesis and Personality: `GEMINI_MODEL`, thinking low;
  - embeddings: `GEMINI_EMBEDDING_MODEL`;
  - eval judge: `GEMINI_JUDGE_MODEL`, thinking high, never on the request path.
- Every LLM call MUST go through one client wrapper that:
  - records model, latency, prompt, output and thinking tokens;
  - computes cost in USD from a price table in environment variables, including Google Search
    queries counted from grounding metadata;
  - logs structured JSON with the `request_id`;
  - applies a timeout and exactly one retry on 429 or 5xx;
  - preserves complete model content, including thought signatures, across tool turns;
  - enforces the per-request token budget.
- Limits MUST be explicit and configurable: message length, top-k, tool iterations, supervisor
  iterations, token budget.

Rationale: the final text deserves the stronger model; control decisions do not. One wrapper
makes cost and failure behavior uniform and measurable.

### VIII. Typed Contracts and Graceful Degradation

- Every LLM output that drives control flow MUST be parsed into a Pydantic model.
- Every tool MUST return a typed result and handle its own failures.
- When the budget is exceeded or the LLM stays unavailable, the API MUST still return valid JSON
  and escalate.

Rationale: untyped control flow and unhandled tool errors turn model noise into outages.

### IX. Observability Implemented

Observability is implemented, not described:

- JSON logs carrying the `request_id`.
- Prometheus metrics at `/metrics`.
- Alert rules with `promtool` unit tests.
- A provisioned Grafana dashboard under a docker compose profile.
- Health split into live and ready endpoints.

### X. Evals Are Part of the Product

- The eval dataset MUST cover the official scenarios plus compound, adversarial, authorization,
  multi-turn memory and human-in-the-loop flows.
- A runner MUST run against the live API with deterministic assertions, including every
  answer-quality check in Principle V.
- An LLM judge MUST score, with a typed rubric and a threshold per criterion: correctness,
  groundedness, relevance, helpfulness, and clarity for a merchant. The judge MUST also check that
  the asked facts survived Personality.
- The judge MUST see the same evidence the agents saw, including tool results and the list of web
  sources. Each judgment MUST run with its own token budget.
- In every report row, the answer, evidence and verdicts MUST come from the same run.
- The judge MUST be calibrated against human labels. Retrieval metrics MUST be reported.
- A sealed held-out set's hash MUST be committed before any code; nobody opens the set during the
  session.
- The runner MUST exit non-zero below thresholds and MUST report cost.

Rationale: without measured quality, every prompt change is a guess.

### XI. Traceable Tests

- Every functional requirement MUST have an ID (FR-001, FR-002, ...) and at least one pytest test
  whose name contains that ID.
- Unit tests MUST mock the LLM.
- Integration tests MUST call the HTTP API with the LLM stubbed at the client wrapper.

### XII. Simplicity

Build only what the spec and this constitution ask for. Abstractions without a current caller are
forbidden; any deviation MUST be justified in the plan's complexity tracking.

## Technology Stack and Delivery Constraints

- Python 3.12 managed with uv; FastAPI for the HTTP API; SQLite for persistence.
- The system MUST run with `docker compose up` and with plain `docker build` and `docker run`.
- The image MUST run as non-root, pin its base image by digest, install the uv lockfile frozen,
  declare a healthcheck, and set log size limits.
- Secrets MUST come only from `.env`, which is never committed; `.env.example` MUST be committed
  and list every variable. In CI, `.env` is materialized from repository secrets.
- GitHub Actions MUST run lint, tests, a container smoke test and `promtool` on every push, and a
  live eval on tags.

## Development Workflow and Quality Gates

- Spec-driven development: constitution, spec, plan, tasks, implementation, in that order.
- Each SDD phase (constitution, spec, plan, tasks) and each completed task MUST get its own commit
  on the repository default branch, pushed immediately. Feature and docs branches are forbidden.
  The remote history proves the stages and their times.
- External contracts (SDK behavior, model names, thinking levels, pricing, API shapes) MUST be
  verified in the plan phase before any task depends on them. The constitution phase uses no web
  research and no API calls.
- A task is done only when its FR-tagged tests pass, lint passes, and the checks it touches in
  Principles V and IX are green.

## Governance

- This constitution supersedes all other project practices. Where a spec, plan or task conflicts
  with it, the constitution wins until amended.
- Amendments are made through `/speckit-constitution`, recorded in their own commit on the default
  branch, and include a version bump:
  - MAJOR: removal or backward-incompatible redefinition of a principle;
  - MINOR: a new principle or section, or materially expanded guidance;
  - PATCH: clarifications and wording fixes without semantic change.
- Every plan MUST include a Constitution Check against all principles, repeated after design.
  Every deviation MUST be listed with its justification in the plan's complexity tracking.
- Reviews of specs, plans, tasks and code MUST verify compliance with this document.

**Version**: 1.0.0 | **Ratified**: 2026-11-26 | **Last Amended**: 2026-11-26
