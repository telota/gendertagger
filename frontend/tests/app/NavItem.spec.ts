import { PhFolders } from '@phosphor-icons/vue'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { afterEach, describe, expect, it, vi } from 'vitest'

import NavItem from '@/app/NavItem.vue'
import { createAppI18n } from '@/app/i18n'

const wrappers: ReturnType<typeof mount>[] = []
afterEach(() => {
  wrappers.splice(0).forEach((wrapper) => wrapper.unmount())
  document.body.replaceChildren()
  vi.useRealTimers()
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})

async function item(props: Partial<InstanceType<typeof NavItem>['$props']> = {}) {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { name: 'projects', path: '/projects', component: { render: () => null } },
      { name: 'projectDetail', path: '/projects/detail', component: { render: () => null } },
    ],
  })
  await router.push('/projects')
  const wrapper = mount(NavItem, {
    attachTo: document.body,
    props: { to: { name: 'projects' }, label: 'Projects', icon: PhFolders, ...props },
    global: { plugins: [router, createAppI18n('en')] },
  })
  wrappers.push(wrapper)
  return { wrapper, router }
}

describe('sidebar navigation items', () => {
  it('uses explicit route ownership without inheriting inclusive router activation', async () => {
    const { wrapper, router } = await item({ current: false })
    expect(wrapper.get('a').attributes('aria-current')).toBeUndefined()
    await wrapper.setProps({ current: true })
    await router.push('/projects/detail')
    expect(wrapper.get('a').attributes('aria-current')).toBe('page')
    expect(wrapper.get('a').classes()).toContain('nav-item--current')
    expect(wrapper.get('a').classes()).not.toContain('router-link-active')
  })

  it('falls back to an exact route name when no ownership prop is supplied', async () => {
    const { wrapper, router } = await item()
    expect(wrapper.get('a').attributes('aria-current')).toBe('page')
    await router.push('/projects/detail')
    expect(wrapper.get('a').attributes('aria-current')).toBeUndefined()
  })

  it('exposes an unavailable destination and its explanation through keyboard focus without navigation', async () => {
    const { wrapper, router } = await item({
      to: null,
      unavailableReason: 'Choose a snapshot first.',
    })
    const disabled = wrapper.get<HTMLElement>('[aria-disabled="true"]')
    expect(disabled.attributes('role')).toBe('link')
    expect(disabled.element.tabIndex).toBe(0)
    expect(disabled.attributes('title')).toBeUndefined()
    disabled.element.focus()
    await flushPromises()
    const tooltip = document.getElementById(disabled.attributes('aria-describedby') ?? '')
    expect(tooltip?.textContent).toBe('Projects: Choose a snapshot first.')
    expect(tooltip?.getAttribute('role')).toBe('tooltip')
    await disabled.trigger('keydown', { key: 'Enter' })
    expect(router.currentRoute.value.path).toBe('/projects')
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))
    await flushPromises()
    expect(document.querySelector('[role="tooltip"]')).toBeNull()
    expect(document.activeElement).toBe(disabled.element)
  })

  it('keeps a tooltip available while the pointer moves onto it and until the pointer leaves', async () => {
    vi.useFakeTimers()
    const { wrapper } = await item({ desktopCollapsed: true })
    const trigger = wrapper.get('a')
    await trigger.trigger('mouseenter')
    await trigger.trigger('mouseleave')
    const tooltip = document.querySelector('[role="tooltip"]')!
    tooltip.dispatchEvent(new MouseEvent('mouseenter'))
    await vi.advanceTimersByTimeAsync(5000)
    expect(document.querySelector('[role="tooltip"]')).not.toBeNull()
    tooltip.dispatchEvent(new MouseEvent('mouseleave'))
    await vi.advanceTimersByTimeAsync(150)
    expect(document.querySelector('[role="tooltip"]')).toBeNull()
  })

  it('places the tooltip outside clipping ancestors and keeps it within viewport bounds', async () => {
    vi.stubGlobal('innerWidth', 320)
    vi.stubGlobal('innerHeight', 240)
    vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockImplementation(function (
      this: HTMLElement,
    ) {
      return this.getAttribute('role') === 'tooltip'
        ? new DOMRect(0, 0, 120, 40)
        : new DOMRect(280, 210, 32, 28)
    })
    const { wrapper } = await item({ desktopCollapsed: true })
    await wrapper.get('a').trigger('mouseenter')
    await flushPromises()
    const tooltip = document.querySelector<HTMLElement>('[role="tooltip"]')!
    expect(tooltip.parentElement).toBe(document.body)
    expect(tooltip.style.left).toBe('152px')
    expect(tooltip.style.top).toBe('192px')
  })

  it('keeps mobile labels available and omits redundant tooltips for full mobile links', async () => {
    const { wrapper } = await item({ desktopCollapsed: true, mobile: true })
    expect(wrapper.get('a').classes()).toContain('nav-item--mobile')
    await wrapper.get('a').trigger('focus')
    expect(document.querySelector('[role="tooltip"]')).toBeNull()
    expect(wrapper.get('.nav-item-label').text()).toBe('Projects')
  })
})
