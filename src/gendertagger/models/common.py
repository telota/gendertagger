"""Shared canonical contract value types."""

from datetime import UTC, datetime
from typing import Annotated, TypeAlias

from pydantic import AfterValidator


def normalize_utc_datetime(value: datetime) -> datetime:
    """Require a timezone-aware instant and normalize it to UTC."""
    if value.tzinfo is None or value.utcoffset() is None:
        msg = "timestamp must be timezone-aware"
        raise ValueError(msg)
    return value.astimezone(UTC)


UtcDatetime: TypeAlias = Annotated[datetime, AfterValidator(normalize_utc_datetime)]
