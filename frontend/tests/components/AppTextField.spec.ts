import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import AppTextField from '@/components/base/AppTextField.vue'

describe('AppTextField', () => {
  it('associates the visible label with the input by id', () => {
    const wrapper = mount(AppTextField, {
      props: { id: 'username', label: 'Username', modelValue: '' },
    })

    const label = wrapper.get('label')
    expect(label.text()).toBe('Username')
    expect(label.attributes('for')).toBe('username')
    expect(wrapper.get('input').attributes('id')).toBe('username')
  })

  it('names the field after id by default, for the request body key it maps to', () => {
    const wrapper = mount(AppTextField, {
      props: { id: 'change-password-current', label: 'Current password', modelValue: '' },
    })

    expect(wrapper.get('input').attributes('name')).toBe('change-password-current')
  })

  it('accepts a name distinct from a page-unique id', () => {
    const wrapper = mount(AppTextField, {
      props: {
        id: 'change-password-current',
        name: 'current-password',
        label: 'Current password',
        modelValue: '',
      },
    })

    expect(wrapper.get('input').attributes('name')).toBe('current-password')
  })

  it('updates the bound model as the user types', async () => {
    const wrapper = mount(AppTextField, {
      props: { id: 'username', label: 'Username', modelValue: '' },
    })

    await wrapper.get('input').setValue('reviewer.one')

    expect(wrapper.emitted('update:modelValue')?.at(-1)).toEqual(['reviewer.one'])
  })

  it('defaults to a text input and forwards type, autocomplete and required', () => {
    const wrapper = mount(AppTextField, {
      props: {
        id: 'password',
        label: 'Password',
        modelValue: '',
        type: 'password',
        autocomplete: 'current-password',
        required: true,
      },
    })
    const input = wrapper.get('input')

    expect(input.attributes('type')).toBe('password')
    expect(input.attributes('autocomplete')).toBe('current-password')
    expect(input.attributes('required')).toBeDefined()
  })

  it('shows no error markup when unconfigured', () => {
    const wrapper = mount(AppTextField, {
      props: { id: 'username', label: 'Username', modelValue: '' },
    })

    expect(wrapper.find('[role="alert"]').exists()).toBe(false)
    expect(wrapper.get('input').attributes('aria-invalid')).toBeUndefined()
  })

  it('links a given error message to the input for assistive technology', () => {
    const wrapper = mount(AppTextField, {
      props: {
        id: 'username',
        label: 'Username',
        modelValue: '',
        errorMessage: 'This field is required.',
      },
    })
    const input = wrapper.get('input')
    const error = wrapper.get('[role="alert"]')

    expect(error.text()).toBe('This field is required.')
    expect(input.attributes('aria-invalid')).toBe('true')
    expect(input.attributes('aria-describedby')).toBe(error.attributes('id'))
  })
})
