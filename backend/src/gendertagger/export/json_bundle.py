"""Pure JSON result-bundle export."""

from __future__ import annotations

import json
from collections.abc import Sequence

from gendertagger.models.export import ExportPersonRecord

JSON_BUNDLE_MEDIA_TYPE = "application/json"


def build_json_bundle(records: Sequence[ExportPersonRecord]) -> bytes:
    """Serialize one ordered set of per-person export projections to JSON."""
    payload = [record.model_dump(mode="json") for record in records]
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8") + b"\n"
