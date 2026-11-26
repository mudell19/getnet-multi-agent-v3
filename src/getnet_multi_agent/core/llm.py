"""The only module that imports google.genai: model routing, cost, budget, retry and tracing."""

from __future__ import annotations

import time
from typing import Any, Literal

import httpx
from google import genai
from google.genai import errors, types
from pydantic import BaseModel

from getnet_multi_agent.contracts import (
    LLM,
    LLMResult,
    LLMRole,
    LLMUnavailable,
    Source,
    ToolSpec,
    TraceCall,
)
from getnet_multi_agent.core import metrics
from getnet_multi_agent.core.context import current
from getnet_multi_agent.core.logging import log_event
from getnet_multi_agent.core.settings import LLM_TIMEOUT_S, Settings, get_settings

RETRY_DELAY_S = 1.0
EMBED_BATCH = 100


def record_call(call: TraceCall) -> None:
    """Charge the open request context, log the call and update metrics."""
    ctx = current()
    if ctx is not None:
        ctx.charge(call)
    log_event("llm_call", **call.model_dump())
    metrics.LLM_TOKENS.labels(call.model, "prompt").inc(call.prompt_tokens)
    metrics.LLM_TOKENS.labels(call.model, "output").inc(call.output_tokens)
    metrics.LLM_TOKENS.labels(call.model, "thinking").inc(call.thinking_tokens)
    metrics.LLM_COST.labels(call.model).inc(call.cost_usd)


def check_budget() -> None:
    ctx = current()
    if ctx is not None:
        ctx.check_budget()


def _retryable(exc: Exception) -> bool:
    if isinstance(exc, httpx.TimeoutException):
        return True
    return isinstance(exc, errors.APIError) and (exc.code == 429 or (exc.code or 0) >= 500)


def _with_retry(fn, what: str):
    for attempt in (1, 2):
        try:
            return fn()
        except (errors.APIError, httpx.HTTPError) as exc:
            if attempt == 1 and _retryable(exc):
                log_event("llm_retry", level="warning", what=what, error=str(exc)[:200])
                time.sleep(RETRY_DELAY_S)
                continue
            raise LLMUnavailable(f"{what}: {exc}") from exc
    raise LLMUnavailable(what)  # unreachable


def _to_contents(contents: list[Any]) -> list[Any]:
    out: list[Any] = []
    for item in contents:
        if isinstance(item, str):
            out.append(types.Content(role="user", parts=[types.Part(text=item)]))
        elif isinstance(item, dict) and "function_response" in item:
            fr = item["function_response"]
            part = types.Part.from_function_response(name=fr["name"], response=fr["response"])
            prev = out[-1] if out else None
            if (isinstance(prev, types.Content) and prev.role == "user" and prev.parts
                    and all(p.function_response is not None for p in prev.parts)):
                prev.parts.append(part)
            else:
                out.append(types.Content(role="user", parts=[part]))
        else:
            out.append(item)  # model Content from an earlier LLMResult: thought signatures survive
    return out


