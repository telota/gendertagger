import { describe, expect, it } from 'vitest'

import { ApiError, isApiErrorEnvelope, parseApiError } from '@/api/errors'

describe('isApiErrorEnvelope', () => {
  it('accepts the shared envelope', () => {
    expect(isApiErrorEnvelope({ error: { code: 'forbidden', message: 'No.' } })).toBe(true)
  })

  it.each([
    ['null', null],
    ['a string', 'Bad gateway'],
    ['an array', []],
    ['an object without error', { detail: 'x' }],
    ['a non-object error', { error: 'x' }],
    ['a missing code', { error: { message: 'No.' } }],
    ['a non-string message', { error: { code: 'forbidden', message: 7 } }],
  ])('rejects %s', (_description, body) => {
    expect(isApiErrorEnvelope(body)).toBe(false)
  })
})

describe('ApiError', () => {
  it('defaults its optional fields', () => {
    const error = new ApiError({ status: 500, code: 'internal_error', message: 'Failed.' })

    expect(error).toMatchObject({ details: {}, requestId: null, name: 'ApiError' })
    expect(error.cause).toBeUndefined()
  })
})

describe('parseApiError', () => {
  it('prefers the request id of the envelope over the header', () => {
    const headers = new Headers({ 'x-request-id': 'header' })
    const error = parseApiError(
      500,
      { error: { code: 'internal_error', message: 'Failed.', request_id: 'body' } },
      headers,
    )

    expect(error.requestId).toBe('body')
  })
})
