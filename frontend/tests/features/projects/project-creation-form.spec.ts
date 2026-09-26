import { VueQueryPlugin } from '@tanstack/vue-query'
import { DOMWrapper, flushPromises, mount } from '@vue/test-utils'
import { afterEach, describe, expect, it } from 'vitest'

import { createApiClient } from '@/api'
import { createAppI18n, type AppLocale } from '@/app/i18n'
import { createQueryClient } from '@/app/queryClient'
import { API_CLIENT_KEY } from '@/composables/useApiClient'
import ProjectCreationForm from '@/features/projects/ProjectCreationForm.vue'
import de from '@/locales/de.json'
import en from '@/locales/en.json'

import { expectNoAxeViolations } from '../../helpers/axe'
import { waitFor } from '../../helpers/wait'

const catalogues = { de, en } as const
const PRINCIPAL = 'a0000000-0000-0000-0000-000000000001'
const TEAM_A = {
  id: 'b0000000-0000-0000-0000-000000000001',
  slug: 'team-a',
  display_name: 'Team A',
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
}
const TEAM_B = { ...TEAM_A, id: 'b0000000-0000-0000-0000-000000000002', display_name: 'Team B' }
const MANAGER_A = {
  team_id: TEAM_A.id,
  user_id: PRINCIPAL,
  display_name: 'Member A',
  is_active: true,
  created_at: '2026-01-01T00:00:00Z',
}
const MANAGER_B = {
  ...MANAGER_A,
  user_id: 'c0000000-0000-0000-0000-000000000002',
  display_name: 'Member B',
}
const INACTIVE = {
  ...MANAGER_A,
  user_id: 'inactive',
  display_name: 'Inactive member',
  is_active: false,
}
const cleanups: (() => void)[] = []

function page(items: unknown[], next: string | null = null): Response {
  return Response.json({ items, has_more: next !== null, next_cursor: next })
}

function failure(): Response {
  return Response.json(
    { error: { code: 'internal_error', message: 'Unavailable.' } },
    { status: 503 },
  )
}

function deferred() {
  let resolve!: (response: Response) => void
  const promise = new Promise<Response>((settle) => {
    resolve = settle
  })
  return { promise, resolve }
}

async function mountForm(
  locale: AppLocale,
  handler: (request: Request) => Response | Promise<Response>,
  isAdministrator = false,
) {
  const queryClient = createQueryClient()
  const wrapper = mount(ProjectCreationForm, {
    attachTo: document.body,
    props: { principalId: PRINCIPAL, isAdministrator },
    global: {
      plugins: [createAppI18n(locale), [VueQueryPlugin, { queryClient }]],
      provide: {
        [API_CLIENT_KEY as symbol]: createApiClient({ fetch: async (request) => handler(request) }),
      },
    },
  })
  cleanups.push(() => {
    wrapper.unmount()
    queryClient.clear()
  })
  await flushPromises()
  return wrapper
}

afterEach(() => {
  for (const cleanup of cleanups.splice(0)) cleanup()
  document.body.replaceChildren()
})

