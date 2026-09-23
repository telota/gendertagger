"""Shared canonical contract value types."""

import hashlib
import json
from datetime import UTC, datetime
from typing import Annotated, TypeAlias

from pydantic import AfterValidator, JsonValue


def normalize_utc_datetime(value: datetime) -> datetime:
    """Require a timezone-aware instant and normalize it to UTC."""
    if value.tzinfo is None or value.utcoffset() is None:
        msg = "timestamp must be timezone-aware"
        raise ValueError(msg)
    return value.astimezone(UTC)


def canonical_json_sha256(value: JsonValue) -> str:
    """Hash a finite JSON value using the run-configuration canonical encoding."""
    encoded = json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


UtcDatetime: TypeAlias = Annotated[datetime, AfterValidator(normalize_utc_datetime)]
