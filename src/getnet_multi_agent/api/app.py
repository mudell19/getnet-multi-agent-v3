"""FastAPI app: routers, JSON errors, HTTP metrics and background ingestion at startup."""

from __future__ import annotations

import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from getnet_multi_agent.api import chat, conversations, health, operator
from getnet_multi_agent.core import metrics
from getnet_multi_agent.core.logging import log_event, setup_logging


def _ingest() -> None:
    health.STATE["ingesting"] = True
    try:
        from getnet_multi_agent.rag.ingest import ingest
        n = ingest()
        health.STATE["chunks"] = n
        from getnet_multi_agent.api import deps
        deps.retriever()  # warm the shared store client before traffic arrives
        llm = deps.llm()
        getattr(llm, "client", None)  # and the single model client
        log_event("ingest_done", chunks=n)
    except Exception as e:  # the service starts anyway; readiness stays false
        log_event("ingest_failed", level="error", error=f"{type(e).__name__}: {e}"[:300])
    finally:
        health.STATE["ingesting"] = False


@asynccontextmanager
async def lifespan(_: FastAPI):
    setup_logging()
    threading.Thread(target=_ingest, daemon=True).start()
    yield


app = FastAPI(title="Getnet Multi-Agent Support", lifespan=lifespan)
for r in (chat.router, conversations.router, operator.router, health.router):
    app.include_router(r)


@app.middleware("http")
async def http_metrics(request: Request, call_next):
    try:
        response = await call_next(request)
    except Exception as e:
        log_event("unhandled_error", level="error", error=f"{type(e).__name__}: {e}"[:300],
                  path=request.url.path)
        response = JSONResponse({"detail": "internal error"}, status_code=500)
    route = request.scope.get("route")
    path = getattr(route, "path", "unmatched")
    metrics.HTTP_RESPONSES.labels(path=path, code=str(response.status_code)).inc()
    return response
