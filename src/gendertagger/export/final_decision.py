"""Pure FinalDecision resolution combining machine and human-reviewed evidence."""

from __future__ import annotations

from gendertagger.export.certainty_projection import project_certainty_to_tei
from gendertagger.models.aggregation import AggregatedResult
from gendertagger.models.export import ExportPersonRecord, LabelSourcePolicy
from gendertagger.models.review import Annotation

_MACHINE_RESP_ID = "#gendertagger"


def resolve_final_decision(
    *,
    tei_id: str,
    source_member_name: str | None,
    aggregated_result: AggregatedResult,
    annotation: Annotation | None,
    label_source_policy: LabelSourcePolicy,
    human_resp_id: str,
) -> ExportPersonRecord:
    """Project one person's FinalDecision view without mutating any evidence.

    FinalDecision is "latest valid human annotation, else the selected
    aggregated result": under ``human_overrides``, a current annotation with a
    non-null label (``verify``/``correct``) supersedes the machine label and
    is projected at TEI certainty ``high``. A ``defer`` annotation carries no
    label and therefore never overrides -- the machine result stands. Under
    ``machine_aggregation``, annotations are never consulted. Neither branch
    rewrites the underlying Prediction or AggregatedResult.

    Args:
        tei_id: The person's canonical project identity.
        source_member_name: The exact source member this person came from,
            carried through for TEI output grouping. ``None`` for records
            imported before locator provenance was introduced.
        aggregated_result: The immutable selected aggregation output.
        annotation: The person's current annotation, if any.
        label_source_policy: Whether human annotations may override the label.
        human_resp_id: The configured human/editor responsibility identifier.

    Returns:
        The immutable per-person export projection.
    """
    override_label = (
        annotation.label
        if label_source_policy is LabelSourcePolicy.human_overrides and annotation is not None
        else None
    )
    is_human_reviewed = override_label is not None
    label = override_label if is_human_reviewed else aggregated_result.label

    if label is None:
        return ExportPersonRecord(
            tei_id=tei_id,
            person_record_id=aggregated_result.person_record_id,
            source_member_name=source_member_name,
            label=None,
            agreement_tier=aggregated_result.agreement_tier,
            certainty_tier=aggregated_result.certainty_tier,
            is_human_reviewed=is_human_reviewed,
        )

    return ExportPersonRecord(
        tei_id=tei_id,
        person_record_id=aggregated_result.person_record_id,
        source_member_name=source_member_name,
        label=label,
        evidence="assigned",
        resp=human_resp_id if is_human_reviewed else _MACHINE_RESP_ID,
        cert=project_certainty_to_tei(
            aggregated_result.certainty_tier,
            is_human_reviewed=is_human_reviewed,
        ),
        agreement_tier=aggregated_result.agreement_tier,
        certainty_tier=aggregated_result.certainty_tier,
        is_human_reviewed=is_human_reviewed,
    )
