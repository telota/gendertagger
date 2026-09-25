import { computed, onMounted, onUnmounted, watch } from 'vue'

import { useLocale } from './useLocale'
import { useTheme } from './useTheme'
import { useUserPreferences } from './useUserPreferences'

/** Apply account-owned presentation only after a canonical API read or confirmed save. */
export function usePreferencePresentation() {
  const preferences = useUserPreferences()
  const locale = useLocale()
  const theme = useTheme()

  const saved = preferences.preferences

  function sync(): void {
    if (preferences.principalId.value !== null) {
      // Anonymous choices and a preceding account never stand in for unavailable account values.
      locale.applyLocale(saved.value?.locale ?? null)
      theme.applyPreference(saved.value?.theme ?? 'system')
    } else if (preferences.accessState.value === 'signedOut') {
      locale.restoreAnonymousLocale()
      theme.restoreAnonymousPreference()
    }
    // Before session resolution, keep the anonymous bootstrap presentation. There is no private
    // startup cache, identity marker, or automatic migration of the legacy browser choices.
  }

  watch([preferences.principalId, preferences.accessState, saved], sync, {
    immediate: true,
    flush: 'sync',
  })

  function handleBrowserLanguageChange(): void {
    if (preferences.principalId.value === null) locale.restoreAnonymousLocale()
    else locale.applyLocale(saved.value?.locale ?? null)
  }

  onMounted(() => window.addEventListener('languagechange', handleBrowserLanguageChange))
  onUnmounted(() => window.removeEventListener('languagechange', handleBrowserLanguageChange))

  const desktopSidebarCollapsed = computed(() => saved.value?.desktop_sidebar_collapsed ?? false)
  return { desktopSidebarCollapsed }
}
