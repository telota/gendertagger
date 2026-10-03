"""Synthetic legacy-characterization expectations for Wiki-Gendersort replacement."""

from __future__ import annotations

from collections import Counter
from pathlib import Path

import pytest
from unidecode import unidecode

import gendertagger.methods.adapters.wiki_gendersort as wiki_adapter
from gendertagger.methods.adapters.wiki_gendersort import (
    WikiGendersortConfig,
    WikiGendersortMethod,
    WikiGendersortTable,
    compile_wiki_gendersort_lookup,
)
from gendertagger.methods.wiki_gendersort_rules import clean_candidates, resolve_candidates
from gendertagger.models.person import PersonInput

pytestmark = [pytest.mark.unit, pytest.mark.scientific]


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("", []),
        (" ", []),
        ("NULL", ["Null"]),
        ("null", ["Null"]),
        ("NuLl", ["Null"]),
        ("NUL L", ["Nul"]),
        ("123-...", []),
        ("J.", []),
        ("a", []),
        ("Ai", ["Ai"]),
        ("Yv", ["Yv"]),
        ("Brr", []),
        ("A1na", ["Na"]),
        ("Ana", ["Ana"]),
        ("aNa", ["Ana"]),
        ("ANA", ["Ana"]),
        ("Aa Aa", ["Aa", "Aa"]),
        ("Ma. Ana", ["Ana", "Ma"]),
        ("Ab. Io", ["Io", "Ab"]),
        ("Abc. Io", ["Abc", "Io"]),
        ("A. Ma. Io", ["Io", "Ma"]),
        ("AnaM.", ["Ana"]),
        ("AnaM.N.", ["Anam"]),
        ("AAM.", ["Aam"]),
        ("AaM.", ["Aa"]),
        ("AiM.", ["Ai"]),
        ("Anam.", ["Anam"]),
        ("Ana.M", ["Ana"]),
        ("A.B.Ana", ["Ana"]),
        ("..Ana..Io.", ["Ana", "Io"]),
        ("Ana..Io", ["Ana", "Io"]),
        ("-Ana-", ["Ana"]),
        ("---Ana---", ["Ana"]),
        ("Ana-Io", ["Ana-io", "Ana", "Io"]),
        ("Ana--Io", ["Ana--io", "Ana", "Io"]),
        ("Ana-Io-Eva", ["Ana-io-eva", "Ana", "Io", "Eva"]),
        ("-J.-Ana-", ["Ana"]),
        ("Ana-Ana", ["Ana-ana", "Ana", "Ana"]),
        ("Ana - Io", ["Ana", "Io"]),
        ('Ana"Io"Eva', ["Ana", "Eva", "Io"]),
        ('"Ana" Io', ["Io", "Ana"]),
        ('Ana "Io" Eva', ["Ana", "Eva", "Io"]),
        ("Ana (Io) Eva", ["Ana", "Eva", "Io"]),
        ("Ana (Io (Eva)) Zoe", ["Ana", "Zoe", "Io", "Eva"]),
        ("Ana (Io) Eva (Zoe)", ["Ana", "Io", "Eva", "Zoe"]),
        ('"Ana" (Io) Eva', ["Eva", "Io", "Ana"]),
        ('Ana("Io")Eva', ["Ana", "Eva", "Io"]),
        ('Ana "Io', ["Ana", "Io"]),
        ("Ana)Io(Eva", ["Ana", "Io", "Eva"]),
        ("Ana[Io]Eva", ["Ana", "Io", "Eva"]),
        ("Ana_Io", ["Ana", "Io"]),
        ("Ana\tIo\nEva", ["Ana", "Io", "Eva"]),
        ("Éva", ["Éva", "Eva"]),
        ("E\u0301va", ["Va"]),
        ("Æva", ["Va"]),
        ("ßara", ["Ara"]),
        ("Œva", ["Va"]),
        ("Ła", ["Ła", "La"]),
        ("Aiǅa", ["Ai"]),
        ("ǰana", ["J\u030cana", "Jana"]),
        ("Aİ", ["Ai\u0307", "Ai"]),
        ("İa", ["İa", "Ia"]),
        ("\u2126a", []),
        ("\U0001d504na", ["\U0001d504na", "Ana"]),
        ("A\u200dna", ["Na"]),
        ("Ana\u2013Io", ["Ana", "Io"]),
        ("Ana\u2011Io", ["Ana", "Io"]),
        ("Ana\u2014Io", ["Ana", "Io"]),
        ("Þora", ["Ora"]),
        ("Ðara", ["Ðara", "Dara"]),
        ("Ǽna", ["Na"]),
        ("Ö", []),
        ("øø", ["Øø", "Oo"]),
        ("ÉÉ", ["Éé", "Ee"]),
        ("Vi", ["Vi"]),
        ("Ana\x00Io", ["Ana", "Io"]),
    ],
)
def test_legacy_characterization_candidate_generation_preserves_exact_order(
    name: str, expected: list[str]
) -> None:
    assert clean_candidates(name, unidecode) == expected


