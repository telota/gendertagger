"""Celery-backed publisher for persisted task-dispatch outbox messages."""

from typing import Any
from uuid import UUID

from gendertagger.models.dispatch import DispatchMessage
from gendertagger.models.run import TaskBatchMessage
from gendertagger.tasks.aggregation import EXECUTE_AGGREGATION_TASK_NAME
from gendertagger.tasks.execution import EXECUTE_BATCH_TASK_NAME


class CeleryMessagePublisher:
    """Publish one validated envelope by stable task name and work identifier."""

    def __init__(self, celery_app: Any) -> None:
        self._celery_app = celery_app

    def publish(
        self,
        message: DispatchMessage,
        *,
        queue_name: str,
        task_id: UUID,
    ) -> None:
        """Publish one identifiers-only application-work message to Celery."""
        if isinstance(message, TaskBatchMessage):
            if task_id != message.task_batch_id:
                msg = "broker task_id must match the task-batch message"
                raise ValueError(msg)
            task_name = EXECUTE_BATCH_TASK_NAME
            kwargs = {
                "method_execution_id": str(message.method_execution_id),
                "task_batch_id": str(message.task_batch_id),
            }
        else:
            if task_id != message.aggregation_execution_id:
                msg = "broker task_id must match the aggregation message"
                raise ValueError(msg)
            task_name = EXECUTE_AGGREGATION_TASK_NAME
            kwargs = {
                "aggregation_execution_id": str(message.aggregation_execution_id),
            }
        self._celery_app.send_task(
            task_name,
            kwargs=kwargs,
            queue=queue_name,
            task_id=str(task_id),
            retry=False,
        )
