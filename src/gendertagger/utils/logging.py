"""Logging configuration and JSON formatter for the application."""

import json
import logging
import os
import traceback
from datetime import UTC, datetime


class JsonFormatter(logging.Formatter):
    """A basic JSON formatter for structured logging."""

    def format(self, record: logging.LogRecord) -> str:
        """Format a log record as a JSON string."""
        log_data = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "name": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            log_data["exc_info"] = "".join(traceback.format_exception(*record.exc_info))
        return json.dumps(log_data)


def configure_logging() -> None:
    """Configure structured JSON logging for the application."""
    log_level_str = os.getenv("LOG_LEVEL", "INFO").upper()
    log_format = os.getenv("LOG_FORMAT", "text").lower()

    log_level = getattr(logging, log_level_str, logging.INFO)

    handler = logging.StreamHandler()
    if log_format == "json":
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(
            logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
        )

    # Configure root logger
    logging.basicConfig(
        level=log_level,
        handlers=[handler],
        force=True,
    )

    # Silence verbose loggers if necessary
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
