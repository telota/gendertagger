import { mount } from '@vue/test-utils'
import { defineComponent } from 'vue'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const STORAGE_KEY = 'gendertagger.theme'

/** A `matchMedia` stand-in whose `matches` and listeners a test can drive directly. */
function stubMatchMedia(initialMatches: boolean) {
  let matches = initialMatches
  const listeners = new Set<() => void>()
  const mediaQueryList = {
    get matches() {
      return matches
    },
    addEventListener: (_type: string, handler: () => void) => listeners.add(handler),
    removeEventListener: (_type: string, handler: () => void) => listeners.delete(handler),
  }
  vi.stubGlobal(
    'matchMedia',
    vi.fn(() => mediaQueryList),
  )
  return {
    setMatches: (value: boolean) => {
      matches = value
      for (const listener of listeners) listener()
    },
    listenerCount: () => listeners.size,
  }
}

// Every mount creates its own application-owned effective presentation state.
async function mountTheme() {
  const { useTheme } = await import('@/composables/useTheme')
  let hook!: ReturnType<typeof useTheme>
  let second!: ReturnType<typeof useTheme>
  const wrapper = mount(
    defineComponent({
      setup() {
        hook = useTheme()
        second = useTheme()
        return () => null
      },
    }),
  )
  return { wrapper, hook: () => hook, second: () => second }
}

function currentTheme(): string | undefined {
  return document.documentElement.dataset.theme
}

beforeEach(() => {
  vi.resetModules()
})

afterEach(() => {
  vi.unstubAllGlobals()
  localStorage.clear()
  delete document.documentElement.dataset.theme
})

describe('useTheme', () => {
  it('defaults to following the system preference when nothing is stored', async () => {
    stubMatchMedia(true)

    const { hook } = await mountTheme()

    expect(hook().preference.value).toBe('system')
    expect(currentTheme()).toBe('dark')
  })

  it.each([
    ['light', false],
    ['dark', true],
  ] as const)(
    'reads a stored %s preference regardless of the system setting',
    async (stored, opposite) => {
      localStorage.setItem(STORAGE_KEY, stored)
      stubMatchMedia(opposite)

      const { hook } = await mountTheme()

      expect(hook().preference.value).toBe(stored)
      expect(currentTheme()).toBe(stored)
    },
  )

  it('ignores an unrecognised stored value and falls back to system', async () => {
    localStorage.setItem(STORAGE_KEY, 'purple')
    stubMatchMedia(false)

    const { hook } = await mountTheme()

    expect(hook().preference.value).toBe('system')
  })

  it('still starts when storage is blocked', async () => {
    stubMatchMedia(false)
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new DOMException('Storage is disabled.', 'SecurityError')
    })

    const { hook } = await mountTheme()

    expect(hook().preference.value).toBe('system')
    vi.restoreAllMocks()
  })

  it('setPreference applies the theme immediately and persists the choice', async () => {
    stubMatchMedia(false)
    const { hook } = await mountTheme()

    hook().setPreference('dark')

    expect(hook().preference.value).toBe('dark')
    expect(currentTheme()).toBe('dark')
    expect(localStorage.getItem(STORAGE_KEY)).toBe('dark')
  })

  it('applies saved account values without replacing anonymous persistence', async () => {
    localStorage.setItem(STORAGE_KEY, 'dark')
    stubMatchMedia(false)
    const { hook } = await mountTheme()

    hook().applyPreference('light')

    expect(currentTheme()).toBe('light')
    expect(localStorage.getItem(STORAGE_KEY)).toBe('dark')
    hook().restoreAnonymousPreference()
    expect(currentTheme()).toBe('dark')
  })

  it('restores the anonymous choice in memory when storage is blocked', async () => {
    stubMatchMedia(false)
    const { hook } = await mountTheme()
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new DOMException('Storage is disabled.', 'SecurityError')
    })
    hook().setPreference('dark')
    hook().applyPreference('light')
    hook().restoreAnonymousPreference()
    expect(currentTheme()).toBe('dark')
    vi.restoreAllMocks()
  })

  it('shares one media listener and effective value across callers in the same application', async () => {
    const media = stubMatchMedia(false)
    const { wrapper, hook, second } = await mountTheme()

    hook().applyPreference('dark')
    expect(second().preference.value).toBe('dark')
    expect(media.listenerCount()).toBe(1)
    wrapper.unmount()
    expect(media.listenerCount()).toBe(0)
  })

  it('setPreference still applies the theme when storage is blocked', async () => {
    stubMatchMedia(false)
    const { hook } = await mountTheme()
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new DOMException('Storage is disabled.', 'SecurityError')
    })

    hook().setPreference('dark')

    expect(currentTheme()).toBe('dark')
    vi.restoreAllMocks()
  })

  it('follows a live system change while the preference is "system"', async () => {
    const media = stubMatchMedia(false)
    const { hook } = await mountTheme()
    expect(currentTheme()).toBe('light')

    media.setMatches(true)

    expect(hook().preference.value).toBe('system')
    expect(currentTheme()).toBe('dark')
  })

  it('ignores a live system change once an explicit preference is set', async () => {
    const media = stubMatchMedia(false)
    const { hook } = await mountTheme()
    hook().setPreference('light')

    media.setMatches(true)

    expect(currentTheme()).toBe('light')
  })

  it('stops listening for system changes once the component unmounts', async () => {
    const media = stubMatchMedia(false)
    const { wrapper } = await mountTheme()
    expect(media.listenerCount()).toBe(1)

    wrapper.unmount()

    expect(media.listenerCount()).toBe(0)
  })
})
