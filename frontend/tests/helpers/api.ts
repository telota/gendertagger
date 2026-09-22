import { createApiClient, type ApiClient } from '@/api'

/** A client whose every request resolves with the given JSON body and status. */
export function apiClientWithJsonResponse(body: unknown, init: ResponseInit = {}): ApiClient {
  return createApiClient({
    fetch: () =>
      Promise.resolve(
        new Response(JSON.stringify(body), {
          headers: { 'content-type': 'application/json' },
          ...init,
        }),
      ),
  })
}

/** A client whose every request rejects, as an unreachable server would. */
export function apiClientWithNetworkError(): ApiClient {
  return createApiClient({ fetch: () => Promise.reject(new TypeError('fetch failed')) })
}
