import { describe, expect, it } from 'vitest'

import { ApiError, parseApiError } from '@/api/errors'

describe('parseApiError envelope boundary', () => {
  it('accepts the shared envelope', () => {
    const error = parseApiError(
      403,
      { error: { code: 'forbidden', message: 'No.' } },
      new Headers({ 'x-request-id': 'header' }),
    )

    expect(error).toBeInstanceOf(ApiError)
    expect(error).toMatchObject({
      status: 403,
      code: 'forbidden',
      message: 'No.',
      details: {},
      requestId: 'header',
    })
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
    const error = parseApiError(502, body, new Headers({ 'x-request-id': 'header' }))

    expect(error).toBeInstanceOf(ApiError)
    expect(error).toMatchObject({
      status: 502,
      code: 'unparseable_response',
      message: 'The server answered 502 without a recognisable error envelope.',
      details: {},
      requestId: 'header',
    })
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
