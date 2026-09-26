"""Task-entry read models composed from canonical domain resources."""

from uuid import UUID

from pydantic import BaseModel, ConfigDict

from gendertagger.models.aggregation import AggregationExecution
from gendertagger.models.common import UtcDatetime
from gendertagger.models.project import DatasetSnapshot
from gendertagger.models.run import Run


class ProjectReviewResult(BaseModel):
    """One completed aggregation that can be opened for review, with exact provenance."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: UUID
    created_at: UtcDatetime
    aggregation: AggregationExecution
    run: Run
    snapshot: DatasetSnapshot
