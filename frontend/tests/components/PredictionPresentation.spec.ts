import { enableAutoUnmount, mount } from '@vue/test-utils'
import { afterEach, describe, expect, it } from 'vitest'

import { createAppI18n } from '@/app/i18n'
import PredictionDecision from '@/components/domain/PredictionDecision.vue'
import PredictionStatus from '@/components/domain/PredictionStatus.vue'
import MethodConfidence from '@/components/domain/MethodConfidence.vue'
import de from '@/locales/de.json'
import en from '@/locales/en.json'

enableAutoUnmount(afterEach)
const catalogues = { de, en } as const

describe.each(['de', 'en'] as const)('prediction presentation in %s', (locale) => {
  const global = { plugins: [createAppI18n(locale)] }
  const messages = catalogues[locale]

  it('preserves a zero method confidence beside an unnormalized output and substantive unknown label', () => {
    const wrapper = mount(PredictionDecision, {
      global,
      props: {
        prediction: { label: 'unknown', raw_label: 'unmapped source value', method_confidence: 0 },
        method: true,
        gloss: messages.review.gloss.label.unknown,
      },
    })
    expect(wrapper.text()).toContain('unknown')
    expect(wrapper.text()).toContain(messages.review.gloss.label.unknown)
    expect(wrapper.text()).toContain('unmapped source value')
    expect(wrapper.text()).toMatch(/0[.,]00/)
    expect(wrapper.text()).not.toContain(messages.runs.results.noPrediction)
  })

  it('distinguishes an absent output from abstention with no decision or confidence', () => {
    const absent = mount(PredictionDecision, {
      global,
      props: { prediction: null, method: true, missing: true },
    })
    const abstention = mount(PredictionDecision, {
      global,
      props: {
        prediction: { label: null, raw_label: null, method_confidence: null },
        method: true,
      },
    })
    expect(absent.text()).toContain(messages.runs.results.noPrediction)
    expect(abstention.text()).not.toContain(messages.runs.results.noPrediction)
    expect(abstention.text()).not.toContain('unknown')
    expect(abstention.text()).not.toMatch(/\d[.,]\d/)
    for (const status of ['missing', 'abstain', 'error'] as const) {
      const output = mount(PredictionStatus, { global, props: { status, display: 'badge' } })
      expect(output.text()).toBe(status)
    }
  })

  it('renders null confidence as missing without treating zero as missing in a separate evidence cell', async () => {
    const wrapper = mount(MethodConfidence, { global, props: { value: null } })
    expect(wrapper.text()).toBe(messages.review.none)
    await wrapper.setProps({ value: 0 })
    expect(wrapper.text()).toMatch(/^0[.,]00$/)
    await wrapper.setProps({ value: undefined })
    expect(wrapper.text()).toBe(messages.review.none)
  })
})
