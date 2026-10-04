import { useQueryClient } from '@tanstack/vue-query'
import { flushPromises, type VueWrapper } from '@vue/test-utils'
import { nextTick } from 'vue'
import { afterEach, describe, expect, it } from 'vitest'

import { createApiClient } from '@/api'
import type { UserPreferences, UserPreferencesUpdate } from '@/composables/useUserPreferences'
import de from '@/locales/de.json'
import en from '@/locales/en.json'
import { useSessionStore } from '@/stores/session'

import { mountApplicationAt } from '../helpers/render'
import { waitFor } from '../helpers/wait'

const messages = { de, en }
const USER = { id: 'a0000000-0000-0000-0000-000000000001', display_name: 'Reviewer', roles: [] }
let wrapper: VueWrapper | undefined

function response(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  })
}

function fixture(locale: 'de' | 'en') {
  const state = {
    saved: {
      locale,
      theme: 'light',
      desktop_sidebar_collapsed: false,
      revision: 3,
    } as UserPreferences,
    patches: [] as UserPreferencesUpdate[],
    getStatus: 200,
    patchStatus: 200,
    beforeWrite: null as (() => Promise<void>) | null,
  }
  const client = createApiClient({
    fetch: async (request) => {
      const path = new URL(request.url).pathname
      if (path === '/api/v1/me') return response(USER)
      if (path === '/api/v1/auth/session') return response({ must_change_password: false })
      if (path === '/api/v1/branding') return response({})
      if (path === '/api/v1/projects') return response({ items: [], has_more: false })
      if (path === '/api/v1/me/preferences') {
        if (request.method === 'GET') return response(state.saved, state.getStatus)
        const command = (await request.json()) as UserPreferencesUpdate
        state.patches.push(command)
        await state.beforeWrite?.()
        if (state.patchStatus !== 200) {
          return response(
            { error: { code: 'preferences_revision_conflict', message: 'Save failed.' } },
            state.patchStatus,
          )
        }
        state.saved = {
          ...state.saved,
          desktop_sidebar_collapsed: command.desktop_sidebar_collapsed ?? false,
          revision: state.saved.revision + 1,
        }
        return response(state.saved)
      }
      return response({}, 404)
    },
  })
  return { state, client }
}

afterEach(() => {
  wrapper?.unmount()
  wrapper = undefined
  document.body.replaceChildren()
  localStorage.clear()
  document.documentElement.removeAttribute('data-theme')
})

