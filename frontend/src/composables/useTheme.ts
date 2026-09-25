import { getCurrentInstance, onMounted, onUnmounted, ref, type App, type Ref } from 'vue'

// This legacy key belongs exclusively to anonymous browser presentation. Account preferences
// are never written here, and the prepaint script uses it only until authentication resolves.
const THEME_STORAGE_KEY = 'gendertagger.theme'

export type ThemePreference = 'system' | 'light' | 'dark'

export interface UseTheme {
  preference: Ref<ThemePreference>
  /** Change and persist only the anonymous browser choice. */
  setPreference: (value: ThemePreference) => void
  /** Apply a confirmed account choice without writing anonymous browser storage. */
  applyPreference: (value: ThemePreference) => void
  restoreAnonymousPreference: () => void
}

interface ThemeState {
  preference: Ref<ThemePreference>
  anonymousPreference: ThemePreference
  media: MediaQueryList
  subscribers: number
  sync: () => void
}

// Effective presentation is shared within one Vue application, without module-time browser reads
// or a second copy of the server resource. Separate app instances cannot inherit each other's theme.
const states = new WeakMap<App, ThemeState>()

function readAnonymousPreference(): ThemePreference {
  try {
    const stored = localStorage.getItem(THEME_STORAGE_KEY)
    return stored === 'light' || stored === 'dark' ? stored : 'system'
  } catch {
    return 'system'
  }
}

function createThemeState(): ThemeState {
  const anonymousPreference = readAnonymousPreference()
  const preference = ref<ThemePreference>(anonymousPreference)
  const media = window.matchMedia('(prefers-color-scheme: dark)')
  function sync(): void {
    const isDark = preference.value === 'dark' || (preference.value === 'system' && media.matches)
    document.documentElement.dataset.theme = isDark ? 'dark' : 'light'
  }
  return { preference, anonymousPreference, media, subscribers: 0, sync }
}

export function useTheme(): UseTheme {
  const instance = getCurrentInstance()
  if (!instance) throw new Error('useTheme requires a component setup scope.')
  const app = instance.appContext.app
  let existing = states.get(app)
  if (!existing) {
    existing = createThemeState()
    states.set(app, existing)
  }
  const state = existing

  onMounted(() => {
    state.sync()
    if (state.subscribers === 0) state.media.addEventListener('change', state.sync)
    state.subscribers += 1
  })
  onUnmounted(() => {
    state.subscribers -= 1
    if (state.subscribers === 0) state.media.removeEventListener('change', state.sync)
  })

  function applyPreference(value: ThemePreference): void {
    state.preference.value = value
    state.sync()
  }

  function setPreference(value: ThemePreference): void {
    state.anonymousPreference = value
    applyPreference(value)
    try {
      localStorage.setItem(THEME_STORAGE_KEY, value)
    } catch {
      // Retain the anonymous choice in memory even when browser storage is blocked.
    }
  }

  function restoreAnonymousPreference(): void {
    applyPreference(state.anonymousPreference)
  }

  return {
    preference: state.preference,
    setPreference,
    applyPreference,
    restoreAnonymousPreference,
  }
}
