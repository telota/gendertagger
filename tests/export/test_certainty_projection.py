from __future__ import annotations

import pytest

from gendertagger.export.certainty_projection import project_certainty_to_tei
from gendertagger.models.classification import CertaintyTier

pytestmark = [pytest.mark.unit, pytest.mark.scientific]


@pytest.mark.parametrize(
    ("certainty_tier", "expected"),
    [
        (CertaintyTier.high, "high"),
        (CertaintyTier.low, "low"),
        (CertaintyTier.contested, "unknown"),
        (CertaintyTier.single, "unknown"),
        (CertaintyTier.uncertain, "unknown"),
        (CertaintyTier.no_data, "unknown"),
    ],
)
def test_machine_certainty_projects_per_the_reference_table(
    certainty_tier: CertaintyTier,
    expected: str,
) -> None:
    assert project_certainty_to_tei(certainty_tier, is_human_reviewed=False) == expected


@pytest.mark.parametrize("certainty_tier", list(CertaintyTier))
def test_human_reviewed_decisions_always_project_to_high(certainty_tier: CertaintyTier) -> None:
    assert project_certainty_to_tei(certainty_tier, is_human_reviewed=True) == "high"
