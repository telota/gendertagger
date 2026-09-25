import { VueQueryPlugin } from '@tanstack/vue-query'
import { createPinia } from 'pinia'
import { flushPromises, mount } from '@vue/test-utils'
import { defineComponent } from 'vue'
import { describe, expect, it } from 'vitest'

import { createApiClient } from '@/api'
import { createQueryClient } from '@/app/queryClient'
import { shouldRetryAfterUnauthorized } from '@/app/sessionGuard'
import { API_CLIENT_KEY } from '@/composables/useApiClient'
import {
  useUserPreferences,
  userPreferencesQueryKey,
  type UserPreferences,
} from '@/composables/useUserPreferences'
import { useSessionStore } from '@/stores/session'

const SAVED: UserPreferences = {
  locale: 'de',
  theme: 'dark',
  desktop_sidebar_collapsed: true,
  revision: 3,
}
const COMMAND = {
  locale: 'en',
  theme: 'light',
  desktop_sidebar_collapsed: false,
  expected_revision: 3,
} as const

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  })
}

function deferred() {
  let resolve!: (value: Response) => void
  const promise = new Promise<Response>((accept) => {
    resolve = accept
  })
  return { resolve, promise }
}

function mountPreferences(
  fetch: (request: Request) => Promise<Response>,
  principal: string | null = 'a',
  queryClient = createQueryClient(),
) {
  let hook!: ReturnType<typeof useUserPreferences>
  const wrapper = mount(
    defineComponent({
      setup() {
        const session = useSessionStore()
        session.status = 'ready'
        session.user =
          principal === null ? null : { id: principal, display_name: principal, roles: [] }
        hook = useUserPreferences()
        return () => null
      },
    }),
    {
      global: {
        plugins: [createPinia(), [VueQueryPlugin, { queryClient }]],
        provide: { [API_CLIENT_KEY as symbol]: createApiClient({ fetch }) },
      },
    },
  )
  return { hook, queryClient, wrapper }
}

