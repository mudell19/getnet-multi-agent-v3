# LLM wrapper interface (`core/llm.py`)

The only module that imports `google.genai`. Agents depend on this interface; tests inject a fake.

```text
class LLM(Protocol):
    def generate(self, *, purpose: str, role: "router"|"answer"|"judge",
                 system: str, contents: list, schema: type[BaseModel] | None = None,
                 tools: list[Callable] | None = None, search: bool = False) -> LLMResult
    def embed(self, texts: list[str], task: "document"|"query") -> list[list[float]]

LLMResult { text, parsed, function_calls, content (whole model Content), sources (web),
            search_queries, usage: TraceCall }
```

Rules
- `role` selects model and thinking level from Settings (`router` → ROUTER/minimal, `answer` →
  MODEL/low, `judge` → JUDGE/high).
- `search=True` and `tools` together raise `ValueError` (400 at the API).
- Before each call: raise `BudgetExceeded` if the request context's tokens ≥
  `REQUEST_TOKEN_BUDGET`. After: add prompt + candidates + thoughts tokens and cost; append a
  `TraceCall`; emit a JSON log line with `request_id`; update metrics.
- Timeout 30 s; one retry on 429/5xx; final failure raises `LLMUnavailable`.
- `embed` sends one `types.Content` per text with `output_dimensionality=768` and asserts
  `len(vectors) == len(texts)`.
- `LLM_MODE=stub` returns `StubLLM`: deterministic outputs and 768-d hash embeddings.
- `request_context(request_id)` context manager opens a fresh budget; required per HTTP request
  and per judge call.
