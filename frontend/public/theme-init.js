// Resolve the colour theme before first paint so the page never flashes the wrong palette.
//
// Loaded synchronously from <head>. It is a separate same-origin file rather than an inline script so a
// strict Content-Security-Policy stays possible. The stored value is a three-state preference
// (system, light, dark); "system" follows prefers-color-scheme.
;(() => {
  const STORAGE_KEY = 'gendertagger.theme'
  let stored = null
  try {
    stored = window.localStorage.getItem(STORAGE_KEY)
  } catch {
    // Storage can be blocked; fall back to the system preference.
  }
  const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches
  const isDark = stored === 'dark' || (stored !== 'light' && prefersDark)
  document.documentElement.dataset.theme = isDark ? 'dark' : 'light'
})()