describe.each(['de', 'en'] as const)('project creation discovery in %s', (locale) => {
  const messages = catalogues[locale].projects.creation

  it('describes slug constraints accessibly and shows focus help that Escape dismisses', async () => {
    const wrapper = await mountForm(locale, () => page([TEAM_A]))
    expect(wrapper.get('.project-creation').classes()).toContain('app-card')
    const input = wrapper.get<HTMLInputElement>('#project-create-slug')
    const label = wrapper.get('.project-creation-label')
    const button = wrapper.get<HTMLButtonElement>('.app-field-help')
    expect(label.get('label').attributes('for')).toBe('project-create-slug')
    expect(label.get('.app-field-help').element).toBe(button.element)
    expect(label.element.nextElementSibling).toBe(input.element)
    expect(input.attributes('aria-describedby')).toBe('project-create-slug-help')
    expect(wrapper.get('#project-create-slug-help').text()).toBe(messages.slugConstraints)
    expect(wrapper.find('p#project-create-slug-help').exists()).toBe(false)
    expect(input.attributes('placeholder')).toBe(messages.slugExample)
    expect(button.attributes('aria-label')).toBe(messages.slugHelpLabel)
    expect(document.querySelector('[role="tooltip"]')).toBeNull()

    button.element.focus()
    await flushPromises()
    const tooltip = document.querySelector('[role="tooltip"]')!
    expect(tooltip.textContent).toBe(messages.slugConstraints)
    expect(button.attributes('aria-describedby')).toBe(tooltip.id)
    await expectNoAxeViolations(wrapper.element)
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))
    await flushPromises()
    expect(document.querySelector('[role="tooltip"]')).toBeNull()
    expect(document.activeElement).toBe(button.element)
    expect(wrapper.get('#project-create-slug-help').text()).toBe(messages.slugConstraints)
  })

  it('keeps slug help open while the pointer moves from its trigger onto the tooltip', async () => {
    const wrapper = await mountForm(locale, () => page([TEAM_A]))
    const button = wrapper.get('.app-field-help')
    await button.trigger('mouseenter')
    const tooltip = new DOMWrapper(document.querySelector('[role="tooltip"]')!)
    await button.trigger('mouseleave')
    await tooltip.trigger('mouseenter')
    await new Promise((resolve) => setTimeout(resolve, 180))
    expect(document.querySelector('[role="tooltip"]')).not.toBeNull()
    await tooltip.trigger('mouseleave')
    await waitFor(() => expect(document.querySelector('[role="tooltip"]')).toBeNull())
  })

  it('opens help on touch activation even after focus, and dismisses on another tap or outside interaction', async () => {
    const wrapper = await mountForm(locale, () => page([TEAM_A]))
    const button = wrapper.get<HTMLButtonElement>('.app-field-help')
    await button.trigger('pointerdown', { pointerType: 'touch' })
    button.element.focus()
    await button.trigger('click')
    expect(document.querySelector('[role="tooltip"]')?.textContent).toBe(messages.slugConstraints)
    await button.trigger('click')
    expect(document.querySelector('[role="tooltip"]')).toBeNull()
    await button.trigger('click')
    expect(document.querySelector('[role="tooltip"]')).not.toBeNull()
    document.body.dispatchEvent(new Event('pointerdown', { bubbles: true }))
    await flushPromises()
    expect(document.querySelector('[role="tooltip"]')).toBeNull()
    expect(wrapper.get<HTMLInputElement>('#project-create-slug').element.value).toBe('')
  })

  it('distinguishes loading, failed discovery and confirmed empty team results', async () => {
    const pending = deferred()
    const queries: (string | null)[] = []
    const wrapper = await mountForm(locale, (request) => {
      queries.push(new URL(request.url).searchParams.get('query'))
      return queries.length === 1 ? pending.promise : page([])
    })
    expect(wrapper.find('#project-create-team-search').exists()).toBe(false)
    expect(wrapper.get('[role="status"]').text()).toBe(messages.teamsLoading)
    expect(wrapper.text()).not.toContain(messages.noTeams)
    pending.resolve(failure())
    await waitFor(() => expect(wrapper.get('[role="alert"]').text()).toBe(messages.teamsLoadError))
    expect(wrapper.text()).not.toContain(messages.noTeams)

    await wrapper.get('.project-creation-teams-error button').trigger('click')
    await waitFor(() => expect(wrapper.text()).toContain(messages.noTeams))
    expect(wrapper.find('[role="alert"]').exists()).toBe(false)
    expect(queries).toEqual([null, null])
    await expectNoAxeViolations(wrapper.element)
  })

  it('keeps loaded teams and the selected team through a next-page failure and retry', async () => {
    const pending = deferred()
    const cursors: (string | null)[] = []
    const queries: (string | null)[] = []
    const wrapper = await mountForm(locale, (request) => {
      const url = new URL(request.url)
      const cursor = url.searchParams.get('cursor')
      cursors.push(cursor)
      queries.push(url.searchParams.get('query'))
      if (cursor === null) return page([TEAM_A], 'team-next')
      return cursors.length === 2 ? pending.promise : page([TEAM_B])
    })
    await wrapper.get('#project-create-team').setValue(TEAM_A.id)
    await wrapper.get('#project-create-name').setValue('Unfinished edition')
    await wrapper.get('.project-creation-teams-more').trigger('click')
    await flushPromises()
    expect(wrapper.get<HTMLButtonElement>('.project-creation-teams-more').element.disabled).toBe(
      true,
    )
    expect(wrapper.get('.project-creation-teams-more').text()).toBe(messages.teamsLoading)
    pending.resolve(failure())
    await waitFor(() => expect(wrapper.get('[role="alert"]').text()).toBe(messages.teamsPageError))
    expect(wrapper.get<HTMLSelectElement>('#project-create-team').element.value).toBe(TEAM_A.id)
    expect(wrapper.text()).not.toContain(messages.noTeams)

    await wrapper.get('.project-creation-teams-page-error button').trigger('click')
    await waitFor(() =>
      expect(wrapper.find(`#project-create-team option[value="${TEAM_B.id}"]`).exists()).toBe(true),
    )
    expect(wrapper.get<HTMLSelectElement>('#project-create-team').element.value).toBe(TEAM_A.id)
    expect(wrapper.get<HTMLInputElement>('#project-create-name').element.value).toBe(
      'Unfinished edition',
    )
    expect(cursors).toEqual([null, 'team-next', 'team-next'])
    expect(queries).toEqual([null, null, null])
    expect(wrapper.find('.project-creation-teams-more').exists()).toBe(false)
  })

  it('loads managers only after team selection and distinguishes a failure from an empty roster', async () => {
    const pending = deferred()
    let attempts = 0
    const wrapper = await mountForm(
      locale,
      (request) => {
        if (new URL(request.url).pathname === '/api/v1/teams') return page([TEAM_A])
        attempts += 1
        return attempts === 1 ? pending.promise : page([])
      },
      true,
    )
    expect(attempts).toBe(0)
    expect(wrapper.get<HTMLSelectElement>('#project-create-manager').element.disabled).toBe(true)
    expect(wrapper.get('#project-create-manager option').text()).toBe(messages.defaultManager)
    expect(wrapper.get('#project-create-manager-help').text()).toBe(messages.managerHelp)
    await wrapper.get('#project-create-team').setValue(TEAM_A.id)
    await waitFor(() =>
      expect(wrapper.get('[role="status"]').text()).toBe(messages.managersLoading),
    )
    expect(wrapper.text()).not.toContain(messages.noManagers)
    pending.resolve(failure())
    await waitFor(() =>
      expect(wrapper.get('[role="alert"]').text()).toBe(messages.managersLoadError),
    )
    expect(wrapper.text()).not.toContain(messages.noManagers)

    await wrapper.get('.project-creation-managers-error button').trigger('click')
    await waitFor(() => expect(wrapper.text()).toContain(messages.noManagers))
    expect(wrapper.find('[role="alert"]').exists()).toBe(false)
  })

  it('keeps active manager options and selection through a later-page error', async () => {
    const pending = deferred()
    const cursors: (string | null)[] = []
    const wrapper = await mountForm(
      locale,
      (request) => {
        const url = new URL(request.url)
        if (url.pathname === '/api/v1/teams') return page([TEAM_A])
        const cursor = url.searchParams.get('cursor')
        cursors.push(cursor)
        if (cursor === null) return page([MANAGER_A], 'manager-next')
        return cursors.length === 2 ? pending.promise : page([MANAGER_B, INACTIVE])
      },
      true,
    )
    await wrapper.get('#project-create-team').setValue(TEAM_A.id)
    await waitFor(() =>
      expect(
        wrapper.find(`#project-create-manager option[value="${MANAGER_A.user_id}"]`).exists(),
      ).toBe(true),
    )
    await wrapper.get('#project-create-manager').setValue(MANAGER_A.user_id)
    await wrapper.get('.project-creation-managers-more').trigger('click')
    await flushPromises()
    expect(wrapper.get<HTMLButtonElement>('.project-creation-managers-more').element.disabled).toBe(
      true,
    )
    expect(wrapper.get('.project-creation-managers-more').text()).toBe(messages.managersLoading)
    pending.resolve(failure())
    await waitFor(() =>
      expect(wrapper.get('[role="alert"]').text()).toBe(messages.managersPageError),
    )
    expect(wrapper.get<HTMLSelectElement>('#project-create-manager').element.value).toBe(
      MANAGER_A.user_id,
    )

    await wrapper.get('.project-creation-managers-page-error button').trigger('click')
    await waitFor(() =>
      expect(
        wrapper.find(`#project-create-manager option[value="${MANAGER_B.user_id}"]`).exists(),
      ).toBe(true),
    )
    expect(wrapper.find('#project-create-manager option[value="inactive"]').exists()).toBe(false)
    expect(wrapper.get<HTMLSelectElement>('#project-create-manager').element.value).toBe(
      MANAGER_A.user_id,
    )
    expect(cursors).toEqual([null, 'manager-next', 'manager-next'])
  })

  it('does not call a partially loaded roster empty when active members may be on later pages', async () => {
    const wrapper = await mountForm(
      locale,
      (request) => {
        const url = new URL(request.url)
        if (url.pathname === '/api/v1/teams') return page([TEAM_A])
        return url.searchParams.get('cursor') === null
          ? page([INACTIVE], 'manager-next')
          : page([MANAGER_B])
      },
      true,
    )
    await wrapper.get('#project-create-team').setValue(TEAM_A.id)
    await waitFor(() => expect(wrapper.text()).toContain(messages.noLoadedManagers))
    expect(wrapper.text()).not.toContain(messages.noManagers)
    await wrapper.get('.project-creation-managers-more').trigger('click')
    await waitFor(() =>
      expect(
        wrapper.find(`#project-create-manager option[value="${MANAGER_B.user_id}"]`).exists(),
      ).toBe(true),
    )
    expect(wrapper.text()).not.toContain(messages.noLoadedManagers)
  })
})
