import { onMounted, onUnmounted, ref, type Ref } from 'vue'

// Keep in step with public/theme-init.js, which resolves the same storage key before first paint
// so the page never flashes the wrong palette; this composable takes over for a live switch
// afterwards (decision D8: system, light, dark, persisted per user).
const THEME_STORAGE_KEY = 'gendertagger.theme'

export type ThemePreference = 'system' | 'light' | 'dark'

export interface UseTheme {
  preference: Ref<ThemePreference>
  setPreference: (value: ThemePreference) => void
}

function readStoredPreference(): ThemePreference {
  try {
    const stored = localStorage.getItem(THEME_STORAGE_KEY)
    return stored === 'light' || stored === 'dark' ? stored : 'system'
  } catch {
    return 'system'
  }
}

function applyTheme(preference: ThemePreference, prefersDark: boolean): void {
  const isDark = preference === 'dark' || (preference === 'system' && prefersDark)
  document.documentElement.dataset.theme = isDark ? 'dark' : 'light'
}

// Preference itself is shared app-wide state; only one component (the header's switcher) is
// expected to call this composable today, so the media-query listener below is set up once in
// practice even though it is not de-duplicated across calls.
const preference = ref<ThemePreference>(readStoredPreference())

export function useTheme(): UseTheme {
  const media = window.matchMedia('(prefers-color-scheme: dark)')

  function sync(): void {
    applyTheme(preference.value, media.matches)
  }

  function handleSystemChange(): void {
    if (preference.value === 'system') sync()
  }

  onMounted(() => {
    sync()
    media.addEventListener('change', handleSystemChange)
  })
  onUnmounted(() => {
    media.removeEventListener('change', handleSystemChange)
  })

  function setPreference(value: ThemePreference): void {
    preference.value = value
    try {
      localStorage.setItem(THEME_STORAGE_KEY, value)
    } catch {
      // Storage can be blocked; the choice still applies for the rest of this page's life.
    }
    sync()
  }

  return { preference, setPreference }
}
