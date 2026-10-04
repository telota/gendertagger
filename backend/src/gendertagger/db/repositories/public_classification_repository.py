"""SQLAlchemy persistence for durable anonymous classification jobs."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import or_, select, update
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from gendertagger.db.rows.public_classification import PublicClassificationJobRow
from gendertagger.models.classification import PredictionResult
from gendertagger.models.common import normalize_utc_datetime
from gendertagger.models.public_classification import (
    PublicClassificationJobRecord,
    PublicClassificationProvenance,
    PublicClassificationStatus,
)
from gendertagger.models.synchronous_classification import ClassifyNamesResponse


class SqlAlchemyPublicClassificationRepository:
    """Map private job contracts to rows in a caller-owned transaction."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def add_job(self, record: PublicClassificationJobRecord) -> PublicClassificationJobRecord:
        """Persist immutable job inputs alongside a durable dispatch intent."""
        row = PublicClassificationJobRow(
            id=record.id,
            retrieval_token_sha256=record.retrieval_token_sha256,
            queue_name=record.queue_name,
            names=list(record.names),
            methods=list(record.methods),
            resolved_method_configs=record.resolved_method_configs,
            provenance=record.provenance.model_dump(mode="json"),
            status=record.status,
            response=record.response.model_dump(mode="json") if record.response else None,
            raw_predictions=(
                [
                    {
                        name: prediction.model_dump(mode="json")
                        for name, prediction in result.items()
                    }
                    for result in record.raw_predictions
                ]
                if record.raw_predictions is not None
                else None
            ),
            failure_code=record.failure_code,
            created_at=record.created_at,
            started_at=record.started_at,
            completed_at=record.completed_at,
            lease_id=record.lease_id,
            lease_until=record.lease_until,
        )
        self._session.add(row)
        self._session.flush()
        return self._record_from_row(row)

    def get_job(self, classification_job_id: UUID) -> PublicClassificationJobRecord | None:
        """Return one private persisted job without modifying its state."""
        row = self._session.get(PublicClassificationJobRow, classification_job_id)
        return self._record_from_row(row) if row is not None else None

    def claim_job(
        self,
        classification_job_id: UUID,
        *,
        now: datetime,
        lease_until: datetime,
        lease_id: UUID,
    ) -> PublicClassificationJobRecord | None:
        """Claim one queued or expired job using a nonblocking row lock."""
        claim_time = normalize_utc_datetime(now)
        lease_expiry = normalize_utc_datetime(lease_until)
        if lease_expiry <= claim_time:
            msg = "classification lease_until must be later than now"
            raise ValueError(msg)
        row = self._session.scalar(
            select(PublicClassificationJobRow)
            .where(
                PublicClassificationJobRow.id == classification_job_id,
                self._recoverable_condition(claim_time),
            )
            .with_for_update(skip_locked=True, of=PublicClassificationJobRow)
            .execution_options(populate_existing=True)
        )
        if row is None:
            return None
        row.status = PublicClassificationStatus.running
        row.started_at = row.started_at or claim_time
        row.lease_id = lease_id
        row.lease_until = lease_expiry
        self._session.flush()
        return self._record_from_row(row)

    def renew_job_lease(
        self,
        classification_job_id: UUID,
        *,
        lease_id: UUID,
        lease_until: datetime,
    ) -> bool:
        """Extend an active worker lease only when its fencing token still matches."""
        renewed_id = self._session.scalar(
            update(PublicClassificationJobRow)
            .where(
                PublicClassificationJobRow.id == classification_job_id,
                PublicClassificationJobRow.status == PublicClassificationStatus.running,
                PublicClassificationJobRow.lease_id == lease_id,
            )
            .values(lease_until=normalize_utc_datetime(lease_until))
            .returning(PublicClassificationJobRow.id)
        )
        self._session.flush()
        return renewed_id is not None

    def complete_job(
        self,
        classification_job_id: UUID,
        *,
        lease_id: UUID,
        response: ClassifyNamesResponse,
        raw_predictions: list[dict[str, PredictionResult]],
        completed_at: datetime,
    ) -> bool:
        """Fence completion by worker token and preserve existing terminal results."""
        return self._finish_job(
            classification_job_id,
            lease_id=lease_id,
            completed_at=completed_at,
            status=PublicClassificationStatus.completed,
            response=response,
            raw_predictions=raw_predictions,
        )

    def fail_job(
        self,
        classification_job_id: UUID,
        *,
        lease_id: UUID,
        completed_at: datetime,
    ) -> bool:
        """Fence failure by worker token and persist only a generic failure code."""
        return self._finish_job(
            classification_job_id,
            lease_id=lease_id,
            completed_at=completed_at,
            status=PublicClassificationStatus.failed,
            response=None,
            raw_predictions=None,
        )

    def _finish_job(
        self,
        classification_job_id: UUID,
        *,
        lease_id: UUID,
        completed_at: datetime,
        status: PublicClassificationStatus,
        response: ClassifyNamesResponse | None,
        raw_predictions: list[dict[str, PredictionResult]] | None,
    ) -> bool:
        statement = (
            update(PublicClassificationJobRow)
            .where(
                PublicClassificationJobRow.id == classification_job_id,
                PublicClassificationJobRow.status == PublicClassificationStatus.running,
                PublicClassificationJobRow.lease_id == lease_id,
            )
            .values(
                status=status,
                response=response.model_dump(mode="json") if response else None,
                raw_predictions=(
                    [
                        {
                            name: prediction.model_dump(mode="json")
                            for name, prediction in result.items()
                        }
                        for result in raw_predictions
                    ]
                    if raw_predictions is not None
                    else None
                ),
                failure_code="classification_failed" if response is None else None,
                completed_at=normalize_utc_datetime(completed_at),
                lease_id=None,
                lease_until=None,
            )
            .returning(PublicClassificationJobRow.id)
        )
        updated_id = self._session.scalar(statement)
        self._session.flush()
        return updated_id is not None

    @staticmethod
    def _recoverable_condition(now: datetime) -> ColumnElement[bool]:
        return or_(
            PublicClassificationJobRow.status == PublicClassificationStatus.queued,
            (
                (PublicClassificationJobRow.status == PublicClassificationStatus.running)
                & (PublicClassificationJobRow.lease_until <= now)
            ),
        )

    @staticmethod
    def _record_from_row(row: PublicClassificationJobRow) -> PublicClassificationJobRecord:
        return PublicClassificationJobRecord(
            id=row.id,
            retrieval_token_sha256=row.retrieval_token_sha256,
            queue_name=row.queue_name,
            names=row.names,
            methods=row.methods,
            resolved_method_configs=row.resolved_method_configs,
            provenance=PublicClassificationProvenance.model_validate(row.provenance),
            status=row.status,
            response=ClassifyNamesResponse.model_validate(row.response) if row.response else None,
            raw_predictions=(
                [
                    {
                        name: PredictionResult.model_validate(prediction)
                        for name, prediction in result.items()
                    }
                    for result in row.raw_predictions
                ]
                if row.raw_predictions is not None
                else None
            ),
            failure_code=row.failure_code,
            created_at=row.created_at,
            started_at=row.started_at,
            completed_at=row.completed_at,
            lease_id=row.lease_id,
            lease_until=row.lease_until,
        )
