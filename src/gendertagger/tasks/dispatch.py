"""Celery-backed dispatcher enqueuing persisted batches onto their queues."""

from collections.abc import Sequence
from typing import Any

from gendertagger.services.execution import ScheduledBatch
from gendertagger.tasks.execution import EXECUTE_BATCH_TASK_NAME


class CeleryBatchDispatcher:
    """Enqueue each scheduled batch by task name onto its routing-class queue."""

    def __init__(self, celery_app: Any) -> None:
        self._celery_app = celery_app

    def dispatch(self, batches: Sequence[ScheduledBatch]) -> None:
        """Send one execute-batch message per batch; identifiers only, no data."""
        for batch in batches:
            self._celery_app.send_task(
                EXECUTE_BATCH_TASK_NAME,
                kwargs={
                    "method_execution_id": str(batch.method_execution_id),
                    "task_batch_id": str(batch.task_batch_id),
                },
                queue=batch.queue_name,
            )