describe('account preferences query ownership', () => {
  it('does not read or save for anonymous or forced-password users', async () => {
    const calls: Request[] = []
    const { hook } = mountPreferences((request) => {
      calls.push(request)
      return Promise.resolve(json(SAVED))
    }, null)
    await flushPromises()
    expect(await hook.save(COMMAND)).toEqual({ status: 'discarded' })
    expect(await hook.reload()).toBeNull()
    hook.session.mustChangePassword = true
    hook.session.user = { id: 'a', display_name: 'a', roles: [] }
    await flushPromises()
    expect(hook.accessState.value).toBe('passwordChangeRequired')
    expect(calls).toHaveLength(0)
  })

  it('discards late reads and clears the previous account cache on account switching', async () => {
    const first = deferred()
    let calls = 0
    const other = { ...SAVED, locale: 'en', theme: 'light', revision: 8 }
    const { hook, queryClient } = mountPreferences(() =>
      ++calls === 1 ? first.promise : Promise.resolve(json(other)),
    )
    await flushPromises()
    hook.session.user = { id: 'b', display_name: 'b', roles: [] }
    expect(hook.preferences.value).toBeNull()
    await flushPromises()
    first.resolve(json(SAVED))
    await flushPromises()
    expect(hook.preferences.value).toEqual(other)
    expect(queryClient.getQueryData(userPreferencesQueryKey('a'))).toBeUndefined()
    hook.session.forgetSession()
    expect(hook.preferences.value).toBeNull()
    await flushPromises()
    expect(queryClient.getQueryData(userPreferencesQueryKey('b'))).toBeUndefined()
  })

  it('discards a pending save after A to B to A even if transport ignores abort', async () => {
    const pending = deferred()
    const { hook, queryClient } = mountPreferences((request) =>
      request.method === 'PATCH' ? pending.promise : Promise.resolve(json(SAVED)),
    )
    await flushPromises()
    const saving = hook.save(COMMAND)
    await flushPromises()
    hook.session.user = { id: 'b', display_name: 'b', roles: [] }
    hook.session.user = { id: 'a', display_name: 'a', roles: [] }
    pending.resolve(json({ ...SAVED, ...COMMAND, revision: 4 }))
    expect(await saving).toEqual({ status: 'discarded' })
    await flushPromises()
    expect(queryClient.getQueryData(userPreferencesQueryKey('a'))).not.toMatchObject({
      revision: 4,
    })
    expect(hook.isSaving.value).toBe(false)
  })

  it('adopts only a confirmed canonical save and prevents an earlier read overwriting it', async () => {
    const lateRead = deferred()
    let reads = 0
    const canonical = { ...SAVED, locale: 'en', theme: 'light', revision: 4 }
    const { hook, queryClient } = mountPreferences((request) => {
      if (request.method === 'PATCH') return Promise.resolve(json(canonical))
      return ++reads === 1 ? Promise.resolve(json(SAVED)) : lateRead.promise
    })
    await flushPromises()
    const reloading = hook.reload()
    await flushPromises()
    const result = await hook.save(COMMAND)
    lateRead.resolve(json({ ...SAVED, revision: 2 }))
    await reloading
    await flushPromises()
    expect(result).toEqual({ status: 'success', preferences: canonical })
    expect(queryClient.getQueryData(userPreferencesQueryKey('a'))).toEqual(canonical)
  })

  it.each([409, 500])(
    'keeps the saved cache after a %s response without replaying',
    async (status) => {
      let writes = 0
      const { hook, queryClient } = mountPreferences((request) => {
        if (request.method === 'GET') return Promise.resolve(json(SAVED))
        writes += 1
        return Promise.resolve(
          json(
            {
              error: {
                code: status === 409 ? 'preferences_revision_conflict' : 'internal_error',
                message: 'Failed.',
              },
            },
            status,
          ),
        )
      })
      await flushPromises()
      expect((await hook.save(COMMAND)).status).toBe(status === 409 ? 'conflict' : 'failure')
      expect(queryClient.getQueryData(userPreferencesQueryKey('a'))).toEqual(SAVED)
      expect(writes).toBe(1)
    },
  )

  it('keeps shared reads working when the settings observer unmounts', async () => {
    const pending = deferred()
    let reads = 0
    const fetch = () => {
      reads += 1
      return reads === 2 ? pending.promise : Promise.resolve(json({ ...SAVED, revision: reads }))
    }
    const shell = mountPreferences(fetch)
    await flushPromises()
    const view = mountPreferences(fetch, 'a', shell.queryClient)
    await flushPromises()
    view.wrapper.unmount()
    pending.resolve(json({ ...SAVED, revision: 2 }))
    await flushPromises()
    expect(shell.hook.preferences.value?.revision).toBe(2)
    await shell.queryClient.invalidateQueries({ queryKey: userPreferencesQueryKey('a') })
    await flushPromises()
    expect(shell.hook.preferences.value?.revision).toBe(3)
    shell.wrapper.unmount()
  })

  it('discards a write completion after the view unmounts', async () => {
    const pending = deferred()
    const { hook, wrapper, queryClient } = mountPreferences((request) =>
      request.method === 'PATCH' ? pending.promise : Promise.resolve(json(SAVED)),
    )
    await flushPromises()
    const saving = hook.save(COMMAND)
    await flushPromises()
    wrapper.unmount()
    pending.resolve(json({ ...SAVED, revision: 4 }))
    expect(await saving).toEqual({ status: 'discarded' })
    expect(queryClient.getQueryData(userPreferencesQueryKey('a'))).toEqual(SAVED)
  })

  it('does not open authentication recovery for a cancelled old-account response', async () => {
    const pending = deferred()
    let recoveries = 0
    const client = createApiClient({
      fetch: () => pending.promise,
      onUnauthorized: () => {
        recoveries += 1
        return Promise.resolve()
      },
      shouldRetryAfterUnauthorized,
    })
    const controller = new AbortController()
    const request = client.GET('/api/v1/me/preferences', { signal: controller.signal })
    await flushPromises()
    controller.abort()
    pending.resolve(json({ error: { code: 'authentication_required', message: 'Expired.' } }, 401))
    await request
    expect(recoveries).toBe(0)
  })

  it.each(['GET', 'PATCH'])(
    'does not replay %s preferences after authentication recovery',
    async (method) => {
      let calls = 0
      const client = createApiClient({
        fetch: () => {
          calls += 1
          return Promise.resolve(
            json({ error: { code: 'authentication_required', message: 'Expired.' } }, 401),
          )
        },
        onUnauthorized: () => Promise.resolve(),
        shouldRetryAfterUnauthorized,
      })
      if (method === 'GET') await client.GET('/api/v1/me/preferences')
      else await client.PATCH('/api/v1/me/preferences', { body: COMMAND })
      expect(calls).toBe(1)
    },
  )
})
