import createClient, { type Client, type Middleware } from 'openapi-fetch'

import { CSRF_HEADER_NAME, isUnsafeMethod, readCsrfToken } from './csrf'
import { networkError, parseApiError } from './errors'
import type { paths } from './schema'

export type ApiClient = Client<paths>

export interface ApiClientOptions {
  /** Custom `fetch`, used by tests to keep the network at the transport boundary. */
  fetch?: (request: Request) => Promise<Response>
  /** Source of the CSRF token; defaults to the provider's `csrf_token` cookie. */
  csrfToken?: () => string | null
  /**
   * Called for every `401` response (decision D1: a `401` always means the session is gone, since it
   * can end through a logout elsewhere or an administrative reset, not only local inactivity).
   * Resolving means the caller recovered the session (e.g. an inline sign-in prompt succeeded) and the
   * original request should be retried once, with a fresh CSRF token; rejecting means it should
   * propagate as an ordinary `ApiError`, exactly as before this option existed.
   */
  onUnauthorized?: (request: Request) => Promise<void>
}

function defaultCsrfToken(): string | null {
  return readCsrfToken(document.cookie)
}

/** Attach the CSRF header to a request's unsafe method, if a token is available. */
function applyCsrfHeader(request: Request, csrfToken: () => string | null): void {
  if (!isUnsafeMethod(request.method)) return
  const token = csrfToken()
  if (token !== null) request.headers.set(CSRF_HEADER_NAME, token)
}

/**
 * Create the one typed HTTP client of the application.
 *
 * Requests carry the session cookie (`credentials: 'include'`) and, for every unsafe method, the CSRF
 * header. No call site opts out of either.
 */
export function createApiClient(options: ApiClientOptions = {}): ApiClient {
  const csrfToken = options.csrfToken ?? defaultCsrfToken
  const doFetch = options.fetch ?? ((request: Request) => window.fetch(request))
  const client = createClient<paths>({
    // Every path in the generated schema already starts with `/api/v1`, and the deployment is
    // same-origin, so the base is the page's own origin, spelled out because a `Request` needs an
    // absolute URL outside a browser.
    baseUrl: window.location.origin,
    credentials: 'include',
    fetch: doFetch,
  })

  const attachCsrfToken: Middleware = {
    onRequest({ request }) {
      applyCsrfHeader(request, csrfToken)
      return request
    },
  }
  client.use(attachCsrfToken)

  if (options.onUnauthorized) {
    const onUnauthorized = options.onUnauthorized
    // A request's body can only be read once, and by the time `onResponse` fires it already has been
    // (by the network call itself); a clone taken up front, before that happens, is what a retry needs.
    // `Request.clone()` is cheap even for a large upload, since a `File`/`Blob`-backed body isn't
    // duplicated in memory, only re-referenced.
    const clones = new Map<string, Request>()
    const recoverFromExpiredSession: Middleware = {
      onRequest({ request, id }) {
        clones.set(id, request.clone())
        return request
      },
      async onResponse({ request, response, id }) {
        const retryRequest = clones.get(id)
        clones.delete(id)
        if (response.status !== 401 || !retryRequest) return undefined
        try {
          await onUnauthorized(request)
        } catch {
          return undefined
        }
        // The session that produced the original CSRF token is gone; the recovered one issues a new
        // one, so the retry needs its own header, not the stale value the clone still carries.
        applyCsrfHeader(retryRequest, csrfToken)
        return doFetch(retryRequest)
      },
    }
    client.use(recoverFromExpiredSession)
  }

  return client
}

type Settled<T> =
  | { data: T; error?: never; response: Response }
  | { data?: never; error: unknown; response: Response }

/**
 * Resolve a typed client call to its data, or throw a classified `ApiError`.
 *
 * A rejected `fetch` becomes `network_error`; a non-success response is parsed centrally from the
 * shared error envelope. An aborted request rethrows untouched so a superseded query stays silent.
 */
export async function unwrap<T>(pending: PromiseLike<Settled<T>>): Promise<T> {
  let settled: Settled<T>
  try {
    settled = await pending
  } catch (cause) {
    if (cause instanceof DOMException && cause.name === 'AbortError') throw cause
    throw networkError(cause)
  }
  if (settled.error !== undefined) {
    throw parseApiError(settled.response.status, settled.error, settled.response.headers)
  }
  // openapi-fetch reports either `data` or `error`. A 204 carries neither, and `T` is then the
  // operation's no-content type, which the compiler cannot see through the optional union member.
  return settled.data as T
}