@pytest.mark.parametrize(
    ("name", "entries", "expected"),
    [
        ("", {"Ana": "F"}, ("UNK", None)),
        (" ", {"Ana": "F"}, ("INI", None)),
        ("J.", {"Ana": "F"}, ("INI", None)),
        ("123-...", {"Ana": "F"}, ("INI", None)),
        ("Unlisted", {"Ana": "F"}, ("UNK", None)),
        ("Ana", {"Ana": "UNK"}, ("UNK", None)),
        ("Ana", {"Ana": "INI"}, ("INI", "Ana")),
        ("NULL", {"Null": "F"}, ("UNK", "Null")),
        ("NuLl", {"Null": "UNI"}, ("UNK", "Null")),
        (" null ", {"Null": "F"}, ("F", "Null")),
        ("Ma. Ana", {"Ma": "F", "Ana": "M"}, ("M", "Ana")),
        ("Ana-Io", {"Ana-io": "F", "Ana": "M", "Io": "M"}, ("F", "Ana-io")),
        ("Ana-Io", {"Ana-io": "UNK", "Ana": "M", "Io": "F"}, ("M", "Ana")),
        ("Ana-Io", {"Ana-io": "UNI", "Ana": "UNK", "Io": "F"}, ("F", "Io")),
        ("Ana-Io", {"Ana-io": "UNI", "Ana": "UNI", "Io": "UNK"}, ("UNI", "Ana-io")),
        ("Ana-Io", {"Ana-io": "UNK", "Ana": "UNI", "Io": "UNI"}, ("UNI", "Ana")),
        ("Ana-Io", {"Ana-io": "INI", "Ana": "M", "Io": "F"}, ("INI", "Ana-io")),
        ("Åna", {"Åna": "M", "Ana": "F"}, ("M", "Åna")),
        ("Åna", {"Åna": "UNK", "Ana": "F"}, ("F", "Ana")),
        ("Åna", {"Åna": "UNI", "Ana": "F"}, ("F", "Ana")),
        ("Åna", {"Åna": "UNI", "Ana": "UNI"}, ("UNI", "Åna")),
        ("Ana-Ana", {"Ana": "UNI"}, ("UNI", "Ana")),
        ('"Ana" Io', {"Ana": "F", "Io": "M"}, ("M", "Io")),
    ],
)
def test_legacy_characterization_assignment_preserves_native_label_and_match(
    tmp_path: Path,
    name: str,
    entries: dict[str, str],
    expected: tuple[str, str | None],
) -> None:
    assert resolve_candidates(name, clean_candidates(name, unidecode), entries) == expected
    source = tmp_path / "synthetic-names.txt"
    source.write_text(
        "".join(f"{entry_name}\t{label}\n" for entry_name, label in entries.items()),
        encoding="utf-8",
    )
    lookup_path = tmp_path / "lookup.sqlite3"
    compile_wiki_gendersort_lookup(source, lookup_path, source_sha256="f" * 64)
    table = WikiGendersortTable(lookup_path)

    assert table.assign(name) == expected
    assert table.assign_many([name, name]) == [expected, expected]


