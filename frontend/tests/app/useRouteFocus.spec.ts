import { mount, type VueWrapper } from '@vue/test-utils'
import { defineComponent, h, nextTick, ref } from 'vue'
import { createMemoryHistory, createRouter, RouterView, useRoute } from 'vue-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { useRouteFocus } from '@/app/useRouteFocus'

const mounted: VueWrapper[] = []
let frames: Map<number, FrameRequestCallback>
let nextFrame: number

beforeEach(() => {
  frames = new Map()
  nextFrame = 0
  vi.stubGlobal('requestAnimationFrame', (callback: FrameRequestCallback) => {
    const id = ++nextFrame
    frames.set(id, callback)
    return id
  })
  vi.stubGlobal('cancelAnimationFrame', (id: number) => frames.delete(id))
})

afterEach(() => {
  mounted.splice(0).forEach((wrapper) => wrapper.unmount())
  document.body.replaceChildren()
  vi.unstubAllGlobals()
})

async function renderFrames(): Promise<void> {
  await nextTick()
  const pending = [...frames.values()]
  frames.clear()
  for (const callback of pending) callback(0)
  await nextTick()
}

function fixture() {
  const loaded = ref(false)
  const page = {
    setup() {
      const route = useRoute()
      return () => h('main', [h('h1', route.path), h('input', { 'aria-label': 'Filter' })])
    },
  }
  const delayed = {
    setup: () => () =>
      h('main', [
        loaded.value ? h('h1', 'Loaded page') : h('p', { role: 'status' }, 'Loading'),
        h('input', { 'aria-label': 'Draft' }),
      ]),
  }
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/', component: page },
      { path: '/page', component: page },
      { path: '/person/:id', component: page },
      { path: '/delayed', component: delayed },
      { path: '/old', redirect: '/page' },
    ],
  })
  const shell = defineComponent({
    setup() {
      const content = ref<HTMLElement | null>(null)
      useRouteFocus(content)
      return () =>
        h('div', [
          h('button', { type: 'button', class: 'navigation' }, 'Navigate'),
          h('div', { id: 'main-content', ref: content, tabindex: -1 }, [h(RouterView)]),
        ])
    },
  })
  function mountShell(): VueWrapper {
    const wrapper = mount(shell, { attachTo: document.body, global: { plugins: [router] } })
    mounted.push(wrapper)
    return wrapper
  }
  async function ready() {
    await router.push('/')
    await router.isReady()
    const wrapper = mountShell()
    return { wrapper, router, loaded }
  }
  return { router, mountShell, ready }
}

