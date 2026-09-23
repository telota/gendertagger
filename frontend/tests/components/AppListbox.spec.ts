import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import AppListbox from '@/components/base/AppListbox.vue'

const OPTIONS = [
  { value: 'de', label: 'Deutsch' },
  { value: 'en', label: 'English' },
] as const

describe('AppListbox', () => {
  it('shows the current value on the button and gives the control an accessible name', () => {
    const wrapper = mount(AppListbox, {
      props: { label: 'Sprache', options: OPTIONS, modelValue: 'de' },
    })

    expect(wrapper.get('button').text()).toBe('Deutsch')
    expect(wrapper.text()).toContain('Sprache')
  })

  it('lists every option once opened', async () => {
    const wrapper = mount(AppListbox, {
      props: { label: 'Sprache', options: OPTIONS, modelValue: 'de' },
      attachTo: document.body,
    })

    await wrapper.get('button').trigger('click')

    const items = wrapper.findAll('li')
    expect(items.map((item) => item.text())).toEqual(['Deutsch', 'English'])
    wrapper.unmount()
  })

  it('marks the current value as selected among the options', async () => {
    const wrapper = mount(AppListbox, {
      props: { label: 'Sprache', options: OPTIONS, modelValue: 'en' },
      attachTo: document.body,
    })

    await wrapper.get('button').trigger('click')

    const selected = wrapper.findAll('li').find((item) => item.text() === 'English')
    expect(selected?.classes()).toContain('app-listbox-option--selected')
    wrapper.unmount()
  })

  it('emits the chosen value and closes when an option is picked', async () => {
    const wrapper = mount(AppListbox, {
      props: { label: 'Sprache', options: OPTIONS, modelValue: 'de' },
      attachTo: document.body,
    })

    await wrapper.get('button').trigger('click')
    const englishOption = wrapper.findAll('li').find((item) => item.text() === 'English')
    await englishOption?.trigger('click')

    expect(wrapper.emitted('update:modelValue')?.at(-1)).toEqual(['en'])
    wrapper.unmount()
  })

  it('falls back to an empty label for a model value absent from options', () => {
    const wrapper = mount(AppListbox, {
      props: { label: 'Sprache', options: OPTIONS, modelValue: 'fr' },
    })

    expect(wrapper.get('button').text()).toBe('')
  })
})