class _Resolver:
    def __init__(self, path: Path) -> None:
        self._path = path

    def materialize(self, logical_type: str, sha256: str) -> Path:
        return self._path


@pytest.fixture
def synthetic_method(tmp_path: Path) -> WikiGendersortMethod:
    source = tmp_path / "synthetic-names.txt"
    source.write_text("Aro\tM\nEvo\tF\nAe\tUNI\nNull\tF\nÉvo\tUNI\nMa\tF\n", encoding="utf-8")
    lookup_path = tmp_path / "lookup.sqlite3"
    compile_wiki_gendersort_lookup(source, lookup_path, source_sha256="f" * 64)
    return WikiGendersortMethod(lookup_asset_resolver=_Resolver(lookup_path))


@pytest.mark.parametrize(
    (
        "forenames",
        "tokens",
        "native_labels",
        "token_results",
        "matched_names",
        "raw_label",
        "label",
        "status",
        "normalization_reason",
    ),
    [
        ([], [], [], [], [], "no_name", None, "abstain", "no_input"),
        (["J.", "(Aro)", "de"], [], [], [], [], "no_name", None, "abstain", "no_input"),
        (["J"], ["J"], ["INI"], ["no_name"], [""], "no_name", None, "abstain", "no_input"),
        (
            ["Unlisted"],
            ["Unlisted"],
            ["UNK"],
            ["unknown"],
            [""],
            "unknown",
            "unknown",
            "success",
            "mapped",
        ),
        (["Ae"], ["Ae"], ["UNI"], ["unisex"], ["Ae"], "unisex", "unknown", "success", "mapped"),
        (
            ["NULL"],
            ["NULL"],
            ["UNK"],
            ["unknown"],
            ["Null"],
            "unknown",
            "unknown",
            "success",
            "mapped",
        ),
        (["Évo"], ["Évo"], ["F"], ["female"], ["Evo"], "female", "female", "success", "mapped"),
        (
            ["Aro", "Evo"],
            ["Aro", "Evo"],
            ["M", "F"],
            ["male", "female"],
            ["Aro", "Evo"],
            "conflict",
            "unknown",
            "success",
            "mapped",
        ),
        (
            ["Ae Unlisted Aro"],
            ["Ae", "Unlisted", "Aro"],
            ["UNI", "UNK", "M"],
            ["unisex", "unknown", "male"],
            ["Ae", "", "Aro"],
            "male",
            "male",
            "success",
            "mapped",
        ),
        (
            ["Ma.", "Aro"],
            ["Ma.", "Aro"],
            ["F", "M"],
            ["female", "male"],
            ["Ma", "Aro"],
            "conflict",
            "unknown",
            "success",
            "mapped",
        ),
        (
            ["Evo", "Evo"],
            ["Evo", "Evo"],
            ["F", "F"],
            ["female", "female"],
            ["Evo", "Evo"],
            "female",
            "female",
            "success",
            "mapped",
        ),
    ],
)
def test_legacy_characterization_prediction_preserves_complete_normalization_provenance(
    synthetic_method: WikiGendersortMethod,
    forenames: list[str],
    tokens: list[str],
    native_labels: list[str],
    token_results: list[str],
    matched_names: list[str],
    raw_label: str,
    label: str | None,
    status: str,
    normalization_reason: str,
) -> None:
    config = WikiGendersortConfig(lookup_sha256="f" * 64)
    person = PersonInput(tei_id="synthetic-person", forenames=forenames)
    (prediction,) = synthetic_method.predict_batch([person], config)

    assert prediction.model_dump(mode="json") == {
        "label": label,
        "status": status,
        "method_confidence": None,
        "raw_label": raw_label,
        "raw_output": {
            "tokens": tokens,
            "native_labels": native_labels,
            "token_results": token_results,
            "matched_names": matched_names,
        },
        "metadata": {
            "normalization_version": "wiki_gendersort_v1",
            "normalization_reason": normalization_reason,
        },
    }


