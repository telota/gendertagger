import { enableAutoUnmount, mount } from '@vue/test-utils'
import { afterEach, describe, expect, it } from 'vitest'

import { createAppI18n } from '@/app/i18n'
import JsonData from '@/components/domain/JsonData.vue'
import ProvenanceValue from '@/components/domain/ProvenanceValue.vue'
import SelectedExecution from '@/components/domain/SelectedExecution.vue'
import de from '@/locales/de.json'
import en from '@/locales/en.json'

enableAutoUnmount(afterEach)
const catalogues = { de, en } as const

describe.each(['de', 'en'] as const)('provenance presentation in %s', (locale) => {
  const global = { plugins: [createAppI18n(locale)] }

  it('shows an unresolved selected execution ID rather than inventing a method identity', async () => {
    const wrapper = mount(SelectedExecution, {
      global,
      props: { id: 'selected-but-unloaded', execution: null, showStatus: true },
    })
    expect(wrapper.get('code').text()).toBe('selected-but-unloaded')
    expect(wrapper.text()).not.toContain(catalogues[locale].runs.status.completed)
    await wrapper.setProps({
      execution: {
        method_name: 'gnd',
        implementation_version: 'source-v2',
        status: 'completed_with_errors',
      },
    })
    expect(wrapper.text()).toContain('gnd')
    expect(wrapper.text()).toContain('source-v2')
    expect(wrapper.text()).toContain(catalogues[locale].runs.status.completedWithErrors)
    expect(wrapper.find('code').exists()).toBe(false)
  })

  it('marks unrecorded provenance explicitly and replaces it with the recorded value', async () => {
    const wrapper = mount(ProvenanceValue, { global, props: { value: null } })
    expect(wrapper.text()).toBe(catalogues[locale].runs.provenance.notRecorded)
    await wrapper.setProps({ value: 'sha256:recorded-digest' })
    expect(wrapper.get('code').text()).toBe('sha256:recorded-digest')
    expect(wrapper.text()).not.toContain(catalogues[locale].runs.provenance.notRecorded)
  })

  it('keeps the same raw configuration visible or disclosed without dropping null, zero or source text', async () => {
    const value = {
      selected: ['gnd', 'local_llm'],
      source: '<untranslated>',
      confidence: 0,
      absent: null,
    }
    const wrapper = mount(JsonData, { props: { value } })
    expect(JSON.parse(wrapper.get('pre').text())).toEqual(value)
    expect(wrapper.find('details').exists()).toBe(false)
    await wrapper.setProps({ summary: catalogues[locale].runs.provenance.resolvedConfig })
    expect(wrapper.get('summary').text()).toBe(catalogues[locale].runs.provenance.resolvedConfig)
    expect(wrapper.get<HTMLDetailsElement>('details').element.open).toBe(false)
    wrapper.get<HTMLDetailsElement>('details').element.open = true
    expect(JSON.parse(wrapper.get('pre').text())).toEqual(value)
  })
})
