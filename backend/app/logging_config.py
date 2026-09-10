"""Structured JSON logging configuration."""
import json
import logging
import sys
from datetime import datetime, timezone

from app.config import settings


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        extra = getattr(record, "extra_fields", None)
        if extra:
            payload.update(extra)
        return json.dumps(payload)


def configure_logging() -> None:
    root = logging.getLogger()
    root.setLevel(settings.LOG_LEVEL)
    root.handlers.clear()

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root.addHandler(handler)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
