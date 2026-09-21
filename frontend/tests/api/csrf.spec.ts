import { describe, expect, it } from 'vitest'

import { CSRF_COOKIE_NAME, isUnsafeMethod, readCsrfToken } from '@/api/csrf'

describe('isUnsafeMethod', () => {
  it.each(['GET', 'HEAD', 'OPTIONS', 'TRACE', 'get'])('treats %s as safe', (method) => {
    expect(isUnsafeMethod(method)).toBe(false)
  })

  it.each(['POST', 'PUT', 'PATCH', 'DELETE', 'post'])('treats %s as unsafe', (method) => {
    expect(isUnsafeMethod(method)).toBe(true)
  })
})

describe('readCsrfToken', () => {
  it('finds the token among other cookies', () => {
    expect(readCsrfToken(`theme=dark; ${CSRF_COOKIE_NAME}=abc123; locale=de`)).toBe('abc123')
  })

  it('decodes a percent-encoded token', () => {
    expect(readCsrfToken(`${CSRF_COOKIE_NAME}=a%2Fb`)).toBe('a/b')
  })

  it.each([
    ['no cookies at all', ''],
    ['other cookies only', 'theme=dark'],
    ['an empty value', `${CSRF_COOKIE_NAME}=`],
    ['a malformed pair', 'no-equals-sign'],
    ['a cookie whose name merely ends with the token name', `x${CSRF_COOKIE_NAME}=abc`],
  ])('returns null for %s', (_description, cookies) => {
    expect(readCsrfToken(cookies)).toBeNull()
  })
})
