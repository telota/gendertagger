from __future__ import annotations

import pytest

from gendertagger.models.run import TaskBatchPlan
from gendertagger.services.task_batches import plan_task_batches

pytestmark = pytest.mark.unit


def test_even_total_splits_into_equal_contiguous_batches() -> None:
    plans = plan_task_batches(6, batch_size=2)
    assert plans == [
        TaskBatchPlan(batch_index=0, record_offset=0, record_count=2),
        TaskBatchPlan(batch_index=1, record_offset=2, record_count=2),
        TaskBatchPlan(batch_index=2, record_offset=4, record_count=2),
    ]


def test_uneven_total_makes_final_batch_smaller() -> None:
    plans = plan_task_batches(5, batch_size=2)
    assert [(p.record_offset, p.record_count) for p in plans] == [(0, 2), (2, 2), (4, 1)]


def test_total_below_batch_size_is_one_batch() -> None:
    assert plan_task_batches(3, batch_size=10) == [
        TaskBatchPlan(batch_index=0, record_offset=0, record_count=3)
    ]


def test_zero_records_plans_no_batches() -> None:
    assert plan_task_batches(0, batch_size=100) == []


def test_plan_covers_every_record_without_gaps_or_overlap() -> None:
    plans = plan_task_batches(101, batch_size=25)
    offset = 0
    for plan in plans:
        assert plan.record_offset == offset
        offset += plan.record_count
    assert offset == 101


@pytest.mark.parametrize("batch_size", [0, -1])
def test_rejects_nonpositive_batch_size(batch_size: int) -> None:
    with pytest.raises(ValueError, match="batch_size must be positive"):
        plan_task_batches(10, batch_size=batch_size)


def test_rejects_negative_total() -> None:
    with pytest.raises(ValueError, match="total_count must not be negative"):
        plan_task_batches(-1, batch_size=10)
