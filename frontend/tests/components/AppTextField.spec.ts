import { mount } from '@vue/test-utils'
import { defineComponent, ref } from 'vue'
import { describe, expect, it } from 'vitest'

import AppTextField from '@/components/base/AppTextField.vue'

const FieldForm = defineComponent({
  components: { AppTextField },
  setup() {
    const username = ref('')
    const touched = ref(false)
    const locked = ref(false)
    const submitted = ref('')
    function submit(event: Event) {
      if (!(event.target instanceof HTMLFormElement)) return
      submitted.value = String(new FormData(event.target).get('username') ?? '')
    }
    return { username, touched, locked, submitted, submit }
  },
  template: `
    <form novalidate @submit.prevent="submit">
      <p id="account-context">Choose your account identifier.</p>
      <AppTextField
        id="account-name"
        v-model="username"
        name="username"
        label="Account name"
        help-text="Use lowercase letters."
        help-label="Account name constraints"
        aria-describedby="account-context"
        pattern="[a-z]+"
        required
        :disabled="locked"
        :error-message="touched && !username ? 'Enter an account name.' : undefined"
        @blur="touched = true"
      />
      <AppTextField id="account-kind" model-value="local" name="kind" label="Account kind" readonly />
      <label><input v-model="locked" type="checkbox" />Lock name</label>
      <button type="submit">Submit</button>
      <output>{{ submitted }}</output>
    </form>
  `,
})

describe('native fields in a form', () => {
  it('keeps contextual and persistent help descriptions alongside a blur-timed error', async () => {
    const wrapper = mount(FieldForm, { attachTo: document.body })
    try {
      const input = wrapper.get<HTMLInputElement>('#account-name')
      const label = wrapper.get<HTMLLabelElement>('label[for="account-name"]')
      expect(label.element.control).toBe(input.element)
      expect(wrapper.find('[role="alert"]').exists()).toBe(false)
      expect(input.attributes('aria-describedby')).toBe('account-context account-name-help')

      await input.trigger('blur')
      expect(wrapper.get('[role="alert"]').text()).toBe('Enter an account name.')
      expect(input.attributes('aria-invalid')).toBe('true')
      expect(input.attributes('aria-describedby')).toBe(
        'account-context account-name-help account-name-error',
      )
      expect(wrapper.get('#account-name-help').text()).toBe('Use lowercase letters.')

      await input.setValue('reviewer')
      expect(wrapper.find('[role="alert"]').exists()).toBe(false)
      expect(input.attributes('aria-describedby')).toBe('account-context account-name-help')
    } finally {
      wrapper.unmount()
    }
  })

  it('uses native constraint validation and successful-control semantics when submitting', async () => {
    const wrapper = mount(FieldForm)
    const input = wrapper.get<HTMLInputElement>('#account-name')
    await input.setValue('Reviewer 1')
    expect(input.element.checkValidity()).toBe(false)
    await input.setValue('reviewer')
    expect(input.element.checkValidity()).toBe(true)
    await wrapper.get('form').trigger('submit')
    expect(wrapper.get('output').text()).toBe('reviewer')
    await wrapper.get('input[type="checkbox"]').setValue(true)
    await wrapper.get('form').trigger('submit')
    expect(wrapper.get('output').text()).toBe('')
    const form = wrapper.get<HTMLFormElement>('form').element
    expect(new FormData(form).get('kind')).toBe('local')
    expect(wrapper.get<HTMLInputElement>('#account-kind').element.readOnly).toBe(true)
    wrapper.unmount()
  })
})
