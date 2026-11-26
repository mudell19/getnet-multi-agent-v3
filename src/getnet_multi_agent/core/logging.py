"""JSON line logging with request_id, app revision and DLP masking."""

from __future__ import annotations

import json
import logging
import os
import sys
from datetime import UTC, datetime
from typing import Any

from getnet_multi_agent.core.context import current
from getnet_multi_agent.security.dlp import mask


def _clean(value: Any) -> Any:
    if isinstance(value, str):
        return mask(value)
    if isinstance(value, dict):
        return {k: _clean(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [_clean(v) for v in value]
    return value


def _line(event: str, level: str, fields: dict[str, Any]) -> str:
    ctx = current()
    record: dict[str, Any] = {
        "ts": datetime.now(UTC).isoformat(),
        "level": level,
        "event": event,
        "request_id": ctx.request_id if ctx else None,
        "app_rev": os.environ.get("APP_REV", "dev"),
    }
    record.update({k: _clean(v) for k, v in fields.items()})
    return json.dumps(record, ensure_ascii=False, default=str)


def log_event(event: str, level: str = "info", **fields: Any) -> None:
    print(_line(event, level, fields), file=sys.stdout, flush=True)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        fields: dict[str, Any] = {"logger": record.name, "message": record.getMessage()}
        if record.exc_info:
            fields["exc"] = self.formatException(record.exc_info)
        return _line("log", record.levelname.lower(), fields)


def setup_logging(level: int = logging.INFO) -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        lg = logging.getLogger(name)
        lg.handlers = []
        lg.propagate = True
