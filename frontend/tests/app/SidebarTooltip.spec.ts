import { mount, type VueWrapper } from '@vue/test-utils'
import { nextTick } from 'vue'
import { afterEach, describe, expect, it, vi } from 'vitest'

import SidebarTooltip from '@/app/SidebarTooltip.vue'

let wrapper: VueWrapper | undefined

function mountTooltip() {
  const mounted = mount(SidebarTooltip, {
    attachTo: document.body,
    props: { text: 'Expand sidebar' },
    slots: {
      default: `
        <template #default="{ triggerProps }">
          <button v-bind="triggerProps" type="button">Toggle sidebar</button>
        </template>
      `,
    },
  })
  wrapper = mounted
  return mounted
}

afterEach(() => {
  wrapper?.unmount()
  wrapper = undefined
  document.body.replaceChildren()
  vi.useRealTimers()
})

describe('sidebar tooltip activation', () => {
  it.each(['pointer', 'keyboard'] as const)(
    'opens on the first %s interaction after being disabled while idle',
    async (interaction) => {
      const tooltip = mountTooltip()
      const button = tooltip.get<HTMLButtonElement>('button')
      await tooltip.setProps({ disabled: true })
      await tooltip.setProps({ disabled: false })
      expect(document.querySelector('[role="tooltip"]')).toBeNull()

      if (interaction === 'pointer') await button.trigger('mouseenter')
      else {
        button.element.focus()
        await nextTick()
      }
      expect(document.querySelector('[role="tooltip"]')?.textContent).toBe('Expand sidebar')
      expect(button.attributes('aria-describedby')).toBeDefined()
    },
  )

  it.each([
    { activation: 'pointer', detail: 1 },
    { activation: 'keyboard', detail: 0 },
  ])(
    'keeps a $activation activation dismissed until hover and focus both leave',
    async ({ detail }) => {
      vi.useFakeTimers()
      const tooltip = mountTooltip()
      const button = tooltip.get<HTMLButtonElement>('button')
      button.element.focus()
      await button.trigger('mouseenter')
      expect(document.querySelector('[role="tooltip"]')).not.toBeNull()

      button.element.dispatchEvent(new MouseEvent('click', { bubbles: true, detail }))
      await nextTick()
      expect(document.querySelector('[role="tooltip"]')).toBeNull()
      expect(button.attributes('aria-describedby')).toBeUndefined()
      expect(document.activeElement).toBe(button.element)

      await tooltip.setProps({ disabled: true })
      await tooltip.setProps({ disabled: false })
      await button.trigger('mouseleave')
      await vi.advanceTimersByTimeAsync(200)
      await button.trigger('mouseenter')
      expect(document.querySelector('[role="tooltip"]')).toBeNull()

      button.element.blur()
      await vi.advanceTimersByTimeAsync(200)
      button.element.focus()
      await vi.advanceTimersByTimeAsync(200)
      expect(document.querySelector('[role="tooltip"]')).toBeNull()

      button.element.blur()
      await button.trigger('mouseleave')
      await vi.advanceTimersByTimeAsync(200)
      await button.trigger('mouseenter')
      expect(document.querySelector('[role="tooltip"]')?.textContent).toBe('Expand sidebar')
      expect(button.attributes('aria-describedby')).toBeDefined()
    },
  )

  it('allows a new keyboard focus to open the tooltip after activation and blur', async () => {
    vi.useFakeTimers()
    const tooltip = mountTooltip()
    const button = tooltip.get<HTMLButtonElement>('button')
    button.element.focus()
    button.element.click()
    await nextTick()
    expect(document.querySelector('[role="tooltip"]')).toBeNull()
    expect(document.activeElement).toBe(button.element)

    button.element.blur()
    await vi.advanceTimersByTimeAsync(200)
    button.element.focus()
    await vi.advanceTimersByTimeAsync(200)
    expect(document.querySelector('[role="tooltip"]')?.textContent).toBe('Expand sidebar')
  })

  it('allows a fresh hover after Escape dismisses the popup under the pointer', async () => {
    const tooltip = mountTooltip()
    const button = tooltip.get<HTMLButtonElement>('button')
    await button.trigger('mouseenter')
    await button.trigger('mouseleave')
    document.querySelector('[role="tooltip"]')!.dispatchEvent(new MouseEvent('mouseenter'))

    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))
    await nextTick()
    expect(document.querySelector('[role="tooltip"]')).toBeNull()

    await button.trigger('mouseenter')
    expect(document.querySelector('[role="tooltip"]')?.textContent).toBe('Expand sidebar')
  })
})
