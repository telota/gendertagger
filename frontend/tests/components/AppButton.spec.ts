import { mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'

import AppButton from '@/components/base/AppButton.vue'

describe('AppButton', () => {
  it('renders its slot content', () => {
    const wrapper = mount(AppButton, { slots: { default: 'Save' } })

    expect(wrapper.text()).toBe('Save')
  })

  it('defaults to a solid, type="button" control', () => {
    const wrapper = mount(AppButton)

    expect(wrapper.classes()).toContain('app-button--solid')
    expect(wrapper.attributes('type')).toBe('button')
  })

  it.each(['ghost', 'text'] as const)('applies the %s variant class', (variant) => {
    const wrapper = mount(AppButton, { props: { variant } })

    expect(wrapper.classes()).toContain(`app-button--${variant}`)
  })

  it('applies the destructive tone class', () => {
    const wrapper = mount(AppButton, { props: { tone: 'destructive' } })

    expect(wrapper.classes()).toContain('app-button--destructive')
  })

  it('renders as a submit control for a form action', () => {
    const wrapper = mount(AppButton, { props: { type: 'submit' } })

    expect(wrapper.attributes('type')).toBe('submit')
  })

  it('disables the control so a click never reaches the listener', async () => {
    const onClick = vi.fn()
    const wrapper = mount(AppButton, { props: { disabled: true }, attrs: { onClick } })

    expect(wrapper.attributes('disabled')).toBeDefined()
    await wrapper.trigger('click')
    expect(onClick).not.toHaveBeenCalled()
  })

  it('forwards a click listener from the call site to the native button', async () => {
    const onClick = vi.fn()
    const wrapper = mount(AppButton, { attrs: { onClick } })

    await wrapper.trigger('click')

    expect(onClick).toHaveBeenCalledOnce()
  })
})
