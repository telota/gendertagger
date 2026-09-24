import { useI18n } from 'vue-i18n'

import type { components } from '@/api'

export type CanonicalLabel = components['schemas']['CanonicalLabel']
export type CertaintyTier = components['schemas']['CertaintyTier']
export type AgreementTier = components['schemas']['AgreementTier']
export type ReviewWorkflowState = components['schemas']['ReviewWorkflowState']
export type ReviewAction = components['schemas']['ReviewAction']
export type OverrideSource = components['schemas']['OverrideSource']
export type PredictionStatus = components['schemas']['PredictionStatus']
export type AggregationOutcome = components['schemas']['AggregationOutcome']

export const CANONICAL_LABELS: readonly CanonicalLabel[] = [
  'male',
  'female',
  'unknown',
  'institution',
]
export const CERTAINTY_TIERS: readonly CertaintyTier[] = [
  'high',
  'low',
  'contested',
  'single',
  'uncertain',
  'no_data',
]
export const AGREEMENT_TIERS: readonly AgreementTier[] = [
  'unanimous',
  'strong_majority',
  'weak_majority',
  'no_consensus',
  'single_rater',
  'no_answer',
]
export const WORKFLOW_STATES: readonly ReviewWorkflowState[] = [
  'unreviewed',
  'reviewed',
  'deferred',
]

/**
 * D3 (ADR-0030): the controlled vocabulary is never translated, because it is the same set of values
 * the API returns, the TEI output carries and the paper reports. Where a plain-language gloss helps,
 * it is shown *beside* the token, never instead of it. Each lookup is a switch because the i18n lint
 * rule requires every message key to appear literally in the source.
 */
export function useVocabularyGloss() {
  const { t } = useI18n()

  return {
    label(value: CanonicalLabel): string {
      return value === 'unknown' ? t('review.gloss.label.unknown') : ''
    },
    certainty(value: CertaintyTier): string {
      switch (value) {
        case 'high':
          return t('review.gloss.certainty.high')
        case 'low':
          return t('review.gloss.certainty.low')
        case 'contested':
          return t('review.gloss.certainty.contested')
        case 'single':
          return t('review.gloss.certainty.single')
        case 'uncertain':
          return t('review.gloss.certainty.uncertain')
        case 'no_data':
          return t('review.gloss.certainty.noData')
      }
    },
    agreement(value: AgreementTier): string {
      switch (value) {
        case 'unanimous':
          return t('review.gloss.agreement.unanimous')
        case 'strong_majority':
          return t('review.gloss.agreement.strongMajority')
        case 'weak_majority':
          return t('review.gloss.agreement.weakMajority')
        case 'no_consensus':
          return t('review.gloss.agreement.noConsensus')
        case 'single_rater':
          return t('review.gloss.agreement.singleRater')
        case 'no_answer':
          return t('review.gloss.agreement.noAnswer')
      }
    },
    workflow(value: ReviewWorkflowState): string {
      switch (value) {
        case 'unreviewed':
          return t('review.gloss.workflow.unreviewed')
        case 'reviewed':
          return t('review.gloss.workflow.reviewed')
        case 'deferred':
          return t('review.gloss.workflow.deferred')
      }
    },
    outcome(value: AggregationOutcome): string {
      switch (value) {
        case 'decided':
          return t('review.gloss.outcome.decided')
        case 'unresolved_tie':
          return t('review.gloss.outcome.unresolvedTie')
        case 'no_data':
          return t('review.gloss.outcome.noData')
      }
    },
    override(value: OverrideSource): string {
      switch (value) {
        case 'gnd':
          return t('review.gloss.override.gnd')
        case 'parenthetical_qualifier':
          return t('review.gloss.override.parentheticalQualifier')
      }
    },
    prediction(value: PredictionStatus): string {
      switch (value) {
        case 'success':
          return t('review.gloss.prediction.success')
        case 'abstain':
          return t('review.gloss.prediction.abstain')
        case 'error':
          return t('review.gloss.prediction.error')
      }
    },
    action(value: ReviewAction): string {
      switch (value) {
        case 'verify':
          return t('review.gloss.action.verify')
        case 'correct':
          return t('review.gloss.action.correct')
        case 'defer':
          return t('review.gloss.action.defer')
      }
    },
  }
}
