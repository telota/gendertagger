from __future__ import annotations

import pytest

from gendertagger.tasks.execution import _retry_countdown

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("retries", range(8))
def test_retry_countdown_is_within_exponential_jittered_ceiling(retries: int) -> None:
    ceiling = min(2.0 * (2**retries), 60.0)
    countdown = _retry_countdown(retries)
    assert 0.0 <= countdown <= ceiling


def test_retry_countdown_is_bounded_for_large_retry_counts() -> None:
    assert _retry_countdown(100) <= 60.0