describe('route-transition focus', () => {
  it('leaves initial focus alone when the shell mounts before router readiness', async () => {
    const { router, mountShell } = fixture()
    let finishNavigation: (() => void) | undefined
    let announceGuard: (() => void) | undefined
    const guardStarted = new Promise<void>((resolve) => (announceGuard = resolve))
    router.beforeEach(() => {
      announceGuard!()
      return new Promise<void>((resolve) => (finishNavigation = resolve))
    })
    const wrapper = mountShell()
    const navigation = wrapper.get<HTMLButtonElement>('.navigation')
    navigation.element.focus()
    // Mounting starts the router's first navigation. Let its guard begin before releasing it.
    await guardStarted
    expect(finishNavigation).toBeDefined()
    finishNavigation!()
    await router.isReady()
    await renderFrames()

    expect(wrapper.get('h1').text()).toBe('/')
    expect(document.activeElement).toBe(navigation.element)
  })

  it('focuses the stable destination once after a confirmed pathname change', async () => {
    const { wrapper, router } = await fixture().ready()
    const navigation = wrapper.get<HTMLButtonElement>('.navigation')
    const content = wrapper.get<HTMLElement>('#main-content')
    const focus = vi.spyOn(content.element, 'focus')
    navigation.element.focus()
    await router.push('/page')
    expect(document.activeElement).toBe(navigation.element)
    await renderFrames()

    expect(wrapper.get('h1').text()).toBe('/page')
    expect(document.activeElement).toBe(content.element)
    expect(focus).toHaveBeenCalledTimes(1)
  })

  it('preserves local focus on query, hash, and duplicate navigations', async () => {
    const { wrapper, router } = await fixture().ready()
    const filter = wrapper.get<HTMLInputElement>('input')
    filter.element.focus()
    for (const location of ['/?query=kept', '/?query=kept#anchor', '/?query=kept#anchor']) {
      await router.push(location)
      await renderFrames()
      expect(document.activeElement).toBe(filter.element)
    }
  })

  it('retains source focus when a route guard cancels navigation', async () => {
    const { wrapper, router } = await fixture().ready()
    const navigation = wrapper.get<HTMLButtonElement>('.navigation')
    navigation.element.focus()
    router.beforeEach(() => false)
    await router.push('/page')
    await renderFrames()

    expect(router.currentRoute.value.path).toBe('/')
    expect(document.activeElement).toBe(navigation.element)
  })

  it('focuses reused views on parameter changes and the final redirected destination', async () => {
    const { wrapper, router } = await fixture().ready()
    for (const [location, destination] of [
      ['/person/first', '/person/first'],
      ['/person/second', '/person/second'],
      ['/old', '/page'],
    ]) {
      wrapper.get<HTMLButtonElement>('.navigation').element.focus()
      await router.push(location!)
      await renderFrames()
      expect(wrapper.get('h1').text()).toBe(destination)
      expect(document.activeElement).toBe(wrapper.get('#main-content').element)
    }
  })

  it('does not refocus when pending route content becomes available', async () => {
    const { wrapper, router, loaded } = await fixture().ready()
    await router.push('/delayed')
    await renderFrames()
    expect(wrapper.find('h1').exists()).toBe(false)
    expect(document.activeElement).toBe(wrapper.get('#main-content').element)
    const draft = wrapper.get<HTMLInputElement>('input')
    draft.element.focus()
    loaded.value = true
    await renderFrames()

    expect(wrapper.get('h1').text()).toBe('Loaded page')
    expect(document.activeElement).toBe(draft.element)
  })

  it.each(['dialog', 'alertdialog', 'native dialog'] as const)(
    'preserves an active %s and does not steal focus after it closes',
    async (kind) => {
      const { wrapper, router } = await fixture().ready()
      const modal = document.createElement(kind === 'native dialog' ? 'dialog' : 'div')
      if (kind === 'native dialog') modal.setAttribute('open', '')
      else {
        modal.setAttribute('role', kind)
        modal.setAttribute('aria-modal', 'true')
      }
      const input = document.createElement('input')
      modal.append(input)
      document.body.append(modal)
      input.focus()
      await router.push('/page')
      await renderFrames()
      expect(document.activeElement).toBe(input)
      modal.remove()
      const navigation = wrapper.get<HTMLButtonElement>('.navigation')
      navigation.element.focus()
      await renderFrames()
      expect(document.activeElement).toBe(navigation.element)
    },
  )

  it('discards a pending transfer superseded by another page navigation', async () => {
    const { wrapper, router } = await fixture().ready()
    const content = wrapper.get<HTMLElement>('#main-content')
    const focus = vi.spyOn(content.element, 'focus')
    await router.push('/page')
    await router.push('/person/latest')
    await renderFrames()

    expect(wrapper.get('h1').text()).toBe('/person/latest')
    expect(document.activeElement).toBe(content.element)
    expect(focus).toHaveBeenCalledTimes(1)
  })

  it('preserves a filter used before a pending page focus transfer', async () => {
    const { wrapper, router } = await fixture().ready()
    await router.push('/page')
    await nextTick()
    const filter = wrapper.get<HTMLInputElement>('input')
    filter.element.focus()
    await router.replace('/page?filter=updated')
    await renderFrames()

    expect(document.activeElement).toBe(filter.element)
  })

  it('keeps page-entry focus when automatic query hydration leaves focus in the shell', async () => {
    const { wrapper, router } = await fixture().ready()
    wrapper.get<HTMLButtonElement>('.navigation').element.focus()
    await router.push('/page')
    await router.replace('/page?person=first')
    await renderFrames()

    expect(document.activeElement).toBe(wrapper.get('#main-content').element)
  })

  it('cancels pending work and removes the navigation hook when disposed', async () => {
    const { wrapper, router } = await fixture().ready()
    const focus = vi.spyOn(wrapper.get<HTMLElement>('#main-content').element, 'focus')
    await router.push('/page')
    wrapper.unmount()
    mounted.splice(mounted.indexOf(wrapper), 1)
    await renderFrames()
    await router.push('/person/later')
    await renderFrames()

    expect(focus).not.toHaveBeenCalled()
    expect(frames.size).toBe(0)
  })
})
