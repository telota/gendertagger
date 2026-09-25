import { describe, expect, it } from 'vitest'

import {
  applyDocumentLanguage,
  createAppI18n,
  DEFAULT_LOCALE,
  isAppLocale,
  resolveInitialLocale,
} from '@/app/i18n'
import de from '@/locales/de.json'
import en from '@/locales/en.json'

describe('resolveInitialLocale', () => {
  it('prefers an explicit stored choice over the browser languages', () => {
    expect(resolveInitialLocale({ stored: 'en', languages: ['de-DE'] })).toBe('en')
  })

  it('ignores a stored value that is not a supported locale', () => {
    expect(resolveInitialLocale({ stored: 'fr', languages: ['en-GB'] })).toBe('en')
  })

  it('uses the first browser language whose primary subtag is supported', () => {
    expect(resolveInitialLocale({ stored: null, languages: ['fr-FR', 'EN-us', 'de'] })).toBe('en')
  })

  it('falls back to the default locale', () => {
    expect(resolveInitialLocale({ stored: null, languages: ['fr', 'nl'] })).toBe(DEFAULT_LOCALE)
    expect(resolveInitialLocale({ stored: null, languages: [] })).toBe(DEFAULT_LOCALE)
  })
})

describe('isAppLocale', () => {
  it('accepts exactly the supported locales', () => {
    expect(isAppLocale('de')).toBe(true)
    expect(isAppLocale('en')).toBe(true)
    expect(isAppLocale('fr')).toBe(false)
    expect(isAppLocale(null)).toBe(false)
  })
})

describe('createAppI18n', () => {
  it.each([
    ['de', de],
    ['en', en],
  ] as const)('translates the interface chrome in %s', (locale, catalogue) => {
    const i18n = createAppI18n(locale)

    expect(i18n.global.t('app.title')).toBe(catalogue.app.title)
  })

  it('formats numbers and dates for the active locale', () => {
    const german = createAppI18n('de').global
    const english = createAppI18n('en').global

    expect(german.n(1234.5, 'decimal')).toBe('1.234,5')
    expect(english.n(1234.5, 'decimal')).toBe('1,234.5')
    expect(german.d(new Date(Date.UTC(2026, 8, 21, 12)), 'date')).toBe('21.09.2026')
    expect(english.d(new Date(Date.UTC(2026, 8, 21, 12)), 'date')).toBe('Sep 21, 2026')
  })

  it('keeps the two catalogues in step', () => {
    expect(Object.keys(de.app)).toEqual(Object.keys(en.app))
  })
})

describe('applyDocumentLanguage', () => {
  it('sets the language of the document element', () => {
    const root = document.createElement('html')

    applyDocumentLanguage('en', root)

    expect(root.lang).toBe('en')
  })
})
