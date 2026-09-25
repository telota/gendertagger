import { mount } from '@vue/test-utils'
import { defineComponent } from 'vue'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { createAppI18n, DEFAULT_LOCALE, LOCALE_STORAGE_KEY, type AppLocale } from '@/app/i18n'
import { useLocale, type UseLocale } from '@/composables/useLocale'

function mountLocale(initial: AppLocale = 'de') {
  const i18n = createAppI18n(initial)
  let hook!: UseLocale
  const wrapper = mount(
    defineComponent({
      setup() {
        hook = useLocale()
        return () => null
      },
    }),
    { global: { plugins: [i18n] } },
  )
  return { wrapper, hook: () => hook, i18n }
}

afterEach(() => {
  localStorage.clear()
  document.documentElement.lang = ''
})

describe('useLocale', () => {
  it('reports the active locale and both supported options', () => {
    const { hook } = mountLocale('de')

    expect(hook().current.value).toBe('de')
    expect(hook().options).toEqual([
      { value: 'de', label: 'Deutsch' },
      { value: 'en', label: 'English' },
    ])
  })

  it('switches the active locale, persists the choice, and updates <html lang>', () => {
    const { hook } = mountLocale('de')

    hook().setLocale('en')

    expect(hook().current.value).toBe('en')
    expect(localStorage.getItem(LOCALE_STORAGE_KEY)).toBe('en')
    expect(document.documentElement.lang).toBe('en')
  })

  it('applies account language without replacing the anonymous choice', () => {
    localStorage.setItem(LOCALE_STORAGE_KEY, 'de')
    const { hook } = mountLocale('de')

    hook().applyLocale('en')

    expect(hook().current.value).toBe('en')
    expect(document.documentElement.lang).toBe('en')
    expect(localStorage.getItem(LOCALE_STORAGE_KEY)).toBe('de')
    hook().restoreAnonymousLocale()
    expect(hook().current.value).toBe('de')
  })

  it('resolves browser default using the first supported primary language, then German', () => {
    const { hook } = mountLocale()
    vi.spyOn(navigator, 'languages', 'get').mockReturnValue(['fr', 'en-GB', 'de'])
    hook().applyLocale(null)
    expect(hook().current.value).toBe('en')

    vi.spyOn(navigator, 'languages', 'get').mockReturnValue(['fr', 'es'])
    hook().applyLocale(null)
    expect(hook().current.value).toBe('de')
    vi.restoreAllMocks()
  })

  it('restores the anonymous choice in memory when storage is blocked', () => {
    const { hook } = mountLocale('de')
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new DOMException('Storage is disabled.', 'SecurityError')
    })
    hook().setLocale('en')
    hook().applyLocale('de')
    hook().restoreAnonymousLocale()
    expect(hook().current.value).toBe('en')
    vi.restoreAllMocks()
  })

  it('still switches the locale when storage is blocked', () => {
    const { hook } = mountLocale('de')
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new DOMException('Storage is disabled.', 'SecurityError')
    })

    hook().setLocale('en')

    expect(hook().current.value).toBe('en')
    expect(document.documentElement.lang).toBe('en')
    vi.restoreAllMocks()
  })

  it('falls back to the default locale if the underlying i18n locale is ever unrecognised', () => {
    const { hook, i18n } = mountLocale('de')

    // Only `setLocale`/bootstrap ever assign this in practice; simulate an unexpected value
    // (deliberately bypassing the type) to exercise the defensive fallback.
    i18n.global.locale.value = 'fr' as AppLocale

    expect(hook().current.value).toBe(DEFAULT_LOCALE)
  })
})
