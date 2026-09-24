import { describe, expect, it, vi } from 'vitest'

import { ApiError, CLIENT_ERROR_CODES, CSRF_HEADER_NAME, createApiClient, unwrap } from '@/api'

const USER_ID = '6f9619ff-8b86-4011-b42d-00c04fc964ff'
const TEAM_ID = 'e248da36-6ff9-4ea3-a486-cc2ce8ddf32a'

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

    await client.POST('/api/v1/projects', {
      body: { display_name: 'Register', slug: 'register', team_id: TEAM_ID },
    })

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

    await client.POST('/api/v1/projects', {
      body: { display_name: 'Register', slug: 'register', team_id: TEAM_ID },
    })

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

    await client.POST('/api/v1/projects', {
      body: { display_name: 'Register', slug: 'register', team_id: TEAM_ID },
    })

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

describe('createApiClient onUnauthorized', () => {
  function setupWithRecovery(
    respond: (request: Request, callNumber: number) => Response | Promise<Response>,
    onUnauthorized: (request: Request) => Promise<void>,
  ) {
    const requests: Request[] = []
    let callNumber = 0
    let token = 'token-before'
    const fetch = vi.fn((request: Request) => {
      callNumber += 1
      requests.push(request.clone())
      return Promise.resolve(respond(request, callNumber))
    })
    const client = createApiClient({ fetch, onUnauthorized, csrfToken: () => token })
    return { client, requests, rotateCsrfToken: (value: string) => (token = value) }
  }

  it('does not call onUnauthorized for a successful response', async () => {
    const onUnauthorized = vi.fn(() => Promise.resolve())
    const { client } = setupWithRecovery(() => jsonResponse({}), onUnauthorized)

    await client.GET('/api/v1/me')

    expect(onUnauthorized).not.toHaveBeenCalled()
  })

  it('retries the request once the caller recovers the session, with a fresh CSRF token', async () => {
    const onUnauthorized = vi.fn(() => Promise.resolve())
    const { client, requests, rotateCsrfToken } = setupWithRecovery((_request, callNumber) => {
      if (callNumber === 1) {
        rotateCsrfToken('token-after')
        return jsonResponse(
          { error: { code: 'authentication_required', message: 'Session gone.' } },
          { status: 401 },
        )
      }
      return jsonResponse({ ok: true }, { status: 201 })
    }, onUnauthorized)

    const result = await client.POST('/api/v1/me/password', {
      body: { current_password: 'old', new_password: 'new-password-1' },
    })

    expect(onUnauthorized).toHaveBeenCalledTimes(1)
    expect(requests).toHaveLength(2)
    expect(requests[0]?.headers.get(CSRF_HEADER_NAME)).toBe('token-before')
    expect(requests[1]?.headers.get(CSRF_HEADER_NAME)).toBe('token-after')
    expect(result.data).toEqual({ ok: true })
  })

  it('recovers but never replays an administrative write without deliberate resubmission', async () => {
    const onUnauthorized = vi.fn(() => Promise.resolve())
    const requests: Request[] = []
    const client = createApiClient({
      fetch: (request) => {
        requests.push(request.clone())
        return Promise.resolve(
          jsonResponse(
            { error: { code: 'authentication_required', message: 'Session gone.' } },
            { status: 401 },
          ),
        )
      },
      onUnauthorized,
      shouldRetryAfterUnauthorized: () => false,
    })

    const failure = await unwrap(
      client.POST('/api/v1/admin/users', {
        body: { username: 'new.admin', display_name: 'New admin', roles: [] },
      }),
    ).catch((error: unknown) => error)

    expect(onUnauthorized).toHaveBeenCalledTimes(1)
    expect(requests).toHaveLength(1)
    expect(failure).toMatchObject({ status: 401, code: 'authentication_required' })
  })

  it('propagates the 401 when the caller declines recovery', async () => {
    const onUnauthorized = vi.fn(() => Promise.reject(new Error('declined')))
    const { client, requests } = setupWithRecovery(
      () =>
        jsonResponse(
          { error: { code: 'authentication_required', message: 'Session gone.' } },
          { status: 401 },
        ),
      onUnauthorized,
    )

    const failure = await unwrap(client.GET('/api/v1/me')).catch((error: unknown) => error)

    expect(onUnauthorized).toHaveBeenCalledTimes(1)
    expect(requests).toHaveLength(1)
    expect(failure).toMatchObject({ status: 401, code: 'authentication_required' })
  })

  it('never sends the request body of a large retry candidate twice over the network', async () => {
    // Regression guard for the clone-up-front design: the original request's body must still be
    // readable by the real fetch even though a clone of it was already taken for a possible retry.
    const onUnauthorized = vi.fn(() => Promise.reject(new Error('declined')))
    const requests: Request[] = []
    const fetch = vi.fn((request: Request) => {
      requests.push(request)
      return request
        .text()
        .then(() =>
          jsonResponse(
            { error: { code: 'authentication_required', message: 'Session gone.' } },
            { status: 401 },
          ),
        )
    })
    const client = createApiClient({ fetch, onUnauthorized, csrfToken: () => 'token' })

    await unwrap(
      client.POST('/api/v1/me/password', {
        body: { current_password: 'old', new_password: 'new-password-1' },
      }),
    ).catch((error: unknown) => error)

    expect(onUnauthorized).toHaveBeenCalledTimes(1)
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
