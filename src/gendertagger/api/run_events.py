"""Server-Sent Events projection of persisted run progress."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from uuid import UUID

from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from gendertagger.models.lifecycle import MethodExecutionStatus, RunStatus
from gendertagger.models.run import MethodExecutionStateEvent, Progress, RunStateEvent
from gendertagger.services.ports.persistence_errors import ResourceNotFoundError
from gendertagger.services.runs import RunService

RUN_STATE_CHANGED = "run.state_changed"
RUN_PROGRESS = "run.progress"
METHOD_EXECUTION_STATE_CHANGED = "method_execution.state_changed"
METHOD_EXECUTION_PROGRESS = "method_execution.progress"
RUN_COMPLETED = "run.completed"
RUN_FAILED = "run.failed"

_DEFAULT_POLL_INTERVAL_SECONDS = 1.0
_DEFAULT_MAX_STREAM_SECONDS = 300.0
_TERMINAL = {RunStatus.completed, RunStatus.completed_with_errors, RunStatus.failed}
_SUCCEEDED = {RunStatus.completed, RunStatus.completed_with_errors}


def _sse(event: str, payload: BaseModel) -> str:
    return f"event: {event}\ndata: {payload.model_dump_json()}\n\n"


async def stream_run_events(
    run_service: RunService,
    run_id: UUID,
    *,
    poll_interval_seconds: float = _DEFAULT_POLL_INTERVAL_SECONDS,
    max_stream_seconds: float = _DEFAULT_MAX_STREAM_SECONDS,
) -> AsyncIterator[str]:
    """Emit persisted run/execution progress as SSE until the run is terminal.

    Persisted PostgreSQL state is authoritative; a disconnected client recovers
    the current state with ``GET /runs/{run_id}``. No event log is kept yet, so
    ``Last-Event-ID`` resume is not offered.
    """
    previous_run: tuple[RunStatus, Progress] | None = None
    previous_executions: dict[UUID, tuple[MethodExecutionStatus, Progress]] = {}
    elapsed = 0.0
    while True:
        try:
            run = await run_in_threadpool(run_service.get_run, run_id)
            executions = await run_in_threadpool(run_service.list_executions, run_id)
        except ResourceNotFoundError:
            return

        run_event = RunStateEvent(run_id=run.id, status=run.status, progress=run.progress)
        if previous_run is None or previous_run[0] != run.status:
            yield _sse(RUN_STATE_CHANGED, run_event)
        if previous_run is None or previous_run[1] != run.progress:
            yield _sse(RUN_PROGRESS, run_event)
        previous_run = (run.status, run.progress)

        for execution in executions:
            event = MethodExecutionStateEvent(
                method_execution_id=execution.id,
                method_name=execution.method_name,
                status=execution.status,
                progress=execution.progress,
            )
            previous = previous_executions.get(execution.id)
            if previous is None or previous[0] != execution.status:
                yield _sse(METHOD_EXECUTION_STATE_CHANGED, event)
            if previous is None or previous[1] != execution.progress:
                yield _sse(METHOD_EXECUTION_PROGRESS, event)
            previous_executions[execution.id] = (execution.status, execution.progress)

        if run.status in _TERMINAL:
            yield _sse(RUN_COMPLETED if run.status in _SUCCEEDED else RUN_FAILED, run_event)
            return
        elapsed += poll_interval_seconds
        if elapsed >= max_stream_seconds:
            return
        await asyncio.sleep(poll_interval_seconds)
