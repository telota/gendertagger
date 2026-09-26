from uuid import uuid4

import pytest
from pydantic import ValidationError

from gendertagger.domain.game_scoring import score_game_round
from gendertagger.models.game import GameRoundCreate


def test_game_score_awards_only_fixed_points_for_verified_answers() -> None:
    assert score_game_round(0) == 0
    assert score_game_round(3) == 30

    with pytest.raises(ValueError, match="non-negative"):
        score_game_round(-1)


def test_game_round_command_rejects_reused_annotations_and_oversized_rounds() -> None:
    annotation_id = uuid4()
    with pytest.raises(ValidationError, match="must not repeat"):
        GameRoundCreate(
            id=uuid4(),
            aggregation_execution_id=uuid4(),
            round_size=10,
            annotation_ids=(annotation_id, annotation_id),
        )

    with pytest.raises(ValidationError, match="must not exceed round_size"):
        GameRoundCreate(
            id=uuid4(),
            aggregation_execution_id=uuid4(),
            round_size=10,
            annotation_ids=tuple(uuid4() for _ in range(11)),
        )
