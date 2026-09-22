import { createApiClient, type ApiClient } from '@/api'

const NO_BODY_STATUSES = new Set([204, 205, 304])

function jsonResponse(body: unknown, init: ResponseInit = {}): Response {
  // The Fetch spec forbids a body on these statuses; the Response constructor throws otherwise,
  // even for a body as small as the string "null".
  if (init.status !== undefined && NO_BODY_STATUSES.has(init.status)) {
    return new Response(null, init)
  }
  return new Response(JSON.stringify(body), {
    headers: { 'content-type': 'application/json' },
    ...init,
  })
}

function authenticationRequired(): Response {
  return jsonResponse(
    { error: { code: 'authentication_required', message: 'Authentication is required.' } },
    { status: 401 },
  )
}

export interface RouteResponse {
  body: unknown
  init?: ResponseInit
}

/** Resolve one canned response per path; an unmocked path is `404`. */
function routeResponse(routes: Record<string, RouteResponse>, pathname: string): Response {
  const route = routes[pathname]
  if (!route) {
    return jsonResponse(
      { error: { code: 'resource_not_found', message: `${pathname} is not mocked.` } },
      { status: 404 },
    )
  }
  return jsonResponse(route.body, route.init)
}

/**
 * A client that answers `GET /api/v1/branding` with the given body/status and, since every mounted
 * screen also has the app-shell session store call `GET /api/v1/me`, answers every other request with
 * "not signed in" — the realistic default for a test that isn't exercising the session itself.
 *
 * Tests that do exercise the session use {@link apiClientWithRoutes} for per-path control instead.
 */
export function apiClientWithJsonResponse(body: unknown, init: ResponseInit = {}): ApiClient {
  return createApiClient({
    fetch: (request) => {
      const { pathname } = new URL(request.url)
      return Promise.resolve(
        pathname === '/api/v1/branding' ? jsonResponse(body, init) : authenticationRequired(),
      )
    },
  })
}

/** A client with a distinct canned response per path; an unmocked path is `404`. */
export function apiClientWithRoutes(routes: Record<string, RouteResponse>): ApiClient {
  return createApiClient({
    fetch: (request) => Promise.resolve(routeResponse(routes, new URL(request.url).pathname)),
  })
}

/**
 * Like {@link apiClientWithRoutes}, but `unreachablePath` rejects instead, as a down server would —
 * for a test that needs one specific request to fail while the rest of the page loads normally.
 */
export function apiClientWithRoutesAndOneUnreachablePath(
  routes: Record<string, RouteResponse>,
  unreachablePath: string,
): ApiClient {
  return createApiClient({
    fetch: (request) => {
      const { pathname } = new URL(request.url)
      if (pathname === unreachablePath) return Promise.reject(new TypeError('fetch failed'))
      return Promise.resolve(routeResponse(routes, pathname))
    },
  })
}

/** A client whose every request rejects, as an unreachable server would. */
export function apiClientWithNetworkError(): ApiClient {
  return createApiClient({ fetch: () => Promise.reject(new TypeError('fetch failed')) })
}
