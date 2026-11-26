"""FR-031, FR-057, FR-058: JSON logs with request_id and masking; metrics exposition."""

from __future__ import annotations

import json
import logging

from getnet_multi_agent.core import metrics
from getnet_multi_agent.core.context import request_context
from getnet_multi_agent.core.logging import log_event, setup_logging


def test_fr057_log_line_is_json_with_request_id(capsys):
    with request_context(request_id="r_test123", budget=1000):
        log_event("chat_done", route="support", tokens=12)
    line = json.loads(capsys.readouterr().out.strip())
    assert line["request_id"] == "r_test123" and line["event"] == "chat_done"
    assert line["level"] == "info" and line["app_rev"] and line["ts"] and line["tokens"] == 12


def test_fr057_log_outside_context_has_null_request_id(capsys):
    log_event("startup")
    assert json.loads(capsys.readouterr().out)["request_id"] is None


def test_fr031_log_masks_card_and_cpf(capsys):
    log_event("msg", message="card 4111 1111 1111 1111 cpf 529.982.247-25",
              nested={"m": "4111111111111111"})
    out = capsys.readouterr().out
    assert "4111 1111" not in out and "529.982" not in out and "4111111111111111" not in out
    assert "[card ****1111]" in out and "[cpf ***]" in out


def test_fr057_stdlib_logging_goes_through_json(capsys):
    setup_logging()
    logging.getLogger("uvicorn.error").info("server up")
    rec = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert rec["message"] == "server up" and rec["logger"] == "uvicorn.error"


def test_fr058_metrics_render():
    metrics.REQUESTS.labels("support", "answered").inc()
    metrics.LLM_TOKENS.labels("m", "prompt").inc(3)
    metrics.TICKETS_OPEN.set(2)
    body, ctype = metrics.render()
    text = body.decode()
    assert "getnet_requests_total" in text and "getnet_llm_tokens_total" in text
    assert "getnet_request_latency_seconds_bucket" in text and "getnet_tickets_open 2.0" in text
    assert ctype.startswith("text/plain")
