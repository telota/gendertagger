import { mount, type VueWrapper } from '@vue/test-utils'
import { h, nextTick, ref } from 'vue'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { createAppI18n } from '@/app/i18n'
import AppScrollRegion from '@/components/base/AppScrollRegion.vue'
import de from '@/locales/de.json'
import en from '@/locales/en.json'

import { expectNoAxeViolations } from '../helpers/axe'

const catalogues = { de, en } as const
const mounted: VueWrapper[] = []
const disconnect = vi.fn()
let notifyResize: () => void
let observed: Element[]

beforeEach(() => {
  observed = []
  disconnect.mockClear()
  class TestResizeObserver implements ResizeObserver {
    constructor(callback: ResizeObserverCallback) {
      notifyResize = () => callback([], this)
    }
    observe(target: Element): void {
      observed.push(target)
    }
    unobserve(): void {
      // The component disconnects the entire observer on unmount.
    }
    disconnect(): void {
      disconnect()
    }
  }
  vi.stubGlobal('ResizeObserver', TestResizeObserver)
})

afterEach(() => {
  mounted.splice(0).forEach((wrapper) => wrapper.unmount())
  document.body.replaceChildren()
  vi.unstubAllGlobals()
})

// jsdom has no layout engine. These dimensions exercise overflow response, not CSS geometry.
function dimensions(element: HTMLElement, width = 300, contentWidth = 300) {
  const sizes = { width, contentWidth }
  Object.defineProperties(element, {
    clientWidth: { get: () => sizes.width },
    scrollWidth: { get: () => sizes.contentWidth },
  })
  return sizes
}

async function resized(): Promise<void> {
  notifyResize()
  await nextTick()
}

describe.each(['de', 'en'] as const)('AppScrollRegion in %s', (locale) => {
  const messages = catalogues[locale]

  function render() {
    const wrapper = mount(AppScrollRegion, {
      attachTo: document.body,
      props: { label: messages.review.detail.methods.title },
      slots: {
        default:
          '<table><tbody><tr><th scope="row">method_a</th><td>unknown</td></tr></tbody></table>',
      },
      global: { plugins: [createAppI18n(locale)] },
    })
    mounted.push(wrapper)
    const region = wrapper.get<HTMLElement>('[role="region"]')
    const sizes = dimensions(region.element)
    return { wrapper, region, sizes }
  }

  it('names the table region without an extra keyboard stop or scroll hint when it fits', async () => {
    const { wrapper, region } = render()
    await resized()

    expect(region.attributes('aria-label')).toBe(messages.review.detail.methods.title)
    expect(region.attributes('tabindex')).toBeUndefined()
    expect(region.attributes('aria-describedby')).toBeUndefined()
    expect(wrapper.find('p').exists()).toBe(false)
    expect(region.get('th[scope="row"]').text()).toBe('method_a')
    expect(region.get('td').text()).toBe('unknown')
    await expectNoAxeViolations(wrapper.element)
  })

  it('offers keyboard scrolling and a linked visible localized cue only while content overflows', async () => {
    const { wrapper, region, sizes } = render()
    sizes.contentWidth = 600
    await resized()

    expect(region.attributes('tabindex')).toBe('0')
    const hintId = region.attributes('aria-describedby')
    expect(document.getElementById(hintId ?? '')?.textContent).toBe(
      messages.layout.horizontalScrollHint,
    )
    region.element.focus()
    expect(document.activeElement).toBe(region.element)
    await expectNoAxeViolations(wrapper.element)

    sizes.width = 700
    await resized()
    expect(region.attributes('tabindex')).toBeUndefined()
    expect(region.attributes('aria-describedby')).toBeUndefined()
    expect(wrapper.find('p').exists()).toBe(false)
    expect(document.activeElement).toBe(region.element)
  })

  it('remeasures async slot content and releases resize observations on unmount', async () => {
    const rows = ref(['method_a'])
    const wrapper = mount(
      {
        setup: () => () =>
          h(
            AppScrollRegion,
            { label: messages.review.detail.methods.title },
            {
              default: () =>
                h(
                  'table',
                  h(
                    'tbody',
                    rows.value.map((name) =>
                      h('tr', { key: name }, [h('th', { scope: 'row' }, name), h('td', 'unknown')]),
                    ),
                  ),
                ),
            },
          ),
      },
      { attachTo: document.body, global: { plugins: [createAppI18n(locale)] } },
    )
    const region = wrapper.get<HTMLElement>('[role="region"]')
    const sizes = dimensions(region.element)
    await resized()
    expect(observed).toHaveLength(3)
    expect(observed).toContain(wrapper.get('table').element)
    expect(region.attributes('tabindex')).toBeUndefined()

    sizes.contentWidth = 600
    rows.value = ['method_a', 'long_method_name']
    await nextTick()
    await nextTick()
    expect(region.attributes('tabindex')).toBe('0')
    expect(wrapper.findAll('th')).toHaveLength(2)

    wrapper.unmount()
    expect(disconnect).toHaveBeenCalledOnce()
  })
})
