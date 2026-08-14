"""Celery-backed publisher for persisted batch-dispatch outbox messages."""

from typing import Any
from uuid import UUID

from gendertagger.models.run import TaskBatchMessage
from gendertagger.tasks.execution import EXECUTE_BATCH_TASK_NAME


class CeleryMessagePublisher:
    """Publish one validated batch envelope by stable task name and identifier."""

    def __init__(self, celery_app: Any) -> None:
        self._celery_app = celery_app

    def publish(
        self,
        message: TaskBatchMessage,
        *,
        queue_name: str,
        task_id: UUID,
    ) -> None:
        """Publish one identifiers-only execute-batch message to Celery."""
        self._celery_app.send_task(
            EXECUTE_BATCH_TASK_NAME,
            kwargs={
                "method_execution_id": str(message.method_execution_id),
                "task_batch_id": str(message.task_batch_id),
            },
            queue=queue_name,
            task_id=str(task_id),
            retry=False,
        )
