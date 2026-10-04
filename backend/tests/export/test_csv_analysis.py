from __future__ import annotations

import csv
import json
from io import StringIO
from uuid import UUID, uuid4

import pytest

from gendertagger.export.csv_analysis import build_csv_analysis
from gendertagger.export.json_bundle import build_json_bundle
from gendertagger.models.classification import AgreementTier, CanonicalLabel, CertaintyTier
from gendertagger.models.export import ExportPersonRecord

pytestmark = [pytest.mark.unit, pytest.mark.scientific]


def test_csv_has_a_header_and_one_row_per_person() -> None:
    labeled = ExportPersonRecord(
        tei_id="p1",
        person_record_id=uuid4(),
        label=CanonicalLabel.male,
        evidence="assigned",
        resp="#editor",
        cert="high",
        agreement_tier=AgreementTier.unanimous,
        certainty_tier=CertaintyTier.high,
        is_human_reviewed=True,
    )
    unlabeled = ExportPersonRecord(
        tei_id="p2",
        person_record_id=uuid4(),
        label=None,
        agreement_tier=AgreementTier.no_answer,
        certainty_tier=CertaintyTier.no_data,
        is_human_reviewed=False,
    )

    rows = list(csv.reader(StringIO(build_csv_analysis([labeled, unlabeled]).decode("utf-8"))))

    assert rows[0] == [
        "tei_id",
        "label",
        "evidence",
        "resp",
        "cert",
        "agreement_tier",
        "certainty_tier",
        "human_reviewed",
    ]
    assert rows[1] == ["p1", "male", "assigned", "#editor", "high", "unanimous", "high", "true"]
    assert rows[2] == ["p2", "", "", "", "", "no_answer", "no_data", "false"]


def test_empty_csv_has_only_the_header() -> None:
    rows = list(csv.reader(StringIO(build_csv_analysis([]).decode("utf-8"))))

    assert len(rows) == 1


def _labeled_record(*, tei_id: str = "p1", resp: str = "#editor") -> ExportPersonRecord:
    return ExportPersonRecord(
        tei_id=tei_id,
        person_record_id=UUID(int=1),
        label=CanonicalLabel.male,
        evidence="assigned",
        resp=resp,
        cert="high",
        agreement_tier=AgreementTier.unanimous,
        certainty_tier=CertaintyTier.high,
        is_human_reviewed=True,
    )


@pytest.mark.parametrize(
    "value",
    [
        "=1+1",
        "+1+1",
        "-1+1",
        "@SUM(1;1)",
        "\uff1d1+1",
        "\uff0b1+1",
        "\uff0d1+1",
        "\uff20SUM(1;1)",
        " =1+1",
        "\t@editor",
        "\r=1+1",
        "\n=1+1",
        "\vordinary",
        "\fordinary",
        "\x1fordinary",
        "\x7fordinary",
        "\x85ordinary",
        "\u00a0ordinary",
        "\u2003ordinary",
        "\u200bordinary",
        "\u202eordinary",
        "\ufeffordinary",
        "\ufeff \t=1+1",
        '=1+1,"quoted"\r\nline',
    ],
)
def test_csv_protects_hazardous_identifiers_and_responsibility_text(value: str) -> None:
    record = _labeled_record(tei_id=value, resp=value)

    rows = list(csv.DictReader(StringIO(build_csv_analysis([record]).decode("utf-8"))))

    assert len(rows) == 1
    assert rows[0]["tei_id"] == "'" + value
    assert rows[0]["resp"] == "'" + value
    assert rows[0]["evidence"] == "assigned"
    assert rows[0]["cert"] == "high"
    assert None not in rows[0]


@pytest.mark.parametrize(
    "value",
    [
        "ordinary text",
        "Müller",
        "person=1",
        "00123",
        "2026-10-04",
        "1E10",
        "'=1+1",
        "'original",
        'comma,quote"\r\nline',
    ],
)
def test_csv_preserves_ordinary_identifiers_and_field_boundaries(value: str) -> None:
    record = _labeled_record(tei_id=value, resp=value)

    rows = list(csv.DictReader(StringIO(build_csv_analysis([record]).decode("utf-8"))))

    assert len(rows) == 1
    assert rows[0]["tei_id"] == value
    assert rows[0]["resp"] == value
    assert rows[0]["human_reviewed"] == "true"
    assert len(rows[0]) == 8
    assert None not in rows[0]


def test_csv_safety_does_not_change_canonical_records_or_lossless_json() -> None:
    resp = "\t@editor"
    record = _labeled_record(
        tei_id='\ufeff \t=1+1,"source"\r\nnext',
        resp=resp,
    )
    original = record.model_dump(mode="json")
    json_before = build_json_bundle([record])
    records = [record]

    content = build_csv_analysis(records)
    row = next(csv.DictReader(StringIO(content.decode("utf-8"))))

    assert row["tei_id"] == "'" + record.tei_id
    assert row["resp"] == "'" + resp
    assert record.model_dump(mode="json") == original
    assert build_json_bundle(records) == json_before
    assert json.loads(json_before) == [original]
