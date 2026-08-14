from __future__ import annotations

import pytest

from gendertagger.methods.name_tokens import (
    CONFLICT_LABEL,
    NO_NAME_LABEL,
    consensus_label,
    usable_forename_tokens,
)

pytestmark = [pytest.mark.unit, pytest.mark.scientific]

_PRIORITY = ("no_name", "unknown", "andy", "mostly_male", "mostly_female", "male", "female")
_MALE = frozenset({"male", "mostly_male"})
_FEMALE = frozenset({"female", "mostly_female"})


def _consensus(results: list[str]) -> str:
    return consensus_label(results, priority=_PRIORITY, male_labels=_MALE, female_labels=_FEMALE)


def test_bracketed_initial_digit_and_dash_tokens_are_skipped() -> None:
    tokens = usable_forename_tokens(["(Frau) L. 3tes -- Karl"])
    assert tokens == ["Karl"]


def test_particles_are_filtered_case_and_trailing_punctuation_insensitively() -> None:
    tokens = usable_forename_tokens(["Johann Von der de, Maria"])
    assert tokens == ["Johann", "Maria"]


def test_dotted_particle_without_a_bare_form_survives_the_reference_quirk() -> None:
    # Trailing "." is stripped before the particle check, so "geb." and "jr."
    # (no bare form) survive, while "v." and "d." match their bare particles.
    assert usable_forename_tokens(["Geb. Jr. V. D."]) == ["Geb.", "Jr."]


def test_tokens_are_flattened_across_forenames_in_order() -> None:
    tokens = usable_forename_tokens(["Karl Wilhelm", "Friedrich"])
    assert tokens == ["Karl", "Wilhelm", "Friedrich"]


def test_no_forenames_yields_no_tokens() -> None:
    assert usable_forename_tokens([]) == []
    assert usable_forename_tokens(["von der"]) == []


def test_consensus_of_no_results_is_the_no_name_label() -> None:
    assert _consensus([]) == NO_NAME_LABEL


def test_definite_male_and_female_disagreement_is_conflict() -> None:
    assert _consensus(["male", "female"]) == CONFLICT_LABEL
    # A leaning label counts as a definite vote for conflict detection.
    assert _consensus(["mostly_male", "female"]) == CONFLICT_LABEL


def test_highest_priority_label_wins_without_a_definite_conflict() -> None:
    assert _consensus(["unknown", "male"]) == "male"
    assert _consensus(["andy", "mostly_male"]) == "mostly_male"
    # Two leaning-male votes never trip conflict detection.
    assert _consensus(["mostly_male", "male"]) == "male"


def test_unanimous_ambiguous_results_stay_ambiguous() -> None:
    assert _consensus(["unknown", "unknown"]) == "unknown"


def test_label_absent_from_priority_ranks_as_weakly_as_the_first_entry() -> None:
    # Matches the reference default rank of 0; a ranked label still outranks it.
    assert _consensus(["surprise", "male"]) == "male"
    assert _consensus(["surprise"]) == "surprise"
