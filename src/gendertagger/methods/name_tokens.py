"""Shared forename tokenization and per-token vote consensus.

The published name-based classifiers (`gender_guesser`, `wiki_gendersort`,
`hivoto`, and `nomquamgender`) split a person's forename into candidate name
tokens under one identical filter, classify each token independently, and reduce
the per-token labels to one label by a priority-ranked consensus with explicit
conflict detection. This module owns that shared behavior so the frozen token
filter cannot drift between adapters; per-token classification and the label
alphabet stay method-specific. See ADR-0012.

The filter and consensus are pure and deterministic: their output depends only
on the forename tokens and the caller's declared label priority, never on
insertion or iteration order beyond the deterministic token sequence.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Final

# Label returned when a forename yields no checkable tokens. It normalizes to an
# abstention (``no_name`` is a shared abstain label) rather than a substantive
# answer.
NO_NAME_LABEL: Final = "no_name"

# Label returned when definite male and female tokens disagree within one
# forename. It normalizes to substantive ``unknown`` for every name-based
# adapter, distinct from an abstention.
CONFLICT_LABEL: Final = "conflict"

# Tokens that are structurally not personal first names: bracketed relational
# qualifiers, single-letter initials, digits, and dash-only fragments.
_SKIP_PATTERN: Final = re.compile(
    r"""
    ^\(          |   # bracketed: (Frau), (Kinder...)
    \)$          |   # closing bracket (trailing)
    ^\w\.$       |   # single-letter abbreviations: L., A., ...
    ^\d          |   # starts with digit
    ^-+$             # dashes only
    """,
    re.VERBOSE,
)

# Lowercase particles, prepositions, abbreviations, and register noise words
# checked against the token lowercased and stripped of trailing punctuation.
# This set is ported verbatim and is identical across all four reference
# name-based adapters; changing it is a scientific change requiring an ADR.
_PARTICLES: Final[frozenset[str]] = frozenset(
    {
        # Noble/name particles (German, Dutch, French, Italian, Spanish, Arabic, Scandinavian)
        "af",
        "da",
        "de",
        "dei",
        "del",
        "della",
        "dem",
        "der",
        "des",
        "di",
        "du",
        "ibn",
        "il",
        "la",
        "le",
        "les",
        "van",
        "vom",
        "von",
        "zu",
        "zum",
        "zur",
        "v",
        "v.",
        # French titles / particles
        "comte",
        "conte",
        "duc",
        "d",
        # Arabic
        "al",
        "al-din",
        "al-husayn",
        # Prepositions / conjunctions
        "an",
        "e",
        "in",
        "mit",
        "of",
        "und",
        # Abbreviations / suffixes
        "d.",
        "geb.",
        "jr.",
        "jun.",
        "med.",
        "od.",
        "phil.",
        "sen.",
        # Descriptive noise words that appear in the register
        "biblische",
        "die",
        "eisernen",
        "historisch-philologische",
        "ihre",
        "kurmärkische",
        "mathematische",
        "mittlere",
        "philosophisch-historische",
        "philosophische",
        "physikalisch-mathematische",
        "physikalische",
        "reformiertes",
    }
)


def _forename_string_tokens(forename: str) -> list[str]:
    tokens: list[str] = []
    for token in forename.split():
        if _SKIP_PATTERN.match(token):
            continue
        normalized = token.lower().rstrip(".,;:)\"'")
        if normalized in _PARTICLES:
            continue
        tokens.append(token)
    return tokens


def usable_forename_tokens(forenames: Sequence[str]) -> list[str]:
    """Return the ordered checkable name tokens across a person's forenames.

    Each forename value is split on whitespace and filtered by the shared skip
    pattern and particle set, then the surviving tokens are concatenated in
    forename order. Splitting per forename value is equivalent to the legacy
    single-column whitespace split because both operate on whitespace-separated
    tokens.

    Args:
        forenames: The person's forename values in source order.

    Returns:
        The checkable tokens in order; empty when no forename token survives.
    """
    return [token for forename in forenames for token in _forename_string_tokens(forename)]


def consensus_label(
    results: Sequence[str],
    *,
    priority: Sequence[str],
    male_labels: frozenset[str],
    female_labels: frozenset[str],
) -> str:
    """Reduce per-token labels to one label by priority with conflict detection.

    Returns :data:`NO_NAME_LABEL` for no results and :data:`CONFLICT_LABEL`
    when definite male and female labels both occur. Otherwise the label with
    the highest ``priority`` rank wins. A label absent from ``priority`` is
    ranked as weakly as the first priority entry, matching the reference
    pipeline. The result is deterministic for a fixed token sequence.

    Args:
        results: Per-token labels in token order.
        priority: Labels from weakest to strongest signal; the last wins ties.
        male_labels: Labels counted as a definite male vote for conflict checks.
        female_labels: Labels counted as a definite female vote for conflict checks.

    Returns:
        The single consensus label.
    """
    if not results:
        return NO_NAME_LABEL
    definite = {result for result in results if result in male_labels | female_labels}
    if definite & male_labels and definite & female_labels:
        return CONFLICT_LABEL
    rank = {label: index for index, label in enumerate(priority)}
    return max(results, key=lambda result: rank.get(result, 0))
