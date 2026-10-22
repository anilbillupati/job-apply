"""Structured JSON logging with secret redaction, plus a timer for external calls."""

import json
import logging
import re
import sys
import time
from contextlib import contextmanager
from datetime import UTC, datetime

from app.config import get_settings

_TOKEN_PATTERNS = [
    re.compile(r"apify_api_[A-Za-z0-9]{10,}"),
    re.compile(r"sk-ant-[A-Za-z0-9_\-]{10,}"),
    re.compile(r"(token=)[^&\s\"']+", re.I),
    re.compile(r"(Bearer\s+)[A-Za-z0-9_\-\.]+", re.I),
]


def redact(text: object) -> str:
    """Remove configured secrets and anything that looks like a token from text."""
    s = str(text)
    for secret in get_settings().secrets:
        s = s.replace(secret, "***")
    for pat in _TOKEN_PATTERNS:
        s = pat.sub(lambda m: (m.group(1) if m.groups() else "") + "***", s)
    return s


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.now(UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        extra = getattr(record, "fields", None)
        if extra:
            payload.update(extra)
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return redact(json.dumps(payload, default=str))


def setup_logging() -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(get_settings().log_level)
    for noisy in ("httpx", "httpcore", "anthropic"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def log(logger: logging.Logger, level: int, msg: str, **fields) -> None:
    logger.log(level, msg, extra={"fields": fields})


@contextmanager
def timed_call(logger: logging.Logger, service: str, op: str, **fields):
    """Time an external call and log it with its outcome. Callers may set info['cost_usd']."""
    info: dict = {}
    start = time.perf_counter()
    try:
        yield info
    except Exception as exc:
        log(logger, logging.WARNING, "external_call", service=service, op=op, ok=False,
            duration_ms=round((time.perf_counter() - start) * 1000), error=redact(exc), **fields, **info)
        raise
    log(logger, logging.INFO, "external_call", service=service, op=op, ok=True,
        duration_ms=round((time.perf_counter() - start) * 1000), **fields, **info)
