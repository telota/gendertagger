import { describe, expect, it } from 'vitest'

import realReport from './fixtures/seed-report.json'

import { parseEvaluationReport, ReportShapeError } from '@/features/evaluation/reportSchema'

const valid = () => ({
  definition: 'gnd_benchmark_v1',
  benchmark: {
    method_name: 'gnd',
    labels: ['male', 'female'],
    size: 2,
    class_counts: { male: 1, female: 1 },
  },
  coverage: [
    {
      method_name: 'gnd',
      total: 2,
      coverage_count: 2,
      coverage_share: 1,
      label_distribution: { male: 1, female: 1 },
      abstain_count: 0,
      error_count: 0,
    },
  ],
  accuracy: [
    {
      method_name: 'gender_guesser',
      answered_count: 2,
      correct_count: 1,
      accuracy: 0.5,
      effective_accuracy: 0.5,
      confusion_matrix: { male: { male: 1 }, female: { male: 1 } },
      recall: [{ label: 'male', class_size: 1, correct: 1, recall: 1, ci_low: 0.2, ci_high: 1 }],
    },
  ],
  kappa_matrix: [{ method_a: 'a', method_b: 'b', co_answered_count: 0, kappa: null }],
})

describe('parseEvaluationReport', () => {
  it('accepts a report the backend would write, with and without an ensemble', () => {
    const parsed = parseEvaluationReport(valid())

    expect(parsed.benchmark.size).toBe(2)
    expect(parsed.accuracy[0]?.confusion_matrix.female?.male).toBe(1)
    expect(parsed.kappa_matrix[0]?.kappa).toBeNull()
    expect(parsed.ensemble).toBeNull()
  })

  it('reads an ensemble when there is one', () => {
    const parsed = parseEvaluationReport({
      ...valid(),
      ensemble: {
        canonical_label_distribution: { male: 1 },
        agreement_tier_distribution: { unanimous: 1 },
        certainty_tier_distribution: { high: 1 },
        human_reviewed_count: 1,
        human_correction_count: 0,
      },
    })

    expect(parsed.ensemble?.human_reviewed_count).toBe(1)
  })

  it.each([
    ['not an object', 'nope'],
    [
      'a missing section',
      (() => {
        const r: Record<string, unknown> = valid()
        delete r['coverage']
        return r
      })(),
    ],
    ['a number that is text', { ...valid(), benchmark: { ...valid().benchmark, size: '2' } }],
    ['a non-finite number', { ...valid(), coverage: [{ ...valid().coverage[0], total: null }] }],
    [
      'a misplaced kappa',
      {
        ...valid(),
        kappa_matrix: [{ method_a: 'a', method_b: 'b', co_answered_count: 1, kappa: 'high' }],
      },
    ],
  ])('refuses %s with a shape error rather than a partial report', (_name, body) => {
    expect(() => parseEvaluationReport(body)).toThrow(ReportShapeError)
  })
})

// A report the real backend stored for the seeded run (fixtures/seed-report.json), not a hand-built
// one: the contract between the evaluation subsystem and this client is only as good as this reads it.
describe('a report as the real backend stored it', () => {
  const parsed = parseEvaluationReport(realReport)

  it('parses without loss', () => {
    expect(parsed.definition).toBe('gnd_benchmark_v1')
    expect(parsed.benchmark.method_name).toBe('gnd')
    expect(parsed.benchmark.labels).toEqual(['male', 'female'])
    expect(parsed.coverage.map((c) => c.method_name)).toContain('hivoto_xgboost')
    expect(parsed.ensemble).not.toBeNull()
  })

  it('keeps the invariants the backend guarantees, so the tables add up', () => {
    const { benchmark } = parsed
    expect(Object.values(benchmark.class_counts).reduce((a, b) => a + b, 0)).toBe(benchmark.size)
    for (const c of parsed.coverage) {
      expect(c.coverage_count + c.abstain_count + c.error_count).toBe(c.total)
      expect(Object.values(c.label_distribution).reduce((a, b) => a + b, 0)).toBe(c.coverage_count)
    }
    for (const a of parsed.accuracy) {
      expect(a.correct_count).toBeLessThanOrEqual(a.answered_count)
      expect(a.effective_accuracy).toBeLessThanOrEqual(a.accuracy)
      expect(a.recall.map((r) => r.label)).toEqual(benchmark.labels)
    }
  })

  it('has one κ cell per unordered pair of the method roster', () => {
    const methods = new Set(parsed.kappa_matrix.flatMap((cell) => [cell.method_a, cell.method_b]))
    expect(parsed.kappa_matrix).toHaveLength((methods.size * (methods.size - 1)) / 2)
  })
})