class GeminiLLM(LLM):
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()
        self._client: Any = None

    @property
    def client(self) -> Any:
        if self._client is None:
            self._client = genai.Client(
                api_key=self.settings.GEMINI_API_KEY,
                http_options=types.HttpOptions(timeout=LLM_TIMEOUT_S * 1000),
            )
        return self._client

    def _model(self, role: LLMRole) -> tuple[str, str]:
        s = self.settings
        return {
            "router": (s.GEMINI_ROUTER_MODEL, s.GEMINI_ROUTER_THINKING),
            "answer": (s.GEMINI_MODEL, s.GEMINI_MODEL_THINKING),
            "judge": (s.GEMINI_JUDGE_MODEL, s.GEMINI_JUDGE_THINKING),
        }[role]

    def _prices(self, model: str) -> tuple[float, float]:
        s = self.settings
        if model == s.GEMINI_ROUTER_MODEL:
            return s.PRICE_LITE_INPUT_PER_M, s.PRICE_LITE_OUTPUT_PER_M
        return s.PRICE_FLASH_INPUT_PER_M, s.PRICE_FLASH_OUTPUT_PER_M

    def cost(self, model: str, prompt: int, candidates: int, thoughts: int, searches: int) -> float:
        p_in, p_out = self._prices(model)
        return ((prompt * p_in + (candidates + thoughts) * p_out) / 1_000_000
                + searches * self.settings.PRICE_SEARCH_PER_1K / 1000)

    def generate(
        self,
        *,
        purpose: str,
        role: LLMRole,
        system: str,
        contents: list[Any],
        schema: type[BaseModel] | None = None,
        tools: list[ToolSpec] | None = None,
        search: bool = False,
    ) -> LLMResult:
        if search and (tools or schema):
            raise ValueError("search grounding cannot share a request with tools or schema")
        model, level = self._model(role)
        cfg: dict[str, Any] = {
            "system_instruction": system,
            "thinking_config": types.ThinkingConfig(thinking_level=level),
        }
        if schema is not None:
            cfg["response_mime_type"] = "application/json"
            cfg["response_schema"] = schema
        if search:
            cfg["tools"] = [types.Tool(google_search=types.GoogleSearch())]
        if tools:
            cfg["tools"] = [types.Tool(function_declarations=[
                types.FunctionDeclaration(name=t.name, description=t.description,
                                          parameters=t.parameters) for t in tools])]
            cfg["automatic_function_calling"] = types.AutomaticFunctionCallingConfig(disable=True)
        config = types.GenerateContentConfig(**cfg)
        payload = _to_contents(contents)

        check_budget()
        start = time.monotonic()
        resp = _with_retry(
            lambda: self.client.models.generate_content(model=model, contents=payload, config=config),
            f"generate {purpose}",
        )
        latency_ms = int((time.monotonic() - start) * 1000)

        try:
            text = resp.text or ""
        except Exception:  # noqa: BLE001 - .text raises on some non-text candidates
            text = ""
        parsed = getattr(resp, "parsed", None) if schema is not None else None
        if schema is not None and not isinstance(parsed, schema):
            try:
                parsed = (schema.model_validate(parsed) if isinstance(parsed, dict)
                          else schema.model_validate_json(text))
            except Exception as exc:  # noqa: BLE001
                raise LLMUnavailable(f"generate {purpose}: invalid structured output") from exc

        calls = [{"name": fc.name, "args": dict(fc.args or {})}
                 for fc in (getattr(resp, "function_calls", None) or [])]
        cand = (resp.candidates or [None])[0]
        content = getattr(cand, "content", None)
        gm = getattr(cand, "grounding_metadata", None)
        sources = [Source(title=c.web.title or "", url=c.web.uri)
                   for c in (getattr(gm, "grounding_chunks", None) or [])
                   if getattr(c, "web", None) is not None and c.web.uri]
        searches = len(getattr(gm, "web_search_queries", None) or [])

        um = resp.usage_metadata
        prompt = (getattr(um, "prompt_token_count", None) or 0) if um else 0
        out = (getattr(um, "candidates_token_count", None) or 0) if um else 0
        thoughts = (getattr(um, "thoughts_token_count", None) or 0) if um else 0
        usage = TraceCall(
            purpose=purpose, model=model, latency_ms=latency_ms, prompt_tokens=prompt,
            output_tokens=out, thinking_tokens=thoughts, search_queries=searches,
            cost_usd=self.cost(model, prompt, out, thoughts, searches),
        )
        record_call(usage)
        return LLMResult(text=text, parsed=parsed, function_calls=calls, content=content,
                         sources=sources, search_queries=searches, usage=usage)

    def embed(self, texts: list[str], task: Literal["document", "query"]) -> list[list[float]]:
        model = self.settings.GEMINI_EMBEDDING_MODEL
        config = types.EmbedContentConfig(
            task_type="RETRIEVAL_DOCUMENT" if task == "document" else "RETRIEVAL_QUERY",
            output_dimensionality=768,
        )
        vectors: list[list[float]] = []
        start = time.monotonic()
        for i in range(0, len(texts), EMBED_BATCH):
            batch = texts[i:i + EMBED_BATCH]
            contents = [types.Content(parts=[types.Part(text=t)]) for t in batch]
            resp = _with_retry(
                lambda c=contents: self.client.models.embed_content(
                    model=model, contents=c, config=config),
                f"embed {task}",
            )
            got = [list(e.values or []) for e in (resp.embeddings or [])]
            if len(got) != len(batch):
                raise LLMUnavailable(f"embed returned {len(got)} vectors for {len(batch)} texts")
            vectors.extend(got)
        assert len(vectors) == len(texts)
        tokens = sum(len(t) for t in texts) // 4
        record_call(TraceCall(
            purpose=f"embed_{task}", model=model,
            latency_ms=int((time.monotonic() - start) * 1000), prompt_tokens=tokens,
            cost_usd=tokens * self.settings.PRICE_EMBEDDING_PER_M / 1_000_000,
        ))
        return vectors


_LLM: LLM | None = None


def get_llm() -> LLM:
    global _LLM
    if _LLM is None:
        if get_settings().LLM_MODE == "stub":
            from getnet_multi_agent.core.stub import StubLLM

            _LLM = StubLLM()
        else:
            _LLM = GeminiLLM()
    return _LLM


def reset_llm() -> None:
    global _LLM
    _LLM = None
