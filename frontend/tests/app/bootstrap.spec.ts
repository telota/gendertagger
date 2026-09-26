import { flushPromises } from '@vue/test-utils'
import { createMemoryHistory } from 'vue-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { createApplication } from '@/app/bootstrap'
import { LOCALE_STORAGE_KEY } from '@/app/i18n'
import en from '@/locales/en.json'

function environment(overrides: { storage?: Storage; languages?: readonly string[] } = {}) {
  return {
    storage: window.localStorage,
    languages: ['de-DE'],
    root: document.documentElement,
    history: createMemoryHistory(),
    ...overrides,
  }
}

beforeEach(() => {
  // createApplication wires the real global-fetch client; every test here mounts the app without
  // asserting on branding content, so the network is stubbed to fail fast rather than reach out.
  vi.stubGlobal('fetch', () => Promise.reject(new TypeError('fetch failed')))
})

afterEach(() => {
  vi.unstubAllGlobals()
  window.localStorage.clear()
  document.documentElement.lang = ''
  document.body.replaceChildren()
})

describe('createApplication', () => {
  it('starts in the browser language and sets the document language', () => {
    createApplication(environment({ languages: ['en-GB'] }))

    expect(document.documentElement.lang).toBe('en')
  })

  it('honours a stored locale over the browser language', () => {
    window.localStorage.setItem(LOCALE_STORAGE_KEY, 'de')

    createApplication(environment({ languages: ['en-GB'] }))

    expect(document.documentElement.lang).toBe('de')
  })

  it('still starts when storage is blocked', () => {
    const blocked = {
      getItem() {
        throw new DOMException('Storage is disabled.', 'SecurityError')
      },
    } as unknown as Storage

    createApplication(environment({ storage: blocked, languages: ['en'] }))

    expect(document.documentElement.lang).toBe('en')
  })

  it('mounts the application into the page with its router and footer', async () => {
    const container = document.createElement('div')
    document.body.append(container)

    const application = createApplication(environment({ languages: ['en'] }))
    application.mount(container)
    await application.config.globalProperties.$router.isReady()
    await flushPromises()

    expect(container.querySelector('h1')?.textContent).toBe(en.home.guest.lede)
    expect(container.querySelector('footer')).not.toBeNull()
  })

  it('defaults to browser history when none is given', () => {
    const { storage, languages, root } = environment()

    expect(() => createApplication({ storage, languages, root })).not.toThrow()
  })
})