def test_character_reuse_respects_each_transliterator_and_each_cleaning_call() -> None:
    first_calls: Counter[str] = Counter()
    second_calls: Counter[str] = Counter()

    def first_transliterate(text: str) -> str:
        first_calls[text] += 1
        return text.replace("é", "a").replace("É", "A")

    def second_transliterate(text: str) -> str:
        second_calls[text] += 1
        return text.replace("é", "i").replace("É", "I")

    assert clean_candidates("éé", first_transliterate) == ["Éé", "Aa"]
    assert clean_candidates("éé", second_transliterate) == ["Éé", "Ii"]
    assert clean_candidates("éé", first_transliterate) == ["Éé", "Aa"]
    assert first_calls == {"é": 2, "Éé": 2}
    assert second_calls == {"é": 1, "Éé": 1}


def test_character_reuse_stays_bounded_without_losing_unusual_accepted_spellings() -> None:
    # A deterministic injected transliterator makes 257 private-use characters
    # count as letters. At least one must be recomputed with a 256-entry bound.
    characters = [chr(0xE000 + index) for index in range(257)]
    name = "".join(characters)
    calls: Counter[str] = Counter()
    replacement = str.maketrans(dict.fromkeys(characters, "a"))

    def transliterate(text: str) -> str:
        calls[text] += 1
        return text.translate(replacement)

    assert clean_candidates(name, transliterate) == [name, "a" * len(characters)]
    assert calls[name] == 1
    assert all(calls[character] >= 1 for character in characters)
    assert sum(calls[character] for character in characters) > len(characters)


def test_batch_reuse_preserves_duplicates_order_and_separate_table_and_batch_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: Counter[str] = Counter()

    def transliterate(text: str) -> str:
        calls[text] += 1
        return str(unidecode(text))

    monkeypatch.setattr(wiki_adapter, "_load_transliterate", lambda: transliterate)
    paths: list[Path] = []
    for index, (aro_label, evo_label) in enumerate((("M", "F"), ("F", "M"))):
        source = tmp_path / f"synthetic-names-{index}.txt"
        source.write_text(
            f"Aro\t{aro_label}\nEvo\t{evo_label}\nAro-Aro\tUNI\nAro-Evo\tUNI\n",
            encoding="utf-8",
        )
        lookup_path = tmp_path / f"lookup-{index}.sqlite3"
        compile_wiki_gendersort_lookup(source, lookup_path, source_sha256="f" * 64)
        paths.append(lookup_path)

    names = ["Aro-Aro", "Evo", "Aro-Aro", "Aro", "Evo", "Aro-Evo", "Aro-Aro"]
    expected = [
        ("M", "Aro"),
        ("F", "Evo"),
        ("M", "Aro"),
        ("M", "Aro"),
        ("F", "Evo"),
        ("M", "Aro"),
        ("M", "Aro"),
    ]
    table = WikiGendersortTable(paths[0])
    assert table.assign_many(names) == expected
    assert calls["Aro-aro"] == 1
    assert calls["Aro-evo"] == 1
    assert calls["Aro"] == 4

    assert table.assign_many(list(reversed(names))) == list(reversed(expected))
    assert calls["Aro-aro"] == 2
    assert calls["Aro"] == 8
    before_empty_batch = calls.copy()
    assert table.assign_many([]) == []
    assert calls == before_empty_batch

    second_table = WikiGendersortTable(paths[1])
    assert second_table.assign_many(names) == [
        ("F", "Aro"),
        ("M", "Evo"),
        ("F", "Aro"),
        ("F", "Aro"),
        ("M", "Evo"),
        ("F", "Aro"),
        ("F", "Aro"),
    ]
    assert calls["Aro-aro"] == 3
    assert calls["Aro"] == 12
