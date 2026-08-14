"""Canonical durable task-dispatch contracts."""

from enum import StrEnum
from typing import Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from gendertagger.models.common import UtcDatetime
from gendertagger.models.run import QUEUE_NAME_PATTERN, TaskBatchMessage


class BatchDispatchStatus(StrEnum):
    """Delivery lifecycle for one durable task-batch outbox entry."""

    pending = "pending"
    published = "published"


class BatchDispatchCreate(BaseModel):
    """Validated durable dispatch intent created with one task batch."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    task_batch_id: UUID
    queue_name: str = Field(pattern=QUEUE_NAME_PATTERN, max_length=100)
    payload: TaskBatchMessage
    available_at: UtcDatetime

    @model_validator(mode="after")
    def _validate_payload_identity(self) -> Self:
        if self.payload.task_batch_id != self.task_batch_id:
            msg = "dispatch payload task_batch_id must match its durable dispatch"
            raise ValueError(msg)
        return self


class BatchDispatch(BatchDispatchCreate):
    """Canonical read model for one durable task-batch dispatch attempt."""

    id: UUID
    status: BatchDispatchStatus
    attempt_count: int = Field(ge=0)
    lease_owner: str | None = Field(default=None, max_length=255)
    lease_until: UtcDatetime | None = None
    published_at: UtcDatetime | None = None
    last_error: str | None = None
    created_at: UtcDatetime
    updated_at: UtcDatetime

    @field_validator("lease_owner")
    @classmethod
    def _validate_lease_owner(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            msg = "dispatch lease_owner must not be blank"
            raise ValueError(msg)
        return value

    @model_validator(mode="after")
    def _validate_delivery_state(self) -> Self:
        if (self.lease_owner is None) != (self.lease_until is None):
            msg = "dispatch lease_owner and lease_until must be present together"
            raise ValueError(msg)
        if self.status is BatchDispatchStatus.pending:
            if self.published_at is not None:
                msg = "a pending dispatch must not have published_at"
                raise ValueError(msg)
        elif self.published_at is None:
            msg = "a published dispatch requires published_at"
            raise ValueError(msg)
        elif self.lease_owner is not None:
            msg = "a published dispatch must not retain a relay lease"
            raise ValueError(msg)
        return self
