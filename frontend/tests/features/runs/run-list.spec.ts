import { flushPromises, type VueWrapper } from '@vue/test-utils'
import { afterEach, describe, expect, it } from 'vitest'

import { createApiClient } from '@/api'
import type { AppLocale } from '@/app/i18n'
import de from '@/locales/de.json'
import en from '@/locales/en.json'
import { useSessionStore } from '@/stores/session'

import { mountApplicationAt } from '../../helpers/render'
import { waitFor } from '../../helpers/wait'

function jsonResponse(body: unknown, init: ResponseInit = {}): Response {
  return new Response(JSON.stringify(body), {
    headers: { 'content-type': 'application/json' },
    ...init,
  })
}

const catalogues = { de, en } as const
const USER = { id: 'a0000000-0000-0000-0000-000000000002', display_name: 'Op', roles: [] }
const PROJECT_ID = 'b0000000-0000-0000-0000-000000000001'
const SNAPSHOT_ID = 'c0000000-0000-0000-0000-000000000001'
const RUN_ID = 'd0000000-0000-0000-0000-000000000001'

const METHODS = [
  {
    name: 'gender_guesser',
    implementation_version: 'gender_guesser_v1',
    normalization_version: 'gender_guesser_v1',
    method_confidence_range: null,
  },
  {
    name: 'local_llm',
    implementation_version: 'local_llm_v1',
    normalization_version: 'local_llm_v1',
    method_confidence_range: { minimum: 0, maximum: 1 },
  },
]

function run(id: string, status: string, extra: Record<string, unknown> = {}) {
  return {
    id,
    dataset_snapshot_id: SNAPSHOT_ID,
    status,
    created_at: '2026-01-01T10:00:00Z',
    config_sha256: 'e'.repeat(64),
    resolved_config: { methods: [{ name: 'gender_guesser', enabled: true, config: {} }] },
    progress: { completed: 3, failed: 1, total: 10, percentage: 40 },
    application_version: '1',
    code_git_commit: 'abc',
    python_version: '3.12',
    ...extra,
  }
}

interface Setup {
  role?: 'operator' | 'viewer'
  runs?: unknown[]
  createStatus?: number
  methodsFail?: boolean
  createResponse?: Promise<Response>
  snapshotProject?: string
  snapshotStatus?: string
  runListFailures?: number
  nextRunListResponse?: Promise<Response>
  runListPages?: (Response | Promise<Response>)[]
}

interface Sent {
  runBodies: unknown[]
  scheduled: string[]
  runListRequests: number
  runListCursors?: (string | null)[]
}

function runsClient(setup: Setup, sent: Sent) {
  const { role = 'operator', runs = [], createStatus = 202 } = setup
  return createApiClient({
    fetch: async (request) => {
      const { pathname, searchParams } = new URL(request.url)
      if (pathname === '/api/v1/branding') return jsonResponse({})
      if (pathname === '/api/v1/me') return jsonResponse(USER)
      if (pathname === '/api/v1/auth/session') {
        return jsonResponse({ must_change_password: false, keep_signed_in: false })
      }
      if (pathname === `/api/v1/projects/${PROJECT_ID}`) {
        return jsonResponse({
          id: PROJECT_ID,
          slug: 'p',
          display_name: 'Project A',
          description: null,
          current_user_role: role,
          created_at: '2026-01-01T00:00:00Z',
        })
      }
      if (pathname === '/api/v1/methods') {
        return setup.methodsFail ? jsonResponse({}, { status: 500 }) : jsonResponse(METHODS)
      }
      if (pathname === `/api/v1/snapshots/${SNAPSHOT_ID}`) {
        return jsonResponse({
          id: SNAPSHOT_ID,
          project_id: setup.snapshotProject ?? PROJECT_ID,
          status: setup.snapshotStatus ?? 'ready',
          record_count: 10,
          created_at: '2026-01-01T09:00:00Z',
        })
      }
      if (pathname === `/api/v1/snapshots/${SNAPSHOT_ID}/runs`) {
        sent.runListRequests += 1
        sent.runListCursors?.push(searchParams.get('cursor'))
        const response = setup.runListPages?.shift()
        if (response) return response
        if (sent.runListRequests <= (setup.runListFailures ?? 0)) {
          return jsonResponse({}, { status: 500 })
        }
        if (setup.nextRunListResponse) return setup.nextRunListResponse
        return jsonResponse({ items: runs, next_cursor: null, has_more: false })
      }
      if (pathname === '/api/v1/runs' && request.method === 'POST') {
        if (createStatus !== 202) {
          return jsonResponse(
            {
              error: { code: 'validation_error', message: 'invalid', details: {}, request_id: 'r' },
            },
            { status: createStatus },
          )
        }
        sent.runBodies.push(await request.json())
        if (setup.createResponse) return setup.createResponse
        return jsonResponse(run(RUN_ID, 'created'), { status: 202 })
      }
      if (pathname === `/api/v1/runs/${RUN_ID}/executions` && request.method === 'POST') {
        sent.scheduled.push(RUN_ID)
        return jsonResponse(run(RUN_ID, 'queued'), { status: 202 })
      }
      return jsonResponse({}, { status: 404 })
    },
  })
}

