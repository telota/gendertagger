from __future__ import annotations

import json
from uuid import uuid4

import pytest

from gendertagger.export.json_bundle import build_json_bundle
from gendertagger.models.classification import AgreementTier, CanonicalLabel, CertaintyTier
from gendertagger.models.export import ExportPersonRecord

pytestmark = [pytest.mark.unit, pytest.mark.scientific]


def test_bundle_round_trips_labeled_and_unlabeled_records() -> None:
    labeled = ExportPersonRecord(
        tei_id="p1",
        person_record_id=uuid4(),
        label=CanonicalLabel.female,
        evidence="assigned",
        resp="#gendertagger",
        cert="high",
        agreement_tier=AgreementTier.unanimous,
        certainty_tier=CertaintyTier.high,
        is_human_reviewed=False,
    )
    unlabeled = ExportPersonRecord(
        tei_id="p2",
        person_record_id=uuid4(),
        label=None,
        agreement_tier=AgreementTier.no_answer,
        certainty_tier=CertaintyTier.no_data,
        is_human_reviewed=False,
    )

    payload = json.loads(build_json_bundle([labeled, unlabeled]))

    assert [entry["tei_id"] for entry in payload] == ["p1", "p2"]
    assert payload[0]["label"] == "female"
    assert payload[0]["cert"] == "high"
    assert payload[1]["label"] is None
    assert payload[1]["evidence"] is None


def test_empty_bundle_is_an_empty_json_array() -> None:
    assert json.loads(build_json_bundle([])) == []
