"""Pure CSV analysis export."""

from __future__ import annotations

import csv
import unicodedata
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


def _encode_text_cell(value: str) -> str:
    """Keep original text after an apostrophe for hazardous prefixes (ADR-0047)."""
    if value and (
        value[0] in "=+-@\uff1d\uff0b\uff0d\uff20"
        or value[0].isspace()
        or unicodedata.category(value[0]) in {"Cc", "Cf"}
    ):
        return "'" + value
    return value


def build_csv_analysis(records: Sequence[ExportPersonRecord]) -> bytes:
    """Serialize spreadsheet-safe text cells without mutating canonical records."""
    buffer = StringIO()
    writer = csv.writer(buffer, lineterminator="\n", quoting=csv.QUOTE_ALL)
    writer.writerow(_HEADER)
    for record in records:
        writer.writerow(
            tuple(
                _encode_text_cell(value)
                for value in (
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
        )
    return buffer.getvalue().encode("utf-8")