describe.each(['de', 'en'] as const)('desktop sidebar collapse in %s', (locale) => {
  it('saves only the explicit desktop choice with the latest canonical revision', async () => {
    const { state, client } = fixture(locale)
    wrapper = await mountApplicationAt('/projects', locale, client)
    const button = wrapper.get<HTMLButtonElement>('.sidebar-collapse-button')
    expect(button.attributes('aria-label')).toBe(messages[locale].nav.collapseSidebar)
    expect(button.attributes('aria-expanded')).toBe('true')
    await button.trigger('click')
    await waitFor(() => expect(button.attributes('aria-expanded')).toBe('false'))
    expect(state.patches).toEqual([{ expected_revision: 3, desktop_sidebar_collapsed: true }])
    expect(wrapper.get('aside').classes()).toContain('app-sidebar--desktop-collapsed')
    expect(button.attributes('aria-label')).toBe(messages[locale].nav.expandSidebar)
    expect(state.saved.locale).toBe(locale)
    expect(state.saved.theme).toBe('light')
    expect(localStorage.getItem('gendertagger.sidebar.collapsed')).toBeNull()
    await button.trigger('click')
    await waitFor(() => expect(button.attributes('aria-expanded')).toBe('true'))
    expect(state.patches[1]).toEqual({ expected_revision: 4, desktop_sidebar_collapsed: false })
  })

  it('waits for the confirmed response and prevents duplicate writes while saving', async () => {
    const { state, client } = fixture(locale)
    let finish!: () => void
    state.beforeWrite = () =>
      new Promise<void>((resolve) => {
        finish = resolve
      })
    wrapper = await mountApplicationAt('/projects', locale, client)
    const button = wrapper.get<HTMLButtonElement>('.sidebar-collapse-button')
    await button.trigger('click')
    await waitFor(() => expect(state.patches).toHaveLength(1))
    expect(button.element.disabled).toBe(true)
    expect(button.attributes('aria-expanded')).toBe('true')
    await button.trigger('click')
    finish()
    await waitFor(() => expect(button.attributes('aria-expanded')).toBe('false'))
    expect(state.patches).toHaveLength(1)
    expect(button.element.disabled).toBe(false)
  })

  it.each(['pointer', 'Enter', 'Space'] as const)(
    'dismisses the tooltip on %s activation throughout a delayed expansion',
    async (activation) => {
      const { state, client } = fixture(locale)
      state.saved.desktop_sidebar_collapsed = true
      let finish!: () => void
      state.beforeWrite = () =>
        new Promise<void>((resolve) => {
          finish = resolve
        })
      wrapper = await mountApplicationAt('/projects', locale, client)
      const button = wrapper.get<HTMLButtonElement>(
        `button[aria-label="${messages[locale].nav.expandSidebar}"]`,
      )
      button.element.focus()
      await button.trigger('mouseenter')
      expect(document.querySelector('[role="tooltip"]')?.textContent).toBe(
        messages[locale].nav.expandSidebar,
      )
      expect(button.attributes('aria-describedby')).toBeDefined()

      if (activation !== 'pointer') {
        const key = activation === 'Space' ? ' ' : activation
        await button.trigger('keydown', { key })
        await button.trigger('keyup', { key })
      }
      // jsdom does not synthesize the native button click for Enter or Space.
      button.element.dispatchEvent(
        new MouseEvent('click', { bubbles: true, detail: activation === 'pointer' ? 1 : 0 }),
      )
      await nextTick()
      expect(document.querySelector('[role="tooltip"]')).toBeNull()
      expect(button.attributes('aria-describedby')).toBeUndefined()
      expect(document.activeElement).toBe(button.element)
      await waitFor(() => expect(state.patches).toHaveLength(1))
      expect(button.element.disabled).toBe(true)
      expect(button.attributes('aria-expanded')).toBe('false')
      await button.trigger('mouseleave')
      await button.trigger('mouseenter')
      expect(document.querySelector('[role="tooltip"]')).toBeNull()

      finish()
      await waitFor(() => expect(button.attributes('aria-expanded')).toBe('true'))
      expect(button.element.disabled).toBe(false)
      expect(document.activeElement).toBe(button.element)
      expect(document.querySelector('[role="tooltip"]')).toBeNull()
      expect(button.attributes('aria-describedby')).toBeUndefined()

      button.element.blur()
      await button.trigger('mouseleave')
      button.element.focus()
      await button.trigger('mouseenter')
      expect(document.querySelector('[role="tooltip"]')).toBeNull()
    },
  )

  it('does not show a redundant tooltip for the labelled expanded button', async () => {
    const { client } = fixture(locale)
    wrapper = await mountApplicationAt('/projects', locale, client)
    const button = wrapper.get<HTMLButtonElement>(
      `button[aria-label="${messages[locale].nav.collapseSidebar}"]`,
    )
    button.element.focus()
    await button.trigger('mouseenter')
    expect(document.querySelector('[role="tooltip"]')).toBeNull()
    expect(button.attributes('aria-describedby')).toBeUndefined()
  })

  it('keeps the saved layout and shows a recoverable error after a failed save', async () => {
    const { state, client } = fixture(locale)
    state.patchStatus = 500
    wrapper = await mountApplicationAt('/projects', locale, client)
    const button = wrapper.get<HTMLButtonElement>('.sidebar-collapse-button')
    await button.trigger('click')
    await waitFor(() =>
      expect(wrapper!.get('.sidebar-collapse-error').text()).toContain(
        messages[locale].nav.collapseSaveError,
      ),
    )
    expect(button.attributes('aria-expanded')).toBe('true')
    expect(button.element.disabled).toBe(false)
    await wrapper.findAll('.sidebar-collapse-error button')[1]?.trigger('click')
    expect(wrapper.find('.sidebar-collapse-error').exists()).toBe(false)
    state.patchStatus = 200
    await button.trigger('click')
    await waitFor(() => expect(button.attributes('aria-expanded')).toBe('false'))
  })

  it('blocks conflict replay until a successful explicit reload, preserving other settings', async () => {
    const { state, client } = fixture(locale)
    wrapper = await mountApplicationAt('/projects', locale, client)
    const button = wrapper.get<HTMLButtonElement>('.sidebar-collapse-button')
    state.saved = { ...state.saved, theme: 'dark', desktop_sidebar_collapsed: true, revision: 4 }
    state.patchStatus = 409
    await button.trigger('click')
    await waitFor(() =>
      expect(wrapper!.get('.sidebar-collapse-error').text()).toContain(
        messages[locale].sidebarPreferences.conflict,
      ),
    )
    expect(button.element.disabled).toBe(true)
    expect(button.attributes('aria-expanded')).toBe('true')
    state.getStatus = 500
    await wrapper.get('.sidebar-collapse-error button').trigger('click')
    await waitFor(() =>
      expect(wrapper!.get('.sidebar-collapse-error').text()).toContain(
        messages[locale].sidebarPreferences.reloadError,
      ),
    )
    expect(button.element.disabled).toBe(true)
    state.getStatus = 200
    await wrapper.get('.sidebar-collapse-error button').trigger('click')
    await waitFor(() => expect(button.element.disabled).toBe(false))
    expect(button.attributes('aria-expanded')).toBe('false')
    expect(document.documentElement.dataset.theme).toBe('dark')
    expect(state.patches).toHaveLength(1)
    state.patchStatus = 200
    await button.trigger('click')
    await waitFor(() => expect(state.patches).toHaveLength(2))
    expect(state.patches[1]).toEqual({ expected_revision: 4, desktop_sidebar_collapsed: false })
  })

  it('discards a late save after the initiating account signs out', async () => {
    localStorage.setItem('gendertagger.theme', 'dark')
    const { state, client } = fixture(locale)
    let finish!: () => void
    state.beforeWrite = () =>
      new Promise<void>((resolve) => {
        finish = resolve
      })
    wrapper = await mountApplicationAt('/projects', locale, client)
    const queryClient = wrapper.vm.$.appContext.app.runWithContext(() => useQueryClient())
    const savedPreferences = { ...state.saved }
    await wrapper.get('.sidebar-collapse-button').trigger('click')
    await waitFor(() => expect(state.patches).toHaveLength(1))
    useSessionStore().user = null
    await flushPromises()
    expect(wrapper.find('aside').exists()).toBe(false)
    expect(
      queryClient
        .getQueryCache()
        .getAll()
        .map((query) => query.state.data),
    ).not.toContainEqual(savedPreferences)

    finish()
    await flushPromises()

    expect(wrapper.find('aside').exists()).toBe(false)
    expect(wrapper.find('.sidebar-collapse-button').exists()).toBe(false)
    expect(wrapper.find('.sidebar-collapse-error').exists()).toBe(false)
    expect(wrapper.find('.app-header-navigation').exists()).toBe(false)
    expect(wrapper.find('.app-header-brand').exists()).toBe(true)
    expect(wrapper.get('header [data-preference="theme"]').text()).toContain(
      messages[locale].theme.dark,
    )
    expect(document.documentElement.dataset.theme).toBe('dark')
    const cachedData = queryClient
      .getQueryCache()
      .getAll()
      .map((query) => query.state.data)
    expect(cachedData).not.toContainEqual(savedPreferences)
    expect(cachedData).not.toContainEqual(state.saved)
    expect(localStorage.getItem('gendertagger.theme')).toBe('dark')
    expect(localStorage.getItem('gendertagger.sidebar.collapsed')).toBeNull()
    expect(state.patches).toEqual([{ expected_revision: 3, desktop_sidebar_collapsed: true }])
  })
})
