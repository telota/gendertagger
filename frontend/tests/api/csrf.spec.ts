import { describe, expect, it } from 'vitest'

import { isUnsafeMethod, readCsrfToken } from '@/api/csrf'

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
    expect(readCsrfToken('theme=dark; csrf_token=abc123; locale=de')).toBe('abc123')
  })

  it('decodes a percent-encoded token', () => {
    expect(readCsrfToken('csrf_token=a%2Fb')).toBe('a/b')
  })

  it.each([
    ['no cookies at all', ''],
    ['other cookies only', 'theme=dark'],
    ['an empty value', 'csrf_token='],
    ['a malformed pair', 'no-equals-sign'],
    ['a cookie whose name merely ends with the token name', 'xcsrf_token=abc'],
  ])('returns null for %s', (_description, cookies) => {
    expect(readCsrfToken(cookies)).toBeNull()
  })
})
