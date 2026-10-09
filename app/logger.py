"""Centralized structured JSON logging.

All application logs are emitted as single-line JSON to stdout, following the
Kubernetes standard container logging approach (apps write logs to
stdout/stderr; the node/container runtime collects them).

Example log record:
{
  "timestamp": "2026-10-07T10:04:00.123Z",
  "service": "ai-log-app",
  "level": "ERROR",
  "event": "database_timeout",
  "method": "POST",
  "path": "/api/payment",
  "status_code": 500,
  "latency_ms": 8200
}
"""
import json
import logging
import sys
import time
import uuid
from contextvars import ContextVar
from datetime import UTC, datetime

request_id_var: ContextVar[str] = ContextVar("request_id", default="-")

SERVICE_NAME = "ai-log-app"


class JsonFormatter(logging.Formatter):
    """Formats log records as single-line JSON suitable for log aggregation."""

    RESERVED = set(
        vars(logging.LogRecord("x", 0, "x", 0, "x", None, None))
    ) - {"message", "asctime"}

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.fromtimestamp(
                record.created, tz=UTC
            ).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
            "service": SERVICE_NAME,
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "event": getattr(record, "event", record.name),
            "request_id": request_id_var.get(),
        }
        # Merge any structured extras passed via logging.Logger.extra
        for key, value in record.__dict__.items():
            if key not in payload and key not in self.RESERVED and not key.startswith("_"):
                payload[key] = value
        return json.dumps(payload, default=str)


def setup_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level.upper())
    # Quiet noisy third-party loggers while keeping their output JSON-formatted
    for name in ("uvicorn", "uvicorn.access", "uvicorn.error"):
        logging.getLogger(name).handlers = [handler]
        logging.getLogger(name).propagate = False


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


def new_request_id() -> str:
    return uuid.uuid4().hex[:12]


def monotonic_ms() -> int:
    return int(time.perf_counter() * 1000)
