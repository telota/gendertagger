// The local account provider (ADR-0031) sets a readable `csrf_token` cookie at login and validates it
// against the `X-CSRF-Token` header on every unsafe request. Both names must match
// `gendertagger.api.authentication`; they live here so a provider change stays a one-file edit.
export const CSRF_HEADER_NAME = 'X-CSRF-Token'
export const CSRF_COOKIE_NAME = 'csrf_token'

const SAFE_METHODS = new Set(['GET', 'HEAD', 'OPTIONS', 'TRACE'])

/** Whether the HTTP method changes server state and therefore needs CSRF protection. */
export function isUnsafeMethod(method: string): boolean {
  return !SAFE_METHODS.has(method.toUpperCase())
}

/** Read the CSRF token from a `document.cookie`-style string, or `null` when absent. */
export function readCsrfToken(cookieHeader: string): string | null {
  for (const pair of cookieHeader.split(';')) {
    const separator = pair.indexOf('=')
    if (separator === -1) continue
    if (pair.slice(0, separator).trim() !== CSRF_COOKIE_NAME) continue
    const value = pair.slice(separator + 1).trim()
    return value === '' ? null : decodeURIComponent(value)
  }
  return null
}
