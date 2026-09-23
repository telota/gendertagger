from __future__ import annotations

import csv
from io import StringIO
from uuid import uuid4

import pytest

from gendertagger.export.csv_analysis import build_csv_analysis
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