afterEach(() => {
  document.body.replaceChildren()
})

async function tick(): Promise<void> {
  await flushPromises()
  await new Promise((resolve) => setTimeout(resolve, 20))
  await flushPromises()
}

describe.each(['de', 'en'] as const)('run list and new run in %s', (locale: AppLocale) => {
  const messages = catalogues[locale].runs
  const path = `/projects/${PROJECT_ID}/snapshots/${SNAPSHOT_ID}/runs`

  async function mountRuns(setup: Setup = {}, openForm = true) {
    const sent: Sent = { runBodies: [], scheduled: [], runListRequests: 0 }
    const wrapper = await mountApplicationAt(path, locale, runsClient(setup, sent))
    await waitFor(() =>
      expect(wrapper.find('.run-list, .run-list-unavailable').exists()).toBe(true),
    )
    await tick()
    if (openForm && wrapper.find('.run-list-create').exists()) {
      await wrapper.get('.run-list-create').trigger('click')
      await tick()
    }
    return { wrapper, sent }
  }

  async function pick(wrapper: VueWrapper, name: string): Promise<void> {
    await wrapper.get(`#method-${name}`).setValue(true)
  }

  it('does not report a draft after toggling a method and empty configuration back off', async () => {
    const { wrapper } = await mountRuns()
    try {
      await pick(wrapper, 'local_llm')
      await wrapper.get('#config-local_llm').setValue('{}')
      await wrapper.get('#config-local_llm').setValue('')
      await wrapper.get('#method-local_llm').setValue(false)
      const navigation = wrapper.vm.$router.push('/projects')
      await tick()
      expect(document.querySelector('[role="dialog"]')).toBeNull()
      await navigation
      expect(wrapper.vm.$router.currentRoute.value.path).toBe('/projects')
    } finally {
      wrapper.unmount()
    }
  })

  it('keeps configuration edited while run creation is pending when the operator stays', async () => {
    let finish!: (response: Response) => void
    const createResponse = new Promise<Response>((resolve) => {
      finish = resolve
    })
    const { wrapper, sent } = await mountRuns({ createResponse })
    try {
      await pick(wrapper, 'local_llm')
      await wrapper.get('#config-local_llm').setValue('{"model":"submitted"}')
      await wrapper.get('.new-run').trigger('submit')
      await waitFor(() => expect(sent.runBodies).toHaveLength(1))
      await wrapper.get('#config-local_llm').setValue('{"model":"next-draft"}')
      finish(jsonResponse(run(RUN_ID, 'created'), { status: 202 }))
      await waitFor(() => expect(document.querySelector('[role="dialog"]')).not.toBeNull())
      const stay = Array.from(
        document.querySelectorAll<HTMLButtonElement>('[role="dialog"] button'),
      ).find((button) => button.textContent?.trim() === catalogues[locale].draftNavigation.stay)
      expect(stay).toBeDefined()
      stay?.click()
      await tick()
      expect(wrapper.vm.$router.currentRoute.value.path).toBe(path)
      expect(wrapper.get<HTMLTextAreaElement>('#config-local_llm').element.value).toBe(
        '{"model":"next-draft"}',
      )
      expect(sent.scheduled).toEqual([RUN_ID])
    } finally {
      wrapper.unmount()
    }
  })

  it('does not return to a late-created run after the operator discards and leaves', async () => {
    let finish!: (response: Response) => void
    const createResponse = new Promise<Response>((resolve) => {
      finish = resolve
    })
    const { wrapper, sent } = await mountRuns({ createResponse })
    try {
      await pick(wrapper, 'local_llm')
      await wrapper.get('.new-run').trigger('submit')
      await waitFor(() => expect(sent.runBodies).toHaveLength(1))
      const navigation = wrapper.vm.$router.push('/projects')
      await waitFor(() => expect(document.querySelector('[role="dialog"]')).not.toBeNull())
      const discard = Array.from(
        document.querySelectorAll<HTMLButtonElement>('[role="dialog"] button'),
      ).find((button) => button.textContent?.trim() === catalogues[locale].draftNavigation.discard)
      expect(discard).toBeDefined()
      discard?.click()
      await navigation
      finish(jsonResponse(run(RUN_ID, 'created'), { status: 202 }))
      await tick()
      expect(wrapper.vm.$router.currentRoute.value.path).toBe('/projects')
      expect(document.querySelector('[role="dialog"]')).toBeNull()
    } finally {
      wrapper.unmount()
    }
  })

  it.each([false, true])(
    'never schedules an old account’s delayed run after replacement (return to A: %s)',
    async (returnToOriginal) => {
      let finish!: (response: Response) => void
      const createResponse = new Promise<Response>((resolve) => {
        finish = resolve
      })
      const { wrapper, sent } = await mountRuns({ createResponse })
      await pick(wrapper, 'local_llm')
      await wrapper.get('.new-run').trigger('submit')
      await waitFor(() => expect(sent.runBodies).toHaveLength(1))

      const session = useSessionStore()
      session.user = { ...USER, id: 'a0000000-0000-0000-0000-000000000003' }
      if (returnToOriginal) session.user = USER
      finish(jsonResponse(run(RUN_ID, 'created'), { status: 202 }))
      await tick()

      expect(sent.scheduled).toEqual([])
      expect(wrapper.vm.$router.currentRoute.value.path).toBe(path)
    },
  )

  it('schedules a delayed run when authentication refreshes the same account', async () => {
    let finish!: (response: Response) => void
    const createResponse = new Promise<Response>((resolve) => {
      finish = resolve
    })
    const { wrapper, sent } = await mountRuns({ createResponse })
    await pick(wrapper, 'local_llm')
    await wrapper.get('.new-run').trigger('submit')
    await waitFor(() => expect(sent.runBodies).toHaveLength(1))

    useSessionStore().user = { ...USER, display_name: 'Refreshed operator' }
    finish(jsonResponse(run(RUN_ID, 'created'), { status: 202 }))
    await waitFor(() => expect(sent.scheduled).toEqual([RUN_ID]))
  })

  it('lists the snapshot runs with status, progress and an explicit open action', async () => {
    const { wrapper } = await mountRuns({
      runs: [run('r1', 'completed_with_errors', { failure_diagnostic: 'one method failed' })],
    })

    const item = wrapper.get('.run')
    expect(item.get('.run-status').text()).toBe(messages.status.completedWithErrors)
    expect(item.text()).toContain('gender_guesser')
    expect(item.text()).toMatch(/3.*10.*1/)
    expect(item.find('.run-hash').exists()).toBe(false)
    expect(item.get('.run-open').attributes('href')).toContain('/runs/r1')
    expect(item.get('.run-failure').text()).toBe('one method failed')
  })

  it('says so when the snapshot has no runs yet', async () => {
    const { wrapper } = await mountRuns()
    expect(wrapper.get('.run-list-empty').text()).toBe(messages.empty)
  })

  it('announces a run-list failure and recovers without announcing the retry action', async () => {
    let finish!: (response: Response) => void
    const nextRunListResponse = new Promise<Response>((resolve) => {
      finish = resolve
    })
    const sent: Sent = { runBodies: [], scheduled: [], runListRequests: 0 }
    const wrapper = await mountApplicationAt(
      path,
      locale,
      runsClient({ runListFailures: 1, nextRunListResponse }, sent),
    )
    try {
      await waitFor(() => expect(wrapper.find('.run-list-load-error').exists()).toBe(true))

      const feedback = wrapper.get('.run-list-load-error')
      const alert = feedback.get('[role="alert"]')
      const retry = feedback.get('.run-list-retry')
      expect(alert.text()).toBe(messages.loadError)
      expect(alert.attributes('aria-atomic')).toBe('true')
      expect(alert.find('button').exists()).toBe(false)
      expect(feedback.classes()).toContain('app-feedback--critical')
      expect(retry.text()).toBe(messages.retry)

      const firstRetry = retry.trigger('click')
      const duplicateRetry = retry.trigger('click')
      await Promise.all([firstRetry, duplicateRetry])
      await waitFor(() => expect(sent.runListRequests).toBe(2))
      expect(wrapper.find('.run-list-retry:not([disabled])').exists()).toBe(false)
      expect(sent.runListRequests).toBe(2)

      finish(jsonResponse({ items: [], next_cursor: null, has_more: false }))
      await waitFor(() => expect(wrapper.find('.run-list-empty').exists()).toBe(true))

      expect(wrapper.find('.run-list-load-error').exists()).toBe(false)
    } finally {
      wrapper.unmount()
    }
  })

  it('retains rows and retries a failed next page with the same cursor without duplicate requests', async () => {
    let finish!: (response: Response) => void
    const retryPage = new Promise<Response>((resolve) => {
      finish = resolve
    })
    const sent: Sent = {
      runBodies: [],
      scheduled: [],
      runListRequests: 0,
      runListCursors: [],
    }
    const wrapper = await mountApplicationAt(
      path,
      locale,
      runsClient(
        {
          runListPages: [
            jsonResponse({
              items: [run('r1', 'completed')],
              next_cursor: 'page-two',
              has_more: true,
            }),
            jsonResponse({}, { status: 500 }),
            retryPage,
          ],
        },
        sent,
      ),
    )
    const runLinks = () => wrapper.findAll('main h3 a').map((link) => link.attributes('href'))
    const expectedLinks = ['r1', 'r2'].map((id) => `${path}/${id}`)
    const action = (name: string) => {
      const button = wrapper.findAll('main button').find((candidate) => candidate.text() === name)
      if (!button) throw new Error(`Missing action: ${name}`)
      return button
    }
    try {
      await waitFor(() => expect(runLinks()).toEqual([expectedLinks[0]]))
      await action(messages.loadMore).trigger('click')
      await waitFor(() => expect(wrapper.get('main [role="alert"]').isVisible()).toBe(true))
      expect(runLinks()).toEqual([expectedLinks[0]])
      const retry = action(messages.retry)
      await Promise.all([retry.trigger('click'), retry.trigger('click')])
      await waitFor(() => expect(sent.runListRequests).toBe(3))
      expect(retry.attributes('disabled')).toBeDefined()
      expect(sent.runListCursors).toEqual([null, 'page-two', 'page-two'])
      finish(jsonResponse({ items: [run('r2', 'completed')], next_cursor: null, has_more: false }))
      await waitFor(() => expect(runLinks()).toEqual(expectedLinks))
      const actionNames = wrapper.findAll('main button').map((button) => button.text())
      expect(actionNames).not.toContain(messages.loadMore)
      expect(actionNames).not.toContain(messages.retry)
    } finally {
      wrapper.unmount()
    }
  })

  it('takes the method roster from the server and states each own confidence range', async () => {
    const { wrapper } = await mountRuns()

    const names = wrapper.findAll('.new-run-method-name').map((label) => label.text())
    expect(names).toEqual(['gender_guesser', 'local_llm'])
    const facts = wrapper.findAll('.new-run-method-facts').map((p) => p.text())
    expect(facts[0]).toContain('gender_guesser_v1')
    expect(facts[0]).not.toMatch(/0[.,]0/)
    expect(facts[1]).toMatch(/0[.,]0.*1[.,]0/)
  })

  it('creates and schedules a run from the chosen methods and their JSON configuration', async () => {
    const { wrapper, sent } = await mountRuns()

    await pick(wrapper, 'gender_guesser')
    await pick(wrapper, 'local_llm')
    await wrapper
      .get('#config-local_llm')
      .setValue('{"model": "llama3", "base_url": "http://llm:11434/v1"}')
    await wrapper.get('#fail-on-optional').setValue(true)
    await wrapper.get('form').trigger('submit')
    await tick()

    expect(sent.runBodies).toEqual([
      {
        dataset_snapshot_id: SNAPSHOT_ID,
        config: {
          methods: [
            { name: 'gender_guesser', enabled: true, config: {} },
            {
              name: 'local_llm',
              enabled: true,
              config: { model: 'llama3', base_url: 'http://llm:11434/v1' },
            },
          ],
          execution: { fail_run_on_optional_method_error: true },
        },
      },
    ])
    expect(sent.scheduled).toEqual([RUN_ID])
  })

  it('needs at least one method before it can start', async () => {
    const { wrapper } = await mountRuns()
    expect(wrapper.get('.new-run-submit').attributes('disabled')).toBeDefined()

    await pick(wrapper, 'gender_guesser')

    expect(wrapper.get('.new-run-submit').attributes('disabled')).toBeUndefined()
  })

  it('keeps method and execution configuration behind explicit disclosures', async () => {
    const { wrapper } = await mountRuns()
    await pick(wrapper, 'local_llm')
    const methodConfig = wrapper.get<HTMLDetailsElement>('.new-run-config')
    expect(methodConfig.element.open).toBe(false)
    expect(methodConfig.get('summary').text()).toBe(messages.new.configureMethod)
    expect(wrapper.get<HTMLDetailsElement>('.new-run-advanced').element.open).toBe(false)
    expect(wrapper.get('.new-run-submit').attributes('disabled')).toBeUndefined()
  })

  it('refuses a configuration that is not a JSON object, before sending', async () => {
    const { wrapper, sent } = await mountRuns()

    await pick(wrapper, 'local_llm')
    await wrapper.get('#config-local_llm').setValue('{not json')

    expect(wrapper.get('.new-run-error').text()).toBe(messages.new.errors.notJsonObject)
    expect(wrapper.get('.new-run-submit').attributes('disabled')).toBeDefined()
    await wrapper.get('form').trigger('submit')
    await tick()
    expect(sent.runBodies).toHaveLength(0)
  })

  it('shows the server rejection of a run configuration and keeps the form filled', async () => {
    const { wrapper } = await mountRuns({ createStatus: 422 })

    await pick(wrapper, 'local_llm')
    await wrapper.get('form').trigger('submit')
    await tick()

    expect(wrapper.get('.new-run-error').text()).toBe(messages.new.errors.invalidConfig)
    expect((wrapper.get('#method-local_llm').element as HTMLInputElement).checked).toBe(true)
  })

  it('offers no form to a viewer', async () => {
    const { wrapper } = await mountRuns({ role: 'viewer' })

    expect(wrapper.find('.new-run').exists()).toBe(false)
    expect(wrapper.find('.run-list-create').exists()).toBe(false)
  })

  it('retries when the method roster cannot be loaded', async () => {
    const { wrapper } = await mountRuns({ methodsFail: true })

    expect(wrapper.get('.new-run-load-error').text()).toContain(messages.new.methodsLoadError)
  })

  it('starts with the run list and preserves a guarded draft when the form is collapsed', async () => {
    const { wrapper } = await mountRuns({}, false)
    try {
      expect(wrapper.find('.new-run').exists()).toBe(false)
      await wrapper.get('.run-list-create').trigger('click')
      await tick()
      expect(document.activeElement?.id).toBe('new-run-heading')
      await pick(wrapper, 'local_llm')
      await wrapper.get('#config-local_llm').setValue('{"model":"draft"}')
      await wrapper.get('.run-list-create').trigger('click')
      expect(wrapper.get('.new-run').isVisible()).toBe(false)
      await wrapper.get('.run-list-create').trigger('click')
      expect(wrapper.get<HTMLTextAreaElement>('#config-local_llm').element.value).toContain('draft')
      await wrapper.get('.run-list-create').trigger('click')
      void wrapper.vm.$router.push('/projects')
      await waitFor(() => expect(document.querySelector('[role="dialog"]')).not.toBeNull())
    } finally {
      wrapper.unmount()
    }
  })

  it('retains the guarded configuration while same-account authentication pauses private reads', async () => {
    const { wrapper } = await mountRuns()
    try {
      await pick(wrapper, 'local_llm')
      await wrapper.get('#config-local_llm').setValue('{"model":"recovery-draft"}')
      const session = useSessionStore()
      session.isAuthenticating = true
      await flushPromises()
      expect(wrapper.get('.new-run').isVisible()).toBe(false)
      session.user = { ...USER, display_name: 'Recovered operator' }
      session.isAuthenticating = false
      await waitFor(() => expect(wrapper.get('.new-run').isVisible()).toBe(true))
      expect(wrapper.get<HTMLTextAreaElement>('#config-local_llm').element.value).toBe(
        '{"model":"recovery-draft"}',
      )
      void wrapper.vm.$router.push('/projects')
      await waitFor(() => expect(document.querySelector('[role="dialog"]')).not.toBeNull())
    } finally {
      wrapper.unmount()
    }
  })

  it.each([{ snapshotProject: 'another-project' }, { snapshotStatus: 'importing' }])(
    'does not offer a form or runs for an unavailable snapshot context %o',
    async (setup) => {
      const { wrapper } = await mountRuns(setup, false)
      expect(wrapper.find('.run-list-create').exists()).toBe(false)
      expect(wrapper.find('.run-list').exists()).toBe(false)
      expect(wrapper.get('.run-list-unavailable').text()).toContain(messages.contextUnavailable)
    },
  )
})
