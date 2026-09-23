"""Wilson score confidence interval for per-class recall."""

from __future__ import annotations

from statsmodels.stats.proportion import proportion_confint

_ROUNDING_DECIMAL_PLACES = 3


def wilson_recall_interval(
    correct: int,
    class_size: int,
    *,
    confidence_level: float,
) -> dict[str, float]:
    """Compute recall and its two-sided Wilson score confidence interval.

    Args:
        correct: Number of correctly labeled entries in the class.
        class_size: Total benchmark entries in the class.
        confidence_level: Two-sided confidence level, e.g. ``0.95``.

    Returns:
        A mapping with ``recall``, ``ci_low``, and ``ci_high``, each rounded
        to three decimal places. Returns an all-zero mapping when
        ``class_size`` is zero (no benchmark support for that class), since
        the Wilson interval is undefined without observations.
    """
    if class_size == 0:
        return {"recall": 0.0, "ci_low": 0.0, "ci_high": 0.0}

    ci_low, ci_high = proportion_confint(
        correct,
        class_size,
        alpha=1.0 - confidence_level,
        method="wilson",
    )
    return {
        "recall": round(correct / class_size, _ROUNDING_DECIMAL_PLACES),
        "ci_low": round(max(0.0, float(ci_low)), _ROUNDING_DECIMAL_PLACES),
        "ci_high": round(min(1.0, float(ci_high)), _ROUNDING_DECIMAL_PLACES),
    }
