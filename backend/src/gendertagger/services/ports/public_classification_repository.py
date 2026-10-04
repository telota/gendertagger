"""Transaction-scoped persistence contract for anonymous classification jobs."""

from datetime import datetime
from typing import Protocol
from uuid import UUID

from gendertagger.models.classification import PredictionResult
from gendertagger.models.public_classification import PublicClassificationJobRecord
from gendertagger.models.synchronous_classification import ClassifyNamesResponse


class PublicClassificationRepository(Protocol):
    """Persist immutable inputs and lease-fenced classification results."""

    def add_job(self, record: PublicClassificationJobRecord) -> PublicClassificationJobRecord:
        """Persist a new job without committing the surrounding transaction."""
        ...

    def get_job(self, classification_job_id: UUID) -> PublicClassificationJobRecord | None:
        """Return one private job record, or ``None`` when it does not exist."""
        ...

    def claim_job(
        self,
        classification_job_id: UUID,
        *,
        now: datetime,
        lease_until: datetime,
        lease_id: UUID,
    ) -> PublicClassificationJobRecord | None:
        """Claim queued or expired running work; reject concurrent live leases."""
        ...

    def renew_job_lease(
        self,
        classification_job_id: UUID,
        *,
        lease_id: UUID,
        lease_until: datetime,
    ) -> bool:
        """Extend the current running worker lease; reject superseded tokens."""
        ...

    def complete_job(
        self,
        classification_job_id: UUID,
        *,
        lease_id: UUID,
        response: ClassifyNamesResponse,
        raw_predictions: list[dict[str, PredictionResult]],
        completed_at: datetime,
    ) -> bool:
        """Persist one terminal response only for the current worker lease."""
        ...

    def fail_job(
        self,
        classification_job_id: UUID,
        *,
        lease_id: UUID,
        completed_at: datetime,
    ) -> bool:
        """Persist a sanitized terminal failure only for the current lease."""
        ...
