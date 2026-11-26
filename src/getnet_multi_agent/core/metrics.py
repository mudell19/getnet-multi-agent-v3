"""Prometheus metrics on the default registry."""

from __future__ import annotations

from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest

REQUESTS = Counter("getnet_requests_total", "Chat requests by route and status", ["route", "status"])
HTTP_RESPONSES = Counter("getnet_http_responses_total", "HTTP responses by path and code", ["path", "code"])
LATENCY = Histogram(
    "getnet_request_latency_seconds", "Chat request latency",
    buckets=(0.5, 1, 2, 5, 10, 15, 20, 30, 60),
)
LLM_TOKENS = Counter("getnet_llm_tokens_total", "LLM tokens by model and kind", ["model", "kind"])
LLM_COST = Counter("getnet_llm_cost_usd_total", "LLM cost in USD by model", ["model"])
REPLANS = Counter("getnet_replans_total", "Supervisor replans")
REFUSALS = Counter("getnet_refusals_total", "Refusals by reason", ["reason"])
ESCALATIONS = Counter("getnet_escalations_total", "Escalations by reason", ["reason"])
QUALITY_VIOLATIONS = Counter("getnet_quality_violations_total", "Answer quality violations", ["rule"])
TICKETS_OPEN = Gauge("getnet_tickets_open", "Open escalation tickets")
TICKET_OLDEST_AGE = Gauge("getnet_ticket_oldest_age_seconds", "Age of the oldest open ticket")


def render() -> tuple[bytes, str]:
    return generate_latest(), CONTENT_TYPE_LATEST
