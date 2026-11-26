"""Liveness, readiness and metrics."""

from __future__ import annotations

from fastapi import APIRouter, Response
from fastapi.responses import JSONResponse

from getnet_multi_agent.core import metrics

router = APIRouter()
STATE = {"chunks": 0}


@router.get("/health/live")
def live() -> dict:
    return {"status": "ok"}


@router.get("/health/ready")
def ready():
    if STATE["chunks"] <= 0:
        try:
            from getnet_multi_agent.rag.store import Store
            STATE["chunks"] = Store().count()
        except Exception:
            STATE["chunks"] = 0
    if STATE["chunks"] > 0:
        return {"status": "ready", "chunks": STATE["chunks"]}
    return JSONResponse({"status": "not_ready"}, status_code=503)


@router.get("/metrics")
def prometheus_metrics() -> Response:
    body, ctype = metrics.render()
    return Response(content=body, media_type=ctype)
