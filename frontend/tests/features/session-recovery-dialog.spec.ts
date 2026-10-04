import { DOMWrapper, flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { afterEach, describe, expect, it } from 'vitest'

import { createAppI18n } from '@/app/i18n'
import { API_CLIENT_KEY } from '@/composables/useApiClient'
import { requestReauthentication, useSessionRecovery } from '@/composables/useSessionRecovery'
import SessionRecoveryDialog from '@/features/auth/SessionRecoveryDialog.vue'
import de from '@/locales/de.json'
import { useSessionStore } from '@/stores/session'

import { apiClientWithRoutes, type RouteResponse } from '../helpers/api'
import { waitFor } from '../helpers/wait'

let mounted: VueWrapper | undefined

function mountDialog(routes: Record<string, RouteResponse> = {}) {
  mounted = mount(SessionRecoveryDialog, {
    attachTo: document.body,
    global: {
      plugins: [createPinia(), createAppI18n('de')],
      provide: { [API_CLIENT_KEY as symbol]: apiClientWithRoutes(routes) },
    },
  })
  return mounted
}

// Headless UI's Dialog teleports its content to a portal root appended straight to `document.body`,
// a sibling of the mounted wrapper's own element rather than a descendant of it — `wrapper.find()`
// only searches the wrapper's own subtree and never sees it, so every lookup here goes through the
// document instead.
function bodyGet(selector: string): DOMWrapper<Element> {
  const element = document.body.querySelector(selector)
  if (!element) throw new Error(`Unable to find ${selector} in document.body.`)
  return new DOMWrapper(element)
}

function bodyExists(selector: string): boolean {
  return document.body.querySelector(selector) !== null
}

async function opened(): Promise<void> {
  await waitFor(() => {
    if (!bodyExists('#session-recovery-username')) throw new Error('The prompt has not opened yet.')
  })
}

afterEach(() => {
  // Settle any prompt a test left open so it cannot leak into the next test, and fully unmount —
  // Headless UI's Dialog tracks open/close state (and a body scroll lock) beyond this component's
  // own template, so leaving a previous instance mounted confuses the next test's fresh one.
  useSessionRecovery().reject(new Error('test cleanup'))
  mounted?.unmount()
  mounted = undefined
  document.body.replaceChildren()
})

describe('SessionRecoveryDialog', () => {
  it('renders nothing until a recovery is requested', () => {
    mountDialog()

    expect(bodyExists('#session-recovery-username')).toBe(false)
  })

  it('shows the sign-in prompt once a recovery is requested', async () => {
    mountDialog()

    // Chained immediately, not just before settling it below: otherwise there is a real window
    // where Node considers the eventual rejection unhandled.
    const settled = requestReauthentication().catch(() => undefined)
    await opened()

    expect(document.body.textContent).toContain(de.sessionRecovery.title)

    useSessionRecovery().reject(new Error('cleanup'))
    await settled
  })

  it('resolves the pending recovery and closes once sign-in succeeds', async () => {
    const USER = {
      id: 'a0000000-0000-0000-0000-000000000001',
      display_name: 'Reviewer One',
      roles: [],
    }
    mountDialog({
      '/api/v1/auth/login': { body: USER },
      '/api/v1/auth/session': { body: { must_change_password: false, keep_signed_in: false } },
    })
    const pending = requestReauthentication()
    await opened()

    await bodyGet('#session-recovery-username').setValue('reviewer.one')
    await bodyGet('#session-recovery-password').setValue('a-correct-passphrase')
    await bodyGet('form').trigger('submit')
    await flushPromises()

    await expect(pending).resolves.toBeUndefined()
    expect(bodyExists('#session-recovery-username')).toBe(false)
  })

  it('keeps the username but clears the submitted password before the next same-account prompt', async () => {
    const user = {
      id: 'a0000000-0000-0000-0000-000000000001',
      display_name: 'Reviewer One',
      roles: [],
    }
    mountDialog({
      '/api/v1/auth/login': { body: user },
      '/api/v1/auth/session': { body: { must_change_password: false, keep_signed_in: false } },
    })
    const session = useSessionStore()
    session.user = user
    session.status = 'ready'
    const revision = session.principalRevision
    const recovering = requestReauthentication()
    await opened()
    await bodyGet('#session-recovery-username').setValue('reviewer.one')
    await bodyGet('#session-recovery-password').setValue('a-correct-passphrase')
    await bodyGet('form').trigger('submit')
    await recovering
    await flushPromises()
    expect(session.principalRevision).toBe(revision)
    expect(bodyExists('#session-recovery-password')).toBe(false)

    const nextRecovery = requestReauthentication().catch(() => undefined)
    await opened()
    expect((bodyGet('#session-recovery-password').element as HTMLInputElement).value).toBe('')
    expect((bodyGet('#session-recovery-username').element as HTMLInputElement).value).toBe(
      'reviewer.one',
    )
    useSessionRecovery().reject(new Error('cleanup'))
    await nextRecovery
  })

  it('clears a dismissed password and error while preserving the username for the next prompt', async () => {
    mountDialog({
      '/api/v1/auth/login': {
        body: { error: { code: 'invalid_credentials', message: 'Wrong.' } },
        init: { status: 401 },
      },
    })
    const firstRecovery = requestReauthentication().catch(() => undefined)
    await opened()
    await bodyGet('#session-recovery-username').setValue('reviewer.one')
    await bodyGet('#session-recovery-password').setValue('wrong')
    await bodyGet('form').trigger('submit')
    await flushPromises()
    expect(bodyExists('.session-recovery-error')).toBe(true)
    await bodyGet('.session-recovery-cancel').trigger('click')
    await firstRecovery

    const nextRecovery = requestReauthentication().catch(() => undefined)
    await opened()
    expect((bodyGet('#session-recovery-password').element as HTMLInputElement).value).toBe('')
    expect((bodyGet('#session-recovery-username').element as HTMLInputElement).value).toBe(
      'reviewer.one',
    )
    expect(bodyExists('.session-recovery-error')).toBe(false)
    useSessionRecovery().reject(new Error('cleanup'))
    await nextRecovery
  })

  it('clears a mounted recovery password and feedback when the account changes', async () => {
    mountDialog({
      '/api/v1/auth/login': {
        body: { error: { code: 'invalid_credentials', message: 'Wrong.' } },
        init: { status: 401 },
      },
    })
    const session = useSessionStore()
    session.user = { id: 'account-a', display_name: 'Reviewer A', roles: [] }
    session.status = 'ready'
    const recovering = requestReauthentication().catch(() => undefined)
    await opened()
    await bodyGet('#session-recovery-username').setValue('reviewer.one')
    await bodyGet('#session-recovery-password').setValue('wrong')
    await bodyGet('form').trigger('submit')
    await flushPromises()
    expect(bodyExists('.session-recovery-error')).toBe(true)

    session.user = { id: 'account-b', display_name: 'Reviewer B', roles: [] }
    await flushPromises()
    expect((bodyGet('#session-recovery-password').element as HTMLInputElement).value).toBe('')
    expect(bodyExists('.session-recovery-error')).toBe(false)
    expect((bodyGet('#session-recovery-username').element as HTMLInputElement).value).toBe(
      'reviewer.one',
    )
    useSessionRecovery().reject(new Error('cleanup'))
    await recovering
  })

  it('shows an inline error and keeps the prompt open on invalid credentials', async () => {
    mountDialog({
      '/api/v1/auth/login': {
        body: { error: { code: 'invalid_credentials', message: 'Wrong.' } },
        init: { status: 401 },
      },
    })
    // Chained immediately, not just before settling it below: otherwise there is a real window
    // where Node considers the eventual rejection unhandled.
    const settled = requestReauthentication().catch(() => undefined)
    await opened()

    await bodyGet('#session-recovery-username').setValue('reviewer.one')
    await bodyGet('#session-recovery-password').setValue('wrong')
    await bodyGet('form').trigger('submit')
    await flushPromises()

    expect(document.body.textContent).toContain(de.login.errors.invalidCredentials)
    expect(bodyExists('#session-recovery-username')).toBe(true)

    useSessionRecovery().reject(new Error('cleanup'))
    await settled
  })

  it('rejects the pending recovery and closes when the user cancels', async () => {
    mountDialog()
    // Chained in the same tick the promise is created, not after `trigger('click')` resolves it:
    // otherwise there is a real window where Node considers the rejection unhandled.
    const failure = requestReauthentication().catch((error: unknown) => error)
    await opened()

    await bodyGet('.session-recovery-cancel').trigger('click')
    await flushPromises()

    expect(await failure).toBeInstanceOf(Error)
    expect(bodyExists('#session-recovery-username')).toBe(false)
  })
})
