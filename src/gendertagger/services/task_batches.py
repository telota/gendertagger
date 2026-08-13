"""Pure planning of a method execution into bounded, reproducible batches."""

from gendertagger.models.run import TaskBatchPlan


def plan_task_batches(total_count: int, *, batch_size: int) -> list[TaskBatchPlan]:
    """Split a deterministic person ordering into contiguous bounded batches.

    Batches cover ``[record_offset, record_offset + record_count)`` over the
    snapshot's stable ``(tei_id, id)`` ordering, so the plan is reproducible from
    the immutable snapshot and the persisted batch size alone.

    Args:
        total_count: Number of person records the execution must classify.
        batch_size: Maximum records per batch.

    Returns:
        Ordered plans, one per batch. Empty when ``total_count`` is zero.

    Raises:
        ValueError: If ``total_count`` is negative or ``batch_size`` is not positive.
    """
    if total_count < 0:
        msg = "total_count must not be negative"
        raise ValueError(msg)
    if batch_size <= 0:
        msg = "batch_size must be positive"
        raise ValueError(msg)

    plans: list[TaskBatchPlan] = []
    offset = 0
    while offset < total_count:
        count = min(batch_size, total_count - offset)
        plans.append(
            TaskBatchPlan(batch_index=len(plans), record_offset=offset, record_count=count)
        )
        offset += count
    return plans
