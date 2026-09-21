import { readFileSync } from 'node:fs'
import { join } from 'node:path'

import { afterEach, describe, expect, it, vi } from 'vitest'

// public/theme-init.js runs before first paint, so it is exercised the way the browser runs it: as a
// classic script evaluated against the current window.
const SCRIPT = readFileSync(join(import.meta.dirname, '../../public/theme-init.js'), 'utf-8')

function stubSystemPreference(prefersDark: boolean): void {
  vi.stubGlobal(
    'matchMedia',
    vi.fn(() => ({ matches: prefersDark })),
  )
}

function runThemeInit(): string | undefined {
  new Function(SCRIPT)()
  return document.documentElement.dataset.theme
}

afterEach(() => {
  vi.unstubAllGlobals()
  window.localStorage.clear()
  delete document.documentElement.dataset.theme
})

describe('theme-init.js', () => {
  it.each([
    [true, 'dark'],
    [false, 'light'],
  ])('follows the system preference (dark: %s) when nothing is stored', (prefersDark, expected) => {
    stubSystemPreference(prefersDark)

    expect(runThemeInit()).toBe(expected)
  })

  it.each([
    ['dark', false, 'dark'],
    ['light', true, 'light'],
    ['system', true, 'dark'],
    ['nonsense', false, 'light'],
  ])('resolves the stored preference %s', (stored, prefersDark, expected) => {
    stubSystemPreference(prefersDark)
    window.localStorage.setItem('gendertagger.theme', stored)

    expect(runThemeInit()).toBe(expected)
  })

  it('falls back to the system preference when storage is blocked', () => {
    stubSystemPreference(true)
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new DOMException('Storage is disabled.', 'SecurityError')
    })

    expect(runThemeInit()).toBe('dark')
    vi.restoreAllMocks()
  })
})
