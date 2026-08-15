"""Pure CSV analysis export."""

from __future__ import annotations

import csv
from collections.abc import Sequence
from io import StringIO

from gendertagger.models.export import ExportPersonRecord

CSV_ANALYSIS_MEDIA_TYPE = "text/csv"

_HEADER = (
    "tei_id",
    "label",
    "evidence",
    "resp",
    "cert",
    "agreement_tier",
    "certainty_tier",
    "human_reviewed",
)


def build_csv_analysis(records: Sequence[ExportPersonRecord]) -> bytes:
    """Serialize one ordered set of per-person export projections to CSV."""
    buffer = StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(_HEADER)
    for record in records:
        writer.writerow(
            (
                record.tei_id,
                record.label.value if record.label is not None else "",
                record.evidence or "",
                record.resp or "",
                record.cert or "",
                record.agreement_tier.value,
                record.certainty_tier.value,
                "true" if record.is_human_reviewed else "false",
            )
        )
    return buffer.getvalue().encode("utf-8")
