import { afterEach, describe, expect, it } from 'vitest'

import { createApplication } from '@/app/bootstrap'
import { LOCALE_STORAGE_KEY } from '@/app/i18n'
import en from '@/locales/en.json'

function environment(overrides: { storage?: Storage; languages?: readonly string[] } = {}) {
  return {
    storage: window.localStorage,
    languages: ['de-DE'],
    root: document.documentElement,
    ...overrides,
  }
}

afterEach(() => {
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

  it('mounts the application into the page', () => {
    const container = document.createElement('div')
    document.body.append(container)

    createApplication(environment({ languages: ['en'] })).mount(container)

    expect(container.querySelector('h1')?.textContent).toBe(en.app.title)
  })
})
