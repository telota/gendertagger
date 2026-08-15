"""Pure projection from internal certainty tiers to the TEI ``@cert`` vocabulary."""

from __future__ import annotations

from typing import Final, Literal

from gendertagger.models.classification import CertaintyTier

TeiCert = Literal["high", "low", "unknown"]

_CERTAINTY_TO_TEI_CERT: Final[dict[CertaintyTier, TeiCert]] = {
    CertaintyTier.high: "high",
    CertaintyTier.low: "low",
    CertaintyTier.contested: "unknown",
    CertaintyTier.single: "unknown",
    CertaintyTier.uncertain: "unknown",
    CertaintyTier.no_data: "unknown",
}


def project_certainty_to_tei(
    certainty_tier: CertaintyTier,
    *,
    is_human_reviewed: bool,
) -> TeiCert:
    """Project one internal certainty tier to its deterministic TEI ``@cert`` value.

    A human-reviewed final decision always projects to ``high``, per
    ``docs/08-ingestion-and-export.md``'s TEI certainty projection table.
    Otherwise ``contested``/``single``/``uncertain``/``no_data`` collapse to
    ``unknown`` and ``high``/``low`` pass through unchanged.
    """
    if is_human_reviewed:
        return "high"
    return _CERTAINTY_TO_TEI_CERT[certainty_tier]
