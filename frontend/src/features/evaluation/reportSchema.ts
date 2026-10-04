import { AGREEMENT_TIERS, CANONICAL_LABELS, CERTAINTY_TIERS } from '@/composables/useVocabulary'
import type { components } from '@/api/schema'

type CanonicalLabel = components['schemas']['CanonicalLabel']

export type BenchmarkSummary = components['schemas']['BenchmarkSummary']
export type MethodCoverage = components['schemas']['MethodCoverage']
type RecallWithCI = components['schemas']['RecallWithCI']
export type MethodAccuracy = components['schemas']['MethodAccuracy']
export type KappaCell = components['schemas']['KappaCell']
export type EnsembleMetrics = components['schemas']['EnsembleMetrics']
export type EvaluationReport = components['schemas']['EvaluationReport']

export class ReportShapeError extends Error {
  constructor(where: string) {
    super(`The evaluation report is not in the expected shape (${where}).`)
    this.name = 'ReportShapeError'
  }
}

type Json = Record<string, unknown>

function record(value: unknown, where: string): Json {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) {
    throw new ReportShapeError(where)
  }
  return value as Json
}

function list(value: unknown, where: string): unknown[] {
  if (!Array.isArray(value)) throw new ReportShapeError(where)
  return value
}

function text(value: unknown, where: string): string {
  if (typeof value !== 'string') throw new ReportShapeError(where)
  return value
}

function label(value: unknown, where: string): CanonicalLabel {
  const parsed = CANONICAL_LABELS.find((entry) => entry === value)
  if (parsed === undefined) throw new ReportShapeError(where)
  return parsed
}

function definition(value: unknown): EvaluationReport['definition'] {
  if (value !== 'gnd_benchmark_v1') throw new ReportShapeError('definition')
  return value
}

function num(value: unknown, where: string): number {
  if (typeof value !== 'number' || !Number.isFinite(value)) throw new ReportShapeError(where)
  return value
}

function counts(value: unknown, where: string, keys: readonly string[]): Record<string, number> {
  const source = record(value, where)
  const result: Record<string, number> = {}
  for (const [key, entry] of Object.entries(source)) {
    if (!keys.includes(key)) throw new ReportShapeError(`${where}.${key}`)
    result[key] = num(entry, `${where}.${key}`)
  }
  return result
}

/** Validate an untyped report body and return it typed, or throw a `ReportShapeError`. */
export function parseEvaluationReport(body: unknown): EvaluationReport {
  const root = record(body, 'report')

  const benchmark = record(root['benchmark'], 'benchmark')
  const coverage = list(root['coverage'], 'coverage').map((raw, i): MethodCoverage => {
    const c = record(raw, `coverage[${i}]`)
    return {
      method_name: text(c['method_name'], `coverage[${i}].method_name`),
      total: num(c['total'], `coverage[${i}].total`),
      coverage_count: num(c['coverage_count'], `coverage[${i}].coverage_count`),
      coverage_share: num(c['coverage_share'], `coverage[${i}].coverage_share`),
      label_distribution: counts(
        c['label_distribution'],
        `coverage[${i}].label_distribution`,
        CANONICAL_LABELS,
      ),
      abstain_count: num(c['abstain_count'], `coverage[${i}].abstain_count`),
      error_count: num(c['error_count'], `coverage[${i}].error_count`),
    }
  })

  const accuracy = list(root['accuracy'], 'accuracy').map((raw, i): MethodAccuracy => {
    const a = record(raw, `accuracy[${i}]`)
    const matrix = record(a['confusion_matrix'], `accuracy[${i}].confusion_matrix`)
    return {
      method_name: text(a['method_name'], `accuracy[${i}].method_name`),
      answered_count: num(a['answered_count'], `accuracy[${i}].answered_count`),
      correct_count: num(a['correct_count'], `accuracy[${i}].correct_count`),
      accuracy: num(a['accuracy'], `accuracy[${i}].accuracy`),
      effective_accuracy: num(a['effective_accuracy'], `accuracy[${i}].effective_accuracy`),
      confusion_matrix: Object.fromEntries(
        Object.entries(matrix).map(([truth, row]) => [
          label(truth, `accuracy[${i}].confusion_matrix.${truth}`),
          counts(row, `accuracy[${i}].confusion_matrix.${truth}`, CANONICAL_LABELS),
        ]),
      ),
      recall: list(a['recall'], `accuracy[${i}].recall`).map((rawRecall, j): RecallWithCI => {
        const r = record(rawRecall, `accuracy[${i}].recall[${j}]`)
        return {
          label: label(r['label'], `accuracy[${i}].recall[${j}].label`),
          class_size: num(r['class_size'], `accuracy[${i}].recall[${j}].class_size`),
          correct: num(r['correct'], `accuracy[${i}].recall[${j}].correct`),
          recall: num(r['recall'], `accuracy[${i}].recall[${j}].recall`),
          ci_low: num(r['ci_low'], `accuracy[${i}].recall[${j}].ci_low`),
          ci_high: num(r['ci_high'], `accuracy[${i}].recall[${j}].ci_high`),
        }
      }),
    }
  })

  const kappa = list(root['kappa_matrix'], 'kappa_matrix').map((raw, i): KappaCell => {
    const k = record(raw, `kappa_matrix[${i}]`)
    const value = k['kappa']
    return {
      method_a: text(k['method_a'], `kappa_matrix[${i}].method_a`),
      method_b: text(k['method_b'], `kappa_matrix[${i}].method_b`),
      co_answered_count: num(k['co_answered_count'], `kappa_matrix[${i}].co_answered_count`),
      kappa: value === null || value === undefined ? null : num(value, `kappa_matrix[${i}].kappa`),
    }
  })

  let ensemble: EnsembleMetrics | null = null
  if (root['ensemble'] !== null && root['ensemble'] !== undefined) {
    const e = record(root['ensemble'], 'ensemble')
    ensemble = {
      canonical_label_distribution: counts(
        e['canonical_label_distribution'],
        'ensemble.labels',
        CANONICAL_LABELS,
      ),
      agreement_tier_distribution: counts(
        e['agreement_tier_distribution'],
        'ensemble.agreement',
        AGREEMENT_TIERS,
      ),
      certainty_tier_distribution: counts(
        e['certainty_tier_distribution'],
        'ensemble.certainty',
        CERTAINTY_TIERS,
      ),
      human_reviewed_count: num(e['human_reviewed_count'], 'ensemble.human_reviewed_count'),
      human_correction_count: num(e['human_correction_count'], 'ensemble.human_correction_count'),
    }
  }

  return {
    definition: definition(root['definition']),
    benchmark: {
      method_name: text(benchmark['method_name'], 'benchmark.method_name'),
      labels: list(benchmark['labels'], 'benchmark.labels').map((entry, i) =>
        label(entry, `benchmark.labels[${i}]`),
      ),
      size: num(benchmark['size'], 'benchmark.size'),
      class_counts: counts(benchmark['class_counts'], 'benchmark.class_counts', CANONICAL_LABELS),
    },
    coverage,
    accuracy,
    kappa_matrix: kappa,
    ensemble,
  }
}
