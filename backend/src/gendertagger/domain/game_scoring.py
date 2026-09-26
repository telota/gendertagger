"""Server-verifiable scoring for completed game rounds."""

BASE_POINTS = 10


def score_game_round(answered_count: int) -> int:
    """Award a fixed score for each annotation already verified by the server."""
    if answered_count < 0:
        msg = "answered_count must be non-negative"
        raise ValueError(msg)
    return answered_count * BASE_POINTS
