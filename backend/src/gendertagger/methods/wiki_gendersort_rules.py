"""Pure ordered name rules specified in docs/29-wiki-gendersort-compatibility.md."""

from collections import deque
from collections.abc import Callable, Iterator, Mapping, Sequence
from string import ascii_letters
from typing import Final

_VOWEL_SPELLINGS: Final = "aeiouyAEIOUY"
_RETAINED_PUNCTUATION: Final = frozenset({".", "-"})
_DEFERRED_ABBREVIATION_LENGTHS: Final = frozenset({2, 3})
_FUSED_ABBREVIATION_MIN_LENGTH: Final = 4
_DEFINITIVE_LABELS: Final = frozenset({"M", "F", "INI"})
_CHARACTER_CACHE_MAX_SIZE: Final = 256


def clean_candidates(name: str, transliterate: Callable[[str], str]) -> list[str]:
    """Generate compatible lookup spellings in their observable priority order.

    Character classification uses the injected deterministic transliterator on
    individual source characters. Qualifiers, abbreviations, and compounds
    retain their specified ordering, including duplicate candidate spellings.
    A whole-spelling transliteration immediately follows its native spelling
    when the two differ; it receives no further filtering or case conversion.

    Args:
        name: Original name text, including any qualifiers and punctuation.
        transliterate: Deterministic string-to-string transliteration function.

    Returns:
        Accepted native and transliterated lookup candidates in order.
    """
    character_properties = _make_character_properties(transliterate)
    relocated = _relocate_qualifiers(name)
    separated = "".join(
        character
        if character in _RETAINED_PUNCTUATION or character_properties(character)[0]
        else " "
        for character in relocated
    )
    tokens = [
        token
        for token in separated.split()
        if any(character_properties(character)[0] for character in token)
    ]
    candidates: list[str] = []
    for component in _iter_period_components(tokens):
        for spelling in _iter_compound_spellings(component):
            if not _is_usable_spelling(spelling, character_properties):
                continue
            normalized = (
                spelling.upper()
                if len(spelling) == 1
                else spelling[0].upper() + spelling[1:].lower()
            )
            candidates.append(normalized)
            transliterated = transliterate(normalized)
            if transliterated != normalized:
                candidates.append(transliterated)
    return candidates


def resolve_candidates(
    name: str,
    candidates: Sequence[str],
    native_labels: Mapping[str, str],
) -> tuple[str, str | None]:
    """Select the first definitive table match, retaining an earlier UNI fallback.

    Lookup values are native ``M``, ``F``, ``UNI``, ``INI``, or ``UNK`` labels.
    Missing and UNK entries contribute no match. The original input's exact
    case-insensitive NULL sentinel forces UNK while retaining match evidence.

    Args:
        name: Original unstripped name text used for empty-input and NULL rules.
        candidates: Ordered lookup spellings, with duplicates retained.
        native_labels: Exact-spelling mapping to the supported native labels.

    Returns:
        The native classification label and its matched spelling, or no match.
    """
    label = "UNK"
    matched_candidate: str | None = None
    for candidate in candidates:
        candidate_label = native_labels.get(candidate, "UNK")
        if candidate_label in _DEFINITIVE_LABELS:
            label = candidate_label
            matched_candidate = candidate
            break
        if candidate_label == "UNI" and matched_candidate is None:
            label = candidate_label
            matched_candidate = candidate
    if not candidates and name:
        label = "INI"
    if name.upper() == "NULL":
        label = "UNK"
    return label, matched_candidate


def _make_character_properties(
    transliterate: Callable[[str], str],
) -> Callable[[str], tuple[bool, bool]]:
    """Reuse bounded character properties within one candidate-generation call."""
    properties_by_character: dict[str, tuple[bool, bool]] = {}

    def properties_for(character: str) -> tuple[bool, bool]:
        properties = properties_by_character.get(character)
        if properties is None:
            spelling = transliterate(character)
            properties = (
                len(spelling) == 1 and spelling in ascii_letters,
                spelling in _VOWEL_SPELLINGS,
            )
            if len(properties_by_character) < _CHARACTER_CACHE_MAX_SIZE:
                properties_by_character[character] = properties
        return properties

    return properties_for


def _qualifier_span(name: str) -> tuple[int, int] | None:
    """Locate the next relocatable span, preferring outer parentheses to quotes."""
    opening = name.find("(")
    closing = name.rfind(")")
    if 0 <= opening < closing:
        return opening, closing
    opening = name.find('"')
    closing = name.find('"', opening + 1) if opening >= 0 else -1
    return (opening, closing) if 0 <= opening < closing else None


def _relocate_qualifiers(name: str) -> str:
    """Move enclosed text behind surrounding text while removing its delimiters."""
    remaining = name
    while (span := _qualifier_span(remaining)) is not None:
        opening, closing = span
        remaining = (
            remaining[:opening]
            + " "
            + remaining[closing + 1 :]
            + " "
            + remaining[opening + 1 : closing]
        )
    return remaining


def _iter_period_components(tokens: Sequence[str]) -> Iterator[str]:
    """Apply abbreviation deferrals before yielding period-separated components."""
    pending = deque(tokens)
    while pending:
        token = pending.popleft()
        if (
            len(token) >= _FUSED_ABBREVIATION_MIN_LENGTH
            and token.endswith(".")
            and token[-2].isupper()
            and token[-3].islower()
        ):
            pending.appendleft(token[-2:])
            token = token[:-2]
        if len(token) in _DEFERRED_ABBREVIATION_LENGTHS and token.endswith("."):
            pending.append(token[:-1])
            continue
        yield from token.split(".")


def _iter_compound_spellings(component: str) -> Iterator[str]:
    """Yield the trimmed compound first and then its internal hyphen components."""
    spelling = component.strip("-")
    yield spelling
    if "-" in spelling:
        yield from spelling.split("-")


def _is_usable_spelling(
    spelling: str,
    character_properties: Callable[[str], tuple[bool, bool]],
) -> bool:
    """Apply independent source-character letter-count and vowel requirements."""
    letter_count = sum(character_properties(character)[0] for character in spelling)
    return letter_count > 1 and any(character_properties(character)[1] for character in spelling)
