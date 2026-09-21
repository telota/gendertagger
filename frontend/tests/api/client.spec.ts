import { describe, expect, it, vi } from 'vitest'

import { ApiError, CLIENT_ERROR_CODES, CSRF_HEADER_NAME, createApiClient, unwrap } from '@/api'

const USER_ID = '6f9619ff-8b86-4011-b42d-00c04fc964ff'

function jsonResponse(body: unknown, init: ResponseInit = {}): Response {
  return new Response(JSON.stringify(body), {
    headers: { 'content-type': 'application/json' },
    ...init,
  })
}

function setup(respond: (request: Request) => Response | Promise<Response>, token = 'token-1') {
  const requests: Request[] = []
  const fetch = vi.fn((request: Request) => {
    requests.push(request)
    return Promise.resolve(respond(request))
  })
  const client = createApiClient({ fetch, csrfToken: () => token })
  return { client, requests }
}

describe('createApiClient', () => {
  it('sends the session cookie on every request', async () => {
    const { client, requests } = setup(() =>
      jsonResponse({ id: USER_ID, display_name: 'Reviewer', roles: ['reviewer'] }),
    )

    await client.GET('/api/v1/me')

    expect(requests[0]?.credentials).toBe('include')
    expect(new URL(requests[0]?.url ?? '').pathname).toBe('/api/v1/me')
  })

  it('does not attach the CSRF token to safe methods', async () => {
    const { client, requests } = setup(() => jsonResponse([]))

    await client.GET('/api/v1/methods')

    expect(requests[0]?.headers.has(CSRF_HEADER_NAME)).toBe(false)
  })

  it('attaches the CSRF token to every unsafe method', async () => {
    const { client, requests } = setup(() => jsonResponse({}, { status: 201 }))

    await client.POST('/api/v1/projects', { body: { display_name: 'Register', slug: 'register' } })

    expect(requests[0]?.headers.get(CSRF_HEADER_NAME)).toBe('token-1')
  })

  it('sends an unsafe request without a header when no token is available', async () => {
    const requests: Request[] = []
    const client = createApiClient({
      fetch: (request) => {
        requests.push(request)
        return Promise.resolve(jsonResponse({}, { status: 201 }))
      },
      csrfToken: () => null,
    })

    await client.POST('/api/v1/projects', { body: { display_name: 'Register', slug: 'register' } })

    expect(requests[0]?.headers.has(CSRF_HEADER_NAME)).toBe(false)
  })

  it('reads the CSRF token from the cookie by default', async () => {
    // The literal backend cookie name (ADR-0031), not the constant, so a client-side rename fails here.
    document.cookie = 'csrf_token=from-cookie'
    const requests: Request[] = []
    const client = createApiClient({
      fetch: (request) => {
        requests.push(request)
        return Promise.resolve(jsonResponse({}, { status: 201 }))
      },
    })

    await client.POST('/api/v1/projects', { body: { display_name: 'Register', slug: 'register' } })

    expect(requests[0]?.headers.get(CSRF_HEADER_NAME)).toBe('from-cookie')
  })

  it('uses the global fetch when none is injected', async () => {
    const requests: Request[] = []
    vi.stubGlobal('fetch', (request: Request) => {
      requests.push(request)
      return Promise.resolve(jsonResponse([]))
    })
    try {
      await createApiClient({ csrfToken: () => null }).GET('/api/v1/methods')
    } finally {
      vi.unstubAllGlobals()
    }

    expect(new URL(requests[0]?.url ?? '').pathname).toBe('/api/v1/methods')
  })
})

describe('unwrap', () => {
  it('returns the data of a successful call', async () => {
    const { client } = setup(() =>
      jsonResponse({ id: USER_ID, display_name: 'Reviewer', roles: ['reviewer'] }),
    )

    const user = await unwrap(client.GET('/api/v1/me'))

    expect(user.display_name).toBe('Reviewer')
  })

  it('classifies a failure by the stable code of the shared envelope', async () => {
    const { client } = setup(() =>
      jsonResponse(
        {
          error: {
            code: 'annotation_conflict',
            message: 'The review revision is stale.',
            details: { current_revision: 4 },
            request_id: 'req-1',
          },
        },
        { status: 409 },
      ),
    )

    const failure = await unwrap(client.GET('/api/v1/me')).catch((error: unknown) => error)

    expect(failure).toBeInstanceOf(ApiError)
    expect(failure).toMatchObject({
      status: 409,
      code: 'annotation_conflict',
      details: { current_revision: 4 },
      requestId: 'req-1',
    })
  })

  it('falls back to the response header for the request id', async () => {
    const { client } = setup(() =>
      jsonResponse(
        { error: { code: 'forbidden', message: 'CSRF validation failed.' } },
        { status: 403, headers: { 'x-request-id': 'req-from-header' } },
      ),
    )

    const failure = await unwrap(client.GET('/api/v1/me')).catch((error: unknown) => error)

    expect(failure).toMatchObject({ code: 'forbidden', details: {}, requestId: 'req-from-header' })
  })

  it('keeps the status of a body that is not an error envelope', async () => {
    const { client } = setup(() => new Response('<h1>Bad gateway</h1>', { status: 502 }))

    const failure = await unwrap(client.GET('/api/v1/me')).catch((error: unknown) => error)

    expect(failure).toMatchObject({
      status: 502,
      code: CLIENT_ERROR_CODES.unparseableResponse,
    })
  })

  it('reports an unreachable server as a network error', async () => {
    const client = createApiClient({ fetch: () => Promise.reject(new TypeError('fetch failed')) })

    const failure = await unwrap(client.GET('/api/v1/me')).catch((error: unknown) => error)

    expect(failure).toMatchObject({
      status: null,
      code: CLIENT_ERROR_CODES.networkError,
      cause: expect.any(TypeError),
    })
  })

  it('rethrows an aborted request untouched', async () => {
    const abort = new DOMException('The operation was aborted.', 'AbortError')
    const client = createApiClient({ fetch: () => Promise.reject(abort) })

    const failure = await unwrap(client.GET('/api/v1/me')).catch((error: unknown) => error)

    expect(failure).toBe(abort)
  })
})
