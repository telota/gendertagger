import { mount, type VueWrapper } from '@vue/test-utils'
import { h, nextTick, ref } from 'vue'
import { afterEach, describe, expect, it, vi } from 'vitest'

import AppButton from '@/components/base/AppButton.vue'
import AppFeedback from '@/components/base/AppFeedback.vue'
import de from '@/locales/de.json'
import en from '@/locales/en.json'

import { expectNoAxeViolations } from '../helpers/axe'

const catalogues = { de, en } as const
const mounted: VueWrapper[] = []

afterEach(() => {
  mounted.splice(0).forEach((wrapper) => wrapper.unmount())
  document.body.replaceChildren()
})

describe.each(['de', 'en'] as const)('AppFeedback in %s', (locale) => {
  const messages = catalogues[locale]

  it('keeps a static permission explanation readable without an unsolicited announcement', async () => {
    const wrapper = mount(AppFeedback, {
      attachTo: document.body,
      slots: { default: messages.review.decision.viewerNote },
    })
    mounted.push(wrapper)

    expect(wrapper.text()).toBe(messages.review.decision.viewerNote)
    expect(wrapper.find('[role], [aria-live], [aria-atomic]').exists()).toBe(false)
    expect(wrapper.find('button').exists()).toBe(false)
    await expectNoAxeViolations(wrapper.element)
  })

  it('updates one persistent status region while recovery actions remain outside it', async () => {
    const message = ref('')
    const disabled = ref(false)
    const retry = vi.fn()
    const wrapper = mount(
      {
        setup: () => () =>
          h(
            AppFeedback,
            { announcement: 'polite' },
            {
              default: () => message.value,
              actions: () =>
                h(
                  AppButton,
                  { disabled: disabled.value, onClick: retry },
                  () => messages.userSettings.retry,
                ),
            },
          ),
      },
      { attachTo: document.body },
    )
    mounted.push(wrapper)
    const region = wrapper.get('[role="status"]').element
    expect(region.textContent).toBe('')
    expect(region.getAttribute('aria-atomic')).toBe('true')
    expect(region.querySelector('button')).toBeNull()

    for (const text of [messages.userSettings.states.saving, messages.userSettings.states.saved]) {
      message.value = text
      await nextTick()
      expect(wrapper.get('[role="status"]').element).toBe(region)
      expect(region.textContent).toBe(text)
    }

    const button = wrapper.get<HTMLButtonElement>('button')
    button.element.focus()
    expect(document.activeElement).toBe(button.element)
    await button.trigger('click')
    expect(retry).toHaveBeenCalledOnce()
    disabled.value = true
    await nextTick()
    expect(button.element.disabled).toBe(true)
    expect(region.textContent).toBe(messages.userSettings.states.saved)
    await expectNoAxeViolations(wrapper.element)
  })

  it('announces a conflict without flattening its explanation or reading the action as an error', async () => {
    const wrapper = mount(AppFeedback, {
      attachTo: document.body,
      props: { announcement: 'assertive', tone: 'critical' },
      slots: {
        default: () => [
          h('p', messages.userSettings.conflict),
          h('p', messages.userSettings.conflictReloadHint),
        ],
        actions: () => h(AppButton, { variant: 'ghost' }, () => messages.userSettings.reloadSaved),
      },
    })
    mounted.push(wrapper)

    const alert = wrapper.get('[role="alert"]')
    expect(alert.attributes('aria-atomic')).toBe('true')
    expect(alert.findAll('p').map((paragraph) => paragraph.text())).toEqual([
      messages.userSettings.conflict,
      messages.userSettings.conflictReloadHint,
    ])
    expect(alert.find('button').exists()).toBe(false)
    expect(wrapper.get('button').text()).toBe(messages.userSettings.reloadSaved)
    await expectNoAxeViolations(wrapper.element)
  })
})
